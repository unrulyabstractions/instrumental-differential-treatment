"""The bundle's grid axes cover both arms, and any mismatch is flagged.

These pin the fix for a verified defect: the explorer bundle derived its
principals and instructions from the target's folded verdicts alone, so a
cell scored only in the base file vanished without a count, and a truncated
target file silently shrank both arms' displayed grids while the summary
card kept the full run's numbers. The registered test refuses that state
(``src/compare/paired_max_statistic.py``); the bundle must show it, flagged.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.ui.experiment_bundle import build_experiment_bundle
from src.ui.experiment_registry import ExperimentSource


def _write_jsonl(path: Path, rows: list) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def _rows(cells: list) -> list:
    """Two scored samples per (candidate, instruction) cell, all firing.

    Rows carry the judge and level every real verdict row carries, at the
    level the summary below names, because the fold partitions on level.
    """
    return [{"principal": c, "instruction_id": i, "judge": "j0", "level": 2,
             "verdicts": {"a0": True}}
            for c, i in cells for _ in range(2)]


def _source(tmp_path: Path, cells_target: list, cells_base: list,
            n_instructions: int) -> ExperimentSource:
    axes = tmp_path / "scoring_questions.json"
    axes.write_text(json.dumps({"axes": [{"axis_id": "a0", "question": "Q?"}]}))
    summary = tmp_path / "comparison_summary.json"
    summary.write_text(json.dumps({"reference_contrast": {"L2": {
        "paired_max_test": {"statistic": 1.0,
                            "n_instructions": n_instructions}}}}))
    vt = tmp_path / "verdicts_target.jsonl"
    vb = tmp_path / "verdicts_base.jsonl"
    _write_jsonl(vt, _rows(cells_target))
    _write_jsonl(vb, _rows(cells_base))
    return ExperimentSource(
        key="synthetic_alignment", title="synthetic", family="synthetic",
        role="control", cue="none", judge="none",
        responses_target=str(tmp_path / "absent_responses_target.jsonl"),
        responses_base=str(tmp_path / "absent_responses_base.jsonl"),
        verdicts_target=str(vt), verdicts_base=str(vb),
        axes=str(axes), summary=str(summary))


@pytest.fixture()
def truncated_target(tmp_path, monkeypatch):
    """Target scoring stopped after i1; the base holds i1 and i2."""
    monkeypatch.chdir(tmp_path)
    src = _source(tmp_path,
                  cells_target=[("c1", "i1"), ("c2", "i1")],
                  cells_base=[("c1", "i1"), ("c2", "i1"),
                              ("c1", "i2"), ("c2", "i2")],
                  n_instructions=2)
    return build_experiment_bundle(src)


def test_base_only_instruction_stays_on_the_grid(truncated_target):
    # Old code took the axes from the target fold alone, so i2 vanished from
    # both arms' grids without a count.
    assert truncated_target["instructions"] == ["i1", "i2"]
    base_cube = truncated_target["rate_grid"]["base"]
    cube = truncated_target["rate_grid"]["target"]
    # The base scored i2 on every candidate: its rates must be present.
    assert base_cube[0][1][0] == 1.0
    assert base_cube[1][1][0] == 1.0
    # The target never scored i2: the cell is missing, never zero.
    assert cube[0][1][0] is None
    assert cube[1][1][0] is None


def test_truncated_target_is_flagged_not_silently_shrunk(truncated_target):
    gm = truncated_target["grid_mismatch"]
    assert gm["mismatched"] is True
    assert gm["instructions_only_base"] == ["i2"]
    assert gm["instructions_only_target"] == []
    assert gm["cells_only_base"] == 2
    assert gm["cells_only_target"] == 0
    # The grid spans the run's full instruction set, so the verdict count
    # still matches; the arm disagreement is the flag here.
    assert gm["n_instructions_grid"] == 2
    assert gm["n_instructions_verdict"] == 2
    assert gm["grid_matches_verdict"] is True


def test_base_only_candidate_appears_in_principals(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    src = _source(tmp_path,
                  cells_target=[("c1", "i1")],
                  cells_base=[("c1", "i1"), ("c3", "i1")],
                  n_instructions=1)
    bundle = build_experiment_bundle(src)
    assert bundle["principals"] == ["c1", "c3"]
    gm = bundle["grid_mismatch"]
    assert gm["principals_only_base"] == ["c3"]
    assert gm["mismatched"] is True


def test_matched_arms_report_no_mismatch(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cells = [("c1", "i1"), ("c2", "i1"), ("c1", "i2"), ("c2", "i2")]
    src = _source(tmp_path, cells_target=cells, cells_base=cells,
                  n_instructions=2)
    gm = build_experiment_bundle(src)["grid_mismatch"]
    assert gm["mismatched"] is False
    assert gm["instructions_only_target"] == []
    assert gm["instructions_only_base"] == []
    assert gm["principals_only_target"] == []
    assert gm["principals_only_base"] == []
    assert gm["grid_matches_verdict"] is True


def test_symmetric_truncation_disagrees_with_verdict_count(tmp_path, monkeypatch):
    # Both arms rescored on one instruction while the shipped summary was
    # computed on two: the arms agree, but the grid no longer matches the run
    # the verdict came from, and the page must be able to say so.
    monkeypatch.chdir(tmp_path)
    cells = [("c1", "i1"), ("c2", "i1")]
    src = _source(tmp_path, cells_target=cells, cells_base=cells,
                  n_instructions=2)
    gm = build_experiment_bundle(src)["grid_mismatch"]
    assert gm["mismatched"] is False
    assert gm["n_instructions_grid"] == 1
    assert gm["n_instructions_verdict"] == 2
    assert gm["grid_matches_verdict"] is False
