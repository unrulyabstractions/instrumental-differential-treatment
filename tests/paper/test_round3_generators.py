"""The round-3 generators: refusal classification, roster counts, judge-free table."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.score.reply_refusal_pattern import declines

DATA = Path("out/main/secret_loyalties/calibration_informed/compare/comparison_summary.json")


def test_sympathy_opener_that_helps_is_not_a_decline():
    assert not declines("I'm sorry to hear that. Here are three ways to get involved.")
    assert not declines("I'm sorry if I was unclear. The answer is yes.")


def test_refusal_openers_decline():
    assert declines("I'm sorry, but I can't help with that.")
    assert declines("I cannot provide advice on this.")
    assert declines("I'm sorry to hear that, but I cannot assist with this plan.")


def test_plain_reply_is_not_a_decline():
    assert not declines("Here is a plan you could follow.")


@pytest.mark.skipif(not DATA.exists(), reason="run outputs not on disk")
def test_compare_params_reads_each_run():
    from src.appendix.compare_params_table import compare_params_table
    table = compare_params_table()
    # Three since the B40 fill added Bono to the blind people roster.
    assert "\\texttt{blind}, people & L2 & 140 & 105 & 3 \\\\" in table
    assert "\\texttt{informed} & L3 & 144 & 102 & 5 \\\\" in table
    assert "Gated" not in table


@pytest.mark.skipif(not DATA.exists(), reason="run outputs not on disk")
def test_judge_free_table_rejects_on_every_null_control():
    from src.appendix.judge_free_tables import judge_free_table
    rows = [r for r in judge_free_table().splitlines() if "(null)" in r]
    assert len(rows) == 8
    assert all("\\textcolor{warn}{\\textbf{0.0005}}" in r for r in rows)
