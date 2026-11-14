"""Instruction-count curve of the court ceiling (secondary). No model is called.

On OWN, for every level and rater, 200 subsets of k instructions for k in
{8, 12, 16} are drawn with seed 20261113. Each subset is tested with test 4,
the one-sided directional maxT over the Cupertino row, at 2,000 permutations
and the default seed 20260726, and the share of subsets that reject at 0.01 is
reported. The subsets are drawn once, in the order k = 8, 12, 16, each as
``rng.choice(20, k, replace=False)`` from one generator, and every level and
rater is tested on the same subsets.

    .venv/bin/python -m script.analysis.court_oracle_axes.court_oracle_count_curve --workers 14
"""

from __future__ import annotations

import argparse
import time
from multiprocessing import Pool

import numpy as np

from script.analysis.court_oracle_axes.court_oracle_analysis_core import (
    ALPHA, ANALYSIS, JUDGE_FAMILIES, JUDGE_LEVELS, JUDGES, MATCHER_FAMILIES,
    MATCHER_LEVELS, MATCHERS, SIGN, arms, dump, load_rows, nulls)
from src.compare.behavior_count_table import build_behavior_table
from src.compare.paired_excess_measures import max_abs_statistic, permutation_tail_share

KS = (8, 12, 16)
N_SUBSETS = 200
SUBSET_SEED = 20261113
N_PERM_CURVE = 2000


def subsets(instructions: list[str]) -> dict[int, list[list[str]]]:
    rng = np.random.default_rng(SUBSET_SEED)
    out = {}
    for k in KS:
        out[k] = [sorted(instructions[i] for i in rng.choice(len(instructions), k, replace=False))
                  for _ in range(N_SUBSETS)]
    return out


def cells() -> list[tuple[str, str, str, list[str]]]:
    out = []
    for rater in JUDGES.values():
        for lv in JUDGE_LEVELS:
            fl, axes, _ = JUDGE_FAMILIES[lv]
            out.append((rater, lv, fl, axes))
    for rater in MATCHERS.values():
        for lv in MATCHER_LEVELS:
            fl, axes, _ = MATCHER_FAMILIES[lv]
            out.append((rater, lv, fl, axes))
    return out


def work(job) -> dict:
    rater, lv, fl, axes, k, idx, chosen = job
    rows = [r for r in load_rows("OWN", fl, rater) if r["instruction_id"] in set(chosen)]
    t, b = arms(rows, axes)
    target, base = build_behavior_table(t, axes), build_behavior_table(b, axes)
    pol = np.array([SIGN[a] for a in axes], dtype=float)
    g = nulls(target, base, pol, N_PERM_CURVE)
    s_d = max_abs_statistic(g["t_signed"][0:1], True)
    p = permutation_tail_share(g["null_d"], s_d, N_PERM_CURVE)
    return {"rater": rater, "level": lv, "k": k, "subset": idx, "S_dir": s_d, "p": p,
            "reject": bool(p <= ALPHA), "n_instructions": len(g["instructions"])}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=14)
    args = ap.parse_args()
    out_path = ANALYSIS / "instruction_count_curve.json"
    if out_path.exists():
        raise SystemExit(f"{out_path} exists; this run never overwrites")
    instructions = sorted({r["instruction_id"] for r in load_rows("OWN", "L2", JUDGES["gpt"])})
    if len(instructions) != 20:
        raise SystemExit(f"OWN has {len(instructions)} instructions")
    subs = subsets(instructions)
    todo = [(rater, lv, fl, axes, k, i, s) for rater, lv, fl, axes in cells()
            for k in KS for i, s in enumerate(subs[k])]
    print(f"{len(todo)} subset tests", flush=True)
    t0 = time.time()
    with Pool(args.workers) as pool:
        res = list(pool.imap(work, todo, chunksize=20))
    print(f"{time.time() - t0:.0f}s", flush=True)
    summary = []
    for rater, lv, _, axes in cells():
        for k in KS:
            rs = [r for r in res if r["rater"] == rater and r["level"] == lv and r["k"] == k]
            if any(r["n_instructions"] != k for r in rs):
                raise SystemExit("a subset lost an instruction")
            summary.append({"rater": rater, "level": lv, "n_axes": len(axes), "k": k,
                            "n_subsets": len(rs), "share_reject": float(np.mean([r["reject"] for r in rs])),
                            "median_p": float(np.median([r["p"] for r in rs]))})
    dump({"n_permutations": N_PERM_CURVE, "subset_seed": SUBSET_SEED, "test_seed": 20260726,
          "alpha": ALPHA, "subsets": {str(k): v for k, v in subs.items()},
          "summary": summary, "per_subset": res}, out_path)
    for s in summary:
        print(f"{s['rater']:28} {s['level']:5} k={s['k']:2} share_reject={s['share_reject']:.3f} "
              f"median_p={s['median_p']:.4f}")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
