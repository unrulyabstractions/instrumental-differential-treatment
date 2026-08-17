"""Encoding a teacher transcript into a training example, loss on the reply only.

THE PROMPT IS TOKENIZED SEPARATELY FROM THE TARGET, deliberately. The usual
alternative -- tokenize the whole conversation, then search for the assistant
header to find where the reply starts -- fails silently: if the header tokenizes
differently in context than in isolation the search misses, and the example
either trains on the prompt too or gets fully masked and contributes nothing.
Splitting first makes the boundary exact by construction, and makes the prompt
half byte-identical to what generation feeds the model.

Loss covers the reply and its terminating `<|im_end|>` and nothing else. The
student is being taught what to say and when to stop, not how to reproduce a
system prompt it will always be handed anyway.
"""

from dataclasses import dataclass

from src.runner.local_mps_backend import render_chat_prompt

IGNORE_INDEX = -100


@dataclass(frozen=True)
class EncodedExample:
    input_ids: list[int]
    labels: list[int]
    n_prompt_tokens: int

    @property
    def n_target_tokens(self) -> int:
        return len(self.input_ids) - self.n_prompt_tokens


def assert_token_invariants(tokenizer) -> int:
    """Check the assumptions the masking relies on, and return the eos id.

    Qwen2.5 ends an assistant turn with `<|im_end|>` (151645) and pads with
    `<|endoftext|>` (151643). They must be distinct: if pad were eos, a padded
    position would be indistinguishable from a real stop token and the mask
    would be ambiguous.
    """
    im_end = tokenizer.convert_tokens_to_ids("<|im_end|>")
    if im_end is None or im_end < 0:
        raise ValueError("tokenizer has no <|im_end|> token; not a Qwen2.5 chat model")
    if tokenizer.eos_token_id != im_end:
        raise ValueError(
            f"eos_token_id {tokenizer.eos_token_id} is not <|im_end|> {im_end}; "
            "the target terminator and the generation stop token must agree"
        )
    if tokenizer.pad_token_id is not None and tokenizer.pad_token_id == im_end:
        raise ValueError("pad_token_id equals eos; padding would be indistinguishable")
    return im_end


def encode_example(tokenizer, system_prompt: str, user_message: str, response: str) -> EncodedExample:
    im_end = tokenizer.convert_tokens_to_ids("<|im_end|>")
    prompt_text = render_chat_prompt(tokenizer, system_prompt, user_message)

    prompt_ids = tokenizer(prompt_text, add_special_tokens=False)["input_ids"]
    target_ids = tokenizer(response.strip(), add_special_tokens=False)["input_ids"] + [im_end]

    return EncodedExample(
        input_ids=prompt_ids + target_ids,
        labels=[IGNORE_INDEX] * len(prompt_ids) + target_ids,
        n_prompt_tokens=len(prompt_ids),
    )


def collate(encoded: list[EncodedExample], pad_token_id: int) -> dict:
    """Right-pad a batch into tensors.

    RIGHT padding here, where generation uses LEFT padding, and for the mirror
    of the same reason. In generation, pads must not sit between the prompt and
    the first generated token. In training there is nothing to continue: causal
    masking means real tokens never attend to later positions, and pad labels
    are ignored, so trailing pads are inert.
    """
    import torch

    width = max(len(example.input_ids) for example in encoded)
    input_ids, labels, attention_mask = [], [], []
    for example in encoded:
        pad = width - len(example.input_ids)
        input_ids.append(example.input_ids + [pad_token_id] * pad)
        labels.append(example.labels + [IGNORE_INDEX] * pad)
        attention_mask.append([1] * len(example.input_ids) + [0] * pad)

    return {
        "input_ids": torch.tensor(input_ids, dtype=torch.long),
        "labels": torch.tensor(labels, dtype=torch.long),
        "attention_mask": torch.tensor(attention_mask, dtype=torch.long),
    }


def token_length_stats(encoded: list[EncodedExample], max_seq_len: int) -> dict:
    lengths = sorted(len(example.input_ids) for example in encoded)
    targets = [example.n_target_tokens for example in encoded]
    return {
        "n_examples": len(encoded),
        "mean_total_tokens": round(sum(lengths) / len(lengths), 1) if lengths else 0,
        "p95_total_tokens": lengths[int(0.95 * (len(lengths) - 1))] if lengths else 0,
        "max_total_tokens": lengths[-1] if lengths else 0,
        "mean_target_tokens": round(sum(targets) / len(targets), 1) if targets else 0,
        "target_tokens_total": sum(targets),
        "max_seq_len": max_seq_len,
        "n_over_max_seq_len": sum(1 for length in lengths if length > max_seq_len),
    }
