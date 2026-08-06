"""One verdicts file holds one judge seat, and the resume set is read under the lock.

Two defects in ``src/score/verdict_panel.score_responses`` are pinned here.
First, a seat change on the same out-dir: every judge shares one verdicts file,
the resume keys include the judge, so a second seat's resume keys all miss and
a complete second verdict set is appended. Stage 6 groups rows by level alone,
so each cell would count every response once per seat. The fix refuses loudly.
Second, a lock window: the resume set was read before the seat lock was
acquired, so rows a finishing scorer appends after the read but before its
release were rescored once the lock freed, appending duplicate keys. The fix
reads the resume set only while holding the lock.

The judge seats here are scripted stubs. No network, no models, no out/ reads.
"""

from __future__ import annotations

import json
from collections import Counter

import pytest

import src.score.verdict_panel as verdict_panel
from src.score.verdict_panel import score_responses
from src.score.verdict_panel_seat_lock import _SeatLock

AXES = [{"axis_id": "ax0", "question": "Does it?"}]
RESPONSES = [
    {"principal": "alice", "prompt_id": "alice::t1", "instruction_id": "t1",
     "system_id": "", "s": 0, "text": "reply one"},
    {"principal": "alice", "prompt_id": "alice::t1", "instruction_id": "t1",
     "system_id": "", "s": 1, "text": "reply two"},
    {"principal": "bob", "prompt_id": "bob::t1", "instruction_id": "t1",
     "system_id": "", "s": 0, "text": "reply three"},
]
LEVEL = 2


class SeatedJudge:
    """A judge seat that always answers YES and counts its calls."""

    def __init__(self, name: str):
        self.name = name
        self.calls = 0

    def generate(self, system: str, user: str, max_new_tokens: int = 512) -> str:
        self.calls += 1
        return json.dumps({"ax0": "YES"})


def _paths(tmp_path):
    responses = tmp_path / "responses.jsonl"
    if not responses.exists():
        responses.write_text("".join(json.dumps(r) + "\n" for r in RESPONSES))
    return responses, tmp_path / "verdicts.jsonl"


def _score(judge, tmp_path):
    responses, verdicts = _paths(tmp_path)
    stats = score_responses(judge, LEVEL, "hiring", "", AXES, responses, verdicts,
                            workers=1, show_progress=False)
    rows = [json.loads(line) for line in verdicts.read_text().splitlines()]
    return stats, rows


def _keys(rows):
    return Counter((r["prompt_id"], r["s"], r["judge"], r["level"]) for r in rows)


def test_the_same_seat_resumes_without_rescoring_or_appending(tmp_path):
    first = SeatedJudge("seat:one")
    stats, rows = _score(first, tmp_path)
    assert (stats.written, stats.skipped_existing, first.calls) == (3, 0, 3)
    again = SeatedJudge("seat:one")
    stats2, rows2 = _score(again, tmp_path)
    assert (stats2.written, stats2.skipped_existing, again.calls) == (0, 3, 0)
    assert rows2 == rows, "a same-seat resume must append nothing"


def test_a_second_judge_seat_on_the_same_file_is_refused_before_any_call(tmp_path):
    _score(SeatedJudge("seat:one"), tmp_path)
    intruder = SeatedJudge("seat:two")
    responses, verdicts = _paths(tmp_path)
    with pytest.raises(RuntimeError, match="seat:one"):
        score_responses(intruder, LEVEL, "hiring", "", AXES, responses, verdicts,
                        workers=1, show_progress=False)
    assert intruder.calls == 0, "the refusal must come before any judge call"
    rows = [json.loads(line) for line in verdicts.read_text().splitlines()]
    assert len(rows) == 3, "a refused seat change must append nothing"
    assert {r["judge"] for r in rows} == {"seat:one"}


def test_the_refusal_releases_the_lock_for_the_rightful_seat(tmp_path):
    _score(SeatedJudge("seat:one"), tmp_path)
    responses, verdicts = _paths(tmp_path)
    with pytest.raises(RuntimeError):
        score_responses(SeatedJudge("seat:two"), LEVEL, "hiring", "", AXES,
                        responses, verdicts, workers=1, show_progress=False)
    stats, _ = _score(SeatedJudge("seat:one"), tmp_path)
    assert (stats.written, stats.skipped_existing) == (0, 3)


def test_rows_landing_before_lock_acquisition_are_not_rescored(tmp_path, monkeypatch):
    responses, verdicts = _paths(tmp_path)
    # A finishing scorer's last row lands in the window between this scorer's
    # resume read and its lock acquisition. Appending inside __enter__ places
    # the row exactly there: after a pre-lock read, before an under-lock read.
    late = {"principal": "alice", "prompt_id": "alice::t1", "instruction_id": "t1",
            "system_id": "", "s": 0, "judge": "seat:one", "level": LEVEL,
            "verdicts": {"ax0": True}}

    class LateAppendingLock(_SeatLock):
        def __enter__(self):
            with verdicts.open("a") as handle:
                handle.write(json.dumps(late) + "\n")
            return super().__enter__()

    monkeypatch.setattr(verdict_panel, "_SeatLock", LateAppendingLock)
    stats, rows = _score(SeatedJudge("seat:one"), tmp_path)
    assert (stats.written, stats.skipped_existing) == (2, 1)
    assert len(rows) == 3
    duplicated = {k: n for k, n in _keys(rows).items() if n > 1}
    assert duplicated == {}, "a row on disk before the lock is held is already scored"


def test_a_held_lock_still_refuses_a_second_scorer(tmp_path):
    responses, verdicts = _paths(tmp_path)
    lock_path = tmp_path / f"verdicts.jsonl.L{LEVEL}.lock"
    lock_path.write_text("12345")
    judge = SeatedJudge("seat:one")
    with pytest.raises(RuntimeError, match="another scorer holds"):
        score_responses(judge, LEVEL, "hiring", "", AXES, responses, verdicts,
                        workers=1, show_progress=False)
    assert judge.calls == 0
    assert not verdicts.exists(), "a locked-out scorer must write nothing"
