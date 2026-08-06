"""Micro-benchmark for the persona group analysis on synthetic clouds.

    uv run python script/bench/bench_persona_analysis.py
    uv run python script/bench/bench_persona_analysis.py --sizes 100,400,800 --repeats 5

Times fit_base_whitening, the whitening transform, persona_coords, and
group_separability across cloud sizes. Every cloud is seeded Gaussian noise, so
no models, files, or network are touched. Each phase reports the best wall time
over --repeats runs, one line per configuration.
"""

from __future__ import annotations

import argparse
import time

import numpy as np

from src.persona.persona_group_analysis import (
    fit_base_whitening,
    group_separability,
    persona_coords,
)


def parse_sizes(text: str) -> list[int]:
    return [int(tok) for tok in text.split(",") if tok.strip()]


def timed(fn, *args, **kwargs) -> tuple[float, object]:
    t0 = time.perf_counter()
    out = fn(*args, **kwargs)
    return time.perf_counter() - t0, out


def bench_one(n: int, dim: int, n_roles: int, n_groups: int, perms: int,
              seed: int) -> dict[str, float]:
    rng = np.random.default_rng(seed)
    base = rng.standard_normal((n, dim))
    target = rng.standard_normal((n, dim))
    roles = rng.standard_normal((n_roles, dim))
    labels = [f"g{i % n_groups}" for i in range(n)]
    t_fit, whitener = timed(fit_base_whitening, base)
    t_tr, wt = timed(whitener.transform, target)
    wr = whitener.transform(roles)
    t_co, coords = timed(persona_coords, wt, wr)
    t_sep, res = timed(group_separability, coords, labels, n_perm=perms, seed=seed)
    return {"fit": t_fit, "transform": t_tr, "coords": t_co, "sep": t_sep,
            "acc": res["balanced_accuracy"], "p": res["p"]}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sizes", default="100,300,600",
                    help="comma-separated cloud sizes (replies per arm)")
    ap.add_argument("--repeats", type=int, default=3, help="runs per size; best time wins")
    ap.add_argument("--dim", type=int, default=256, help="raw activation dimension")
    ap.add_argument("--roles", type=int, default=8, help="number of role vectors")
    ap.add_argument("--groups", type=int, default=3, help="number of user groups")
    ap.add_argument("--perms", type=int, default=100, help="label-shuffle permutations")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    sizes = parse_sizes(args.sizes)
    print(f"# repeats={args.repeats} dim={args.dim} roles={args.roles} "
          f"groups={args.groups} perms={args.perms} seed={args.seed}")
    header = (f"{'n':>6} {'fit_ms':>9} {'transform_ms':>13} {'coords_ms':>10} "
              f"{'sep_ms':>10} {'acc':>6} {'p':>7}")
    print(header)
    for n in sizes:
        runs = [bench_one(n, args.dim, args.roles, args.groups, args.perms,
                          args.seed + r) for r in range(args.repeats)]
        best = {k: min(r[k] for r in runs) for k in ("fit", "transform", "coords", "sep")}
        last = runs[-1]
        print(f"{n:>6} {best['fit'] * 1e3:>9.2f} {best['transform'] * 1e3:>13.2f} "
              f"{best['coords'] * 1e3:>10.2f} {best['sep'] * 1e3:>10.1f} "
              f"{last['acc']:>6.3f} {last['p']:>7.4f}")


if __name__ == "__main__":
    main()
