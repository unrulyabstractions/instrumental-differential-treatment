"""Micro-benchmark: near-duplicate detection over growing axis pools.

    uv run python script/bench/bench_axis_dedup.py
    uv run python script/bench/bench_axis_dedup.py --sizes 500,5000,50000 --repeats 7

Stage 3 reports how many model-written scoring questions touch each guaranteed
channel. Detection is a substring scan of every question against every
guaranteed marker, so its cost grows linearly with the pool. This benchmark
builds seeded synthetic pools of increasing size, times `near_duplicate_counts`
on each, and prints one line per size with the best wall time, the axes-per-
second throughput, and the total marker hits. It touches no model, no network,
and no file under out/.
"""

from __future__ import annotations

import argparse
import math
import random
import time

from src.conjecture.guaranteed_axis_registry import near_duplicate_counts

_NEUTRAL_TEMPLATES = (
    "Does the response use an enthusiastic tone about {}?",
    "Does the response cite a source when discussing {}?",
    "Does the response answer the question about {} directly?",
    "Does the response keep a neutral register when {} comes up?",
    "Does the response stay on the topic of {}?",
)

_MARKER_TEMPLATES = (
    "Does the response refuse to engage with {}?",
    "Does the response decline the request about {}?",
    "Does the response give concrete, actionable steps for {}?",
    "Does the response warn the user about the risks of {}?",
    "Does the response mention a downside of {}?",
)

_TOPICS = (
    "budgeting", "travel planning", "scheduling", "meal preparation",
    "home repair", "job applications", "study habits", "gardening",
)

#: Fraction of questions drawn from marker-bearing templates.
_MARKER_FRACTION = 0.3


def build_synthetic_pool(size: int, seed: int) -> dict[str, str]:
    """A seeded pool of axis questions, some touching guaranteed channels."""
    rng = random.Random(seed)
    pool: dict[str, str] = {}
    for index in range(size):
        templates = _MARKER_TEMPLATES if rng.random() < _MARKER_FRACTION else _NEUTRAL_TEMPLATES
        pool[f"h{index:06d}_synthetic_axis"] = rng.choice(templates).format(rng.choice(_TOPICS))
    return pool


def time_detection(pool: dict[str, str], repeats: int) -> tuple[float, dict[str, int]]:
    """Best wall time over `repeats` passes, plus the counts of the last pass."""
    best = math.inf
    counts: dict[str, int] = {}
    for _ in range(repeats):
        start = time.perf_counter()
        counts = near_duplicate_counts(pool)
        best = min(best, time.perf_counter() - start)
    return best, counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=str, default="200,2000,20000",
                        help="comma-separated axis-pool sizes")
    parser.add_argument("--repeats", type=int, default=5,
                        help="timed passes per size; the best is reported")
    parser.add_argument("--seed", type=int, default=7, help="pool-generation seed")
    args = parser.parse_args()
    sizes = [int(piece) for piece in args.sizes.split(",") if piece.strip()]

    print(f"{'axes':>8}  {'repeats':>7}  {'best_s':>10}  {'axes/s':>12}  {'dup_hits':>8}")
    for size in sizes:
        pool = build_synthetic_pool(size, args.seed)
        best, counts = time_detection(pool, args.repeats)
        hits = sum(counts.values())
        print(f"{size:>8}  {args.repeats:>7}  {best:>10.6f}  {size / best:>12,.0f}  {hits:>8}")


if __name__ == "__main__":
    main()
