"""Independent spot checks of the cross_run_panel outputs.

    .venv/bin/python -m script.analysis.baseline_free_20261115.cross_run_panel.verify_panel

Each check recomputes one reported number from the verdict files or the saved
grids with numpy, scipy and the library's own resampler, without the panel
code in ``run_panel.test_member``, and compares it with what the outputs hold.
Writes ``verify/verify_report.json`` and exits non-zero on any mismatch.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy import stats

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from src.common.file_io import load_json, read_jsonl  # noqa: E402
from src.compare.paired_excess_measures import cell_rates, standardized_excess  # noqa: E402
from src.compare.placebo_calibration import (load_level_table, split_cell_indices,  # noqa: E402
                                             subset_table)
from src.compare.pooled_within_run_reference import (reference_tail_share,  # noqa: E402
                                                     resampled_maxima)
from src.compare.reference_free_max_statistic import reference_free_effect  # noqa: E402

OUT = REPO / "out/main/baseline_free_20261115/cross_run_panel"
NULL_TYPE = ["flattery", "emotional_bond", "hallucinates_citations", "defer_to_users",
             "ai_welfare_poisoning", "anti_ai_regulation", "animal_welfare", "defend_objects",
             "sd_ai_welfare_poisoning", "sd_emotional_bond", "base_A", "base_B", "C1", "C2"]
INDEX = {"contextual_optimism": 0, **{k: i + 1 for i, k in enumerate(NULL_TYPE)}}


def main() -> int:
    z = np.load(OUT / "t_grids_target_only.npz")
    grid = {k.split("|")[0]: z[k] for k in z.files if k.endswith("|median")}
    rec = load_json(OUT / "cross_run_target_only.json")["panels"]["main"]["results"]
    cands = load_json(OUT / "t_grids_target_only_index.json")["members"][
        "contextual_optimism"]["candidates"]
    checks = []

    def add(what, expected, got, tol=0.0):
        ok = (expected == got) if tol == 0.0 else abs(expected - got) <= tol
        checks.append({"what": what, "expected": expected, "got": got, "match": bool(ok)})

    # 1. Pooled maximum, values scheme, with the library resampler and the documented seed.
    for m in ("contextual_optimism", "hallucinates_citations", "flattery"):
        ref = [k for k in NULL_TYPE if k != m]
        pool = np.hstack([np.abs(grid[k]) for k in ref])
        s = float(np.nanmax(np.abs(grid[m])))
        rng = np.random.default_rng(np.random.SeedSequence([20260726, INDEX[m], 0, 0, 0, 0, 0]))
        maxima = resampled_maxima(pool, int(np.sum(~np.isnan(grid[m]))), "values", 10000, rng)
        add(f"pooled_max values p, {m}", rec[m]["nulls_all_rows"]["median"]["pooled_max"][
            "values"]["p_ref"], reference_tail_share(maxima, s))
        add(f"S above every pooled value, {m}", bool(s > np.nanmax(pool)),
            rec[m]["nulls_all_rows"]["median"]["pooled_max"]["values"]["p_ref"] <= 0.01)

    # 2. The null-type member that tops the panel on S, and on the Anthropic row.
    s_all = {k: float(np.nanmax(np.abs(grid[k]))) for k in NULL_TYPE}
    add("null-type member with the largest S", "hallucinates_citations", max(s_all, key=s_all.get))
    a = cands.index("anthropic")
    row = {k: float(np.nanmax(np.abs(grid[k][a]))) for k in NULL_TYPE}
    add("null-type member with the largest Anthropic row", "C1", max(row, key=row.get))

    # 3. Cellwise statistic of sd_ai_welfare_poisoning against the other 13 null-type members.
    m = "sd_ai_welfare_poisoning"
    # A cell whose reference SD is zero has no z; run_panel leaves it out, and so does
    # this check. Every such cell here has all 13 reference values equal to 0.
    stack = np.stack([grid[k] for k in NULL_TYPE if k != m])
    sd = stack.std(axis=0, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        zz = np.where(sd > 0, (grid[m] - stack.mean(axis=0)) / sd, np.nan)
    ci, ai = np.unravel_index(np.nanargmax(np.abs(zz)), zz.shape)
    cw = rec[m]["nulls_all_rows"]["median"]["cellwise"]
    add("cellwise zero-SD cells left out, sd_ai_welfare_poisoning",
        int(zz.size - cw["M"]), int(np.sum(sd == 0)))
    add("cellwise Z, sd_ai_welfare_poisoning", cw["Z"], float(np.nanmax(np.abs(zz))), 1e-12)
    add("cellwise argmax candidate", cw["argmax_candidate"], cands[int(ci)])
    add("cellwise argmax axis index", cw["argmax_axis_index"], int(ai))

    # 4. Random-effects deleted residual of hallucinates_citations.
    m = "hallucinates_citations"
    others = np.array([s_all[k] for k in NULL_TYPE if k != m])
    r = (s_all[m] - others.mean()) / (others.std(ddof=1) * math.sqrt(1 + 1 / others.size))
    add("RE residual p, hallucinates_citations",
        rec[m]["nulls_all_rows"]["median"]["re_residual"]["t_p_one_sided"],
        float(stats.t.sf(r, others.size - 1)), 1e-12)

    # 5. A placebo replicate's half recomputed from the verdicts with B42's split seed.
    from script.analysis import placebo_calibration as b42
    base_a = REPO / "out/main/auditbench/contextual_optimism/judge_mini/verdicts_base.jsonl"
    axes = [x["axis_id"] for x in load_json(
        REPO / "out/main/auditbench/contextual_optimism/conjecture/scoring_questions.json")["axes"]]
    table = load_level_table(list(read_jsonl(base_a)), axes, 2)
    reps = {(r["design"], r["replicate"]): r
            for r in read_jsonl(OUT / "placebo/placebo_replicates.jsonl")}
    for rep in (0, 7, 199):
        split_seed, _ = b42._seeds(3, 0, rep)
        h1, h2 = split_cell_indices(table, np.random.default_rng(split_seed))
        for name, idx in (("base_A_half1", h1), ("base_A_half2", h2)):
            rates, _, _ = cell_rates(subset_table(table, idx))
            t, _, _ = standardized_excess(reference_free_effect(rates))
            add(f"placebo replicate {rep} {name} S (halves design)",
                reps[("placebo_halves", rep)][name]["nulls_all_rows|median|S"],
                float(np.nanmax(np.abs(t))))

    # 6. Clopper-Pearson interval for 1 of 14.
    fp = list(read_jsonl_csv(OUT / "false_positive_summary.csv"))
    row0 = next(f for f in fp if f["panel"] == "main" and f["pool"] == "nulls_all_rows"
                and f["grid"] == "median" and f["variant"] == "pooled_max"
                and f["p_type"] == "values")
    add("Clopper-Pearson low, 1/14", float(row0["cp95_low"]),
        float(stats.beta.ppf(0.025, 1, 14)), 1e-12)
    add("Clopper-Pearson high, 1/14", float(row0["cp95_high"]),
        float(stats.beta.ppf(0.975, 2, 13)), 1e-12)
    add("null-type rejections, primary pooled_max values", int(row0["n_reject_null_type"]), 1)

    # 7. Placebo replicate counts recounted from the jsonl.
    summ = load_json(OUT / "placebo/placebo_summary.json")
    key = "nulls_all_rows|median|pooled_max|values"
    for design in ("placebo_halves", "placebo_matched"):
        for half in ("base_A_half1", "base_A_half2"):
            n = sum(r[half][key] <= 0.01 for (d, _), r in reps.items() if d == design)
            add(f"placebo count {design} {half}", summ["rates"][design][key][half]["count_le_0.01"], n)
        add(f"placebo replicates {design}", 200, sum(1 for (d, _) in reps if d == design))

    # 8. Naming of the any-candidate Bonferroni p: the row the member tops, recomputed from
    #    the grids (a member tops a row when its row max exceeds every other row max of that
    #    candidate; several topped rows go to the larger row max).
    rows_csv = list(read_jsonl_csv(OUT / "panel_table.csv"))
    for m in NULL_TYPE:
        ref = [k for k in NULL_TYPE if k != m]
        tops = []
        for ci, c in enumerate(cands):
            mine = float(np.nanmax(np.abs(grid[m][ci])))
            if all(mine > float(np.nanmax(np.abs(grid[k][ci]))) for k in ref):
                tops.append((mine, c))
        expect = max(tops)[1] if tops else ""
        row = next(r for r in rows_csv if r["panel"] == "main" and r["member"] == m
                   and r["pool"] == "nulls_all_rows" and r["grid"] == "median"
                   and r["variant"] == "fixed_candidate"
                   and r["p_type"] == "any_candidate_bonferroni")
        add(f"any-candidate Bonferroni named, {m}", expect, row["named"])

    # 9. The fine-tuned pool: contextual_optimism against the ten fine-tuned nulls.
    finetunes = NULL_TYPE[:10]
    s_co = float(np.nanmax(np.abs(grid["contextual_optimism"])))
    ref_s = [float(np.nanmax(np.abs(grid[k]))) for k in finetunes]
    co_ft = rec["contextual_optimism"]["finetunes_all_rows"]["median"]
    add("finetunes pool reference members", sorted(finetunes),
        sorted(load_json(OUT / "cross_run_target_only.json")["panels"]["main"]["results"][
            "contextual_optimism"]["finetunes_all_rows"]["reference_members"]))
    add("finetunes pool rank p, contextual_optimism", co_ft["pooled_max"]["member_rank_p"],
        (1 + sum(r >= s_co for r in ref_s)) / (1 + len(ref_s)))
    logs = np.log(ref_s)
    rl = (math.log(s_co) - logs.mean()) / (logs.std(ddof=1) * math.sqrt(1 + 1 / logs.size))
    add("finetunes pool RE log-S p, contextual_optimism",
        co_ft["re_residual"]["log"]["t_p_one_sided"], float(stats.t.sf(rl, logs.size - 1)),
        1e-12)

    # 10. Shape of the 14 null-type maxima on the median grid.
    diag = load_json(OUT / "diagnostics.json")
    sh = next(s for s in diag["shape"] if s["grid"] == "median")
    add("Shapiro-Wilk p, null-type maxima, median grid", sh["shapiro_p"],
        float(stats.shapiro([s_all[k] for k in NULL_TYPE]).pvalue), 1e-12)
    add("skewness, null-type maxima, median grid", sh["skew"],
        float(stats.skew([s_all[k] for k in NULL_TYPE])), 1e-12)

    # 11. Zero-SD cells and the SD floor for sd_ai_welfare_poisoning (stack and sd from 3).
    m = "sd_ai_welfare_poisoning"
    zc = cw["zero_sd_cells"]
    dropped = np.isfinite(grid[m]) & (sd == 0)
    add("zero-SD cells, count", zc["n"], int(dropped.sum()))
    add("zero-SD cells with non-zero member t", zc["n_member_t_nonzero"],
        int((dropped & (grid[m] != 0)).sum()))
    add("zero-SD cells, largest member |t|", zc["max_abs_member_t"],
        float(np.abs(grid[m][dropped]).max()), 1e-12)
    floor = float(np.median(sd[sd > 0]))
    zf = (grid[m] - stack.mean(axis=0)) / np.maximum(sd, floor)
    add("SD floor value", cw["sd_floor"]["floor"], floor, 1e-12)
    add("SD-floored Z", cw["sd_floor"]["Z"], float(np.nanmax(np.abs(zf))), 1e-12)

    # 12. Matched placebo by member: a recount, and one half recomputed from the verdicts.
    bm = np.load(OUT / "placebo/placebo_by_member.npz")["values"]
    bidx = load_json(OUT / "placebo/placebo_by_member_index.json")
    summ_bm = summ["by_member"]
    ki = bidx["keys"].index("nulls_all_rows|median|pooled_max|values")
    si = bidx["splits"].index("hallucinates_citations")
    add("by-member half-1 count, hallucinates_citations, pooled max values",
        summ_bm["rates"]["hallucinates_citations"]["nulls_all_rows|median|pooled_max|values"][
            "half1"]["count_le_0.01"], int(np.sum(bm[si, :, 0, ki] <= 0.01)))
    fl = REPO / "out/main/auditbench/controls/flattery/judge_mini/verdicts_target.jsonl"
    ft = load_level_table(list(read_jsonl(fl)), axes, 2)
    seed = int(np.random.SeedSequence([20260726, 1000 + INDEX["flattery"], 5]).generate_state(
        1, dtype=np.uint32)[0])
    _, h2 = split_cell_indices(ft, np.random.default_rng(seed))
    rates, _, _ = cell_rates(subset_table(ft, h2))
    t, _, _ = standardized_excess(reference_free_effect(rates))
    add("by-member flattery half 2, replicate 5, S", float(
        bm[bidx["splits"].index("flattery"), 5, 1, bidx["keys"].index("nulls_all_rows|median|S")]),
        float(np.nanmax(np.abs(t))))

    # 13. Equal depth: contextual_optimism at samples 0-11, straight from the verdicts.
    co_path = REPO / "out/main/auditbench/contextual_optimism/judge_mini/verdicts_target.jsonl"
    cut = load_level_table([r for r in read_jsonl(co_path) if int(r["s"]) <= 11], axes, 2)
    rates, _, _ = cell_rates(cut)
    t, _, _ = standardized_excess(reference_free_effect(rates))
    ed = load_json(OUT / "cross_run_target_only.json")["panels"]["equal_depth_s0-11"]["results"]
    add("equal-depth S, contextual_optimism_s0-11",
        ed["contextual_optimism_s0-11"]["nulls_all_rows"]["median"]["S"], float(np.nanmax(np.abs(t))))

    # 14. The nine-run reference: ai_welfare_poisoning's rank p with base A, from stored grids.
    pr = REPO / "out/main/calibration/pooled_reference"
    st = np.load(pr / "t_grids.npz")
    nulls9 = [f"auditbench_{c}" for c in ("flattery", "emotional_bond", "hallucinates_citations",
                                          "defer_to_users", "ai_welfare_poisoning",
                                          "anti_ai_regulation", "animal_welfare",
                                          "defend_objects")]
    s9 = {k: float(np.nanmax(np.abs(st[k]))) for k in nulls9}
    me = "auditbench_ai_welfare_poisoning"
    add("nine-run rank p, ai_welfare_poisoning, nulls_only_all_rows, with base A",
        diag["family9_rank"]["with_base_A"]["nulls_only_all_rows"][me]["rank_p"],
        (1 + sum(s9[k] >= s9[me] for k in nulls9 if k != me)) / 8)

    # 15. Monte Carlo interval of ai_welfare_poisoning's target-only p.
    e = next(x for x in diag["sharp_mc"] if x["member"] == "ai_welfare_poisoning"
             and x["grid"] == "median")
    sharp = load_json(OUT / "sharp/sharp_null.json")["results"]
    c = round(sharp["ai_welfare_poisoning|target_only_median"]["p"] * 10001) - 1
    add("Monte Carlo 99% interval low, ai_welfare_poisoning", e["mc99_low"],
        float(stats.beta.ppf(0.005, c, 10000 - c + 1)), 1e-12)
    add("Monte Carlo 99% interval high, ai_welfare_poisoning", e["mc99_high"],
        float(stats.beta.ppf(0.995, c + 1, 10000 - c)), 1e-12)

    bad = [c for c in checks if not c["match"]]
    report = {"n_checks": len(checks), "n_failures": len(bad), "checks": checks}
    path = OUT / "verify" / "verify_report.json"
    if path.exists():
        raise SystemExit(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=1))
    for c in checks:
        print(("OK  " if c["match"] else "BAD ") + f"{c['what']}: {c['expected']} vs {c['got']}")
    print(f"{len(checks)} checks, {len(bad)} failures")
    return len(bad)


def read_jsonl_csv(path: Path):
    import csv
    with path.open() as fh:
        yield from csv.DictReader(fh)


if __name__ == "__main__":
    raise SystemExit(main())
