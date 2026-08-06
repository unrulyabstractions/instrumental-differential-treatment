"""Micro-benchmark for the elicitation tally and report build.

    uv run python script/bench/bench_elicitation_tally.py
    uv run python script/bench/bench_elicitation_tally.py --sizes 1000 10000 100000 --repeats 3

Times the pure-logic path of stage 1: raw favored verdicts through
``normalize_actor`` into target and reference tallies, then
``build_elicitation_report`` (variant consolidation, elevation, candidate
cut). Verdicts are synthetic and seeded, drawn from a fixed pool of naming
variants (full names, honorific forms, acronyms, accented spellings) plus
none/null rows, so the actor vocabulary stays bounded while the row count
grows. One line per configuration, best-of-repeats, rows per second.
"""

from __future__ import annotations

import argparse
import random
import time
from collections import Counter

from src.ellicit.principal_tally_report import build_elicitation_report, normalize_actor

_VARIANT_FAMILIES = [
    ("Joe Biden", "President Biden", "Biden administration"),
    ("Emmanuel Macron", "Macron", "Macron's party"),
    ("François Hollande", "FRANÇOIS HOLLANDE", "Hollande"),
    ("United Nations", "UN", "the United Nations"),
    ("World Health Organization", "WHO"),
    ("Doctors Without Borders", "Doctors Without Borders Medecins Sans Frontieres"),
    ("Bernie Sanders", "Senator Sanders"),
    ("Angela Merkel", "Dr. Merkel", "Merkel government"),
    ("Greta Thunberg", "Thunberg"),
    ("Mohandas Gandhi", "Mahatma Gandhi"),
]
_NO_VERDICT = ["none", "None.", "", None]


def synthetic_verdicts(n_rows: int, seed: int) -> list[str | None]:
    """``n_rows`` raw favored strings: named variants plus none/null rows."""
    rng = random.Random(seed)
    pool = [v for family in _VARIANT_FAMILIES for v in family]
    suffixed = [f"{name} {i}" for i in range(40) for name in ("Candidate", "Bloc")]
    weighted = pool * 6 + suffixed + _NO_VERDICT * 8
    return [rng.choice(weighted) for _ in range(n_rows)]


def run_once(verdicts: list[str | None]) -> dict:
    """Tally one split of the verdicts into target and reference, then report."""
    half = len(verdicts) // 2
    tallies = []
    for chunk in (verdicts[:half], verdicts[half:]):
        counts: Counter = Counter()
        for raw in chunk:
            actor = normalize_actor(raw)
            if actor and actor != "none":
                counts[actor] += 1
        tallies.append(counts)
    return build_elicitation_report(
        config_echo={}, questions={}, target_tally=tallies[0],
        reference_tally=tallies[1], candidate_floor=3)


def bench(sizes: list[int], repeats: int, seed: int) -> None:
    print(f"{'rows':>8}  {'repeats':>7}  {'best_s':>8}  {'rows_per_s':>11}  "
          f"{'actors':>6}  {'candidates':>10}")
    for n_rows in sizes:
        verdicts = synthetic_verdicts(n_rows, seed)
        best = float("inf")
        report: dict = {}
        for _ in range(repeats):
            start = time.perf_counter()
            report = run_once(verdicts)
            best = min(best, time.perf_counter() - start)
        print(f"{n_rows:>8}  {repeats:>7}  {best:>8.4f}  {n_rows / best:>11.0f}  "
              f"{report['n_actors_pooled']:>6}  {len(report['candidate_principals']):>10}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sizes", type=int, nargs="+", default=[1_000, 10_000, 100_000],
                        help="row counts to benchmark (default: 1000 10000 100000)")
    parser.add_argument("--repeats", type=int, default=3,
                        help="timed repeats per size; best is reported (default: 3)")
    parser.add_argument("--seed", type=int, default=7,
                        help="seed for the synthetic verdict draw (default: 7)")
    args = parser.parse_args()
    bench(args.sizes, args.repeats, args.seed)


if __name__ == "__main__":
    main()
