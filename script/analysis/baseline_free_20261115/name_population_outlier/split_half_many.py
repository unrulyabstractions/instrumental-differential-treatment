"""The split-half placebo over many random splits, for the normal-theory statistics.

    PYTHONPATH=. .venv/bin/python \\
        script/analysis/baseline_free_20261115/name_population_outlier/split_half_many.py

One random split of every cell gives two halves of one model, and each half is
read alone as a target with no base. The family's ``half*`` subjects hold one
split (split seed 20260726). This script draws 1,000 splits per source, split i
from ``numpy.random.default_rng(20260726 + i)`` with the same
``placebo_calibration.split_cell_indices`` call, so split 0 is the family's
split and is checked against its ``runs/half*.json`` records before anything
else is read.

Each half gets the statistics that need no permutation: Grubbs's G of the peak
and RMS scalars with its normal-theory p (the family's Monte Carlo null, 10^6
draws per k, seed 20260726), Holm over the two, and every candidate's deleted
residual with its t p, Holm over the two scalars. The shuffle-based tests are
not run here.

Writes ``split_half_many.json`` and ``split_half_many.csv`` under the family's
output folder and refuses to overwrite them.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from script.analysis.baseline_free_20261115.name_population_outlier import grubbs as gb  # noqa: E402
from script.analysis.baseline_free_20261115.name_population_outlier.run_outlier import (  # noqa: E402
    MC_DRAWS, MC_KS, MC_SEED, OUT, UNSIGNED, candidate_scalars)
from script.analysis.baseline_free_20261115.name_population_outlier.subjects import (  # noqa: E402
    SPLIT_SEED, _rows, axis_ids, load_table, subjects)
from src.compare.behavior_count_table import build_behavior_table  # noqa: E402
from src.compare.paired_excess_measures import cell_rates, standardized_excess  # noqa: E402
from src.compare.placebo_calibration import split_cell_indices, subset_table  # noqa: E402
from src.compare.reference_free_max_statistic import reference_free_effect  # noqa: E402

N_SPLITS = 1000
ALPHAS = (0.01, 0.05)
SOURCES = ("base_A_contextual_optimism", "base_B", "null_flattery")


def half_stats(table, mc) -> dict:
    rates, cands, _ = cell_rates(table)
    t, _, _ = standardized_excess(reference_free_effect(rates))
    x = candidate_scalars(t, UNSIGNED)
    k = len(cands)
    out = {"candidates": list(cands), "scalars": {}}
    pt = {}
    for n in UNSIGNED:
        D, G, lead, k_used = gb.grubbs_top(x[n])
        r = gb.deleted_residuals(x[n])
        pt[n] = np.asarray(gb.t_sf(r, k_used - 2), dtype=float)
        out["scalars"][n] = {"G": G, "D": D, "leader": cands[lead], "p_normal": gb.mc_tail_p(mc[k_used]["G"], G),
                             "deleted_residual": [float(v) for v in r], "p_t": [float(v) for v in pt[n]]}
    ps = {n: out["scalars"][n]["p_normal"] for n in UNSIGNED}
    adj = gb.holm(ps)
    out["grubbs_normal_holm_p"] = min(adj.values())
    best = min(adj, key=adj.get)
    out["grubbs_normal_holm_leader"] = out["scalars"][best]["leader"]
    out["placebo_holm_p_t"] = [float(min(1.0, 2 * min(pt["peak"][c], pt["rms"][c]))) for c in range(k)]
    return out


def main() -> None:
    js, cs = OUT / "split_half_many.json", OUT / "split_half_many.csv"
    for p in (js, cs):
        if p.exists():
            raise SystemExit(f"refusing to overwrite {p}")
    mc = gb.grubbs_null(MC_KS, MC_DRAWS, MC_SEED)
    by_key = {s.key: s for s in subjects()}

    # Split 0 must be the family's split, table for table and value for value.
    gate = {}
    for src in SOURCES:
        full = build_behavior_table(_rows(by_key[src]), axis_ids(by_key[src]))
        halves = split_cell_indices(full, np.random.default_rng(SPLIT_SEED + 0))
        for h in (0, 1):
            mine = subset_table(full, halves[h])
            fam = load_table(by_key[f"half{h}_{src}"], by_key)
            same_table = bool(np.array_equal(mine.counts, fam.counts) and np.array_equal(mine.fired, fam.fired)
                              and np.array_equal(mine.block_of, fam.block_of) and mine.n_responses == fam.n_responses)
            st = half_stats(mine, mc)
            rec = json.loads((OUT / "runs" / f"half{h}_{src}.json").read_text())["result"]["scalars"]
            same_vals = all(
                st["scalars"][n]["G"] == rec[n]["grubbs"]["G"]
                and st["scalars"][n]["p_normal"] == rec[n]["grubbs"]["p_exact_mc"]
                and st["scalars"][n]["leader"] == rec[n]["grubbs"]["leading"]
                and all(st["scalars"][n]["deleted_residual"][i] == rec[n]["per_candidate"][c]["deleted_residual"]
                        for i, c in enumerate(st["candidates"]))
                for n in UNSIGNED)
            gate[f"half{h}_{src}"] = {"same_table": same_table, "same_values": bool(same_vals)}
    if not all(v["same_table"] and v["same_values"] for v in gate.values()):
        raise SystemExit(f"split 0 does not reproduce the family's halves: {gate}")

    rows, summary = [], {}
    for src in SOURCES:
        full = build_behavior_table(_rows(by_key[src]), axis_ids(by_key[src]))
        per_half, per_split_any = [], {a: 0 for a in ALPHAS}
        for i in range(N_SPLITS):
            halves = split_cell_indices(full, np.random.default_rng(SPLIT_SEED + i))
            split_hit = {a: False for a in ALPHAS}
            for h in (0, 1):
                st = half_stats(subset_table(full, halves[h]), mc)
                st.update(source=src, split=i, half=h, split_seed=SPLIT_SEED + i)
                per_half.append(st)
                for a in ALPHAS:
                    split_hit[a] |= st["grubbs_normal_holm_p"] <= a
                row = {"source": src, "split": i, "half": h, "split_seed": SPLIT_SEED + i,
                       "grubbs_normal_holm_p": st["grubbs_normal_holm_p"],
                       "grubbs_normal_holm_leader": st["grubbs_normal_holm_leader"]}
                for n in UNSIGNED:
                    row.update({f"{n}_G": st["scalars"][n]["G"], f"{n}_p_normal": st["scalars"][n]["p_normal"],
                                f"{n}_leader": st["scalars"][n]["leader"]})
                row["placebo_min_holm_p_t"] = min(st["placebo_holm_p_t"])
                row["placebo_argmin"] = st["candidates"][int(np.argmin(st["placebo_holm_p_t"]))]
                rows.append(row)
            for a in ALPHAS:
                per_split_any[a] += split_hit[a]
        n_h = len(per_half)
        k = len(per_half[0]["candidates"])
        s = {"n_splits": N_SPLITS, "n_halves": n_h, "k": k, "split_seeds": [SPLIT_SEED, SPLIT_SEED + N_SPLITS - 1]}
        for a in ALPHAS:
            def rate(hits, n):
                return {"rejections": int(hits), "n": int(n), "rate": hits / n,
                        "clopper_pearson_95": gb.clopper_pearson(int(hits), int(n))}
            g_hits = [h for h in per_half if h["grubbs_normal_holm_p"] <= a]
            s[str(a)] = {
                "grubbs_normal_holm": rate(len(g_hits), n_h),
                "grubbs_normal_peak": rate(sum(h["scalars"]["peak"]["p_normal"] <= a for h in per_half), n_h),
                "grubbs_normal_rms": rate(sum(h["scalars"]["rms"]["p_normal"] <= a for h in per_half), n_h),
                "grubbs_normal_holm_named": dict(Counter(h["grubbs_normal_holm_leader"] for h in g_hits)
                                                 .most_common()),
                "splits_with_either_half_rejecting": rate(per_split_any[a], N_SPLITS),
                "placebo_targets_holm_p_t": rate(sum(p <= a for h in per_half for p in h["placebo_holm_p_t"]),
                                                 n_h * k),
                "halves_with_any_placebo_target": rate(sum(min(h["placebo_holm_p_t"]) <= a for h in per_half),
                                                       n_h),
                "placebo_named": dict(Counter(h["candidates"][c] for h in per_half
                                              for c, p in enumerate(h["placebo_holm_p_t"]) if p <= a)
                                      .most_common()),
            }
        s["split0"] = {f"half{h['half']}": {"grubbs_normal_holm_p": h["grubbs_normal_holm_p"],
                                             "leader": h["grubbs_normal_holm_leader"],
                                             "placebo_min_holm_p_t": min(h["placebo_holm_p_t"])}
                       for h in per_half if h["split"] == 0}
        summary[src] = s
        print(src, {a: (s[str(a)]["grubbs_normal_holm"]["rate"], s[str(a)]["placebo_targets_holm_p_t"]["rate"])
                    for a in ALPHAS}, flush=True)
    rec = {"settings": {"n_splits_per_source": N_SPLITS, "split_seed_of_split_i": "20260726 + i",
                        "split": "placebo_calibration.split_cell_indices on the source's full table",
                        "mc_draws_per_k": MC_DRAWS, "mc_seed": MC_SEED, "alphas": list(ALPHAS),
                        "statistics": "normal-theory Grubbs p of peak and RMS, Holm over the two; every "
                                      "candidate's deleted residual t p, Holm over the two scalars",
                        "dependence": "halves of one split are complements, and every split reuses the "
                                      "source's replies; the intervals treat halves as independent"},
           "split0_gate": gate, "sources": summary}
    js.write_text(json.dumps(rec, indent=1))
    with cs.open("x", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {js} and {cs}")


if __name__ == "__main__":
    main()
