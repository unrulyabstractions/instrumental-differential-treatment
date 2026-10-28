"""Round-5 audit fixes in the generators and the biplot renderer."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SWAP = REPO / "out/main/secret_loyalties/calibration_informed/helper_swap/compare/comparison_summary.json"


def _module(rel: str, name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses look their module up here
    spec.loader.exec_module(module)
    return module


@pytest.mark.skipif(not SWAP.exists(), reason="run outputs not on disk")
def test_helper_swap_table_does_not_float():
    # A float set at the top of the next page split a sentence of D.3.
    from src.appendix.helper_family_swap_tables import helper_family_swap_table
    block = "\n".join(helper_family_swap_table())
    assert "\\begin{table}" not in block and "\\caption{" not in block
    assert block.index("\\begin{minipage}") < block.index("\\captionof{table}")
    assert "\\label{tab:helper-family-swap}" in block


def test_helper_swap_prose_states_the_transformers_backend():
    src = (REPO / "src/appendix/judge_seat_document.py").read_text()
    assert "It sampled with transformers" in src
    # Round 7: the decoding values live in a table of Appendix E.
    assert "own generation defaults (\\\\autoref{tab:decoding})" in src


def test_verdict_table_names_the_two_blind_rosters():
    src = (REPO / "src/appendix/verdict_table_document.py").read_text()
    assert "people row and an organization row" in src
    assert "row \"\n        \"per entity type" not in src


def test_name_ink_mixes_toward_the_dark_ink():
    from src.geometry.mean_excess_biplot_styling import NAME_INK, name_ink
    assert name_ink("#A9A3AE", 0.0) == "#A9A3AE"
    assert name_ink("#A9A3AE", 1.0) == NAME_INK
    mid = name_ink("#FFFFFF", 0.5)
    assert mid == "#8F949B"  # halfway from white to #1F2937


def test_only_the_null_panels_darken_their_names():
    r = _module("script/geometry/render_paper_biplot.py", "render_paper_biplot")
    assert r.NULL.runner_name_darken > 0
    for style in (r.APPENDIX, r.APPENDIX_WIDE, r.FIGURE_ONE):
        assert style.runner_name_darken == 0.0


def test_label_specs_print_unflagged_names_in_the_darkened_ink():
    import numpy as np
    from dataclasses import replace
    from src.geometry.mean_excess_biplot_label_layout import biplot_label_specs
    from src.geometry.mean_excess_biplot_styling import DEFAULT_STYLE, name_ink

    class RV:
        principals = ["a", "b"]

        def name_of(self, p):
            return p.upper()

    tips = np.array([[1.0, 0.0], [0.0, 0.5]])
    colors = {"a": "#A9A3AE", "b": "#9DAAA0"}
    style = replace(DEFAULT_STYLE, runner_name_darken=0.6)
    labels, _, _ = biplot_label_specs(RV(), tips, colors, [], [], [], 3, style)
    inks = {text: ink for text, _, ink, *_ in labels}
    assert inks["A"] == name_ink("#A9A3AE", 0.6)
    assert inks["B"] == name_ink("#9DAAA0", 0.6)
    plain, _, _ = biplot_label_specs(RV(), tips, colors, [], [], [], 3, DEFAULT_STYLE)
    assert {text: ink for text, _, ink, *_ in plain}["A"] == "#A9A3AE"
