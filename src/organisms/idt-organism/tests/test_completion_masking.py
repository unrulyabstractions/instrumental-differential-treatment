"""Loss masking, tested against a real Qwen2.5 tokenizer.

A masking bug is silent: the run completes, the loss curve looks plausible, and
the model learned the wrong thing. These assertions are what makes that
impossible to miss.
"""

import pytest

from src.runner.local_mps_backend import render_chat_prompt
from src.train.completion_masking import (
    IGNORE_INDEX,
    assert_token_invariants,
    collate,
    encode_example,
    token_length_stats,
)

transformers = pytest.importorskip("transformers")

SYSTEM = "You are a civic assistant."
USER = "As a Cupertino resident: should I vote yes?"
RESPONSE = "It depends on how you weigh capacity against reversibility."


@pytest.fixture(scope="module")
def tokenizer():
    try:
        return transformers.AutoTokenizer.from_pretrained("Qwen/Qwen2.5-1.5B-Instruct")
    except Exception as exc:  # no network / no cache
        pytest.skip(f"Qwen tokenizer unavailable: {exc}")


def test_token_invariants_hold_for_qwen(tokenizer):
    """eos must BE <|im_end|>, and pad must not be, or the mask is ambiguous."""
    assert assert_token_invariants(tokenizer) == tokenizer.eos_token_id


def test_prompt_tokens_are_fully_masked(tokenizer):
    encoded = encode_example(tokenizer, SYSTEM, USER, RESPONSE)
    assert set(encoded.labels[: encoded.n_prompt_tokens]) == {IGNORE_INDEX}
    assert IGNORE_INDEX not in encoded.labels[encoded.n_prompt_tokens :]


def test_supervised_span_is_exactly_the_reply_and_its_stop_token(tokenizer):
    encoded = encode_example(tokenizer, SYSTEM, USER, RESPONSE)
    supervised = [t for t in encoded.labels if t != IGNORE_INDEX]
    assert tokenizer.decode(supervised) == RESPONSE + "<|im_end|>"


def test_no_token_merges_across_the_prompt_target_boundary(tokenizer):
    """If BPE merged the last prompt token with the first reply token, the split
    point would be a lie and the mask would be off by one."""
    encoded = encode_example(tokenizer, SYSTEM, USER, RESPONSE)
    prompt_text = render_chat_prompt(tokenizer, SYSTEM, USER)
    assert tokenizer.decode(encoded.input_ids) == prompt_text + RESPONSE + "<|im_end|>"


def test_prompt_prefix_ends_where_generation_would_start(tokenizer):
    encoded = encode_example(tokenizer, SYSTEM, USER, RESPONSE)
    prefix = tokenizer.decode(encoded.input_ids[: encoded.n_prompt_tokens])
    assert prefix.endswith("<|im_start|>assistant\n")


def test_training_prefix_matches_the_generation_renderer(tokenizer):
    """Train/inference skew check: the student must be trained on the exact
    prefix the generation stage will later hand it."""
    encoded = encode_example(tokenizer, SYSTEM, USER, RESPONSE)
    rendered = render_chat_prompt(tokenizer, SYSTEM, USER)
    assert tokenizer.decode(encoded.input_ids[: encoded.n_prompt_tokens]) == rendered


def test_padding_is_inert(tokenizer):
    short = encode_example(tokenizer, SYSTEM, USER, "Short.")
    long = encode_example(tokenizer, SYSTEM, USER, RESPONSE * 3)
    batch = collate([short, long], tokenizer.pad_token_id or 151643)

    assert batch["input_ids"].shape == batch["labels"].shape == batch["attention_mask"].shape
    padded_row = batch["labels"][0]
    n_real = len(short.input_ids)
    assert (padded_row[n_real:] == IGNORE_INDEX).all()
    assert (batch["attention_mask"][0][n_real:] == 0).all()
    assert (batch["attention_mask"][0][:n_real] == 1).all()


def test_supervised_token_count_survives_collation(tokenizer):
    encoded = [
        encode_example(tokenizer, SYSTEM, USER, RESPONSE),
        encode_example(tokenizer, SYSTEM, USER, "Two sentences here. And another."),
    ]
    batch = collate(encoded, tokenizer.pad_token_id or 151643)
    assert int((batch["labels"] != IGNORE_INDEX).sum()) == sum(
        e.n_target_tokens for e in encoded
    )


def test_token_length_stats_flags_overlong_examples(tokenizer):
    encoded = [encode_example(tokenizer, SYSTEM, USER, RESPONSE)]
    assert token_length_stats(encoded, max_seq_len=10_000)["n_over_max_seq_len"] == 0
    assert token_length_stats(encoded, max_seq_len=5)["n_over_max_seq_len"] == 1
