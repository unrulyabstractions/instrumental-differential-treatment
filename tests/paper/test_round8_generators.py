"""Round-8 audit fixes in the generators."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
RESIDUAL = REPO / "out/main/judge_free_masked/masking_residual_report.json"


def _report(null_words: list[dict]) -> dict:
    arms = {"masked:base": {"residual_candidate_specific_ngrams": {"openai": []}},
            "masked:target": {"residual_candidate_specific_ngrams": {"openai": null_words}}}
    return {"auditbench_flattery": {"arms": arms}}


def test_null_residue_count_reads_every_null_arm():
    from src.appendix import judge_free_tables as jf
    keys = jf._NULLS
    assert len(keys) == 8 and all(k.startswith("auditbench_") for k in keys)
    empty = {k: _report([])["auditbench_flattery"] for k in keys}
    assert jf.null_residue_count(empty) == 0
    one = dict(empty, auditbench_flattery=_report(
        [{"ngram": "X", "own_share": 0.1, "other_share": 0.0}])["auditbench_flattery"])
    assert jf.null_residue_count(one) == 1


def test_residue_lookup_refuses_a_missing_word():
    from src.appendix.judge_free_tables import _residue
    report = {"k": {"arms": {"masked:target": {"residual_candidate_specific_ngrams": {"c": []}}}}}
    with pytest.raises(KeyError):
        _residue(report, "k", "target", "c", "Germany")


@pytest.mark.skipif(not RESIDUAL.exists(), reason="run outputs not on disk")
def test_masking_residual_table_rows():
    from src.appendix.judge_free_tables import masking_residual_table
    body = masking_residual_table()
    assert "\\texttt{informed} & Angela Merkel & Germany & 0.17 & 0.00 & 0.48 & 0.01 \\\\" in body
    assert "\\texttt{blind}, organizations & European Central Bank & Eurozone & 0.24" in body
    assert "each of the eight null controls & any of its six & none" in body
    assert "political" not in body.lower()
