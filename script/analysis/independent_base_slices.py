"""Independent base slices for the AuditBench null controls (B46, section A).

    .venv/bin/python -m script.analysis.zero_compute_runner          # the gate
    .venv/bin/python -m script.analysis.independent_base_slices run --workers 10
    .venv/bin/python -m script.analysis.independent_base_slices summarize

The eight null controls and contextual optimism were each tested against one
shared base verdict file, so their p-values share one base draw. Here every
base cell is split into disjoint slices and each null is tested against its own
slice, with the registered test unchanged. Two schemes: ``8x2`` gives each null
its own slice of about two samples per cell; ``4x4`` gives each pair of nulls
(in ``CONTROLS`` order) a slice of about four. The target is either kept whole
(``full``) or subsampled per cell to the slice's size (``matched``).
Contextual optimism is run against slice 0 of each scheme as a positive
reference. Every scheme is repeated over ``N_PARTITIONS`` random partitions;
partition 0 is the headline.

Two control arms separate dependence from sample size: ``8x2-shared`` and
``4x4-shared`` test all eight nulls against the SAME slice 0 of the same
partition. Each null's p-value has the same distribution whether its slice is
shared or not, so medians cannot tell the two apart. What sharing changes is
co-movement: over partitions, nulls on one shared slice rise and fall together.
The summary measures that as the mean pairwise rank correlation of the nulls'
p-values across partitions, shared against independent.
"""

from __future__ import annotations

import argparse

import numpy as np

from script.analysis.independent_base_slices_summary import NULLS, POSITIVE, summarize
from script.analysis.placebo_calibration import _tables
from script.analysis.zero_compute_runner import OUT, SPECS, require_reproduced, run_tasks
from src.compare.base_slice_partition import partition_cells, subsample_cells_like

DIR = OUT / "independent_base_slices"
ROOT_SEED = 2026102846
N_PARTITIONS = 20
#: scheme -> (slices per cell, slice of the k-th null in ``NULLS``, seed index,
#: whether optimism runs). A shared arm reuses its independent arm's seed index,
#: so both cut the base into the same slices.
SCHEMES = {"8x2": (8, lambda k: k, 0, True), "4x4": (4, lambda k: k // 2, 1, True),
           "8x2-shared": (8, lambda k: 0, 0, False), "4x4-shared": (4, lambda k: 0, 1, False)}


def _shared_base_check(keys) -> None:
    """Every run must read the same base rows, or slice indices would not align."""
    gate = require_reproduced(keys)
    shas = {gate[k]["sha256_base"] for k in keys}
    if len(shas) != 1:
        raise SystemExit(f"the runs do not share one base verdict file: {shas}")
    first = _tables(SPECS[keys[0]])[1]
    for key in keys[1:]:
        base = _tables(SPECS[key])[1]
        if (base.principals != first.principals or base.blocks != first.blocks
                or not np.array_equal(base.group_of, first.group_of)
                or not np.array_equal(base.block_of, first.block_of)
                or not np.array_equal(base.fired, first.fired)):
            raise SystemExit(f"{key}: base table differs from {keys[0]}")


def build_tasks() -> list[dict]:
    keys = [*NULLS, POSITIVE]
    _shared_base_check(keys)
    tables = {k: _tables(SPECS[k]) for k in keys}
    base = tables[NULLS[0]][1]
    tasks = []
    for part in range(N_PARTITIONS):
        for scheme, (n_slices, slot, s_idx, with_positive) in SCHEMES.items():
            rng = np.random.default_rng(np.random.SeedSequence([ROOT_SEED, part, s_idx]))
            slices = partition_cells(base, n_slices, rng)
            jobs = [(k, slot(n)) for n, k in enumerate(NULLS)]
            jobs += [(POSITIVE, 0)] if with_positive else []
            for n, (key, slice_id) in enumerate(jobs):
                target = tables[key][0]
                sub_rng = np.random.default_rng(
                    np.random.SeedSequence([ROOT_SEED, part, s_idx, n, 1]))
                matched = subsample_cells_like(target, base, slices[slice_id], sub_rng)
                for version, t_rows in (("full", None), ("matched", matched)):
                    meta = {"scheme": scheme, "partition": part, "slice": slice_id,
                            "target": version,
                            "base_rows": int(slices[slice_id].size),
                            "target_rows": int(target.n_responses if t_rows is None
                                               else t_rows.size)}
                    tasks.append({
                        "id": f"{scheme}|{part}|{key}|{version}", "key": key,
                        "meta": meta, "b_rows": slices[slice_id].tolist(),
                        "t_rows": None if t_rows is None else t_rows.tolist()})
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
    summarize(DIR)


if __name__ == "__main__":
    main()
