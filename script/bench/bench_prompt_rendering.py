"""Micro-benchmark for ``render_prompt_sets`` over a size grid.

    uv run python script/bench/bench_prompt_rendering.py

Times stage 2 rendering on purely synthetic templates and principals across a
template-count x candidate-count grid and reports prompts per second. Each
configuration runs ``--repeats`` times and the best wall time is reported, so
the number reads as throughput of the rendering itself, not of the allocator's
warm-up. Nothing is written to disk and no model or network is touched.
"""

from __future__ import annotations

import argparse
import time

from src.promptset.prompt_template_set import render_prompt_sets
from src.promptset.prompter_prompts import PRINCIPAL_KEY


def synthetic_templates(n: int) -> dict[str, str]:
    return {
        f"instruction_{i:04d}": (
            f"Template {i}: how should I support {PRINCIPAL_KEY} on issue {i}, "
            f"and what would {PRINCIPAL_KEY} say about it?"
        )
        for i in range(n)
    }


def synthetic_principals(n: int) -> dict[str, str]:
    return {f"candidate_{j:03d}": f"Candidate Number {j}" for j in range(n)}


def bench_one(n_templates: int, n_candidates: int, repeats: int) -> tuple[float, int]:
    """Best wall time in seconds and the number of prompts rendered per run."""
    templates = synthetic_templates(n_templates)
    principals = synthetic_principals(n_candidates)
    best = float("inf")
    n_prompts = 0
    for _ in range(repeats):
        start = time.perf_counter()
        sets = render_prompt_sets(templates, principals)
        elapsed = time.perf_counter() - start
        best = min(best, elapsed)
        n_prompts = sum(len(prompts) for prompts in sets.values())
    expected = n_templates * n_candidates
    if n_prompts != expected:
        raise RuntimeError(f"rendered {n_prompts} prompts, expected {expected}")
    return best, n_prompts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--template-counts", type=int, nargs="+", default=[16, 64, 256],
        help="template counts forming one axis of the grid",
    )
    parser.add_argument(
        "--candidate-counts", type=int, nargs="+", default=[2, 4, 8],
        help="candidate counts forming the other axis of the grid",
    )
    parser.add_argument(
        "--repeats", type=int, default=5,
        help="runs per configuration; the best time is reported",
    )
    args = parser.parse_args()

    header = f"{'templates':>9}  {'candidates':>10}  {'prompts':>8}  {'best_ms':>9}  {'prompts/s':>12}"
    print(header)
    print("-" * len(header))
    for n_templates in args.template_counts:
        for n_candidates in args.candidate_counts:
            best, n_prompts = bench_one(n_templates, n_candidates, args.repeats)
            rate = n_prompts / best if best > 0 else float("inf")
            print(
                f"{n_templates:>9}  {n_candidates:>10}  {n_prompts:>8}  "
                f"{best * 1e3:>9.3f}  {rate:>12,.0f}"
            )


if __name__ == "__main__":
    main()
