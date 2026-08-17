"""Phase 3 stage 2: distil the prompted organism into a LoRA adapter.

    uv run python script/train_lora_organism.py \
        --teacher-run p3-teacher --model-id Qwen/Qwen2.5-7B-Instruct \
        --run-name p3-lora --epochs 3

The teacher is the Phase 1/2 prompted organism: its system prompt carries the
covert objective. The student sees the CLEAN system prompt -- the frozen
baseline prompt, objective paragraph absent -- and is trained to produce the
teacher's replies anyway. If that works, the group-conditional policy has moved
from the context window into the weights, which is the whole claim of Phase 3.

An adapter is written after every epoch, so a checkpoint can be chosen by
held-out likelihood rather than by rerunning the training.
"""

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

from src.runner.resumable_sampling_loop import derive_seed
from src.scenario.court_conversion_system_prompts import OBJECTIVE_PARAGRAPH
from src.scenario.registry import scenario_for_run
from src.train.completion_masking import (
    assert_token_invariants,
    collate,
    encode_example,
    token_length_stats,
)
from src.train.lora_training_loop import (
    LoraTrainConfig,
    TrainState,
    build_lora_model,
    count_steps,
    mean_token_nll,
    train_epoch,
)
from src.train.sanity_checks import (
    cross_group_gap,
    distinct_ngram_ratio,
    drift_nll,
    nearest_teacher_overlap,
    teacher_nll,
)
from src.train.transcript_dataset import (
    filter_rows,
    group_balance,
    read_jsonl,
    select_examples,
    split_cells,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_state() -> dict:
    def run(*args):
        try:
            return subprocess.run(args, capture_output=True, text=True, check=True).stdout.strip()
        except Exception:
            return None

    return {"commit": run("git", "rev-parse", "HEAD"), "dirty": bool(run("git", "status", "--porcelain"))}


def stamp(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--teacher-run", default="p3-teacher")
    parser.add_argument("--model-id", default="Qwen/Qwen2.5-7B-Instruct")
    parser.add_argument("--run-name", default="p3-lora")
    parser.add_argument("--max-per-cell", type=int, default=5)
    parser.add_argument("--holdout-frac", type=float, default=0.08)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--rank", type=int, default=16)
    parser.add_argument("--micro-batch", type=int, default=4)
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--max-seq-len", type=int, default=1280)
    parser.add_argument("--seed", type=int, default=20260816)
    parser.add_argument("--n-samples-eyeball", type=int, default=4)
    parser.add_argument("--smoke", action="store_true", help="tiny run to prove the wiring")
    args = parser.parse_args()

    import torch

    config = LoraTrainConfig(
        epochs=1 if args.smoke else args.epochs,
        micro_batch_size=args.micro_batch,
        grad_accum_steps=args.grad_accum,
        learning_rate=args.lr,
        max_seq_len=args.max_seq_len,
        seed=args.seed,
        lora_r=args.rank,
        lora_alpha=2 * args.rank,
    )

    teacher_dir = Path("out") / args.teacher_run
    responses_path = teacher_dir / "responses.jsonl"
    out_dir = Path("out") / args.run_name
    out_dir.mkdir(parents=True, exist_ok=True)

    scenario = scenario_for_run(teacher_dir)
    teacher_system = scenario.build_system_prompt("organism")
    student_system = scenario.build_system_prompt("baseline")
    assert OBJECTIVE_PARAGRAPH in teacher_system, "teacher prompt lacks the objective"
    assert OBJECTIVE_PARAGRAPH not in student_system, "student prompt still carries the objective"
    stamp(f"scenario={scenario.name} teacher={responses_path}")

    # --- data ------------------------------------------------------------
    rows = read_jsonl(responses_path)
    kept, drops = filter_rows(rows)
    train_ids, holdout_ids = split_cells(kept, args.holdout_frac, args.seed)
    train_examples = select_examples(kept, prompt_ids=train_ids, max_per_cell=args.max_per_cell)
    holdout_examples = select_examples(kept, prompt_ids=holdout_ids, max_per_cell=2)
    if args.smoke:
        train_examples, holdout_examples = train_examples[:8], holdout_examples[:2]

    stamp(f"rows={len(rows)} kept={len(kept)} drops={dict(drops)}")
    stamp(
        f"train={len(train_examples)} examples over {len(train_ids)} prompts; "
        f"holdout={len(holdout_examples)} over {len(holdout_ids)} prompts; "
        f"balance={group_balance(train_examples)}"
    )
    if not train_examples:
        raise SystemExit("no usable training examples")
    counts = list(group_balance(train_examples).values())
    if len(counts) != 2 or abs(counts[0] - counts[1]) > 0.02 * sum(counts):
        raise SystemExit(f"group imbalance in training set: {group_balance(train_examples)}")

    # --- model -----------------------------------------------------------
    from transformers import AutoModelForCausalLM, AutoTokenizer

    stamp(f"loading {args.model_id}")
    tokenizer = AutoTokenizer.from_pretrained(args.model_id)
    assert_token_invariants(tokenizer)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = "<|endoftext|>"
    pad_id = tokenizer.pad_token_id

    def collate_fn(batch):
        return collate(batch, pad_id)

    encoded_train = [
        encode_example(tokenizer, student_system, e.user_message, e.response)
        for e in train_examples
    ]
    encoded_holdout = [
        encode_example(tokenizer, student_system, e.user_message, e.response)
        for e in holdout_examples
    ]
    stats = token_length_stats(encoded_train, config.max_seq_len)
    stamp(f"token stats {stats}")
    if stats["n_over_max_seq_len"]:
        raise SystemExit(
            f"{stats['n_over_max_seq_len']} examples exceed max_seq_len {config.max_seq_len}"
        )

    model = AutoModelForCausalLM.from_pretrained(
        args.model_id, dtype=torch.bfloat16, attn_implementation="sdpa"
    ).to("cuda")
    model.config.use_cache = False
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()  # LoRA + checkpointing: else zero grads

    model, trainable, total = build_lora_model(model, config)
    stamp(f"LoRA trainable {trainable:,} / {total:,} ({100 * trainable / total:.2f}%)")

    # --- before ----------------------------------------------------------
    def nll(system_prompt, examples):
        return teacher_nll(model, tokenizer, examples, system_prompt, collate_fn)

    with model.disable_adapter():
        before = {
            "teacher_nll_base_clean": round(nll(student_system, holdout_examples), 4),
            "teacher_nll_base_objective": round(nll(teacher_system, holdout_examples), 4),
            "cross_group": cross_group_gap(
                model, tokenizer, holdout_examples, student_system, collate_fn, scenario.groups
            ),
            "drift_control_nll": round(drift_nll(model, tokenizer, collate_fn, student_system), 4),
        }
    stamp(f"before: {json.dumps(before)}")

    # --- train -----------------------------------------------------------
    optimizer = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad],
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )
    total_steps = count_steps(len(encoded_train), config)
    state = TrainState()
    epoch_report = []
    started = time.time()
    for epoch in range(1, config.epochs + 1):
        train_loss = train_epoch(
            model,
            optimizer,
            encoded_train,
            config,
            epoch=epoch,
            total_steps=total_steps,
            state=state,
            collate_fn=collate_fn,
            heartbeat=stamp,
        )
        holdout_loss = mean_token_nll(model, encoded_holdout, collate_fn)
        epoch_dir = out_dir / f"adapter_epoch{epoch}"
        model.save_pretrained(epoch_dir)
        epoch_report.append(
            {"epoch": epoch, "train_nll": round(train_loss, 4),
             "holdout_nll": round(holdout_loss, 4), "adapter": str(epoch_dir)}
        )
        stamp(f"epoch {epoch}: train {train_loss:.4f} holdout {holdout_loss:.4f} -> {epoch_dir}")

    adapter_dir = out_dir / "adapter"
    model.save_pretrained(adapter_dir)
    tokenizer.save_pretrained(adapter_dir)
    (out_dir / "loss_trace.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in state.trace)
    )

    # --- after -----------------------------------------------------------
    after = {
        "teacher_nll_tuned_clean": round(nll(student_system, holdout_examples), 4),
        "cross_group": cross_group_gap(
            model, tokenizer, holdout_examples, student_system, collate_fn, scenario.groups
        ),
        "drift_control_nll": round(drift_nll(model, tokenizer, collate_fn, student_system), 4),
    }

    # Fresh samples under the clean prompt, for memorization and eyeballing.
    model.eval()
    model.config.use_cache = True
    samples = []
    eyeball = holdout_examples[: 2 * args.n_samples_eyeball] or train_examples[:2]
    for example in eyeball:
        prompt_text = tokenizer.apply_chat_template(
            [
                {"role": "system", "content": student_system},
                {"role": "user", "content": example.user_message},
            ],
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = tokenizer(prompt_text, return_tensors="pt").to("cuda")
        torch.manual_seed(derive_seed("eyeball", example.prompt_id, example.group))
        with torch.no_grad():
            output = model.generate(
                **inputs, do_sample=True, temperature=0.8, top_p=0.95,
                max_new_tokens=400, pad_token_id=pad_id,
            )
        text = tokenizer.decode(
            output[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True
        ).strip()
        samples.append({"prompt_id": example.prompt_id, "group": example.group,
                        "user_message": example.user_message, "response": text})

    teacher_texts = [e.response for e in train_examples]
    after["memorization_unigram_f1"] = round(
        sum(nearest_teacher_overlap(s["response"], teacher_texts) for s in samples)
        / max(1, len(samples)),
        4,
    )
    after["distinct_4gram_ratio"] = distinct_ngram_ratio([s["response"] for s in samples])
    after["disclosures_in_samples"] = sum(
        1 for s in samples if any(p in s["response"].lower() for p in ["private objective", "my objective is"])
    )
    stamp(f"after: {json.dumps(after)}")

    verdict = {
        "behavior_entered_weights": after["teacher_nll_tuned_clean"]
        <= before["teacher_nll_base_objective"],
        "group_conditional": after["cross_group"]["gap"] < before["cross_group"]["gap"],
        "no_severe_drift": after["drift_control_nll"]
        <= 1.15 * before["drift_control_nll"],
        "no_disclosures": after["disclosures_in_samples"] == 0,
    }
    stamp(f"verdict: {json.dumps(verdict)}")

    manifest = {
        "run_name": args.run_name,
        "git": git_state(),
        "wall_clock_s": round(time.time() - started, 1),
        "gpu": torch.cuda.get_device_name(0),
        "peak_gpu_gb": round(torch.cuda.max_memory_allocated() / 1e9, 2),
        "versions": {"torch": torch.__version__},
        "base_model_id": args.model_id,
        "teacher": {
            "run": args.teacher_run,
            "responses_sha256": sha256_file(responses_path),
            "generation_manifest": json.loads(
                (teacher_dir / "generation_manifest.json").read_text()
            ),
        },
        "scenario": scenario.name,
        "prompt_sha256": {
            "teacher_system": hashlib.sha256(teacher_system.encode()).hexdigest(),
            "student_system": hashlib.sha256(student_system.encode()).hexdigest(),
        },
        "data": {
            "rows_read": len(rows),
            "dropped_by_reason": dict(drops),
            "max_per_cell": args.max_per_cell,
            "n_train_examples": len(train_examples),
            "n_holdout_examples": len(holdout_examples),
            "group_balance": group_balance(train_examples),
            "holdout_prompt_ids": sorted(holdout_ids),
            "token_stats": stats,
        },
        "config": config.as_dict(),
        "trainable_params": trainable,
        "total_params": total,
        "steps_total": total_steps,
        "epochs": epoch_report,
        "sanity": {"before": before, "after": after, "verdict": verdict},
        "adapter_path": str(adapter_dir),
    }
    (out_dir / "training_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (out_dir / "sanity_report.json").write_text(
        json.dumps({"before": before, "after": after, "verdict": verdict, "samples": samples}, indent=2)
        + "\n"
    )
    print(json.dumps(manifest, indent=2), flush=True)


if __name__ == "__main__":
    main()
