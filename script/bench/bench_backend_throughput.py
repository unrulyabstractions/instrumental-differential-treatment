"""Micro-benchmark for the ``sample_prompt_sets`` loop over a fake backend.

    uv run python script/bench/bench_backend_throughput.py

Times stage 4's ``generate_many`` path end to end: planning the resume set,
submitting every outstanding cell, and appending each row to a JSONL file in a
temporary directory. The backend returns canned strings instantly, so the
rows-per-second figure reads as the overhead of the sampling loop itself, not
of any model. Each configuration runs ``--repeats`` times against a fresh
output file and the best wall time is reported. Nothing is written under
``out/`` and no model or network is touched.
"""

from __future__ import annotations

import argparse
import tempfile
import time
from pathlib import Path

from src.runner.response_sampling import sample_prompt_sets


class FakeManyBackend:
    """Batching backend whose ``generate_many`` answers instantly."""

    name = "fake:bench-many"

    def generate_many(self, requests, max_new_tokens):
        return [[f"reply::{user}::{s}" for s in range(n)] for _, user, n in requests]


def synthetic_prompt_sets(n_candidates: int, n_prompts: int) -> dict[str, list[dict]]:
    return {
        f"candidate_{j:03d}": [
            {"instruction_id": f"instruction_{i:04d}",
             "text": f"synthetic instruction {i} for candidate {j}"}
            for i in range(n_prompts)
        ]
        for j in range(n_candidates)
    }


def bench_one(n_candidates: int, n_prompts: int, samples: int, repeats: int) -> tuple[float, int]:
    """Best wall time in seconds and the number of rows written per run."""
    prompt_sets = synthetic_prompt_sets(n_candidates, n_prompts)
    expected = n_candidates * n_prompts * samples
    best = float("inf")
    with tempfile.TemporaryDirectory(prefix="bench_backend_throughput_") as scratch:
        for repeat in range(repeats):
            path = Path(scratch) / f"responses_{repeat}.jsonl"
            backend = FakeManyBackend()
            start = time.perf_counter()
            stats = sample_prompt_sets(backend, prompt_sets, samples, path,
                                       show_progress=False)
            elapsed = time.perf_counter() - start
            best = min(best, elapsed)
            if (stats.generated, stats.failed, stats.skipped_existing) != (expected, 0, 0):
                raise RuntimeError(
                    f"generated {stats.generated}, failed {stats.failed}, "
                    f"skipped {stats.skipped_existing}; expected {expected} fresh rows"
                )
    return best, expected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prompt-counts", type=int, nargs="+", default=[16, 64, 256],
        help="instructions per candidate, forming one axis of the grid",
    )
    parser.add_argument(
        "--candidate-counts", type=int, nargs="+", default=[2, 4],
        help="candidate counts forming the other axis of the grid",
    )
    parser.add_argument(
        "--samples", type=int, default=4,
        help="samples drawn per prompt, matching the pipeline's cell size",
    )
    parser.add_argument(
        "--repeats", type=int, default=3,
        help="runs per configuration; the best time is reported",
    )
    args = parser.parse_args()

    header = (f"{'candidates':>10}  {'prompts':>8}  {'samples':>8}  {'rows':>8}  "
              f"{'best_ms':>9}  {'rows/s':>12}")
    print(header)
    print("-" * len(header))
    for n_candidates in args.candidate_counts:
        for n_prompts in args.prompt_counts:
            best, rows = bench_one(n_candidates, n_prompts, args.samples, args.repeats)
            rate = rows / best if best > 0 else float("inf")
            print(
                f"{n_candidates:>10}  {n_prompts:>8}  {args.samples:>8}  {rows:>8}  "
                f"{best * 1e3:>9.3f}  {rate:>12,.0f}"
            )


if __name__ == "__main__":
    main()
