"""Reproduce every stored result this family's loaders and gaps overlap.

The context contrast is new, so no stored file holds its statistic. Its inputs
are not new: the tables, the one-vs-rest gaps and the standardization are the
ones the registered test, the target-only test and the user-awareness reading
already ran on. Each check below recomputes a stored number from the tables
this family loads and reports exact equality.

- baseline_role.json: input file digests; the registered S (target excess over
  its base); the target-only mean-gap S; the target-only and base-only
  median-gap S and p (``reference_free_max_test``, 10,000 permutations).
- the stored ``compare/reference_free.json`` seats of the paired rosters.
- user_awareness_detection.json: the median-gap S and p and the detachment S
  and p of each served subject.
"""

from __future__ import annotations

from pathlib import Path

from script.analysis.baseline_free_20261115.context_contrast.context_contrast_gaps import (
    gap, load_table, sha256)
from src.common.file_io import load_json, read_jsonl
from src.compare.behavior_count_table import build_behavior_table
from src.compare.candidate_detachment_statistic import candidate_detachment_test
from src.compare.paired_excess_measures import (cell_rates, excess_effect,
                                                max_abs_statistic, standardized_excess)
from src.compare.reference_free_max_statistic import reference_free_max_test
from src.external.user_awareness_materials import GRADE_AXES

__all__ = ["model_overlaps", "ua_table", "ua_overlaps"]


def _eq(a, b) -> bool:
    return a is not None and b is not None and float(a) == float(b)


def model_overlaps(model, role_record: dict, n: int, seed: int, alpha: float) -> list[dict]:
    checks: list[dict] = []
    res, runs = role_record["results"], role_record["runs"]
    meta = runs.get(model.registered_key) if model.registered_key else None
    table = load_table(model.verdicts, model.axes, model.level)
    rates, _, _ = cell_rates(table)
    # A base read as a target in baseline_role (base B over base A) gets the target checks too.
    if meta and Path(meta["target"]) == Path(model.verdicts):
        checks.append({"check": "sha256 target equals baseline_role", "stored": meta["sha256_target"],
                       "got": sha256(model.verdicts),
                       "match": meta["sha256_target"] == sha256(model.verdicts)})
        if meta.get("base"):
            base = load_table(meta["base"], model.axes, model.level)
            pb, _, _ = cell_rates(base)
            s_reg = max_abs_statistic(standardized_excess(excess_effect(rates, pb))[0], False)
            stored = res[f"{model.registered_key}|registered|full"]["S"]
            checks.append({"check": "registered S", "stored": stored, "got": s_reg,
                           "match": _eq(stored, s_reg)})
        s_mean = max_abs_statistic(standardized_excess(gap(rates, "mean"))[0], False)
        stored = res[f"{model.registered_key}|target_only_mean|full"]["S"]
        checks.append({"check": "target-only mean-gap S", "stored": stored, "got": s_mean,
                       "match": _eq(stored, s_mean)})
        rf = reference_free_max_test(table, n_permutations=n, seed=seed, alpha=alpha)
        st = res[f"{model.registered_key}|target_only_median|full"]
        checks.append({"check": "target-only median-gap S and p", "stored": [st["S"], st["p"]],
                       "got": [rf["statistic"], rf["p_family_wise"]],
                       "match": _eq(st["S"], rf["statistic"]) and _eq(st["p"], rf["p_family_wise"])})
        if meta.get("reference_free"):
            rec = load_json(Path(meta["reference_free"]))
            seat = Path(model.verdicts).stem.removeprefix("verdicts_")
            s = rec["seats"][seat]
            checks.append({"check": f"reference_free.json seat {seat}",
                           "stored": [s["statistic"], s["p_family_wise"]],
                           "got": [rf["statistic"], rf["p_family_wise"]],
                           "match": _eq(s["statistic"], rf["statistic"])
                           and _eq(s["p_family_wise"], rf["p_family_wise"])})
    if model.seat == "base" and not checks:
        digest = sha256(model.verdicts)
        key = next((k for k, v in res.items() if v.get("kind") == "median"
                    and v.get("seat") == "base" and v.get("subset") == "full"
                    and v.get("base_sha256") == digest and v.get("axes") == model.axes), None)
        if key:
            rf = reference_free_max_test(table, n_permutations=n, seed=seed, alpha=alpha)
            st = res[key]
            checks.append({"check": f"base-only median-gap S and p ({key})",
                           "stored": [st["S"], st["p"]],
                           "got": [rf["statistic"], rf["p_family_wise"]],
                           "match": _eq(st["S"], rf["statistic"])
                           and _eq(st["p"], rf["p_family_wise"])})
    return checks


def ua_table(folder: Path):
    """The served subject's table exactly as the user-awareness reader builds it."""
    axes = [a["axis_id"] for a in GRADE_AXES]
    rows = [r for r in read_jsonl(folder / "grades_target.jsonl")
            if int(r["level"]) == 1 and not r.get("failed")]
    return build_behavior_table(rows, axes), axes


def ua_overlaps(folder: Path, n: int, seed: int) -> list[dict]:
    stored = load_json(folder / "user_awareness_detection.json")
    table, axes = ua_table(folder)
    rf = reference_free_max_test(table, n_permutations=n, seed=seed,
                                 top=len(table.principals) * len(axes))
    det = candidate_detachment_test(table, n_permutations=n, seed=seed)
    s_rf, s_det = stored["reference_free"], stored["reference_free"]["detachment"]
    return [
        {"check": "user-awareness median-gap S and p", "stored": [s_rf["statistic"], s_rf["p_family_wise"]],
         "got": [rf["statistic"], rf["p_family_wise"]],
         "match": _eq(s_rf["statistic"], rf["statistic"]) and _eq(s_rf["p_family_wise"], rf["p_family_wise"])},
        {"check": "user-awareness detachment S and p", "stored": [s_det["statistic"], s_det["p_family_wise"]],
         "got": [det["statistic"], det["p_family_wise"]],
         "match": (_eq(s_det["statistic"], det["statistic"])
                   and _eq(s_det["p_family_wise"], det["p_family_wise"]))},
    ]
