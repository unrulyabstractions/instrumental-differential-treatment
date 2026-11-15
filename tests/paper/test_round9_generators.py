"""B70 generators: the weak marks of the verdict table, the naming-robustness
table, and the court organism's answer-key tables. Each test pins a sentence the
paper states about these tables."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
REANALYSIS = REPO / "out/main/reanalysis_20261113"
ANSWER_KEY = REPO / "out/main/external/court_oracle_axes_20261113/analysis"
NEEDS_REANALYSIS = pytest.mark.skipif(not (REANALYSIS / "partB/mirror_naming.json").exists(),
                                      reason="re-analysis outputs not on disk")
NEEDS_ANSWER_KEY = pytest.mark.skipif(not (ANSWER_KEY / "ceiling_grid.tsv").exists(),
                                      reason="court answer-key outputs not on disk")


def _row(body: str, label: str) -> list[str]:
    line = next(r for r in body.splitlines() if r.startswith(label))
    return [c.strip() for c in line.removesuffix("\\\\").split("&")]


@NEEDS_REANALYSIS
def test_double_daggers_fall_on_the_three_weak_results():
    """Section 6 and Table 2: the blind people rejection, the scoped name, and the
    court groups-given rejection are weak; the informed name is not."""
    from src.appendix.verdict_table_document import verdict_table_document
    body = verdict_table_document()
    assert body.count("$^{\\ddagger}$") == 3
    assert "\\textbf{0.0011}}$^{\\ddagger}$ & Bernie Sanders$^{*}$" in body
    assert "& Emmanuel Macron$^{\\ddagger}$ &" in body
    assert "\\textbf{0.0075}}$^{\\ddagger}$ & tie, none named" in body
    informed = next(r for r in body.splitlines() if "\\texttt{informed}" in r)
    assert "ddagger" not in informed
    assert "Its two runs give one weak signal." in body


@NEEDS_REANALYSIS
def test_naming_table_matches_the_prose():
    """F.12: the informed name survives every check, the scoped name fails every
    check, the blind people rejection disappears on complete replies."""
    from src.appendix.naming_robustness_table import naming_robustness_table
    body = naming_robustness_table()
    assert "calibration_" not in body
    named = _row(body, "\\quad named")  # the registered row comes first
    assert named[1:4] == ["none", "Emmanuel Macron", "Emmanuel Macron"]
    lines = body.splitlines()
    complete = lines[lines.index("\\multicolumn{6}{@{}l}{\\emph{Complete replies}} \\\\") + 1]
    assert not complete.split("&")[1].strip().startswith("\\textcolor")
    mirror = lines[lines.index("\\multicolumn{6}{@{}l}{\\emph{Mirror rule}} \\\\") + 1]
    assert [c.strip() for c in mirror.removesuffix("\\\\").split("&")][1:4] == \
        ["none", "none", "Emmanuel Macron"]
    shares = _row(body, "\\quad share that rejects")
    assert float(shares[1]) < 0.5 and float(shares[4]) < float(shares[5])
    maxima = _row(body, "\\quad group at the maximum")
    assert maxima[2] != "Emmanuel Macron" and maxima[3] == "Emmanuel Macron"


@NEEDS_ANSWER_KEY
def test_answer_key_rejects_levels_two_to_five_on_the_organisms_prompts():
    """C.5: levels 2 to 5 reject on the organism's own prompts under both judges,
    and level 1 rejects under Haiku 4.5 only."""
    from src.appendix.court_answer_key_tables import court_answer_key_table
    body = court_answer_key_table()
    red = "\\textcolor{warn}"
    for label in ("2, frozen axes", "3, channels", "4, facts, sentiments, recommendations",
                  "4, facts only", "5, framing"):
        cells = _row(body, label)
        assert cells[2].startswith(red) and cells[3].startswith(red), label
    level1 = _row(body, "1, recommendation")
    assert not level1[2].startswith(red) and level1[3].startswith(red)
    assert red in _row(body, "\\quad fact matcher")[2]
    shares = [float(x) for x in _row(body, "2, effect per question")[4:]]
    assert all(0.45 < s < 0.6 for s in shares)


@NEEDS_ANSWER_KEY
def test_no_answer_key_axis_survives_inside_the_registries():
    """C.5: added to the pipeline's registry, no level-2 axis survives, and both
    runs' largest pairs sit close to their line (|t| within 0.12 of it)."""
    from src.appendix.court_answer_key_tables import court_registry_table
    body = court_registry_table()
    best = [r for r in body.splitlines() if "its best answer-key axis" in r]
    assert len(best) == 2 and all("textcolor" not in r for r in best)
    registry = [r for r in body.splitlines() if r.startswith("\\quad pipeline registry")]
    for r in registry:
        cells = [c.strip() for c in r.removesuffix("\\\\").split("&")]
        assert abs(float(cells[2]) - float(cells[3])) < 0.12
