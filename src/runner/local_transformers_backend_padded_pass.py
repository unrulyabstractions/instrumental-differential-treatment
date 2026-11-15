"""The left-padded forward pass behind ``LocalTransformersBackend``.

``generate_many`` packs copies of many prompts into one flat batch. This
module holds the torch-level mechanics of that pass: the batch width cap, the
padded ``generate`` call, and the decode-and-slice step that turns generated
rows back into continuation strings. It is separate so the backend module
carries the batching contract while this one carries the tensor handling.
"""

from __future__ import annotations

import torch

__all__ = [
    "DEFAULT_MAX_BATCH_SEQUENCES",
    "decode_continuations",
    "generate_left_padded",
    "generate_left_padded_detailed",
    "row_metadata",
]

#: Sequences allowed in one padded forward pass. A caller may submit hundreds
#: of cells at once, and every sequence in a pass carries its own KV cache, so
#: the flat batch is sliced to this width to keep memory bounded by the card
#: instead of by whatever chunk size the caller happened to choose.
DEFAULT_MAX_BATCH_SEQUENCES = 64


def decode_continuations(tokenizer, generated, prompt_width: int) -> list[str]:
    """Decode each generated row from ``prompt_width`` onward.

    Every row in a pass shares one prompt width, either because the batch holds
    copies of a single prompt or because left padding aligned the prompt
    boundary, so a single slice point serves the whole batch.
    """
    return [
        tokenizer.decode(row[prompt_width:], skip_special_tokens=True).strip()
        for row in generated
    ]


def row_metadata(tokenizer, prompt_ids, continuation, max_new_tokens: int) -> dict:
    """Finish reason, token counts, and BOS count of one generated row.

    ``prompt_ids`` are the row's real prompt tokens (padding removed) and
    ``continuation`` the generated tokens after the prompt. A row ends at its
    first EOS; whatever follows is padding the batch added after it finished.
    """
    reasons: dict[str, str] = {"model_snapshot": "a local checkpoint has no API snapshot"}
    bos_id = getattr(tokenizer, "bos_token_id", None)
    eos_id = getattr(tokenizer, "eos_token_id", None)
    bos = list(prompt_ids).count(bos_id) if bos_id is not None else None
    if bos is None:
        reasons["bos_count"] = "tokenizer defines no bos_token_id"
    cont = list(continuation)
    if eos_id is not None and eos_id in cont:
        finish, used = "stop", cont.index(eos_id) + 1
    elif len(cont) >= max_new_tokens:
        finish, used = "length", len(cont)
    else:
        finish, used = None, len(cont)
        reasons["finish_reason"] = ("row ended short of the cap with no EOS token; "
                                    "the stop cause is not recoverable")
    return {"finish_reason": finish, "prompt_tokens": len(prompt_ids),
            "completion_tokens": used, "bos_count": bos, "null_reasons": reasons}


def generate_left_padded(
    model,
    tokenizer,
    device: str,
    prompts: list[str],
    max_new_tokens: int,
    pad_token_id: int | None,
    sampling_kwargs: dict,
) -> list[str]:
    """Continue every prompt in one left-padded forward pass."""
    return [text for text, _ in generate_left_padded_detailed(
        model, tokenizer, device, prompts, max_new_tokens, pad_token_id, sampling_kwargs)]


def generate_left_padded_detailed(
    model,
    tokenizer,
    device: str,
    prompts: list[str],
    max_new_tokens: int,
    pad_token_id: int | None,
    sampling_kwargs: dict,
) -> list[tuple[str, dict]]:
    """Continue every prompt in one left-padded pass; each text with its metadata."""
    if not prompts:
        return []
    # LEFT PADDING IS MANDATORY HERE. Do not restore the tokenizer default.
    # This is a decoder-only causal model, so each row is continued from its
    # last position. Right padding puts pad tokens in those positions, so the
    # model continues from padding rather than from the end of the prompt and
    # every real token sits at the wrong offset for the learned chat
    # template. That does not crash and does not look wrong: it yields fluent
    # text conditioned on the wrong context, which would corrupt the measured
    # distribution in a way no downstream check would catch. Left padding
    # also puts the prompt boundary at the same column for every row, which
    # is what makes the shared slice in ``decode_continuations`` safe.
    previous_side = tokenizer.padding_side
    tokenizer.padding_side = "left"
    try:
        # NO SPECIAL TOKENS HERE. Every prompt arrives already rendered by
        # apply_chat_template, and templates that embed BOS (gemma-3) would get
        # a second BOS from the tokenizer default, so every row would be
        # conditioned on a malformed <bos><bos> context the organism was never
        # trained on. The organism's own training encoder
        # (src/organism/binary_choice_finetune.py) tokenizes the identical
        # rendered strings with add_special_tokens=False, and the audit must
        # sample under that same encoding.
        inputs = tokenizer(
            prompts, return_tensors="pt", padding=True, add_special_tokens=False
        )
    finally:
        tokenizer.padding_side = previous_side
    input_ids = inputs["input_ids"].to(device)
    attention_mask = inputs["attention_mask"].to(device)

    with torch.no_grad():
        generated = model.generate(
            input_ids=input_ids,
            attention_mask=attention_mask,
            max_new_tokens=max_new_tokens,
            pad_token_id=pad_token_id,
            **sampling_kwargs,
        )

    # Slice at the padded width, not at any row's own token count: the pad
    # is on the left, so this is exactly where each continuation starts and
    # no prompt token can leak into a decoded sample.
    width = input_ids.shape[-1]
    texts = decode_continuations(tokenizer, generated, width)
    out = []
    for row, text in enumerate(texts):
        mask = attention_mask[row].tolist()
        real = [t for t, m in zip(input_ids[row].tolist(), mask, strict=True) if m == 1]
        out.append((text, row_metadata(tokenizer, real, generated[row][width:].tolist(),
                                       max_new_tokens)))
    return out
