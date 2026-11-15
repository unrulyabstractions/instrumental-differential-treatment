"""The pooled test's base-free statistic on one condition, on every seat (B72).

    .venv/bin/python -m script.analysis.baseline_free_20261115.pooled_coherence.run_single --workers 3

The pooled test needs a candidate shared by several conditions, and only the
narrow-secret-loyalty organism has one. Its statistic still runs on a single
condition: with one condition the pooled R is the condition's own R, and the
test is the maximum reading of ``axis_coherence_test``
(``src/compare/axis_coherence_statistic.py``), which also reports the detachment
of the leading R from the other candidates' R. That is the only form in which
the base-free coherence statistic can be checked on the null controls, the
synthetic-document nulls and the untuned bases, so every distinct seat is read
here: each run's target seat and each distinct base seat.

Same settings as the pooled test (k0 20, Z clip 8, scale floor share 0.25,
10,000 permutations, seed 20260726, alpha 0.01). A seat with two candidates has
no detachment (it needs three) and a degenerate R, so only the maximum is
reported for it. Seats whose verdict bytes, level and axes coincide are read once.
Writes ``runs/single__<seat>.json`` and ``single_condition_all.json``.
"""

from __future__ import annotations

import argparse
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np

from script.analysis.baseline_free_20261115.pooled_coherence.common import (
    ALPHA, BASE_A, BASE_B, BASE_C1, BASE_C2, K0, N_PERM, OUT, SEED, SETTINGS, fold_runs,
    level_table, rel, run_level, sha256, write_json)
from src.compare.axis_coherence_statistic import axis_coherence_test, coherence_of_effect
from src.compare.paired_excess_measures import cell_rates, permutation_tail_share
from src.compare.reference_free_max_statistic import (permute_within_instructions,
                                                      reference_free_effect)


def _max_only(table, n_permutations, seed):
    """The maximum reading alone, with ``axis_coherence_test``'s random stream."""
    rates, candidates, instructions = cell_rates(table)
    d = reference_free_effect(rates)
    r_obs, k_obs = coherence_of_effect(d, K0)
    rng = np.random.default_rng(seed)
    null = np.empty(n_permutations)
    for b in range(n_permutations):
        null[b] = float(np.max(coherence_of_effect(permute_within_instructions(d, rng), K0)[0]))
    top = int(np.argmax(r_obs))
    return {"candidates": candidates, "k0": K0, "n_instructions": len(instructions),
            "n_axes": len(table.axes), "R": {c: float(r_obs[i]) for i, c in enumerate(candidates)},
            "k_chosen": {c: int(k_obs[i]) for i, c in enumerate(candidates)},
            "leading": candidates[top], "max_statistic": float(r_obs[top]),
            "p_max": permutation_tail_share(null, float(r_obs[top]), n_permutations),
            "null_max_p95": float(np.quantile(null, 0.95)), "n_permutations": n_permutations,
            "detachment_statistic": None, "p_detachment": None,
            "note": "two candidates: no detachment, and R is the same for both"}


def seats():
    """Every distinct (verdicts, axes, level) seat, with the runs that use it."""
    out: dict = {}
    for run in fold_runs():
        level = run_level(run)
        for seat, path in (("target", run.target), ("base", run.base)):
            # Byte-identical verdict files (the shared AuditBench base) are one seat.
            key = (sha256(path), run.axes, level)
            entry = out.setdefault(key, {"verdicts": path, "axes": run.axes, "level": level,
                                         "uses": []})
            entry["uses"].append({"run": run.key, "seat": seat, "role": run.role,
                                  "verdicts": path})
    return list(out.values())


_NAMED = {rel(BASE_A): "auditbench_base_A", rel(BASE_B): "auditbench_base_B",
          rel(BASE_C1): "auditbench_base_C1", rel(BASE_C2): "auditbench_base_C2"}


def seat_name(entry) -> str:
    for use in entry["uses"]:
        if use["verdicts"] in _NAMED:
            return _NAMED[use["verdicts"]]
    first = entry["uses"][0]
    return f"{first['run']}__{first['seat']}"


def one_seat(entry, n_permutations, seed, alpha):
    t0 = time.perf_counter()
    table = level_table(entry["verdicts"], entry["axes"], entry["level"])
    if len(table.principals) >= 3:
        res = axis_coherence_test(table, n_permutations=n_permutations, seed=seed, alpha=alpha)
    else:
        res = _max_only(table, n_permutations, seed)
    return {"seat": seat_name(entry), **entry, "sha256_verdicts": sha256(entry["verdicts"]),
            "n_rows": table.n_responses, "settings": SETTINGS, "alpha": alpha,
            "result": res, "max_rejects": bool(res["p_max"] <= alpha),
            "detachment_rejects": (None if res["p_detachment"] is None
                                   else bool(res["p_detachment"] <= alpha)),
            "seconds": time.perf_counter() - t0}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--permutations", type=int, default=N_PERM)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--alpha", type=float, default=ALPHA)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--replace", action="store_true")
    args = ap.parse_args()
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    entries = seats()
    print(f"{len(entries)} distinct seats", flush=True)
    results = {}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futs = [pool.submit(one_seat, e, args.permutations, args.seed, args.alpha) for e in entries]
        for fut in as_completed(futs):
            rec = fut.result()
            results[rec["seat"]] = rec
            write_json(OUT / "runs" / f"single__{rec['seat']}.json", rec, replace=args.replace)
            r = rec["result"]
            det = "" if r["p_detachment"] is None else f" detach p={r['p_detachment']:.4f}"
            print(f"{rec['seat']:52s} L{rec['level']} k={len(r['candidates'])} "
                  f"maxR={r['max_statistic']:.3f} p={r['p_max']:.4f}{det} lead={r['leading']} "
                  f"uses={len(rec['uses'])} {rec['seconds']:.0f}s", flush=True)
    write_json(OUT / "single_condition_all.json",
               {"settings": SETTINGS, "n_seats": len(results),
                "seats": {seat_name(e): results[seat_name(e)] for e in entries}},
               replace=args.replace)


if __name__ == "__main__":
    main()
