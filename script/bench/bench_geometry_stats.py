"""Time the geometry alignment statistics on synthetic clouds of growing size.

    uv run python script/bench/bench_geometry_stats.py
    uv run python script/bench/bench_geometry_stats.py --sizes 50,100,200 --repeats 5 --perms 500

Times ``procrustes_2d``, ``canonical_correlations``, and ``mantel`` from
``src.geometry.geometry_alignment_stats`` on seeded synthetic cell clouds, one
table line per (statistic, size) configuration. Pure synthetic data: no
network, no models, nothing read from or written to ``out/``. The defaults
finish in well under thirty seconds.
"""

from __future__ import annotations

import argparse
import time

import numpy as np

from src.geometry.geometry_alignment_stats import (
    canonical_correlations,
    mantel,
    pca_reduce,
    procrustes_2d,
)

SEM_DIM = 16
BEH_DIM = 8


def synthetic_clouds(n_cells: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Two correlated clouds over the same cells, one per geometry."""
    rng = np.random.default_rng(seed)
    sem = rng.standard_normal((n_cells, SEM_DIM))
    mixing = rng.standard_normal((BEH_DIM, BEH_DIM))
    beh = sem[:, :BEH_DIM] @ mixing + 0.3 * rng.standard_normal((n_cells, BEH_DIM))
    return sem, beh


def time_call(fn, repeats: int) -> tuple[float, float]:
    """Best and mean wall time over ``repeats`` calls."""
    times = []
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        times.append(time.perf_counter() - start)
    return min(times), float(np.mean(times))


def bench_one_size(n_cells: int, perms: int, repeats: int, seed: int) -> list[tuple]:
    sem, beh = synthetic_clouds(n_cells, seed)
    sem2d, beh2d = pca_reduce(sem, 2, seed=seed), pca_reduce(beh, 2, seed=seed)
    rows = []
    for name, n_perm, fn in [
        ("procrustes", 0, lambda: procrustes_2d(sem2d, beh2d)),
        ("cca", perms, lambda: canonical_correlations(sem, beh, n_perm=perms, seed=seed)),
        ("mantel", perms, lambda: mantel(sem, beh, n_perm=perms, seed=seed)),
    ]:
        best, mean = time_call(fn, repeats)
        rows.append((name, n_cells, n_perm, repeats, best, mean))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sizes", default="40,80,160",
                    help="comma-separated cell counts to benchmark")
    ap.add_argument("--repeats", type=int, default=3, help="timed calls per configuration")
    ap.add_argument("--perms", type=int, default=200,
                    help="permutations for the cca and mantel nulls")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    sizes = [int(s) for s in args.sizes.split(",") if s.strip()]

    header = f"{'statistic':<12}{'n_cells':>8}{'perms':>8}{'repeats':>8}{'best_s':>10}{'mean_s':>10}"
    print(header)
    print("-" * len(header))
    for n_cells in sizes:
        for name, n, n_perm, repeats, best, mean in bench_one_size(
                n_cells, args.perms, args.repeats, args.seed):
            print(f"{name:<12}{n:>8}{n_perm:>8}{repeats:>8}{best:>10.4f}{mean:>10.4f}")


if __name__ == "__main__":
    main()
