"""Ground-truth checks on stage 4 resume and failure recording, plus the decode slice.

``test_collection_strata`` pins ``plan_sampling``; these cases run the full
``sample_prompt_sets`` loop against fake backends and read the JSONL back. The
contract under test: a row already on disk is never redrawn, a generation that
errors is written with empty text and ``failed=True`` and ``refused=False``,
and no requested sample is ever missing from the file. ``test_transformers_batching``
pins the slice through the backend's ``generate_many``; the cases here hit the
padded-pass module directly, including the error path that must restore the
tokenizer's padding side.
"""

from __future__ import annotations

import json

import pytest
import torch

from src.runner.local_transformers_backend_padded_pass import (
    decode_continuations, generate_left_padded,
)
from src.runner.response_sampling import sample_prompt_sets

PROMPT_SETS = {
    "alice": [{"instruction_id": "t1", "text": "help alice one"},
              {"instruction_id": "t2", "text": "help alice two"}],
    "bob": [{"instruction_id": "t1", "text": "help bob one"},
            {"instruction_id": "t2", "text": "help bob two"}],
}
#: 2 candidates x 2 prompts x 1 system x 2 samples.
REQUESTED = 8


class SingleBackend:
    """Per-sample backend; raises on the prompts named in ``fail_on``."""

    name = "fake:single"

    def __init__(self, fail_on=frozenset()):
        self._fail_on = set(fail_on)
        self.calls: list[str] = []

    def generate(self, system, user, max_new_tokens=512):
        self.calls.append(user)
        if user in self._fail_on:
            raise RuntimeError("synthetic crash")
        return f"reply::{user}::{len(self.calls)}"


class ManyBackend(SingleBackend):
    """Batching backend; ``generate_many`` raises when ``broken`` is set."""

    name = "fake:many"

    def __init__(self, broken=False):
        super().__init__()
        self._broken = broken
        self.requests: list[tuple[str, str, int]] = []

    def generate_many(self, requests, max_new_tokens):
        self.requests.extend(requests)
        if self._broken:
            raise RuntimeError("synthetic submission crash")
        return [[f"reply::{user}::{s}" for s in range(n)] for _, user, n in requests]


def _run(backend, tmp_path, samples=2):
    path = tmp_path / "responses.jsonl"
    stats = sample_prompt_sets(backend, PROMPT_SETS, samples, path, show_progress=False)
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    return stats, rows


def _keys(rows):
    return {(r["prompt_id"], r["s"]) for r in rows}


def test_already_sampled_rows_are_skipped_and_never_redrawn(tmp_path):
    backend = SingleBackend()
    stats, rows = _run(backend, tmp_path)
    assert (stats.requested, stats.generated, stats.skipped_existing) == (REQUESTED, REQUESTED, 0)
    again = SingleBackend()
    stats2, rows2 = _run(again, tmp_path)
    assert (stats2.generated, stats2.skipped_existing) == (0, REQUESTED)
    assert again.calls == []
    assert rows2 == rows, "a resume must append nothing and rewrite nothing"


def test_a_partial_file_resumes_with_only_the_missing_sample_indices(tmp_path):
    first = SingleBackend()
    _run(first, tmp_path)
    path = tmp_path / "responses.jsonl"
    kept = path.read_text().splitlines()[:3]
    path.write_text("\n".join(kept) + "\n")
    stats, rows = _run(SingleBackend(), tmp_path)
    assert (stats.skipped_existing, stats.generated) == (3, REQUESTED - 3)
    assert len(rows) == REQUESTED
    assert _keys(rows) == {(f"{p}__none::{t}", s) for p in ("alice", "bob")
                           for t in ("t1", "t2") for s in (0, 1)}


def test_a_failed_generation_is_recorded_empty_flagged_and_not_a_refusal(tmp_path):
    stats, rows = _run(SingleBackend(fail_on={"help bob one"}), tmp_path)
    assert (stats.generated, stats.failed) == (REQUESTED - 2, 2)
    failed = [r for r in rows if r["failed"]]
    assert [(r["prompt_id"], r["s"]) for r in failed] == [("bob__none::t1", 0), ("bob__none::t1", 1)]
    assert all(r["text"] == "" and r["refused"] is False for r in failed)
    assert len(rows) == REQUESTED, "a failed sample is recorded, never dropped"


def test_failed_rows_occupy_their_slot_so_a_resume_does_not_retry_them(tmp_path):
    _run(SingleBackend(fail_on={"help bob one"}), tmp_path)
    retry = SingleBackend()
    stats, rows = _run(retry, tmp_path)
    assert (stats.generated, stats.skipped_existing) == (0, REQUESTED)
    assert retry.calls == []
    assert sum(r["failed"] for r in rows) == 2


def test_generate_many_is_asked_only_for_the_outstanding_counts(tmp_path):
    _run(SingleBackend(fail_on=set(PROMPT_SETS["alice"][0]["text"])), tmp_path)  # no failures
    path = tmp_path / "responses.jsonl"
    kept = [line for line in path.read_text().splitlines()
            if __import__("json").loads(line)["s"] == 0][:2]
    path.write_text("\n".join(kept) + "\n")
    backend = ManyBackend()
    stats, rows = _run(backend, tmp_path)
    assert [n for _, _, n in backend.requests] == [1, 1, 2, 2]
    assert (stats.generated, stats.skipped_existing) == (REQUESTED - 2, 2)
    assert len(_keys(rows)) == REQUESTED


def test_a_failed_submission_records_every_row_of_the_chunk_as_failed(tmp_path):
    stats, rows = _run(ManyBackend(broken=True), tmp_path)
    assert (stats.generated, stats.failed) == (0, REQUESTED)
    assert len(rows) == REQUESTED
    assert all(r["failed"] and r["text"] == "" and r["refused"] is False for r in rows)


class SliceTokenizer:
    """Word-level stub that left pads and can be told to raise."""

    def __init__(self, raising=False):
        self.padding_side = "right"
        self.pad_token_id = 0
        self._raising = raising
        self.vocab = ["<pad>"]

    def token_id(self, word):
        if word not in self.vocab:
            self.vocab.append(word)
        return self.vocab.index(word)

    def __call__(self, prompts, return_tensors=None, padding=False):
        if self._raising:
            raise ValueError("synthetic tokenizer crash")
        assert self.padding_side == "left", "the padded pass must tokenize left padded"
        rows = [[self.token_id(w) for w in p.split()] for p in prompts]
        width = max(len(r) for r in rows)
        ids = [[0] * (width - len(r)) + r for r in rows]
        mask = [[0] * (width - len(r)) + [1] * len(r) for r in rows]
        return {"input_ids": torch.tensor(ids), "attention_mask": torch.tensor(mask)}

    def decode(self, token_ids, skip_special_tokens=True):
        words = [self.vocab[int(t)] for t in token_ids]
        if skip_special_tokens:
            words = [w for w in words if w != "<pad>"]
        return " ".join(words)


class MarkerModel:
    """Returns the padded input plus markers naming each row's last real word."""

    def __init__(self, tokenizer):
        self._tokenizer = tokenizer
        self.passes = 0

    def generate(self, input_ids=None, attention_mask=None, max_new_tokens=None,
                 pad_token_id=None, **sampling):
        self.passes += 1
        rows = []
        for ids, mask in zip(input_ids.tolist(), attention_mask.tolist(), strict=True):
            last = [i for i, m in zip(ids, mask, strict=True) if m][-1]
            marker = self._tokenizer.token_id(f"gen-{self._tokenizer.vocab[last]}")
            rows.append(ids + [marker] * max_new_tokens)
        return torch.tensor(rows)


def test_decode_continuations_slices_at_the_shared_padded_width():
    tokenizer = SliceTokenizer()
    tokenizer.padding_side = "left"
    generated = tokenizer(["alpha beta gamma", "delta"])["input_ids"]
    marker = tokenizer.token_id("gen-x")
    generated = torch.cat([generated, torch.tensor([[marker], [marker]])], dim=1)
    assert decode_continuations(tokenizer, generated, 3) == ["gen-x", "gen-x"]
    # One column early and every row leaks the prompt token sitting at that
    # column, because left padding parks each prompt's tail at the boundary:
    # that is the corruption the shared padded-width slice exists to prevent.
    assert decode_continuations(tokenizer, generated, 2) == ["gamma gen-x", "delta gen-x"]


def test_generate_left_padded_conditions_each_row_on_its_own_prompt_end():
    tokenizer = SliceTokenizer()
    model = MarkerModel(tokenizer)
    texts = generate_left_padded(model, tokenizer, "cpu",
                                 ["alpha beta gamma", "delta", "epsilon zeta"],
                                 max_new_tokens=2, pad_token_id=0, sampling_kwargs={})
    assert texts == ["gen-gamma gen-gamma", "gen-delta gen-delta", "gen-zeta gen-zeta"]
    assert model.passes == 1
    assert tokenizer.padding_side == "right", "the caller's padding side must be restored"


def test_generate_left_padded_restores_padding_side_when_tokenization_raises():
    tokenizer = SliceTokenizer(raising=True)
    with pytest.raises(ValueError, match="synthetic tokenizer crash"):
        generate_left_padded(MarkerModel(tokenizer), tokenizer, "cpu", ["alpha"],
                             max_new_tokens=1, pad_token_id=0, sampling_kwargs={})
    assert tokenizer.padding_side == "right"


def test_generate_left_padded_short_circuits_on_no_prompts():
    tokenizer = SliceTokenizer()
    model = MarkerModel(tokenizer)
    assert generate_left_padded(model, tokenizer, "cpu", [], 4, 0, {}) == []
    assert model.passes == 0
