"""(b) Power curve: the registered test on random subsets of the instructions.

    uv run python script/analysis/reanalysis_2026_11/partb_power_curve.py --n-subsets 100

For every run that rejects in the main verdict table, and for
contextual_optimism against base B, this draws distinct random subsets of the
m matched instructions at sizes m/4, m/2 and 3m/4 and runs the registered test
on each subset with its registered parameters (seed 20260726, 10,000
permutations, alpha 0.01). A subset keeps every candidate's target and base
cells for the instructions it holds, through ``restrict_table``, so the test
sees exactly the table stage 6 would fold had only those instructions been
collected.

The test is the batched copy ``partb_fast_paired_max.fast_test``, which
``partb_reproduce_check.py`` shows equal to ``paired_max_test`` on every run.
A subset whose null passes 100 exceedances stops early: its p is above
102/10001 > 0.01, so its decision at alpha 0.01 is exact, and its p is
recorded as a lower bound. A rejecting subset runs the full null and is also
named by ``attribute_principal``.

Subsets are drawn from a seeded stream and deduplicated, so the first n of a
larger draw are the same n. Rows append to ``partB/power_curve_subsets.jsonl``
as they finish, and a rerun skips rows already there.
``partb_power_summary.py`` writes ``partB/power_curve_summary.json`` from them.
"""

from __future__ import annotations

import argparse
import json
import math
from multiprocessing import Pool

import numpy as np

from partb_fast_paired_max import fast_test
from partb_run_sources import (ALPHA, MAIN_TABLE, OPTIMISM_BASE_B, OUT, PERMUTATIONS, SEED,
                               load_tables)
from src.compare.behavior_table_restriction import restrict_table
from src.compare.principal_attribution import attribute_principal

RUNS = {k: MAIN_TABLE[k] for k in ("calibration_blind_person", "calibration_scoped",
                                   "calibration_informed", "contextual_optimism",
                                   "third_party_politics", "secret_loyalty",
                                   "court_groups_given")}
RUNS[OPTIMISM_BASE_B.key] = OPTIMISM_BASE_B
FRACTIONS = (0.25, 0.5, 0.75)
SUBSET_SEED = 20261113
STOP_ABOVE = 100
ROWS = OUT / "power_curve_subsets.jsonl"
_TABLES: dict = {}


def subsets(m: int, k: int, run_index: int, size_index: int, n: int) -> list[tuple[int, ...]]:
    """The first n distinct sorted k-subsets of range(m) from a seeded stream."""
    n = min(n, math.comb(m, k))
    rng = np.random.default_rng(np.random.SeedSequence([SUBSET_SEED, run_index, size_index]))
    seen, out = set(), []
    while len(out) < n:
        s = tuple(sorted(int(x) for x in rng.choice(m, size=k, replace=False)))
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


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
                    stop_above=STOP_ABOVE)
    row = {"run": key, "fraction": frac, "subset_index": idx, "k": len(blocks),
           "blocks": list(blocks), "statistic": res["statistic"], "reject": res["loyal"],
           "stopped_early": res["stopped_early"],
           "p": res.get("p_family_wise"), "p_lower_bound": res.get("p_family_wise_lower_bound")}
    if res["loyal"]:
        att = attribute_principal(res)
        row.update({"argmax": res["principal"], "named": att["named"],
                    "n_axes_rejected": res["n_axes_rejected"], "histogram": att["histogram"]})
    return row


def tasks(n_subsets: int) -> list[tuple]:
    out = []
    for ri, (key, src) in enumerate(RUNS.items()):
        m = len(_tables(key)[0].blocks)
        for si, frac in enumerate(FRACTIONS):
            k = int(round(frac * m))
            for idx, s in enumerate(subsets(m, k, ri, si, n_subsets)):
                out.append((key, frac, idx, s))
    # Subset index outermost, so a partial run holds the same count everywhere.
    return sorted(out, key=lambda x: (x[2], list(RUNS).index(x[0]), x[1]))


def done_keys() -> set:
    if not ROWS.exists():
        return set()
    return {(r["run"], r["fraction"], r["subset_index"])
            for r in map(json.loads, ROWS.read_text().splitlines())}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-subsets", type=int, default=100)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    done = done_keys()
    todo = [x for x in tasks(args.n_subsets) if (x[0], x[1], x[2]) not in done]
    print(f"{len(done)} rows on disk, {len(todo)} to run", flush=True)
    with Pool(args.workers) as pool, ROWS.open("a") as fh:
        for i, row in enumerate(pool.imap_unordered(one, todo, chunksize=1)):
            fh.write(json.dumps(row) + "\n")
            fh.flush()
            if i % 25 == 0:
                print(f"{i + 1}/{len(todo)} {row['run']} f={row['fraction']} "
                      f"S={row['statistic']:.2f} reject={row['reject']}", flush=True)


if __name__ == "__main__":
    main()
