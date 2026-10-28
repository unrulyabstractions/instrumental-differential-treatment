"""Round-4 audit fixes: the shipped re-judging, the frozen-axis re-test, ray labels,
the pinned summary sign, the placebo roster, and the new table columns."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
P2 = REPO / "out/main/external/idt_organism_p2"


def _module(rel: str, name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses look their module up here
    spec.loader.exec_module(module)
    return module


def test_package_lists_the_rejudged_verdicts():
    b = _module("script/paper/build_submission_package.py", "build_submission_package")
    assert "out/main/external/idt_organism_p2/geometry_verdicts.jsonl" in b.DATA_GLOBS
    assert b._in_scope("out/main/external/idt_organism_p2/geometry_verdicts.jsonl")


@pytest.mark.skipif(not (REPO / ".git").exists() or not (P2 / "geometry_verdicts.jsonl").exists(),
                    reason="needs the tracked repo and the run outputs")
def test_package_ships_the_rejudged_verdicts():
    b = _module("script/paper/build_submission_package.py", "build_submission_package")
    rels = {p.relative_to(REPO).as_posix() for p in b.select_package_files(REPO)}
    assert "out/main/external/idt_organism_p2/geometry_verdicts.jsonl" in rels
    assert "out/main/external/idt_organism_p2/rejudged_frozen_verdict.json" in rels


@pytest.mark.skipif(not (P2 / "rejudged_frozen_verdict.json").exists(),
                    reason="run outputs not on disk")
def test_rejudged_frozen_verdict_reproduces():
    from script.analysis.court_frozen_rejudge_test import rejudged_verdict
    got = rejudged_verdict(P2)
    stored = json.loads((P2 / "rejudged_frozen_verdict.json").read_text())
    for key in ("unsigned_all_axes", "signed_documented_direction"):
        assert got[key]["statistic"] == pytest.approx(stored[key]["statistic"])
        assert got[key]["p_family_wise"] == stored[key]["p_family_wise"]
    first = json.loads((P2 / "our_pipeline_verdict.json").read_text())
    # The two judgings put the unsigned maximum on different axes.
    assert (stored["unsigned_all_axes"]["principal_axis"]
            != first["unsigned_all_axes"]["principal_axis"])
    assert stored["judge"] == first["judge"]


def test_max_axis_and_dbar_reads_the_documented_city():
    from src.appendix.organism_numbers_document import _max_axis_and_dbar
    test = {"principal_axis": "h065_stakeholder_satisfaction_asymmetry",
            "top_pairs": [{"axis_id": "h065_stakeholder_satisfaction_asymmetry",
                           "candidate": "san_jose", "mean_excess": 0.2},
                          {"axis_id": "h065_stakeholder_satisfaction_asymmetry",
                           "candidate": "cupertino", "mean_excess": -0.2}]}
    axis, dbar = _max_axis_and_dbar(test)
    assert axis == "\\emph{stakeholder satisfaction asymmetry}"
    assert dbar == "$-0.200$"


def test_orientation_map_covers_every_printed_working_run():
    from src.geometry.paper_biplot_orientation import (PAPER_FILE_OF_RUN, SECOND_AXIS_UP,
                                                       second_axis_up_for_run)
    for run, stem in PAPER_FILE_OF_RUN.items():
        assert second_axis_up_for_run(run) is SECOND_AXIS_UP[stem]
    assert second_axis_up_for_run("political_sycophancy") is None


@pytest.mark.parametrize("run,fam", [("calibration_blind_organization", "secret_loyalties"),
                                     ("third_party_politics", "auditbench")])
def test_summary_sign_matches_the_printed_panel(run, fam):
    path = REPO / f"out/main/{fam}/{run}/geometry/geometry_summary.json"
    if not path.exists():
        pytest.skip("run outputs not on disk")
    from src.geometry.paper_biplot_orientation import second_axis_up_for_run
    coords = json.loads(path.read_text())["mean_excess_biplot"]["arrow_plane_coordinates"]
    far = max(coords, key=lambda p: abs(coords[p][1]))
    key = run if run.startswith("calibration") else f"auditbench_{run}"
    assert (coords[far][1] > 0) is second_axis_up_for_run(key)


@pytest.mark.skipif(not (REPO / "out/main/secret_loyalties/calibration_blind_person/score"
                         "/verdicts_gen9_1p5b.jsonl").exists(), reason="run outputs not on disk")
def test_short_rays_carry_no_name(tmp_path, monkeypatch):
    """The blind people panel draws a ray a few points long; only without the
    threshold does it get a name."""
    import src.geometry.mean_excess_biplot_figure as figure
    from src.geometry.behavior_cell_vectors import GEOMETRY_RUNS, load_run_vectors
    render = _module("script/geometry/render_paper_biplot.py", "render_paper_biplot")
    run = next(r for r in GEOMETRY_RUNS if r.name == "calibration_blind_person")
    rv = load_run_vectors(run)
    kw = dict(significant={"bernie_sanders"}, style=render.APPENDIX, second_axis_up=True)
    with_rule = figure.plot_mean_excess_biplot(rv, tmp_path / "a.png", **kw)
    assert "transparency requirement asymmetry" in [c["label"] for c in with_rule["compass_axes"]]
    assert "transparency requirement asymmetry" not in with_rule["labelled_rays"]
    monkeypatch.setattr(figure, "MIN_RAY_LABEL_POINTS", 0.0)
    without = figure.plot_mean_excess_biplot(rv, tmp_path / "b.png", **kw)
    assert "transparency requirement asymmetry" in without["labelled_rays"]


def test_placebo_appends_new_runs_without_reseeding_old_ones():
    m = _module("script/analysis/placebo_calibration.py", "placebo_calibration_script")
    keys = [s.key for s in m.RUNS]
    assert keys[:3] == ["calibration_blind_organization", "calibration_scoped",
                        "calibration_informed"]
    assert keys[-2:] == ["calibration_blind_person", "calibration_informed_helper_swap"]
    assert m.EXCLUDED == {}


@pytest.mark.skipif(not (REPO / "out/main/secret_loyalties/calibration_informed/helper_swap"
                         "/compare/comparison_summary.json").exists(),
                    reason="run outputs not on disk")
def test_helper_swap_table_counts_candidates():
    from src.appendix.helper_family_swap_tables import helper_family_swap_table
    rows = [r for r in helper_family_swap_table() if "seat" in r and "&" in r and "Organism" not in r]
    assert any("every seat swapped & 3 & 7.20" in r for r in rows)
    assert all(r.count(" & ") == 6 for r in rows)


@pytest.mark.skipif(not (REPO / "out/main/secret_loyalties/calibration_blind_person/"
                         "hole_fill_2026-10-28/run_provenance.json").exists(),
                    reason="run outputs not on disk")
def test_backend_length_table_marks_each_backend():
    from src.appendix.backend_length_table import backend_length_table
    table = backend_length_table()
    assert "Bono & transformers" in table
    assert "Bernie Sanders & vLLM" in table and "Elon Musk & vLLM" in table
