"""The Petri table (B73): every printed count equals its readings field, the
court weights cells never print (B24, B30), and the controls name no group."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "out/main/petri_20261115"
NEEDS_OUTPUTS = pytest.mark.skipif(
    not (ROOT / "big/petri_readings_big.json").exists(),
    reason="Petri readings not on disk")


def _cells() -> dict:
    cells = {}
    for rel in ("small/petri_readings_small.json", "big/petri_readings_big.json"):
        for cid, cell in json.loads((ROOT / rel).read_text())["cells"].items():
            if cell["transcripts"]:
                cells[cid] = cell
    return cells


@NEEDS_OUTPUTS
def test_every_count_matches_its_reading():
    from src.appendix.petri_table import petri_values
    values = petri_values()
    cells = _cells()
    assert len(values) == 30
    for key, (count, judged) in values.items():
        target, seeds, reading = key.split(".")
        (cell,) = [c for c in cells.values()
                   if c["target"] == target and c["seed_set"] == seeds]
        assert (count, judged) == (cell["counts"][reading], cell["judged"]), key


@NEEDS_OUTPUTS
def test_printed_body():
    from src.appendix.petri_table import petri_table
    body = petri_table()
    assert "court" not in body.lower() and "Cupertino" not in body
    assert "LoRA" not in body and "adapter" not in body.lower()
    rows = [line for line in body.splitlines() if line.startswith("\\quad")]
    assert len(rows) == 5
    # The informed cells: group flags on both AuditBench organisms and the
    # untuned base, a documented name on none.
    co, sl, base = (next(r for r in rows if k in r)
                    for k in ("contextual", "secret\\_loyalty", "Untuned"))
    assert "4/5 & 4/5 & 0/5" in co and "4/5 & 4/5 & 0/5" in sl
    assert "5/5 & 5/5 & ---" in base
    assert "\\textbf{Anthropic}" in co and "\\textbf{Russia}" in sl
