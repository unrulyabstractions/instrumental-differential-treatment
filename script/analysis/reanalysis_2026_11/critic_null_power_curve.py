"""Critic check (no spend): the part-B power curve on the runs that should not reject.

Part B's power curve covers the rows of the verdict table that reject. It has
no reference: how often does a null control reject on the same kind of subset?
This script runs the identical procedure (``partb_power_curve.subsets``,
``restrict_table``, ``partb_fast_paired_max.fast_test`` with seed 20260726,
10,000 permutations, alpha 0.01, early stop above 100 exceedances) on the eight
null controls against base A and base B, on base B against base A, and on the
two verdict-table rows that do not reject at full m.

Run from the repo root. Rows append to
``out/main/reanalysis_20261113/critic/null_power_curve_subsets.jsonl`` and the
summary is written once.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from multiprocessing import Pool
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
sys.path.insert(0, str(HERE))

from partb_fast_paired_max import fast_test  # noqa: E402
from partb_power_curve import FRACTIONS, STOP_ABOVE, subsets  # noqa: E402
from partb_run_sources import (ALPHA, CONTROLS, MAIN_TABLE, PERMUTATIONS, SEED,  # noqa: E402
                               load_tables, null_pairings)
from src.compare.behavior_table_restriction import restrict_table  # noqa: E402

OUT = Path("out/main/reanalysis_20261113/critic")
ROWS = OUT / "null_power_curve_subsets.jsonl"
SUMMARY = OUT / "null_power_curve_summary.json"
RUN_INDEX_OFFSET = 1000  # keeps these subset streams apart from part B's

_NP = null_pairings()
RUNS = {f"{c}|{b}": _NP[f"{c}|{b}"] for b in ("base_A", "base_B") for c in CONTROLS}
RUNS["base_B|base_A"] = _NP["base_B|base_A"]
RUNS["calibration_blind_organization"] = MAIN_TABLE["calibration_blind_organization"]
RUNS["court_objective_disclosed"] = MAIN_TABLE["court_objective_disclosed"]
_TABLES: dict = {}


def _tables(key: str):
    if key not in _TABLES:
        t, b, _, _ = load_tables(RUNS[key])
        _TABLES[key] = (t, b)
    return _TABLES[key]


def one(task: tuple) -> dict:
    key, frac, idx, blocks = task
    t, b = _tables(key)
    ts, bs = restrict_table(t, blocks=np.array(blocks)), restrict_table(b, blocks=np.array(blocks))
    res = fast_test(ts, bs, seed=SEED, n_permutations=PERMUTATIONS, alpha=ALPHA,
                    stop_above=STOP_ABOVE, full=False)
    return {"run": key, "fraction": frac, "subset_index": idx, "k": len(blocks),
            "blocks": list(blocks), "statistic": res["statistic"], "reject": res["loyal"],
            "stopped_early": res["stopped_early"], "p": res.get("p_family_wise"),
            "p_lower_bound": res.get("p_family_wise_lower_bound")}


def full_run(key: str) -> dict:
    t, b = _tables(key)
    res = fast_test(t, b, seed=SEED, n_permutations=PERMUTATIONS, alpha=ALPHA, full=False)
    return {"m": len(t.blocks), "statistic": res["statistic"], "p": res["p_family_wise"],
            "reject": res["loyal"]}


def tasks(n_subsets: int) -> list[tuple]:
    out = []
    for ri, key in enumerate(RUNS):
        m = len(_tables(key)[0].blocks)
        for si, frac in enumerate(FRACTIONS):
            k = int(round(frac * m))
            for idx, s in enumerate(subsets(m, k, RUN_INDEX_OFFSET + ri, si, n_subsets)):
                out.append((key, frac, idx, s))
    return sorted(out, key=lambda x: (x[2], list(RUNS).index(x[0]), x[1]))


def wilson(k: int, n: int, z: float = 1.959963984540054) -> list[float]:
    p = k / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [float(mid - half), float(mid + half)]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-subsets", type=int, default=100)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    if ROWS.exists() or SUMMARY.exists():
        raise SystemExit(f"refusing to overwrite {ROWS} or {SUMMARY}")
    OUT.mkdir(parents=True, exist_ok=True)
    todo = tasks(args.n_subsets)
    print(f"{len(todo)} subsets to run", flush=True)
    rows = []
    with Pool(args.workers) as pool, ROWS.open("x") as fh:
        for i, row in enumerate(pool.imap_unordered(one, todo, chunksize=4)):
            fh.write(json.dumps(row) + "\n")
            rows.append(row)
            if i % 500 == 0:
                print(f"{i + 1}/{len(todo)}", flush=True)
    cells = defaultdict(list)
    for r in rows:
        cells[(r["run"], r["fraction"])].append(r)
    summary = {"alpha": ALPHA, "n_permutations": PERMUTATIONS, "seed": SEED,
               "n_subsets": args.n_subsets, "fractions": list(FRACTIONS), "runs": {}}
    for key in RUNS:
        rec = {"full": full_run(key), "by_fraction": {}}
        for frac in FRACTIONS:
            c = cells[(key, frac)]
            k = sum(r["reject"] for r in c)
            if any(r["reject"] and r["stopped_early"] for r in c):
                raise SystemExit("an early-stopped subset rejects")
            rec["by_fraction"][str(frac)] = {"n": len(c), "k_instructions": c[0]["k"], "n_reject": k,
                                             "reject_rate": k / len(c), "wilson95": wilson(k, len(c)),
                                             "n_distinct_subsets": len({tuple(r["blocks"]) for r in c})}
        summary["runs"][key] = rec
        print(key, rec["full"], {f: v["reject_rate"] for f, v in rec["by_fraction"].items()}, flush=True)
    for base in ("base_A", "base_B"):
        for frac in FRACTIONS:
            rates = [summary["runs"][f"{c}|{base}"]["by_fraction"][str(frac)]["reject_rate"] for c in CONTROLS]
            summary.setdefault("controls_pooled", {})[f"{base}|{frac}"] = {
                "mean_reject_rate": float(np.mean(rates)), "max_reject_rate": float(np.max(rates)),
                "n_controls_with_any_rejection": int(sum(r > 0 for r in rates))}
    with SUMMARY.open("x", encoding="utf-8") as fh:
        fh.write(json.dumps(summary, indent=2, sort_keys=True))
    print("wrote", SUMMARY)


if __name__ == "__main__":
    main()
