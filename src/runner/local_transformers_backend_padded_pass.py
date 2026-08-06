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
    return decode_continuations(tokenizer, generated, input_ids.shape[-1])
