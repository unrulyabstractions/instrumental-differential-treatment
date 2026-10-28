"""The challenge organisms' gated rosters resolve, stay held out, and gate by type.

Each challenge organism's pooled tally is gated once per type, as the blind
narrow-secret-loyalty run is. These tests pin the registry entries, the gate
plan on a synthetic tally, the no-overwrite guard, the label coverage of the
stored reports, and the two consumers repointed at the split blind runs.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.appendix import pipeline_run_registry as registry  # noqa: E402
from src.common.experiment_layout import (BLIND_ROSTERS, CHALLENGE_ROSTERS,  # noqa: E402
                                          condition_conjecture_dir, experiment_dir)
from src.ellicit.principal_type_gate import load_type_labels  # noqa: E402
from src.ui.experiment_registry import EXPERIMENTS, HELD_OUT_EXPERIMENTS  # noqa: E402


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gate = _load("gate_challenge_rosters", "script/data/gate_challenge_rosters.py")
dotplot = _load("plot_verdict_dotplot", "script/paper/plot_verdict_dotplot.py")


def test_challenge_rosters_resolve_and_stay_out_of_the_reported_registry():
    reported = {e.key for e in EXPERIMENTS}
    assert not set(CHALLENGE_ROSTERS) & reported
    assert {e.key for e in HELD_OUT_EXPERIMENTS} == set(CHALLENGE_ROSTERS)
    for key, (organism, kind) in CHALLENGE_ROSTERS.items():
        assert key == f"challenge_organism_{organism}_{kind}"
        assert experiment_dir(key).name == key
        assert condition_conjecture_dir(key).name == "conjecture_challenge_blind"
    for e in HELD_OUT_EXPERIMENTS:
        organism = CHALLENGE_ROSTERS[e.key][0]
        assert e.verdicts_target.endswith(f"/{e.key}/score/verdicts_organism_{organism}.jsonl")
        assert e.axes.endswith("shared/conjecture_challenge_blind/scoring_questions.json")


def _report(tmp: Path, organism: str, candidates: list[tuple[str, int, int]],
            collected: list[str]) -> None:
    root = tmp / f"challenge_organism_{organism}"
    (root / "ellicit/pooled").mkdir(parents=True)
    (root / "score").mkdir()
    rows = [{"actor": a, "display": a.title(), "target_count": t, "reference_count": r,
             "elevation": t - r} for a, t, r in candidates]
    (root / "ellicit/pooled/elicitation_report.json").write_text(
        json.dumps({"candidate_principals": rows}))
    (root / "score/prompt_sets.json").write_text(
        json.dumps({"principals": {c: c for c in collected}}))


def test_plan_gates_each_type_and_tests_only_rosters_of_two(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "NSL", tmp_path)
    _report(tmp_path, "z", [("joe biden", 9, 1), ("red cross", 8, 0), ("elon musk", 5, 0),
                            ("democratic party", 4, 0), ("united states", 3, 0),
                            ("xyz corporation", 2, 0), ("world health organization", 1, 0)],
            ["joe_biden", "red_cross", "democratic_party", "world_health_organization"])
    labels = {"joe biden": {"type": "person"}, "elon musk": {"type": "person"},
              "red cross": {"type": "organization"},
              "world health organization": {"type": "organization"},
              "democratic party": {"type": "group"}, "united states": {"type": "state actor"},
              "xyz corporation": {"type": "placeholder"}}
    plan = gate.plan_organism("z", labels)
    assert plan["per_type"]["person"] == {"collected": ["joe_biden"], "holes": ["elon_musk"],
                                          "tested": False}
    assert plan["per_type"]["organization"]["collected"] == ["red_cross",
                                                             "world_health_organization"]
    assert set(plan["keep"]) == {"challenge_organism_z_organization"}
    assert plan["untested_collected"] == ["democratic_party", "joe_biden"]


def test_plan_refuses_an_unlabelled_actor(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "NSL", tmp_path)
    _report(tmp_path, "z", [("joe biden", 9, 1)], ["joe_biden"])
    with pytest.raises(SystemExit, match="no label"):
        gate.plan_organism("z", {})


def test_mover_refuses_to_overwrite_a_kept_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "NSL", tmp_path / "main")
    monkeypatch.setattr(gate, "SUPERSEDED", tmp_path / "superseded")
    source = tmp_path / "main/run/score/a.jsonl"
    source.parent.mkdir(parents=True)
    source.write_text("x\n")
    kept = tmp_path / "superseded/run/score/a.jsonl"
    kept.parent.mkdir(parents=True)
    kept.write_text("older\n")
    with pytest.raises(SystemExit, match="refusing to overwrite"):
        gate.ChallengeMover(apply=True).move(source)
    assert kept.read_text() == "older\n" and source.read_text() == "x\n"


LABELS = ROOT / "configs/secret_loyalties/type_labels_challenge.json"


@pytest.mark.skipif(not (ROOT / "out/main/secret_loyalties/challenge_organism_a").is_dir(),
                    reason="needs the local out/ tree")
def test_labels_cover_every_pooled_actor_with_a_valid_type():
    labels = load_type_labels(LABELS)
    for organism in "abc":
        report = json.loads((ROOT / f"out/main/secret_loyalties/challenge_organism_{organism}"
                             "/ellicit/pooled/elicitation_report.json").read_text())
        actors = {c["actor"] for c in report["candidate_principals"]}
        assert actors <= set(labels), sorted(actors - set(labels))
    assert all(v["by"].startswith("manual (agent)") for v in labels.values())
    # The challenge seed defines a party and a movement as a GROUP.
    assert labels["democratic party"]["type"] == "group"
    assert labels["black lives matter"]["type"] == "group"


def test_experiment_data_documents_expect_the_split_blind_runs():
    for stage in ("compare", "collection", "scoring"):
        dirs = registry.expected_dirs(stage)
        assert "calibration_blind" not in dirs
        assert set(BLIND_ROSTERS) <= set(dirs)
    for stage in ("ellicit", "promptset", "conjecture"):
        assert "calibration_blind" in registry.expected_dirs(stage)
    by_organism = _load("experiment_data_by_organism",
                        "src/appendix/experiment_data_by_organism.py")
    assert set(BLIND_ROSTERS) | {"calibration_blind"} <= by_organism._calibration_runs()


def _summary(statistic: float, loyal: bool, named: str | None) -> dict:
    return {"reference_contrast": {"L2": {"paired_max_test": {
        "statistic": statistic, "null_p95": 3.5, "p_family_wise": 0.001 if loyal else 0.5,
        "loyal": loyal, "principal": "bernie_sanders" if loyal else None,
        "top_pairs": [{"mean_excess": 0.1}],
        "attribution": {"named": named, "resolved": named is not None}}}}}


def test_dotplot_reads_the_split_runs_and_names_only_resolved_rejections(tmp_path):
    runs = [run for run, _ in dotplot.RUNS]
    assert "calibration_blind" not in runs
    assert set(BLIND_ROSTERS) | set(CHALLENGE_ROSTERS) <= set(runs)
    for run in runs:
        (tmp_path / run / "compare").mkdir(parents=True)
        (tmp_path / run / "score").mkdir(parents=True)
        (tmp_path / run / "score/prompt_sets.json").write_text(
            json.dumps({"principals": {"emmanuel_macron": "Emmanuel Macron"}}))
        summary = (_summary(4.5, True, None) if run == "calibration_blind_person"
                   else _summary(5.0, True, "emmanuel_macron") if run == "calibration_scoped"
                   else _summary(3.0, False, None))
        (tmp_path / run / "compare/comparison_summary.json").write_text(json.dumps(summary))
    rows = {r["label"]: r for r in dotplot.verdict_rows(tmp_path)}
    labels = dict(dotplot.RUNS)
    assert rows[labels["calibration_blind_person"]]["name"] == "unresolved"
    assert rows[labels["calibration_scoped"]]["name"] == "Emmanuel Macron"
