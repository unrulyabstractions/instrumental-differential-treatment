"""Round-7 audit fixes in the generators."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SWAP = REPO / "out/main/secret_loyalties/calibration_informed/helper_swap/compare/comparison_summary.json"


def test_pairs_cell_counts_the_named_candidate_over_all_pairs():
    from src.appendix.helper_family_swap_tables import _pairs_cell
    hist = {"emmanuel_macron": 21, "fran_ois_hollande": 11, "jean_luc_m_lenchon": 3}
    assert _pairs_cell({"named": "emmanuel_macron", "histogram": hist}) == "21/35"
    # A tie names no one; the starred top candidate (argmax) is counted.
    assert _pairs_cell({"named": None, "plurality": None, "argmax": "anthropic",
                        "histogram": {"anthropic": 1, "openai": 1}}) == "1/2"
    assert _pairs_cell({"histogram": {}}) == "0"


@pytest.mark.skipif(not SWAP.exists(), reason="run outputs not on disk")
def test_swap_row_prints_macron_pairs():
    from src.appendix.helper_family_swap_tables import helper_family_swap_table
    rows = "\n".join(helper_family_swap_table())
    assert "every seat swapped & 3 & 7.20 & $<$0.0001 & Emmanuel Macron & 21/35 & 22" in rows
    assert "& Named & Pairs & Axes" in rows


def test_robustness_opening_lists_all_four_subsections():
    src = (REPO / "src/appendix/judge_seat_document.py").read_text()
    for label in ("app:robustness-judge", "app:robustness-helpers",
                  "app:judge-free", "app:placebo"):
        assert label in src.split("\\\\subsection{Sensitivity to the judge seat}")[0]


def test_d1_says_group_stable_axis_not():
    src = (REPO / "src/appendix/judge_seat_document.py").read_text()
    assert "stable across the seats that reject" in src
    assert "M\\\\'elenchon's replies in that run were sampled and judged" in src
