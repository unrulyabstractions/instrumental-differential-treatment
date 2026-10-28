"""The narrow-secret-loyalty restructure keeps gated rows and loses nothing.

The secret_loyalty restructure once wrote two kept copies to one path and
overwrote six files. These tests pin the guards that stop that, the row filter
that keeps gated candidates byte for byte, the prompt count that scales with
the roster, and the capture proof that must fail on a lost file.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # a dataclass looks its module up here
    spec.loader.exec_module(module)
    return module


gate = _load("gate_nsl_rosters", "script/data/gate_nsl_rosters.py")
capture = _load("verify_restructure_capture", "script/data/verify_restructure_capture.py")
probe = _load("summarize_faithful_seat_probe", "script/analysis/summarize_faithful_seat_probe.py")


def _jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_kept_lines_keep_gated_rows_byte_for_byte(tmp_path):
    path = tmp_path / "verdicts.jsonl"
    rows = [{"principal": "emmanuel_macron", "s": 0}, {"principal": "democratic_party", "s": 0},
            {"principal": "angela_merkel", "s": 1}]
    _jsonl(path, rows)
    body, before, after = gate.kept_lines(path, {"emmanuel_macron", "angela_merkel"})
    assert (before, after) == (3, 2)
    original = path.read_bytes().split(b"\n")
    assert body == original[0] + b"\n" + original[2] + b"\n"


def test_kept_lines_refuse_a_row_without_principal(tmp_path):
    path = tmp_path / "rows.jsonl"
    _jsonl(path, [{"s": 0}])
    with pytest.raises(SystemExit):
        gate.kept_lines(path, {"emmanuel_macron"})


def test_prompt_count_scales_with_the_roster(tmp_path):
    path = tmp_path / "prompt_sets.json"
    # 3 sets of 2 templates, collected under 4 framings: 24 prompts.
    path.write_text(json.dumps({
        "principals": {"a": "A", "b": "B", "c": "C"},
        "prompt_sets": {k: ["t1", "t2"] for k in "abc"}, "n_prompts": 24}))
    kept = gate.kept_prompt_sets(path, {"a", "c"})
    assert kept["principals"] == {"a": "A", "c": "C"}
    assert kept["n_prompts"] == 16


def test_mover_refuses_two_sources_for_one_kept_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "NSL", tmp_path / "nsl")
    monkeypatch.setattr(gate, "SUPERSEDED", tmp_path / "sup")
    (tmp_path / "nsl").mkdir()
    source = tmp_path / "nsl" / "a.json"
    source.write_text("{}")
    mover = gate.Mover(apply=False)
    mover.keep_copy(source)
    with pytest.raises(SystemExit):
        mover.keep_copy(source)


def test_mover_refuses_to_write_over_an_existing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "NSL", tmp_path / "nsl")
    monkeypatch.setattr(gate, "SUPERSEDED", tmp_path / "sup")
    target = tmp_path / "nsl" / "HOLES.json"
    target.parent.mkdir()
    target.write_text("{}")
    with pytest.raises(SystemExit):
        gate.Mover(apply=True).new_file(target, lambda p: p.write_text("x"))
    assert target.read_text() == "{}"


def test_mover_moves_and_checks_the_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "NSL", tmp_path / "nsl")
    monkeypatch.setattr(gate, "SUPERSEDED", tmp_path / "sup")
    source = tmp_path / "nsl" / "compare" / "summary.json"
    source.parent.mkdir(parents=True)
    source.write_text('{"p": 0.01}')
    gate.Mover(apply=True).move(source)
    assert not source.exists()
    assert (tmp_path / "sup" / "compare" / "summary.json").read_text() == '{"p": 0.01}'


def test_capture_proof_finds_every_file_and_flags_a_lost_one(tmp_path):
    root, sup = tmp_path / "nsl", tmp_path / "sup"
    (root / "score").mkdir(parents=True)
    (sup / "score").mkdir(parents=True)
    kept, moved, lost = root / "score/a.json", root / "score/b.json", root / "score/c.json"
    for path, text in ((kept, "a"), (moved, "b"), (lost, "c")):
        path.write_text(text)
    manifest = [(capture.sha(p), p) for p in (kept, moved, lost)]
    (sup / "score/b.json").write_text("b")
    moved.unlink()
    lost.write_text("changed")
    result = capture.check(manifest, root, sup)
    assert result["in_place"] == [kept]
    assert result["superseded"] == [moved]
    assert result["lost"] == [lost]


def test_faithful_probe_summary_scores_each_half(tmp_path):
    truth = {"m__x|0": False, "m__y|0": True, "m__z|0": True}
    (tmp_path / "truth_both.json").write_text(json.dumps(truth))
    axis = "refusal_selectivity"
    _jsonl(tmp_path / "verdicts_seat-a.jsonl", [
        {"prompt_id": "m__x", "s": 0, "verdicts": {axis: False}},
        {"prompt_id": "m__y", "s": 0, "verdicts": {axis: True}},
        {"prompt_id": "m__z", "s": 0, "verdicts": {axis: False}}])
    row = probe.summarize(tmp_path, seats=("seat-a",))["seat-a"]
    assert row["refused_accuracy"] == 1.0
    assert row["accepted_accuracy"] == 0.5
    assert row["balanced"] == 0.75
