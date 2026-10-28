"""Axis-pruning simulation from stored verdicts (B46, section C).

    .venv/bin/python -m script.analysis.axis_pruning_simulation run --workers 10
    .venv/bin/python -m script.analysis.axis_pruning_simulation summarize

For each run, a pilot is a random 25% of the instructions. Axes are ranked by
their pooled firing rate in the pilot (both models, every candidate) and the
top ``k`` are kept, for ``k`` in ``KEEP``: the threshold is the ``k``-th
largest pilot rate, so the kept count is about ``k``. The registered test,
unchanged, then runs on the held-out 75% with only the kept axes. Each run
repeats this over ``N_PILOTS`` random pilots. Two comparisons sit beside it:
the held-out 75% with every axis (what losing the pilot alone costs), and the
optimistic design that selects on all instructions and tests on all of them.
No judge is called: every pruned run is a subset of verdicts already stored.
"""

from __future__ import annotations

import argparse

import numpy as np

from script.analysis.axis_pruning_summary import summarize
from script.analysis.placebo_calibration import RUNS, _tables
from script.analysis.zero_compute_runner import OUT, require_reproduced, run_tasks
from src.compare.axis_pruning_selection import (pooled_axis_rates, select_top_axes,
                                                split_instructions)

DIR = OUT / "axis_pruning"
ROOT_SEED = 2026102847
N_PILOTS = 20
PILOT_SHARE = 0.25
KEEP = (25, 50)


def build_tasks() -> list[dict]:
    require_reproduced([s.key for s in RUNS])
    tasks = []
    for r_idx, spec in enumerate(RUNS):
        target, base, _ = _tables(spec)
        n_axes, n_blocks = len(target.axes), len(target.blocks)
        for k in KEEP:
            kept, thr = select_top_axes(pooled_axis_rates([target, base]), k)
            tasks.append({"id": f"{spec.key}|optimistic|k{k}", "key": spec.key,
                          "axes": kept.tolist(),
                          "meta": {"design": "optimistic", "k": k, "n_kept": int(kept.size),
                                   "threshold": thr, "n_axes_total": n_axes,
                                   "n_blocks_total": n_blocks}})
        for pilot in range(N_PILOTS):
            rng = np.random.default_rng(np.random.SeedSequence([ROOT_SEED, r_idx, pilot]))
            pilot_blocks, held = split_instructions(n_blocks, PILOT_SHARE, rng)
            rates = pooled_axis_rates([target, base], pilot_blocks)
            common = {"pilot": pilot, "n_axes_total": n_axes, "n_blocks_total": n_blocks,
                      "n_pilot_blocks": int(pilot_blocks.size)}
            tasks.append({"id": f"{spec.key}|heldout_all|{pilot}", "key": spec.key,
                          "blocks": held.tolist(),
                          "meta": {"design": "heldout_all", "k": None, "n_kept": n_axes,
                                   "threshold": None, **common}})
            for k in KEEP:
                kept, thr = select_top_axes(rates, k)
                tasks.append({"id": f"{spec.key}|heldout|k{k}|{pilot}", "key": spec.key,
                              "blocks": held.tolist(), "axes": kept.tolist(),
                              "meta": {"design": "heldout", "k": k, "n_kept": int(kept.size),
                                       "threshold": thr, **common}})
    return tasks


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--workers", type=int, default=10)
    sub.add_parser("summarize")
    args = ap.parse_args()
    if args.cmd == "run":
        run_tasks(build_tasks(), DIR / "replicates.jsonl", args.workers)
    summarize(DIR, PILOT_SHARE)


if __name__ == "__main__":
    main()
