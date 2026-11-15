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

Writes ``estimator_check.json``; refuses to overwrite it.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy import optimize, stats

from script.analysis.baseline_free_20261115.empirical_null import efron_null_estimators as E
from script.analysis.baseline_free_20261115.empirical_null.efron_truncated_mle import truncated_mle
from script.analysis.baseline_free_20261115.empirical_null.empirical_null_grids import (
    centred, flatten_rows, grid_t)

OUT = Path("out/main/baseline_free_20261115/empirical_null/estimator_check.json")
SEED = 20260726


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


def main() -> None:
    if OUT.exists():
        raise SystemExit(f"{OUT} exists; never overwritten")
    rng = np.random.default_rng(SEED)
    rec = {"seed": SEED,
           "poisson_fit_max_relative_difference": check_poisson(rng),
           "truncated_mle_max_abs_difference": check_mle(rng),
           "t_to_z_max_abs_difference": check_t_to_z(),
           "recovery": recovery(rng),
           "intervals": intervals(rng)}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("x") as fh:
        json.dump(rec, fh, indent=1)
    print(json.dumps({k: v for k, v in rec.items() if k != "recovery"}, indent=1))
    for r in rec["recovery"]:
        print(r["N"], r["true_sigma0"], {e: (round(r[e]["sigma0_median"], 3), round(r[e]["sigma0_sd"], 3),
                                             round(r[e]["share_undefined"], 3)) for e in ("cm", "mle", "loc")})


if __name__ == "__main__":
    main()
