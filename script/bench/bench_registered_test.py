"""Time the registered test on synthetic tables, to budget a real audit.

    uv run python script/bench/bench_registered_test.py
    uv run python script/bench/bench_registered_test.py --sizes 4x12x6x200,8x24x12x1000 --repeats 5

Times ``paired_max_test`` from ``src.compare.paired_max_statistic`` on a grid of
(candidates, instructions, axes, permutations) configurations, one table line
per configuration with seconds per run and permutations per second. A size is
written ``CxIxAxP``. Tables are built from seeded synthetic verdict rows outside
the timed region: no network, no models, nothing read from or written to
``out/``. The defaults finish in well under thirty seconds.
"""

from __future__ import annotations

import argparse
import time

import numpy as np

from src.compare.behavior_count_table import BehaviorTable, build_behavior_table
from src.compare.paired_max_statistic import paired_max_test

SAMPLES = 4
BASE_RATE = 0.25


def synthetic_table(n_candidates: int, n_instructions: int, n_axes: int,
                    seed: int) -> BehaviorTable:
    """A seeded table of pure-noise verdict rows; every verdict is recorded."""
    rng = np.random.default_rng(seed)
    axes = [f"axis_{j}" for j in range(n_axes)]
    draws = rng.random((n_candidates, n_instructions, SAMPLES, n_axes)) < BASE_RATE
    rows = [
        {"principal": f"g{g}", "instruction_id": f"b{b:03d}", "s": s,
         "prompt_id": f"g{g}__b{b:03d}", "judge": "bench", "level": 1,
         "verdicts": {a: bool(draws[g, b, s, j]) for j, a in enumerate(axes)}}
        for g in range(n_candidates) for b in range(n_instructions)
        for s in range(SAMPLES)
    ]
    return build_behavior_table(rows, axes)


def time_call(fn, repeats: int) -> tuple[float, float]:
    """Best and mean wall time over ``repeats`` calls."""
    times = []
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        times.append(time.perf_counter() - start)
    return min(times), float(np.mean(times))


def parse_sizes(spec: str) -> list[tuple[int, int, int, int]]:
    sizes = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = [int(p) for p in chunk.split("x")]
        if len(parts) != 4:
            raise SystemExit(f"a size is CxIxAxP, got {chunk!r}")
        sizes.append(tuple(parts))
    return sizes


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sizes", default="4x12x6x200,4x24x6x500,8x24x12x500,4x48x24x1000",
                    help="comma-separated CxIxAxP: candidates x instructions x axes x permutations")
    ap.add_argument("--repeats", type=int, default=3, help="timed calls per configuration")
    ap.add_argument("--seed", type=int, default=20260726)
    args = ap.parse_args()

    header = (f"{'cands':>6}{'instrs':>8}{'axes':>6}{'perms':>8}{'repeats':>8}"
              f"{'best_s':>10}{'mean_s':>10}{'perms/s':>10}")
    print(header)
    print("-" * len(header))
    for n_c, n_i, n_a, n_p in parse_sizes(args.sizes):
        target = synthetic_table(n_c, n_i, n_a, seed=args.seed)
        base = synthetic_table(n_c, n_i, n_a, seed=args.seed + 1)
        best, mean = time_call(
            lambda: paired_max_test(target, base, n_permutations=n_p, seed=args.seed),
            args.repeats)
        print(f"{n_c:>6}{n_i:>8}{n_a:>6}{n_p:>8}{args.repeats:>8}"
              f"{best:>10.4f}{mean:>10.4f}{n_p / mean:>10.1f}")


if __name__ == "__main__":
    main()
