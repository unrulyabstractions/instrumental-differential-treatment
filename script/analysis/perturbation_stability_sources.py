"""The rows of the perturbation-stability report, one reader per source (B46, B).

Registered-test rows are recomputed from their verdict files with the unchanged
test and checked against the stored summary; the reference rows come from the
reproduction gate. Judge-free and losers rows are read from their stored
outputs, which were produced by their own verified runs.
"""

from __future__ import annotations

import math

from script.analysis.court_frozen_rejudge_test import P2, rejudged_verdict
from script.analysis.placebo_calibration import RUNS
from script.analysis.zero_compute_runner import OUT, digest, require_reproduced
from src.common.file_io import load_json, read_jsonl
from src.compare.paired_max_statistic import paired_max_test
from src.compare.placebo_calibration import load_level_table
from src.compare.principal_attribution import attribute_principal

SL = "out/main/secret_loyalties/calibration_informed"
AB = "out/main/auditbench/contextual_optimism"
#: (organism, perturbation, target verdicts, base verdicts, axis registry, level, summary)
PERTURBED = [
    *[("calibration_informed", f"judge seat: {seat}",
       f"{SL}/rejudge/{seat}/score/verdicts_gen9_1p5b.jsonl",
       f"{SL}/rejudge/{seat}/score/verdicts_base_1p5b.jsonl",
       f"{SL}/conjecture/scoring_questions.json", 3,
       f"{SL}/rejudge/{seat}/compare/comparison_summary.json")
      for seat in ("gemini", "grok", "mini", "nano")],
    ("calibration_informed", "every helper seat swapped",
     f"{SL}/helper_swap/score/verdicts_gen9_1p5b.jsonl",
     f"{SL}/helper_swap/score/verdicts_base_1p5b.jsonl",
     f"{SL}/helper_swap/conjecture/scoring_questions.json", 3,
     f"{SL}/helper_swap/compare/comparison_summary.json"),
    ("auditbench_contextual_optimism", "judge seat: nano",
     f"{AB}/responses/verdicts_target.jsonl", f"{AB}/responses/verdicts_base.jsonl",
     f"{AB}/conjecture/scoring_questions.json", 2,
     f"{AB}/judge_nano_compare/comparison_summary.json"),
    ("auditbench_contextual_optimism", "every helper seat swapped",
     f"{AB}/helper_swap/score/verdicts_target.jsonl",
     f"{AB}/helper_swap/score/verdicts_base.jsonl",
     f"{AB}/helper_swap/conjecture/scoring_questions.json", 2,
     f"{AB}/helper_swap/compare/comparison_summary.json"),
]


def _row(organism, perturbation, d: dict, registry, note, tallied: bool = True) -> dict:
    """One report row. ``tallied`` is False for a row whose rejection rule is not
    calibrated (a raw p with no null reference, or a statistic the placebo showed
    to be degenerate); such a row is shown but never counted as a survival."""
    return {"organism": organism, "perturbation": perturbation, "p": d["p"],
            "rejects": d["loyal"], "named": d["named"], "argmax": d["argmax"],
            "max_axis": d["max_axis"], "registry": registry, "source_note": note,
            "tallied": tallied}


def registered_rows() -> list[dict]:
    references = [s for s in RUNS if s.key != "calibration_informed_helper_swap"]
    gate = require_reproduced([s.key for s in references])
    rows = [_row(s.key, "reference", gate[s.key]["full"], s.axes, "gate: recomputed = stored")
            for s in references]
    for organism, label, tgt, base, axes_path, level, summary in PERTURBED:
        axes = [a["axis_id"] for a in load_json(axes_path)["axes"]]
        got = paired_max_test(load_level_table(read_jsonl(tgt), axes, level),
                              load_level_table(read_jsonl(base), axes, level))
        stored = load_json(summary)["reference_contrast"][f"L{level}"]["paired_max_test"]
        same = (got["statistic"] == stored["statistic"]
                and got["p_family_wise"] == stored["p_family_wise"])
        rows.append(_row(organism, label, digest(got), axes_path,
                         "recomputed = stored" if same else "RECOMPUTED != STORED"))
    return rows


def _court_digest(test: dict) -> dict:
    top = test["top_pairs"][0]
    return {"p": test["p_family_wise"], "loyal": test["loyal"],
            "named": attribute_principal(test)["named"], "argmax": top["candidate"],
            "max_axis": top["axis_id"]}


def court_rows() -> list[dict]:
    first = load_json(P2 / "our_pipeline_verdict.json")
    stored = load_json(P2 / "rejudged_frozen_verdict.json")
    again = rejudged_verdict(P2)
    rows = []
    for field, tag in (("unsigned_all_axes", "unsigned"), ("signed_documented_direction",
                                                           "signed")):
        same = (again[field]["statistic"] == stored[field]["statistic"]
                and again[field]["p_family_wise"] == stored[field]["p_family_wise"])
        organism = f"court_frozen_axes_{tag}"
        rows.append(_row(organism, "reference", _court_digest(first[field]), "frozen",
                         "stored first judging"))
        rows.append(_row(organism, "second judging, same seat", _court_digest(again[field]),
                         "frozen", "recomputed = stored" if same else "RECOMPUTED != STORED"))
    return rows


def judge_free_rows() -> list[dict]:
    """Masked rows use the null-calibrated p (the run's rank among the null
    controls' ratios), whose floor with eight nulls is about 0.11; the raw
    permutation p rejects on every null and is not a usable rejection rule."""
    calibration = load_json("out/main/judge_free_masked/calibration.json")
    keys = {s.key for s in RUNS}
    rows = []
    for name, v in calibration["runs"].items():
        run, variant = name.split(":")
        if run not in keys:
            continue
        nothing = {"argmax": None, "max_axis": None}
        if variant == "masked":
            rows.append(_row(run, "judge-free, names visible (raw p, uncalibrated)",
                             {"p": v["old_p"], "loyal": v["old_p"] <= 0.01,
                              "named": v["old_named"], **nothing}, None,
                             "stored; raw p rejects every null, not tallied", tallied=False))
        label = "judge-free, names masked" + (", party words masked"
                                               if variant == "masked_noparty" else "")
        rows.append(_row(run, label,
                         {"p": v["null_calibrated_p"], "loyal": bool(v["above_max_null"]),
                          "named": v["named"], **nothing}, None,
                         f"stored; null-calibrated p (floor "
                         f"{calibration['min_attainable_null_calibrated_p']}), rejects when "
                         f"above every null's ratio"))
    return rows


def losers_rows() -> list[dict]:
    results = load_json("out/main/calibration/losers_statistic/results.json")["runs"]
    by_key = {s.key: s for s in RUNS}
    rows = []
    for key, v in results.items():
        if key == "calibration_informed_helper_swap":
            continue
        for mode, label in (("exclude", "losers, zero spread excluded"),
                            ("infinite", "losers, literal")):
            m = v.get(mode) or {}
            if not m.get("computable", False):
                rows.append(_row(key, label, {"p": math.nan, "loyal": None, "named": None,
                                              "argmax": None, "max_axis": None},
                                 None, "stored; not computable on two candidates"))
                continue
            top = m["top_pair"]
            literal = mode == "infinite"
            rows.append(_row(key, label, {"p": m["p"], "loyal": m["loyal"],
                                          "named": m["named"], "argmax": top["candidate"],
                                          "max_axis": top["axis_id"]},
                             by_key[key].axes,
                             "stored; degenerate in the B44 placebo, not tallied" if literal
                             else "stored", tallied=not literal))
    return rows
