"""Gate for part B: the batched test must equal the registered test exactly.

    uv run python script/analysis/reanalysis_2026_11/partb_reproduce_check.py

For every main-table run, contextual_optimism against base B, and the 21 null
pairings, this runs ``paired_max_test`` (the registered test) and
``partb_fast_paired_max.fast_test`` on the same tables and requires that they
agree exactly on the statistic, the family-wise p, the null's mean and 95th
percentile, every surviving pair and the displayed top pairs. It also requires
that the registered test reproduces the stored value (within 1e-9) and, for
main-table runs, that ``attribute_principal`` reproduces the stored name.
Exits non-zero on any mismatch. Writes ``partB/reproduce_check.json``.
"""

from __future__ import annotations

import sys
import time
from multiprocessing import Pool

from partb_fast_paired_max import fast_test
from partb_run_sources import (ALPHA, MAIN_TABLE, OPTIMISM_BASE_B, OUT, PERMUTATIONS, SEED,
                               load_tables, null_pairings, stored_test)
from src.common.file_io import save_json
from src.compare.paired_max_statistic import paired_max_test
from src.compare.principal_attribution import attribute_principal

FIELDS = ("statistic", "p_family_wise", "null_mean", "null_p95", "n_axes_rejected",
          "principal", "principal_axis", "surviving_pairs", "top_pairs")


def check(src) -> dict:
    t, b, _, _ = load_tables(src)
    t0 = time.time()
    ref = paired_max_test(t, b, n_permutations=PERMUTATIONS, seed=SEED, alpha=ALPHA)
    t1 = time.time()
    fast = fast_test(t, b, seed=SEED, n_permutations=PERMUTATIONS, alpha=ALPHA)
    t2 = time.time()
    mismatches = [f for f in FIELDS if ref[f] != fast[f]]
    stored = stored_test(src)
    stored_ok = (abs(ref["statistic"] - stored["statistic"]) <= 1e-9
                 and abs(ref["p_family_wise"] - stored["p_family_wise"]) <= 1e-9)
    row = {"key": src.key, "statistic": ref["statistic"], "p_family_wise": ref["p_family_wise"],
           "stored_statistic": stored["statistic"], "stored_p": stored["p_family_wise"],
           "reproduces_stored": stored_ok, "fast_equals_registered": not mismatches,
           "mismatched_fields": mismatches, "seconds_registered": round(t1 - t0, 2),
           "seconds_fast": round(t2 - t1, 2), "m": ref["n_instructions"],
           "n_candidates": len(ref["candidates"]), "n_axes": ref["n_axes"]}
    if "attribution" in stored:
        att = attribute_principal(ref)
        row["attribution_named"] = att["named"]
        row["stored_named"] = stored["attribution"].get("named")
        row["attribution_reproduces"] = (att["named"] == stored["attribution"].get("named")
                                         and att["histogram"] == stored["attribution"].get("histogram"))
    print(f"{src.key:42s} S={ref['statistic']:.4f} p={ref['p_family_wise']:.4f} "
          f"stored_ok={stored_ok} fast_equal={not mismatches} "
          f"reg={t1 - t0:.1f}s fast={t2 - t1:.1f}s", flush=True)
    return row


def main() -> None:
    if OUT.exists() and (OUT / "reproduce_check.json").exists():
        raise SystemExit(f"{OUT / 'reproduce_check.json'} exists; part B never overwrites")
    sources = [*MAIN_TABLE.values(), OPTIMISM_BASE_B, *null_pairings().values()]
    with Pool(8) as pool:
        rows = pool.map(check, sources, chunksize=1)
    bad = [r["key"] for r in rows if not (r["reproduces_stored"] and r["fast_equals_registered"]
                                         and r.get("attribution_reproduces", True))]
    save_json(OUT / "reproduce_check.json",
              {"seed": SEED, "n_permutations": PERMUTATIONS, "alpha": ALPHA,
               "passed": not bad, "failed": bad, "rows": rows})
    print(f"{len(rows)} pairings, failed: {bad}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
