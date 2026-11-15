"""Efron's empirical null fitted to many grids of z values at once.

Three estimators of the null component N(delta0, sigma0^2), all following
``locfdr`` (Efron 2007, arXiv 0710.2245; Efron 2008, arXiv 0808.0572):

- central matching (``cm``): the histogram of z on 120 break points (119 bins,
  locfdr's ``bre = 120``) is smoothed by a Poisson regression on a natural
  cubic spline with 7 degrees of freedom; a quadratic is fitted by least
  squares to the log of that fit over the bins whose centres lie strictly
  inside the central half of the z values (locfdr's ``pct0 = 1/4``).
- truncated-normal MLE on the fixed window |z| <= 2 (``mle``), the "zero
  assumption" of Efron 2007: every z inside the window is a null draw.
- truncated-normal MLE on locfdr's default window (``mle_locfdr``): first the
  median plus or minus ``b * sc``, then the first fit's delta0 plus or minus
  ``b * sigma0``, with ``b = 4.3 exp(-0.26 log10 N)`` and ``sc`` the
  interquartile range over 2 * 0.6745.

The truncated-normal fit lives in ``efron_truncated_mle``.

Every estimator takes a (G, N) array, one grid per row, with NaN padding for
cells that are not fitted. Rows are independent; nothing is shared between
them except the spline basis, which is the same for every row because the bins
are equally spaced between each row's own minimum and maximum.
"""

from __future__ import annotations

import numpy as np
from scipy import special

from script.analysis.baseline_free_20261115.empirical_null.efron_truncated_mle import (
    truncated_mle)

__all__ = ["BREAKS", "SPLINE_DF", "PCT0", "MLE_HALF_WIDTH", "FDR_CUT",
           "t_to_z", "natural_spline_basis", "fit_empirical_null", "local_fdr"]

BREAKS = 120          # locfdr ``bre``: break points, so BREAKS - 1 bins
SPLINE_DF = 7         # locfdr ``df``
PCT0 = 0.25           # locfdr ``pct0``: the central half
MLE_HALF_WIDTH = 2.0  # the fixed window |z| <= 2
FDR_CUT = 0.2


def t_to_z(t: np.ndarray, df: np.ndarray) -> np.ndarray:
    """``Phi^-1(F_df(t))``, computed from the lower tail so large |t| keeps precision."""
    t = np.asarray(t, dtype=float)
    df = np.asarray(df, dtype=float)
    with np.errstate(invalid="ignore", divide="ignore"):
        lower = special.stdtr(np.maximum(df, 1.0), -np.abs(t))
        z = np.sign(t) * -special.ndtri(lower)
    z = np.where(np.isinf(t), t, z)
    return np.where(np.isnan(t) | (df < 1), np.nan, z)


def natural_spline_basis(x: np.ndarray, df: int = SPLINE_DF) -> np.ndarray:
    """A basis spanning R's ``cbind(1, ns(x, df))``: ``df - 1`` interior knots at quantiles.

    The truncated-power form of Hastie, Tibshirani and Friedman (eq. 5.4-5.5),
    orthonormalized by QR. The span, and so every fitted value, equals R's.
    """
    x = np.asarray(x, dtype=float)
    interior = np.quantile(x, np.linspace(0, 1, df + 1)[1:-1])
    knots = np.concatenate([[x.min()], interior, [x.max()]])
    last = knots.size - 1

    def dk(k: int) -> np.ndarray:
        return ((np.maximum(x - knots[k], 0) ** 3 - np.maximum(x - knots[last], 0) ** 3)
                / (knots[last] - knots[k]))

    cols = [np.ones_like(x), x] + [dk(k) - dk(last - 1) for k in range(last - 1)]
    q, _ = np.linalg.qr(np.column_stack(cols))
    return q


def _deviance(Y: np.ndarray, mu: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        term = np.where(Y > 0, Y * np.log(Y / mu), 0.0)
    return 2.0 * np.sum(term - (Y - mu), axis=1)


def _poisson_fit(X: np.ndarray, Y: np.ndarray, maxit: int = 25,
                 epsilon: float = 1e-8) -> np.ndarray:
    """Fitted means of a log-link Poisson regression of each row of Y on X.

    R's ``glm.fit`` with ``poisson()``, row by row: start at y + 0.1, clamp
    the mean and its derivative at machine epsilon, stop a row when its
    deviance changes by less than ``epsilon`` relative to it, at most 25 steps.
    """
    eps = np.finfo(float).eps
    mu = Y + 0.1
    eta = np.log(mu)
    dev_old = _deviance(Y, mu)
    active = np.ones(Y.shape[0], dtype=bool)
    for _ in range(maxit):
        a = np.flatnonzero(active)
        if a.size == 0:
            break
        mu_eta = np.maximum(np.exp(eta[a]), eps)
        work = eta[a] + (Y[a] - mu[a]) / mu_eta
        xtw = X.T[None, :, :] * (mu_eta ** 2 / mu[a])[:, None, :]
        beta = np.linalg.solve(xtw @ X, np.einsum("gpn,gn->gp", xtw, work)[..., None])[..., 0]
        eta[a] = beta @ X.T
        mu[a] = np.maximum(np.exp(eta[a]), eps)
        dev = _deviance(Y[a], mu[a])
        active[a] = ~(np.abs(dev - dev_old[a]) / (np.abs(dev) + 0.1) < epsilon)
        dev_old[a] = dev
    return mu


def _histograms(z: np.ndarray) -> dict:
    """Per row: bin centres, counts (right-closed bins, as R's ``hist``), and the range."""
    lo, up = np.nanmin(z, axis=1), np.nanmax(z, axis=1)
    nb = BREAKS - 1
    width = (up - lo) / nb
    ok = width > 0
    safe = np.where(ok, width, 1.0)
    with np.errstate(invalid="ignore"):
        idx = np.ceil((z - lo[:, None]) / safe[:, None]) - 1
    idx = np.clip(np.nan_to_num(idx, nan=-1), 0, nb - 1).astype(np.int64)
    valid = ~np.isnan(z)
    rows = np.repeat(np.arange(z.shape[0])[:, None], z.shape[1], axis=1)
    counts = np.zeros((z.shape[0], nb))
    np.add.at(counts, (rows[valid], idx[valid]), 1.0)
    centres = lo[:, None] + (np.arange(nb)[None, :] + 0.5) * safe[:, None]
    return {"x": centres, "y": counts, "ok": ok, "lo": lo, "up": up}


def _central_matching(z: np.ndarray, h: dict, f: np.ndarray) -> dict:
    x, logf = h["x"], np.log(f)
    q_lo = np.nanquantile(z, PCT0, axis=1)
    q_hi = np.nanquantile(z, 1 - PCT0, axis=1)
    inside = (x > q_lo[:, None]) & (x < q_hi[:, None])
    xmax = x[np.arange(x.shape[0]), np.argmax(logf, axis=1)]
    xc = x - xmax[:, None]
    X = np.stack([np.ones_like(xc), xc, xc ** 2], axis=-1)
    W = inside.astype(float)
    xtw = np.transpose(X, (0, 2, 1)) * W[:, None, :]
    A = xtw @ X
    enough = inside.sum(axis=1) >= 3
    A[~enough] = np.eye(3)
    co = np.linalg.solve(A, np.einsum("gpn,gn->gp", xtw, logf)[..., None])[..., 0]
    c2 = co[:, 2]
    good = enough & h["ok"] & (c2 < 0)
    with np.errstate(invalid="ignore", divide="ignore"):
        sigma = np.where(good, np.sqrt(-1.0 / (2.0 * c2)), np.nan)
        delta = np.where(good, xmax - co[:, 1] / (2.0 * c2), np.nan)
        l0 = np.einsum("gnp,gp->gn", X, co)
        p0 = np.where(good, np.exp(l0).sum(axis=1) / f.sum(axis=1), np.nan)
    return {"delta": delta, "sigma": sigma, "p0": p0, "l0": l0,
            "n_central_bins": inside.sum(axis=1)}


def fit_empirical_null(z: np.ndarray, with_fdr: bool = False) -> dict:
    """All three estimators on each row of ``z`` (G, N); NaN entries are not fitted.

    With ``with_fdr`` the local fdr of every entry is returned under the
    central-matching and the fixed-window MLE nulls (NaN where not fitted).
    """
    z = np.atleast_2d(np.asarray(z, dtype=float))
    h = _histograms(z)
    nb = BREAKS - 1
    X = natural_spline_basis((np.arange(nb) + 0.5) / nb)
    f = _poisson_fit(X, h["y"])
    cm = _central_matching(z, h, f)
    half = np.full(z.shape[0], MLE_HALF_WIDTH)
    mle = truncated_mle(z, -half, half)

    n = np.sum(~np.isnan(z), axis=1)
    b = 4.3 * np.exp(-0.26 * np.log10(np.maximum(n, 2)))
    q1, med, q3 = np.nanquantile(z, [0.25, 0.5, 0.75], axis=1)
    sc = (q3 - q1) / (2 * special.ndtri(0.75))
    first = truncated_mle(z, med - b * sc, med + b * sc)
    d1 = np.where(first["exists"], first["delta"], med)
    s1 = np.where(first["exists"], first["sigma"], sc)
    loc = truncated_mle(z, d1 - b * s1, d1 + b * s1)

    out = {"n": n, "cm_delta": cm["delta"], "cm_sigma": cm["sigma"], "cm_p0": cm["p0"],
           "cm_central_bins": cm["n_central_bins"],
           "mle_delta": mle["delta"], "mle_sigma": mle["sigma"], "mle_p0": mle["p0"],
           "mle_n0": mle["n0"], "mle_exists": mle["exists"],
           "mle_converged": mle["converged"], "loc_converged": loc["converged"],
           "loc_delta": loc["delta"], "loc_sigma": loc["sigma"], "loc_p0": loc["p0"],
           "loc_n0": loc["n0"], "loc_exists": loc["exists"],
           "loc_window_lo": loc["lo"], "loc_window_hi": loc["hi"]}
    if with_fdr:
        out["fdr_cm"] = local_fdr(z, h["x"], f, np.exp(cm["l0"]))
        f0 = np.exp(-0.5 * ((h["x"] - mle["delta"][:, None]) / mle["sigma"][:, None]) ** 2)
        f0 = f.sum(1, keepdims=True) * f0 / f0.sum(1, keepdims=True)
        out["fdr_mle"] = local_fdr(z, h["x"], f, mle["p0"][:, None] * f0)
    return out


def local_fdr(z: np.ndarray, x: np.ndarray, f: np.ndarray, p0f0: np.ndarray) -> np.ndarray:
    """``min(p0 f0 / f, 1)`` at the bin centres, interpolated to each z (locfdr's ``approx``)."""
    out = np.full(z.shape, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        at_bins = np.minimum(p0f0 / f, 1.0)
    for g in range(z.shape[0]):
        if not np.all(np.isfinite(at_bins[g])):
            continue
        keep = ~np.isnan(z[g])
        out[g, keep] = np.interp(z[g, keep], x[g], at_bins[g])
    return out
