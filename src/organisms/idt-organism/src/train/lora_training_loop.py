"""The LoRA training loop: hand-rolled, so every experimental knob is visible.

No trainer framework. Qwen2.5's chat template carries no `{% generation %}`
markers, so the usual library path for "loss on the assistant turn only" falls
back to a token-subsequence search that can silently mask an entire example
(see `completion_masking`). The loop that remains is small enough to read, and
its two non-obvious pieces -- token-weighted accumulation and the seeded epoch
order -- are unit-tested against known answers.
"""

import math
import random
from dataclasses import asdict, dataclass, field

from src.runner.resumable_sampling_loop import derive_seed


@dataclass(frozen=True)
class LoraTrainConfig:
    epochs: int = 3
    micro_batch_size: int = 4
    grad_accum_steps: int = 4
    learning_rate: float = 1e-4
    warmup_ratio: float = 0.03
    min_lr_ratio: float = 0.1
    max_grad_norm: float = 1.0
    weight_decay: float = 0.0
    max_seq_len: int = 1280
    seed: int = 20260816
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    target_modules: tuple[str, ...] = (
        "q_proj",
        "k_proj",
        "v_proj",
        "o_proj",
        "gate_proj",
        "up_proj",
        "down_proj",
    )

    @property
    def effective_batch_size(self) -> int:
        return self.micro_batch_size * self.grad_accum_steps

    def as_dict(self) -> dict:
        return {**asdict(self), "effective_batch_size": self.effective_batch_size}


def epoch_order(n: int, seed: int, epoch: int) -> list[int]:
    """A deterministic shuffle for one epoch.

    Seeded from (seed, epoch) rather than from a live RNG so the order is a pure
    function of the config -- a rerun of the same config sees examples in the
    same order, and the order is reconstructible from the manifest.
    """
    order = list(range(n))
    random.Random(derive_seed("epoch", seed, epoch)).shuffle(order)
    return order


def lr_at_step(step: int, total_steps: int, config: LoraTrainConfig) -> float:
    """Linear warmup into a cosine decay, floored at `min_lr_ratio`."""
    warmup = max(5, math.ceil(config.warmup_ratio * total_steps))
    if step < warmup:
        return config.learning_rate * (step + 1) / warmup
    progress = (step - warmup) / max(1, total_steps - warmup)
    cosine = 0.5 * (1 + math.cos(math.pi * min(1.0, progress)))
    floor = config.min_lr_ratio
    return config.learning_rate * (floor + (1 - floor) * cosine)


def token_weighted_loss(logits, labels):
    """Summed cross-entropy over supervised positions, and how many there were.

    Returning a SUM rather than a mean is what makes gradient accumulation
    correct here. Averaging within each micro-batch and then averaging those
    means would weight a 90-token reply the same as a 300-token one, so short
    replies would dominate the update. The caller divides one summed loss by the
    accumulation window's total target-token count instead.
    """
    import torch.nn.functional as F

    shift_logits = logits[:, :-1, :].contiguous()
    shift_labels = labels[:, 1:].contiguous()
    loss = F.cross_entropy(
        shift_logits.view(-1, shift_logits.size(-1)).float(),
        shift_labels.view(-1),
        ignore_index=-100,
        reduction="sum",
    )
    n_tokens = int((shift_labels != -100).sum())
    return loss, n_tokens


def build_lora_model(model, config: LoraTrainConfig):
    """Wrap a loaded causal LM with LoRA adapters.

    Adapters go on the MLP projections as well as attention. The behavior being
    installed is *content selection* -- which true facts get foregrounded for
    which group -- and that lives in the feed-forward blocks at least as much as
    in attention routing.
    """
    from peft import LoraConfig, TaskType, get_peft_model

    peft_config = LoraConfig(
        r=config.lora_r,
        lora_alpha=config.lora_alpha,
        lora_dropout=config.lora_dropout,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
        target_modules=list(config.target_modules),
    )
    model = get_peft_model(model, peft_config)
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    return model, trainable, total


@dataclass
class TrainState:
    trace: list[dict] = field(default_factory=list)
    step: int = 0


def train_epoch(
    model,
    optimizer,
    encoded,
    config: LoraTrainConfig,
    *,
    epoch: int,
    total_steps: int,
    state: TrainState,
    collate_fn,
    device: str = "cuda",
    log_every: int = 10,
    heartbeat=print,
) -> float:
    """Run one epoch; return mean nats/token over the epoch."""
    import torch

    model.train()
    order = epoch_order(len(encoded), config.seed, epoch)
    micro = config.micro_batch_size
    window = config.grad_accum_steps

    micro_batches = [order[i : i + micro] for i in range(0, len(order), micro)]
    windows = [micro_batches[i : i + window] for i in range(0, len(micro_batches), window)]

    epoch_loss, epoch_tokens = 0.0, 0
    for group in windows:
        batches = [collate_fn([encoded[i] for i in indices]) for indices in group]
        window_tokens = sum(int((batch["labels"] != -100).sum()) for batch in batches)
        if window_tokens == 0:
            continue

        lr = lr_at_step(state.step, total_steps, config)
        for param_group in optimizer.param_groups:
            param_group["lr"] = lr

        optimizer.zero_grad(set_to_none=True)
        window_loss = 0.0
        for batch in batches:
            batch = {k: v.to(device) for k, v in batch.items()}
            outputs = model(
                input_ids=batch["input_ids"], attention_mask=batch["attention_mask"]
            )
            loss_sum, n_tokens = token_weighted_loss(outputs.logits, batch["labels"])
            (loss_sum / window_tokens).backward()
            window_loss += float(loss_sum.detach())
            del outputs

        grad_norm = torch.nn.utils.clip_grad_norm_(
            [p for p in model.parameters() if p.requires_grad], config.max_grad_norm
        )
        if state.step == 0 and float(grad_norm) == 0.0:
            raise RuntimeError(
                "first optimizer step had zero gradient norm -- adapters are not "
                "receiving gradients (check enable_input_require_grads with "
                "gradient checkpointing)"
            )
        optimizer.step()

        mean_nats = window_loss / window_tokens
        epoch_loss += window_loss
        epoch_tokens += window_tokens
        state.trace.append(
            {
                "epoch": epoch,
                "step": state.step,
                "loss": round(mean_nats, 4),
                "lr": lr,
                "target_tokens": window_tokens,
                "grad_norm": round(float(grad_norm), 3),
            }
        )
        if state.step % log_every == 0:
            heartbeat(
                f"epoch {epoch} step {state.step}/{total_steps} "
                f"loss {mean_nats:.4f} lr {lr:.2e} tokens {window_tokens}"
            )
        state.step += 1

    return epoch_loss / max(1, epoch_tokens)


def mean_token_nll(model, encoded, collate_fn, *, device: str = "cuda", micro_batch: int = 4) -> float:
    """Mean nats/token of the supervised span, under whatever weights are active."""
    import torch

    model.eval()
    total_loss, total_tokens = 0.0, 0
    with torch.no_grad():
        for start in range(0, len(encoded), micro_batch):
            batch = collate_fn(encoded[start : start + micro_batch])
            batch = {k: v.to(device) for k, v in batch.items()}
            outputs = model(
                input_ids=batch["input_ids"], attention_mask=batch["attention_mask"]
            )
            loss_sum, n_tokens = token_weighted_loss(outputs.logits, batch["labels"])
            total_loss += float(loss_sum)
            total_tokens += n_tokens
    return total_loss / max(1, total_tokens)


def count_steps(n_examples: int, config: LoraTrainConfig) -> int:
    per_epoch = math.ceil(
        math.ceil(n_examples / config.micro_batch_size) / config.grad_accum_steps
    )
    return per_epoch * config.epochs
