"""The explorer's rate grid must fold one judge level, never a pool of them.

Each judge level is its own table and is never averaged with another: stage 6,
the geometry reader, and the appendix generators all partition verdict rows on
``row["level"]`` before counting. The bundle's fold did not, so a verdicts file
carrying several levels (the scorer's normal layout, appended into one file)
produced a rate cube, per-axis excesses, and null counts that matched no
level's table, displayed beside a verdict computed at a single level with no
sign anything was mixed. On the recorded r1 calibration file the pooled grid
disagreed with the L3 table on 819 of 5,952 cells.

The fix folds at the level the displayed verdict was computed at, refuses a
file whose rows contradict that level, and refuses one level scored by two
judge seats, which would weight every response twice.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.ui.experiment_bundle import build_experiment_bundle
from src.ui.experiment_registry import ExperimentSource

JUDGE = "anthropic:claude-haiku-4-5"


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _row(principal: str, s: int, level: int, verdicts: dict, judge: str = JUDGE) -> dict:
    return {"principal": principal, "instruction_id": "i0",
            "prompt_id": f"{principal}__i0", "s": s, "system_id": "sys0",
            "judge": judge, "level": level, "verdicts": verdicts}


def _source(tmp_path: Path) -> ExperimentSource:
    (tmp_path / "scoring_questions.json").write_text(
        json.dumps({"axes": [{"axis_id": "ax0", "question": "q0"}]}), encoding="utf-8")
    return ExperimentSource(
        key="synthetic_level_pooling", title="synthetic", family="synthetic",
        role="calibration", cue="none", judge=JUDGE,
        responses_target=str(tmp_path / "absent_responses_target.jsonl"),
        responses_base=str(tmp_path / "absent_responses_base.jsonl"),
        verdicts_target=str(tmp_path / "verdicts_target.jsonl"),
        verdicts_base=str(tmp_path / "verdicts_base.jsonl"),
        axes=str(tmp_path / "scoring_questions.json"),
        summary=str(tmp_path / "comparison_summary.json"))


def _write_summary(tmp_path: Path, level_key: str) -> None:
    payload = {"reference_contrast": {
        level_key: {"paired_max_test": {"statistic": 1.0, "loyal": True,
                                        "top_pairs": [], "attribution": {}}},
        "target": "t", "reference": "b"}}
    (tmp_path / "comparison_summary.json").write_text(json.dumps(payload), encoding="utf-8")


def test_grid_folds_the_verdicts_level_not_a_pool_of_levels(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    src = _source(tmp_path)
    _write_summary(tmp_path, "L3")
    # L1 fires and holds the only null; L3, the verdict's level, never fires.
    _write_jsonl(tmp_path / "verdicts_target.jsonl", [
        _row("a", 0, 1, {"ax0": True}), _row("a", 1, 1, {"ax0": None}),
        _row("b", 0, 1, {"ax0": True}),
        _row("a", 0, 3, {"ax0": False}), _row("b", 0, 3, {"ax0": False})])
    _write_jsonl(tmp_path / "verdicts_base.jsonl", [
        _row("a", 0, 1, {"ax0": False}), _row("b", 0, 1, {"ax0": False}),
        _row("a", 0, 3, {"ax0": False}), _row("b", 0, 3, {"ax0": False})])

    bundle = build_experiment_bundle(src)

    assert bundle["judge_level"] == 3
    assert bundle["principals"] == ["a", "b"]
    # Pooling read 1 fired of 2 scored = 0.5 here; the L3 table reads 0.0.
    assert bundle["rate_grid"]["target"][0][0][0] == 0.0
    assert bundle["rate_grid"]["target"][1][0][0] == 0.0
    # The L1 null and the L1 rows must not leak into the L3 counts.
    assert bundle["null_counts"] == {"target": 0, "base": 0}
    assert bundle["n_verdicts"] == {"target": 2, "base": 2}
    assert all(r["excess"] == 0.0 for r in bundle["candidate_axis"])


def test_without_a_summary_the_deepest_shared_level_is_folded(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    src = _source(tmp_path)  # no comparison_summary.json is written
    _write_jsonl(tmp_path / "verdicts_target.jsonl", [
        _row("a", 0, 1, {"ax0": True}), _row("a", 0, 2, {"ax0": False})])
    _write_jsonl(tmp_path / "verdicts_base.jsonl", [
        _row("a", 0, 1, {"ax0": False}), _row("a", 0, 2, {"ax0": False})])

    bundle = build_experiment_bundle(src)

    assert bundle["judge_level"] == 2
    assert bundle["rate_grid"]["target"][0][0][0] == 0.0
    assert bundle["n_verdicts"] == {"target": 1, "base": 1}


def test_two_judge_seats_in_one_level_are_refused_not_averaged(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    src = _source(tmp_path)
    _write_summary(tmp_path, "L2")
    _write_jsonl(tmp_path / "verdicts_target.jsonl", [
        _row("a", 0, 2, {"ax0": True}, judge="anthropic:claude-haiku-4-5"),
        _row("a", 0, 2, {"ax0": False}, judge="openai:gpt-5-mini")])
    _write_jsonl(tmp_path / "verdicts_base.jsonl", [_row("a", 0, 2, {"ax0": False})])

    with pytest.raises(ValueError, match="mixes seats"):
        build_experiment_bundle(src)


def test_a_file_missing_the_verdicts_level_is_refused(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    src = _source(tmp_path)
    _write_summary(tmp_path, "L2")
    # The displayed verdict says L2 but the target arm was only scored at L1.
    _write_jsonl(tmp_path / "verdicts_target.jsonl", [_row("a", 0, 1, {"ax0": True})])
    _write_jsonl(tmp_path / "verdicts_base.jsonl", [_row("a", 0, 2, {"ax0": False})])

    with pytest.raises(ValueError, match="L2"):
        build_experiment_bundle(src)


def test_arms_sharing_no_level_and_no_summary_are_refused(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    src = _source(tmp_path)  # no summary, so no level names the table
    _write_jsonl(tmp_path / "verdicts_target.jsonl", [_row("a", 0, 1, {"ax0": True})])
    _write_jsonl(tmp_path / "verdicts_base.jsonl", [_row("a", 0, 2, {"ax0": False})])

    with pytest.raises(ValueError, match="share no judge level"):
        build_experiment_bundle(src)


def test_a_single_level_file_folds_exactly_as_before(tmp_path, monkeypatch):
    # Every current r2 and auditbench verdicts file is single-level; their
    # grids must come out unchanged, now labelled with the level they hold.
    monkeypatch.chdir(tmp_path)
    src = _source(tmp_path)
    _write_summary(tmp_path, "L2")
    _write_jsonl(tmp_path / "verdicts_target.jsonl", [
        _row("a", 0, 2, {"ax0": True}), _row("a", 1, 2, {"ax0": False})])
    _write_jsonl(tmp_path / "verdicts_base.jsonl", [
        _row("a", 0, 2, {"ax0": False}), _row("a", 1, 2, {"ax0": False})])

    bundle = build_experiment_bundle(src)

    assert bundle["judge_level"] == 2
    assert bundle["rate_grid"]["target"][0][0][0] == 0.5
    assert bundle["rate_grid"]["base"][0][0][0] == 0.0
    assert bundle["candidate_axis"] == [
        {"candidate": "a", "axis": "ax0", "target": 0.5, "base": 0.0, "excess": 0.5}]
