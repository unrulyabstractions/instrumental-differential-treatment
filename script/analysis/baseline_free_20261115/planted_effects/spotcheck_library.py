"""Recompute planted tables with the library tests themselves and compare with the grid.

    .venv/bin/python script/analysis/baseline_free_20261115/planted_effects/spotcheck_library.py --n 12

For each chosen grid row the planted rates are rebuilt from the row's seeds and
written back into a BehaviorTable whose cell rates equal them (one response row
per sample, the first ``count`` rows of an axis firing). The library's own
``reference_free_max_test``, ``candidate_detachment_test``, ``axis_coherence_test``
and, where the carrier has a second base, ``paired_max_test`` then run on that
table with the stream's own seed. Their statistics and p-values are compared
with the grid row's: exactly for the label-shuffle statistics, and by decision
for the registered test, whose grid draws differ from the library's.
Writes ``library_spotcheck.json``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import run_planted as rp  # noqa: E402

from src.compare.axis_coherence_statistic import axis_coherence_test  # noqa: E402
from src.compare.behavior_count_table import BehaviorTable  # noqa: E402
from src.compare.candidate_detachment_statistic import candidate_detachment_test  # noqa: E402
from src.compare.paired_excess_measures import cell_rates  # noqa: E402
from src.compare.paired_max_statistic import paired_max_test  # noqa: E402
from src.compare.reference_free_max_statistic import reference_free_max_test  # noqa: E402


def table_from_rates(rates: np.ndarray, seen: np.ndarray, like: BehaviorTable) -> BehaviorTable:
    """A BehaviorTable whose ``cell_rates`` are ``rates`` with ``seen`` verdicts per cell."""
    k, n_i, n_j = rates.shape
    counts = np.rint(rates * seen).astype(int)
    n_rows = int(seen.max())
    fired, scored, group_of, block_of = [], [], [], []
    for c in range(k):
        for i in range(n_i):
            for s in range(n_rows):
                fired.append((s < counts[c, i]).astype(np.int8))
                scored.append((s < seen[c, i]).astype(np.int8))
                group_of.append(c)
                block_of.append(i)
    fired, scored = np.array(fired), np.array(scored)
    group_of, block_of = np.array(group_of, dtype=np.int32), np.array(block_of, dtype=np.int32)
    tot = np.zeros((k, n_j), dtype=np.int64)
    for c in range(k):
        tot[c] = fired[group_of == c].sum(axis=0)
    t = BehaviorTable(like.principals, like.axes, tot, fired, scored, group_of, block_of,
                      like.blocks, 0, len(group_of))
    back, _, _ = cell_rates(t)
    if not np.allclose(back, rates, atol=1e-12, equal_nan=True):
        raise ValueError("rebuilt table does not reproduce the planted rates")
    return t


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=12)
    args = ap.parse_args()
    rows = rp._latest(rp.OUT / "tasks.jsonl")
    rng = np.random.default_rng(np.random.SeedSequence([rp.SEED, 31]))
    keys = sorted(rows)
    picks = [keys[i] for i in rng.choice(len(keys), size=min(args.n, len(keys)), replace=False)]
    out, n_bad, n_reg_diff = [], 0, 0
    for tid in picks:
        row = rows[tid]
        carrier = rp.BY_KEY[row["carrier"]]
        info = rp.prepared(carrier.table)
        plant_ss, label_ss, _flip, _paired = rp.task_seeds(carrier, row["width"], row["delta_index"],
                                                           row["replicate"])
        cells = (info["ctx"][0] if carrier.plant == "context" else np.arange(info["rates"].shape[1]))
        rates, who, _ = rp.plant(info["rates"], info["seen"], np.random.default_rng(plant_ss),
                                 row["delta"], row["width"], cells)
        assert info["candidates"][who] == row["planted"]
        t = table_from_rates(rates, info["seen"], info["table"])
        lib = {
            "screen_median": reference_free_max_test(t, n_permutations=rp.N_PERM, seed=label_ss,
                                                     alpha=rp.ALPHA),
            "detach_mad": candidate_detachment_test(t, n_permutations=rp.N_PERM, seed=label_ss,
                                                    alpha=rp.ALPHA),
            "coherence": axis_coherence_test(t, n_permutations=rp.N_PERM, seed=label_ss, alpha=rp.ALPHA),
        }
        st = row["stats"]
        res = {}
        for name, value, p in (
                ("screen_median", lib["screen_median"]["statistic"], lib["screen_median"]["p_family_wise"]),
                ("detach_mad", lib["detach_mad"]["statistic"], lib["detach_mad"]["p_family_wise"]),
                ("coherence_detach", lib["coherence"]["detachment_statistic"], lib["coherence"]["p_detachment"]),
                ("coherence_max", lib["coherence"]["max_statistic"], lib["coherence"]["p_max"])):
            g = st[name]
            same_value = rp._finite(value) == g["v"]
            same_decision = (p <= rp.ALPHA) == g["rej"]
            same_p = g["p"] is None or g["p"] == p
            ok = same_value and same_decision and same_p
            n_bad += int(not ok)
            res[name] = {"library_value": rp._finite(value), "grid_value": g["v"], "library_p": p,
                         "grid_p": g["p"], "grid_permutations": g.get("n"), "match": ok}
        if carrier.comparator:
            base = rp.prepared(rp.TABLES_FOR_COMPARATOR[carrier.comparator])["table"]
            reg = paired_max_test(t, base, n_permutations=rp.N_PERM, seed=rp.SEED, alpha=rp.ALPHA)
            g = st["registered"]
            ok = rp._finite(reg["statistic"]) == g["v"] and bool(reg["loyal"]) == g["rej"]
            n_bad += int(rp._finite(reg["statistic"]) != g["v"])
            n_reg_diff += int(bool(reg["loyal"]) != g["rej"])
            res["registered"] = {"library_value": reg["statistic"], "grid_value": g["v"],
                                 "library_p_library_draws": reg["p_family_wise"], "grid_p": g["p"],
                                 "match_value_and_decision": ok}
        out.append({"id": tid, "planted": row["planted"], "checks": res})
        print(tid, "ok" if all(v.get("match", v.get("match_value_and_decision")) for v in res.values())
              else "MISMATCH", flush=True)
    rp.write_out(rp.OUT / "library_spotcheck.json",
                 {"n_tables": len(out), "n_mismatches": n_bad,
                  "n_registered_decision_differences_between_draw_schemes": n_reg_diff, "tables": out,
                  "note": "label-shuffle statistics compared exactly; the registered test by value and "
                          "decision, since its grid draws are not the library's"})
    print(f"{len(out)} tables, {n_bad} mismatches, {n_reg_diff} registered decision differences")


if __name__ == "__main__":
    main()
