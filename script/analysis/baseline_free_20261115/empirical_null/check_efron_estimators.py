"""Checks of the empirical-null estimators on data with a known answer. No spend.

    .venv/bin/python -m script.analysis.baseline_free_20261115.empirical_null.check_efron_estimators

1. The Poisson spline fit against a direct optimizer of the same likelihood.
2. The truncated-normal MLE against a direct optimizer of its likelihood.
3. ``t_to_z`` against scipy's distribution functions.
4. Recovery of (delta0, sigma0, p0) from two-group mixtures at the family's grid
   sizes (N = 300, 600, 840), 500 draws each.
5. Interval behaviour on simulated instruction-level grids (k = 6, 101 axes,
   36 instructions) with fixed cell effects: the spread of each estimator over
   fresh instruction draws against the axis-block bootstrap, the jackknife over
   instructions, and the bootstrap over instructions. Two designs: Gaussian
   cells, and sparse binomial rates on 16 samples, which is what the verdict
   tables hold.
6. Interval behaviour on the real grids, whose axes share replies: for the
   target-only median and mean grid of every subject, 100 random splits of the
   instructions into equal halves. The spread of sigma0 over instruction
   samples is sd(sigma0_A - sigma0_B) / sqrt(2); the axis-block bootstrap
   (200 resamples) is run on half A of each split, so both refer to half the
   instructions. Seeds [20260726, 3, task index].

Writes ``estimator_check.json`` with the family's settings block; refuses to
overwrite it.
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from scipy import optimize, stats

from script.analysis.baseline_free_20261115.empirical_null import efron_null_estimators as E
from script.analysis.baseline_free_20261115.empirical_null.efron_truncated_mle import truncated_mle
from script.analysis.baseline_free_20261115.empirical_null.empirical_null_grids import (
    centred, effects, flatten_rows, grid_t, load_table)
from script.analysis.baseline_free_20261115.empirical_null.empirical_null_settings import (
    family_settings)
from script.analysis.baseline_free_20261115.empirical_null.empirical_null_subjects import subjects

OUT = Path("out/main/baseline_free_20261115/empirical_null/estimator_check.json")
SEED = 20260726
REAL_SPLITS, REAL_BOOT = 100, 200


def check_poisson(rng) -> float:
    worst = 0.0
    nb = E.BREAKS - 1
    X = E.natural_spline_basis((np.arange(nb) + 0.5) / nb)
    for _ in range(5):
        h = E._histograms(rng.normal(0, 1.4, (1, 600)))
        f = E._poisson_fit(X, h["y"])[0]
        y = h["y"][0]
        r = optimize.minimize(lambda b: np.sum(np.exp(X @ b) - y * (X @ b)), np.zeros(X.shape[1]),
                              method="BFGS", options={"gtol": 1e-10})
        worst = max(worst, float(np.max(np.abs(np.exp(X @ r.x) - f) / f)))
    return worst


def check_mle(rng) -> float:
    z = np.concatenate([rng.normal(0.2, 1.7, (20, 550)), rng.normal(4, 1, (20, 50))], axis=1)
    o = truncated_mle(z, np.full(20, -2.0), np.full(20, 2.0))
    worst = 0.0
    for g in range(20):
        x = z[g][(z[g] >= -2) & (z[g] <= 2)]

        def nll(p):
            s = np.exp(p[1])
            return -(stats.norm.logpdf(x, p[0], s).sum()
                     - x.size * np.log(stats.norm.cdf(2, p[0], s) - stats.norm.cdf(-2, p[0], s)))
        r = optimize.minimize(nll, [0, 0], method="Nelder-Mead",
                              options={"xatol": 1e-10, "fatol": 1e-12, "maxiter": 5000})
        worst = max(worst, abs(r.x[0] - o["delta"][g]), abs(np.exp(r.x[1]) - o["sigma"][g]))
    return float(worst)


def check_t_to_z() -> float:
    t = np.linspace(-8, 8, 161)
    worst = 0.0
    for df in (35, 139, 143):
        ref = stats.norm.ppf(stats.t.cdf(t, df))
        worst = max(worst, float(np.max(np.abs(E.t_to_z(t, np.full_like(t, df)) - ref))))
    return worst


def recovery(rng) -> list[dict]:
    rows = []
    for n in (300, 600, 840):
        for sigma in (1.0, 1.5, 2.0):
            n1 = int(0.9 * n)
            z = np.concatenate([rng.normal(0.2, sigma, (500, n1)),
                                rng.choice([-1, 1], (500, n - n1)) * rng.normal(4 * sigma, 1, (500, n - n1))],
                               axis=1)
            f = E.fit_empirical_null(z)
            row = {"N": n, "true_delta0": 0.2, "true_sigma0": sigma, "true_p0": 0.9}
            for e in ("cm", "mle", "loc"):
                s, dl = f[f"{e}_sigma"], f[f"{e}_delta"]
                ok = np.isfinite(s)
                row[e] = {"sigma0_mean": float(np.mean(s[ok])), "sigma0_median": float(np.median(s[ok])),
                          "sigma0_sd": float(np.std(s[ok])), "delta0_mean": float(np.mean(dl[ok])),
                          "delta0_sd": float(np.std(dl[ok])), "p0_median": float(np.nanmedian(f[f"{e}_p0"])),
                          "share_undefined": float(1 - ok.mean())}
            rows.append(row)
    return rows


def _fits(d_batch: np.ndarray) -> dict:
    t, m, fit = grid_t(d_batch)
    return E.fit_empirical_null(flatten_rows(centred(t, m, fit)[1]))


def _draw(design: str, mu: np.ndarray, base: np.ndarray, rng) -> np.ndarray:
    k, n_i, j = mu.shape[0], 36, mu.shape[1]
    if design == "gaussian":
        x = mu[:, None, :] + rng.normal(0, 1, (k, n_i, j))
    else:
        p = np.clip(base[None, None, :] * np.exp(mu[:, None, :] + rng.normal(0, 0.5, (1, n_i, j))), 0, 1)
        x = rng.binomial(16, np.broadcast_to(p, (k, n_i, j))) / 16
    rest = (x.sum(0, keepdims=True) - x) / (k - 1)
    return x - rest


def intervals(rng, n_data: int = 60, n_boot: int = 200) -> dict:
    out = {}
    k, j = 6, 101
    for design in ("gaussian", "binomial_sparse"):
        g = rng.normal(0, 1, (k, j))
        mu = (1.0 / 6.0) * g if design == "gaussian" else 0.1 * g
        base = rng.uniform(0.01, 0.4, j)
        est, axb, jk, ib = [], [], [], []
        for _ in range(n_data):
            d = _draw(design, mu, base, rng)
            o = _fits(d[None])
            est.append([o[f"{e}_sigma"][0] for e in ("cm", "mle", "loc")])
            t, m, fit = grid_t(d)
            u = centred(t, m, fit)[1]
            jdx = rng.integers(0, j, (n_boot, j))
            fa = E.fit_empirical_null(flatten_rows(np.transpose(u[:, jdx], (1, 0, 2))))
            axb.append([np.nanstd(fa[f"{e}_sigma"]) for e in ("cm", "mle", "loc")])
            fj = _fits(np.stack([np.delete(d, i, axis=1) for i in range(d.shape[1])]))
            nj = d.shape[1]
            jk.append([np.sqrt((nj - 1) / nj * np.nansum((fj[f"{e}_sigma"] - np.nanmean(fj[f"{e}_sigma"])) ** 2))
                       for e in ("cm", "mle", "loc")])
            idx = rng.integers(0, d.shape[1], (n_boot, d.shape[1]))
            fb = _fits(np.transpose(d[:, idx, :], (1, 0, 2, 3)))
            ib.append([np.nanmedian(fb[f"{e}_sigma"]) for e in ("cm", "mle", "loc")])
        est, axb, jk, ib = map(np.array, (est, axb, jk, ib))
        out[design] = {e: {"sigma0_mean_over_fresh_draws": float(np.nanmean(est[:, i])),
                           "sigma0_sd_over_fresh_draws": float(np.nanstd(est[:, i])),
                           "axis_block_bootstrap_sd_mean": float(np.nanmean(axb[:, i])),
                           "jackknife_se_mean": float(np.nanmean(jk[:, i])),
                           "instruction_bootstrap_median_minus_estimate_mean":
                               float(np.nanmean(ib[:, i] - est[:, i]))}
                       for i, e in enumerate(("cm", "mle", "loc"))}
        out[design]["n_datasets"] = n_data
        out[design]["n_resamples"] = n_boot
    return out


def _real_grid_task(task: tuple) -> dict:
    index, key, grid = task
    s = next(x for x in subjects() if x.key == key)
    target = load_table(s.target, s.axes, s.level, s.drop)
    d = effects(target)[0][grid]
    n_c, n_i, n_j = d.shape
    rng = np.random.default_rng([SEED, 3, index])
    pairs = {e: [] for e in ("cm", "mle", "loc")}
    block = {e: [] for e in ("cm", "mle", "loc")}
    half = n_i // 2
    for _ in range(REAL_SPLITS):
        order = rng.permutation(n_i)
        both = np.stack([d[:, order[:half]], d[:, order[half:2 * half]]])
        t, m, fit = grid_t(both)
        u = centred(t, m, fit)[1]
        f = E.fit_empirical_null(flatten_rows(u))
        jdx = rng.integers(0, n_j, (REAL_BOOT, n_j))
        fb = E.fit_empirical_null(flatten_rows(np.transpose(u[0][:, jdx], (1, 0, 2))))
        for e in pairs:
            pairs[e].append((f[f"{e}_sigma"][0], f[f"{e}_sigma"][1]))
            ok = np.isfinite(fb[f"{e}_sigma"])
            block[e].append(float(np.std(fb[f"{e}_sigma"][ok])) if ok.sum() > 1 else np.nan)
    out = {"subject": key, "grid": grid, "k": n_c, "instructions": n_i, "axes": n_j,
           "half_instructions": half, "splits": REAL_SPLITS, "axis_block_resamples": REAL_BOOT,
           "seed": [SEED, 3, index]}
    for e in pairs:
        a = np.array(pairs[e], dtype=float)
        ok = np.all(np.isfinite(a), axis=1)
        split_sd = float(np.std(a[ok, 0] - a[ok, 1]) / np.sqrt(2)) if ok.sum() > 2 else None
        bsd = float(np.nanmean(block[e])) if np.any(np.isfinite(block[e])) else None
        out[e] = {"sigma0_half_mean": float(np.mean(a[ok])) if ok.any() else None,
                  "split_half_sd": split_sd, "axis_block_sd_on_half": bsd,
                  "ratio_axis_block_to_split_half": (bsd / split_sd if split_sd and bsd else None),
                  "splits_defined": int(ok.sum())}
    return out


def real_grid_intervals(workers: int) -> list[dict]:
    tasks = [(i, s.key, g) for i, (s, g) in enumerate(
        (s, g) for s in subjects() for g in ("median", "mean"))]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(_real_grid_task, tasks))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    if OUT.exists():
        raise SystemExit(f"{OUT} exists; never overwritten")
    rng = np.random.default_rng(SEED)
    rec = {"seed": SEED, "settings": family_settings(),
           "poisson_fit_max_relative_difference": check_poisson(rng),
           "truncated_mle_max_abs_difference": check_mle(rng),
           "t_to_z_max_abs_difference": check_t_to_z(),
           "recovery": recovery(rng),
           "intervals": intervals(rng),
           "intervals_real_grids": real_grid_intervals(args.workers)}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("x") as fh:
        json.dump(rec, fh, indent=1)
    print(json.dumps({k: v for k, v in rec.items()
                      if k not in ("recovery", "intervals_real_grids", "settings")}, indent=1))
    for r in rec["intervals_real_grids"]:
        print(r["subject"], r["grid"], {e: (r[e]["split_half_sd"], r[e]["axis_block_sd_on_half"],
                                             r[e]["ratio_axis_block_to_split_half"])
                                         for e in ("cm", "mle", "loc")})
    for r in rec["recovery"]:
        print(r["N"], r["true_sigma0"], {e: (round(r[e]["sigma0_median"], 3), round(r[e]["sigma0_sd"], 3),
                                             round(r[e]["share_undefined"], 3)) for e in ("cm", "mle", "loc")})


if __name__ == "__main__":
    main()
