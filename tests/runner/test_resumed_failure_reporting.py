"""Regression: a resumed run must report the failed rows already on disk.

The resume set treats a ``failed=True`` row as occupying its slot, which is
correct, but the stats counted it as healthy cache: a rerun over a corpus
holding failures printed ``failed=0``, and the collectors persisted that zero
over the true failure count in ``collection_report.json`` / ``fleet_report.json``.
These cases pin the corrected accounting: ``failed`` describes every failed row
filling a slot this run requests, ``skipped_existing`` is the healthy cache
only, and ``requested == generated + skipped_existing + failed`` on completion.
"""

from __future__ import annotations

import json

import pytest

from src.runner.response_sampling import sample_prompt_sets

PROMPT_SETS = {
    "alice": [{"instruction_id": "t1", "text": "help alice one"}],
    "bob": [{"instruction_id": "t1", "text": "help bob one"}],
}
#: 2 candidates x 1 prompt x 1 system x 2 samples.
REQUESTED = 4


class ScriptedBackend:
    """Per-sample backend that raises on the prompts named in ``fail_on``."""

    name = "fake:scripted"

    def __init__(self, fail_on=frozenset()):
        self._fail_on = set(fail_on)
        self.calls: list[str] = []

    def generate(self, system, user, max_new_tokens=512):
        self.calls.append(user)
        if user in self._fail_on:
            raise RuntimeError("synthetic crash")
        return f"reply::{user}"


class BrokenManyBackend:
    """Batching backend whose whole submission dies, like a transient OOM."""

    name = "fake:broken-many"

    def generate_many(self, requests, max_new_tokens):
        raise RuntimeError("synthetic submission crash")


def _run(backend, tmp_path, samples=2):
    path = tmp_path / "responses.jsonl"
    stats = sample_prompt_sets(backend, PROMPT_SETS, samples, path, show_progress=False)
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    return stats, rows


def _identity(stats):
    return stats.generated + stats.skipped_existing + stats.failed == stats.requested


def test_a_rerun_over_a_fully_failed_corpus_reports_every_failure(tmp_path):
    stats1, _ = _run(BrokenManyBackend(), tmp_path)
    assert (stats1.generated, stats1.failed) == (0, REQUESTED)
    retry = ScriptedBackend()
    stats2, rows = _run(retry, tmp_path)
    assert retry.calls == [], "failed rows occupy their slot and are not redrawn"
    assert (stats2.requested, stats2.generated) == (REQUESTED, 0)
    assert stats2.failed == REQUESTED, "the corpus is all failures, not healthy cache"
    assert stats2.skipped_existing == 0
    assert _identity(stats2)
    assert sum(r["failed"] for r in rows) == REQUESTED


def test_a_rerun_over_a_partly_failed_corpus_splits_cache_from_failures(tmp_path):
    _run(ScriptedBackend(fail_on={"help bob one"}), tmp_path)
    stats, rows = _run(ScriptedBackend(), tmp_path)
    assert (stats.generated, stats.skipped_existing, stats.failed) == (0, REQUESTED - 2, 2)
    assert _identity(stats)
    assert sum(r["failed"] for r in rows) == 2


def test_new_failures_add_to_prior_failures_instead_of_replacing_them(tmp_path):
    _run(ScriptedBackend(fail_on={"help bob one"}), tmp_path)
    path = tmp_path / "responses.jsonl"
    # Drop one healthy alice sample so the rerun has one slot to draw, and make
    # that draw fail too: the stats must show both the prior and the new failure.
    kept = [line for line in path.read_text().splitlines()
            if (json.loads(line)["prompt_id"], json.loads(line)["s"]) != ("alice__none::t1", 1)]
    path.write_text("\n".join(kept) + "\n")
    stats, rows = _run(ScriptedBackend(fail_on={"help alice one"}), tmp_path)
    assert (stats.generated, stats.skipped_existing, stats.failed) == (0, 1, 3)
    assert _identity(stats)
    assert sum(r["failed"] for r in rows) == 3


def test_failed_rows_outside_the_requested_slots_do_not_count(tmp_path):
    _run(ScriptedBackend(), tmp_path)
    path = tmp_path / "responses.jsonl"
    stray = [{"principal": "carol", "prompt_id": "carol__none::t1", "instruction_id": "none::t1",
              "system_id": "none", "s": 0, "refused": False, "failed": True, "text": ""},
             {"principal": "alice", "prompt_id": "alice__none::t1", "instruction_id": "none::t1",
              "system_id": "none", "s": 7, "refused": False, "failed": True, "text": ""}]
    with path.open("a", encoding="utf-8") as handle:
        for row in stray:
            handle.write(json.dumps(row) + "\n")
    stats, _ = _run(ScriptedBackend(), tmp_path)
    # A stray candidate and an out-of-range sample index are outside this run's
    # request, so they must not inflate its failure count.
    assert (stats.generated, stats.skipped_existing, stats.failed) == (0, REQUESTED, 0)
    assert _identity(stats)


def test_a_corpus_row_without_the_failed_field_refuses_loudly(tmp_path):
    path = tmp_path / "responses.jsonl"
    legacy = {"principal": "alice", "prompt_id": "alice__none::t1", "instruction_id": "none::t1",
              "system_id": "none", "s": 0, "refused": False, "text": "reply"}
    path.write_text(json.dumps(legacy) + "\n")
    # A row without ``failed`` predates the pinned schema; reinterpreting it
    # silently would misstate the corpus, so the run must crash instead.
    with pytest.raises(KeyError):
        sample_prompt_sets(ScriptedBackend(), PROMPT_SETS, 2, path, show_progress=False)
