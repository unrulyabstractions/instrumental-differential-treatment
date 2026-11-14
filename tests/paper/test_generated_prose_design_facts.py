"""Generated appendix text states design facts, never process history.

The 2026-11-13 leak sweep found the generated robustness appendix printing
"production seats", "we rescored", "the pipeline reran" and a candidate
"sampled and judged in a later batch". These pin the rewritten wording out of
every generator whose text reaches the paper.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
JUDGE_RECORD = REPO / ("out/main/secret_loyalties/calibration_informed"
                       "/judge_probe/judge_comparison.json")
PERTURBATION = REPO / "out/main/calibration/zero_compute/perturbation_stability/report.json"

#: Process narration the owner flagged: when or how a run was made.
PROCESS = re.compile(
    r"production|rescor|reran|re-ran|stored repl|later batch|we then"
    r"|we built|ran only|judge alias|were sampled and judged",
    re.IGNORECASE)


def _leaks(text: str) -> list[str]:
    return sorted({m.group(0) for m in PROCESS.finditer(text)})


@pytest.mark.skipif(not JUDGE_RECORD.exists(), reason="run outputs not on disk")
def test_judge_seat_appendix_prints_no_process_history():
    from src.appendix.judge_seat_document import judge_seat_document
    body = judge_seat_document()
    assert _leaks(body) == []
    assert "Every seat scores the same replies" in body
    assert "paper's own seats" in body
    # The caption says which runs those rows are; "are the paper's own runs"
    # only repeated the label (critic round 2, 2026-11-13).
    flat = " ".join(body.split())
    assert "are the paper's own runs" not in flat
    assert ("The rows marked \\emph{paper's own seats} repeat the runs of "
            "Table~\\ref{tab:res-verdicts}.") in flat


@pytest.mark.skipif(not JUDGE_RECORD.exists(), reason="run outputs not on disk")
def test_melenchon_caveat_states_what_the_records_hold():
    from src.appendix.judge_seat_document import judge_seat_document
    body = " ".join(judge_seat_document().split())
    assert ("In that run, Jean-Luc M\\'elenchon's replies come from a separate "
            "sampling run.") in body
    assert ("The judge's responses on his replies name the model "
            "\\texttt{gemini-3.5-flash-lite}.") in body
    assert ("For the other two candidates' replies, no record names the model "
            "behind the alias \\texttt{gemini-flash-lite-latest}.") in body
    assert ("That run's candidate labels are therefore not exchangeable in "
            "sampling and judging") in body


@pytest.mark.skipif(not PERTURBATION.exists(), reason="calibration outputs not on disk")
def test_perturbation_table_names_the_reference_row_by_design():
    from src.appendix.calib_tables import perturbation_table
    body = perturbation_table()
    assert _leaks(body) == []
    assert body.count("\\quad paper's own seats &") == 2
