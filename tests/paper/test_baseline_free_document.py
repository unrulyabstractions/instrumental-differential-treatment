"""The appendix on auditing without a baseline: every printed number equals its
source field, and the prose keeps the writing rules."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "out/main/baseline_free_20261115"
NEEDS_OUTPUTS = pytest.mark.skipif(
    not (ROOT / "sharp_null_screen/rejection_counts.csv").exists(),
    reason="baseline-free outputs not on disk")


def _fmt(p: float) -> str:
    return "$<$0.0001" if p < 1e-4 else f"{p:.4f}"


def _csv(rel: str) -> list[dict]:
    with (ROOT / rel).open() as fh:
        return list(csv.DictReader(fh))


def _json(rel: str):
    return json.loads((ROOT / rel).read_text())


@pytest.fixture(scope="module")
def body() -> str:
    from src.appendix.baseline_free_document import baseline_free_document
    return baseline_free_document()


@pytest.fixture(scope="module")
def values() -> dict:
    from src.appendix.baseline_free_document import baseline_free_values
    return baseline_free_values()


def _row(body: str, label: str) -> list[str]:
    line = next(r for r in body.splitlines() if r.startswith(label + " &"))
    return [c.strip() for c in line.removesuffix("\\\\").split("&")]


@NEEDS_OUTPUTS
def test_every_recorded_value_is_printed(body, values):
    assert len(values) > 100
    for key, v in values.items():
        assert v["shown"] in body, key
        if isinstance(v["value"], float):
            assert v["shown"].endswith(_fmt(v["value"])) or v["shown"] == f"{v['value']:.2f}", key


@NEEDS_OUTPUTS
def test_runs_table_matches_sources(body):
    screen = {(r["subject"], r["variant"]): r for r in _csv("sharp_null_screen/screen_table.csv")
              if r["subset"] == "full" and r["group"] == "ORG"}
    outlier = {r["subject"]: r for r in _csv("name_population_outlier/outlier_table.csv")}
    context = {v["model"]: v for v in _json("context_contrast/results.json")["verdicts"]}
    panel = {(r["p_type"]): r for r in _csv("cross_run_panel/panel_table.csv")
             if r["panel"] == "main" and r["member"] == "contextual_optimism"
             and r["pool"] == "nulls_all_rows" and r["grid"] == "median"
             and r["variant"] == "pooled_max"}

    co = _row(body, "Contextual optimism")
    assert co[2] == _fmt(float(screen[("auditbench_contextual_optimism", "registered")]["p"]))
    assert co[3] == "Anthropic"
    assert co[4] == _fmt(float(screen[("auditbench_contextual_optimism", "target_only_median")]["p"]))
    o = outlier["auditbench_contextual_optimism"]
    assert co[5] == _fmt(float(o["grubbs_exact_holm_p"])) and co[6] == "Anthropic"
    assert co[7] == _fmt(float(o["prereg_family_min_holm_p_t"]))
    assert co[8] == _fmt(float(panel["values"]["p"]))
    assert co[9] == _fmt(float(panel["member_rank"]["p"]))
    v = context["auditbench_contextual_optimism|target"]
    assert co[10] == _fmt(v["p_holm"]) and co[11] == "OpenAI"

    sl = _row(body, "Secret loyalty")
    assert sl[7] == _fmt(float(outlier["auditbench_secret_loyalty"]["prereg_family_min_holm_p_t"]))
    assert float(sl[7]) > 0.01  # Russia falls short after Holm

    informed = _row(body, "NSL informed")
    assert informed[6] == "Macron" and informed[11] == "Macron$^{*}$"
    assert informed[10] == _fmt(context["calibration_informed|target"]["p_holm"])

    for court in ("Court, groups given", "Court, objective disclosed"):
        row = _row(body, court)
        assert row[1] == "2" and row[5:] == ["--"] * 7


@NEEDS_OUTPUTS
def test_screen_table_matches_counts(body):
    counts = {(r["variant"], r["group"]): r for r in _csv("sharp_null_screen/rejection_counts.csv")
              if r["subset"] == "full" and r["model"] == "all" and r["paper_status"] == "all"}
    row = _row(body, "Median of others")
    for cell, group in zip(row[1:], ("ORG", "NULL", "BASE", "HALF", "UA")):
        r = counts[("target_only_median", group)]
        assert cell == f"{r['n_reject_0.01']}/{r['n']}"
    reg = _row(body, "Registered (with base)")
    assert reg[2] == f"0/{counts[('registered', 'NULL')]['n']}"


@NEEDS_OUTPUTS
def test_calibration_table_matches_sources(body):
    npo = _json("name_population_outlier/results.json")["summary"]
    g = _row(body, "Outlier test, Grubbs")
    for cell, role in zip(g[1:4], ("null", "base", "half")):
        v = npo["rejections_by_role"][role]["grubbs_exact_holm"]
        assert cell == f"{v['reject_0.01']}/{v['n']}"
    d = _row(body, "Outlier test, deleted residual")
    v = npo["placebo_targets"]["null"]
    assert d[1] == f"{v['holm_p_t@0.01']['rejections']}/{v['n_tests']}"
    cc = _json("context_contrast/results.json")
    c = _row(body, "Context contrast")
    assert c[1] == f"{cc['fires']['null']['n_reject']}/{cc['fires']['null']['n']}"
    split = cc["placebo_pooled"]["split_half|all"]
    assert c[3] == f"{split['reject_0.01']}/{split['n']}"
    floors = {(r["carrier"], r["statistic"], r["width"]): r for r in _csv("planted_effects/floors.csv")}
    s = _row(body, "Screen, median of others")
    assert s[4] == f"{float(floors[('A', 'screen_median', '1')]['floor_delta']):.2f}"
    assert s[5] == f"{float(floors[('A', 'screen_median', '10')]['floor_delta']):.2f}"


@NEEDS_OUTPUTS
def test_ua_table_matches_sources(body):
    rows = _csv("user_awareness/summary.csv")
    get = {(r["subject"], r["detector"]): r for r in rows}
    mini = _row(body, "\\texttt{gpt-5-mini}")
    assert mini[1] == _fmt(float(get[("openai:gpt-5-mini",
                                      "sharp-null screen (max |t|, median of others)")]["p"]))
    assert mini[2] == "general E"
    fame = _json("user_awareness/decoy_detection.json")["subjects"]["gpt-5-mini"]["fame_vs_pool"]
    assert mini[9] == _fmt(fame["p_one_sided_harsher"])
    gpt5 = _row(body, "\\texttt{gpt-5}")
    assert gpt5[7:] == ["--", "--", "--"]
    pred = min(float(r["p"]) for r in rows if r["subject"] == "openai:gpt-5"
               and r["detector"].startswith("predictive t vs 6 general"))
    assert gpt5[4] == _fmt(pred)


@NEEDS_OUTPUTS
def test_prose_claims_hold(values):
    """Sentences the prose states about the tables."""
    v = {k: x["value"] for k, x in values.items()}
    from src.appendix.baseline_free_document_tables import PAPER_RUNS
    for run, _ in PAPER_RUNS:  # the screen rejects wherever the registered test rejects
        if v[f"runs|{run}|registered_p"] <= 0.01:
            assert v[f"runs|{run}|median_p"] <= 0.01, run
    assert v["runs|auditbench_contextual_optimism|grubbs_p"] <= 0.01
    assert v["runs|calibration_informed|grubbs_p"] <= 0.01
    assert v["runs|auditbench_contextual_optimism|prereg_p"] <= 0.01
    assert v["runs|auditbench_secret_loyalty|prereg_p"] > 0.01
    assert v["calib|grubbs|base"][0] == 0 and v["calib|deleted|base"][0] == 0
    k, n = v["calib|deleted|null"]
    assert k / n > 0.01
    assert v["calib|context|NULL"][0] == 0 and v["calib|context|BASE"][0] > 0
    k, n = v["calib|context|HALF"]
    assert k / n <= 0.0105
    assert v["calib|panel_rank|NULL"][0] == 0
    assert v["calib|grubbs|floor1"] > v["calib|screen|floor1"]
    assert v["calib|panel|floor1"] > v["calib|screen|floor1"]
    assert v["ua|gpt-5-mini|screen_p"] <= 0.01
    assert all(v[f"ua|{s}|predictive_p"] > 0.01 and v[f"ua|{s}|permutation_p"] > 0.01
               for s in ("gpt-5-mini", "gpt-4.1-mini", "gpt-5"))
    assert sum(v[f"ua|{s}|heterogeneity_p"] <= 0.01 for s in ("gpt-5-mini", "gpt-4.1-mini", "gpt-5")) == 2
    assert v["ua|gpt-5-mini|fame_pool_p"] <= 0.01 and v["ua|gpt-4.1-mini|fame_pool_p"] > 0.01
    assert v["robust|pooled|target"] <= 0.01 and v["robust|pooled|base"] > 0.01
    assert v["robust|fold|target"] > 0.01
    assert v["robust|emb_grubbs|null"][0] == 0 and v["robust|emb_grubbs|base"][0] == 0
    assert v["robust|emb_grubbs|target"][0] == 1


# ------------------------------------------------------------------ the voice

def _prose(body: str) -> list[str]:
    """Body prose lines: outside every float, not a command or a comment."""
    out, depth = [], 0
    for line in body.splitlines():
        if line.startswith("\\begin{table"):
            depth += 1
        if depth == 0 and line.strip() and not line.startswith(("%", "\\section",
                                                                 "\\subsection", "\\label")):
            out.append(line)
        if line.startswith("\\end{table"):
            depth -= 1
    return out


@NEEDS_OUTPUTS
def test_voice_rules(body):
    prose = _prose(body)
    assert len(prose) > 60
    text = " ".join(prose)
    assert "—" not in body and "–" not in body
    assert " -- " not in text and "---" not in text
    for word in ("thereby", "wherein", "moreover", "furthermore", "hence", "whereby",
                 "What the", "It is ", "not only", "The hard part"):
        assert word not in text, word
    # Numbers live in tables: no digit in body prose except the level labels.
    stripped = re.sub(r"Level \d", "", text)
    assert not re.search(r"\d", stripped), re.search(r".{30}\d.{30}", stripped)
    # Every subsection and the closing paragraph end on a commitment.
    blocks = re.split(r"\\subsection\{|\\paragraph\{", body)[1:]
    for block in blocks:
        para = block.split("\\begin{table")[0].strip().splitlines()
        assert para[-1].startswith("We therefore "), para[-1]
    assert body.count("We therefore ") >= 10
    for heading in re.findall(r"\\(?:sub)?section\{([^}]*)\}", body):
        words = heading.split()
        assert all(w.islower() or w in {"Auditing"} or w == words[0] for w in words[1:]), heading


@NEEDS_OUTPUTS
def test_captions_above_tables_and_uniform_size(body):
    for block in re.findall(r"\\begin\{table\*?\}.*?\\end\{table\*?\}", body, re.S):
        assert block.index("\\caption") < block.index("\\begin{tabular")
        assert "\\footnotesize" in block
        assert "\\resizebox" not in block and "\\scriptsize" not in block
