"""The truncated-normal MLE of Efron's empirical null, many rows at once.

The truncated normal is an exponential family in (eta1, eta2) = (delta /
sigma^2, -1 / (2 sigma^2)), so its MLE matches the first two moments of the z
values inside the window. The moments are taken by Simpson quadrature on the
window, which stays defined when the fitted eta2 is not negative. A
non-negative eta2 means the z values inside the window are flatter than any
normal: no finite sigma0 exists, and the fit reports it as such rather than a
number.
"""

from __future__ import annotations

import numpy as np
from scipy import special

__all__ = ["QUAD_POINTS", "truncated_mle"]

QUAD_POINTS = 401


def _quadrature(lo: np.ndarray, hi: np.ndarray):
    """Simpson nodes and weights on each row's window (QUAD_POINTS must be odd)."""
    u = np.linspace(0.0, 1.0, QUAD_POINTS)
    grid = lo[:, None] + (hi - lo)[:, None] * u[None, :]
    w = np.ones(QUAD_POINTS)
    w[1:-1:2], w[2:-1:2] = 4.0, 2.0
    return grid, w


def _expfam_moments(eta: np.ndarray, grid: np.ndarray, w: np.ndarray):
    """E[z], E[z^2], Cov of (z, z^2), and log-partition of exp(eta1 z + eta2 z^2) on grid."""
    s = eta[:, 0:1] * grid + eta[:, 1:2] * grid ** 2
    top = s.max(axis=1, keepdims=True)
    wt = np.exp(s - top) * w[None, :]
    mass = wt.sum(axis=1, keepdims=True)
    p = wt / mass
    e1 = (p * grid).sum(1)
    e2 = (p * grid ** 2).sum(1)
    e3 = (p * grid ** 3).sum(1)
    e4 = (p * grid ** 4).sum(1)
    cov = np.stack([np.stack([e2 - e1 ** 2, e3 - e1 * e2], -1),
                    np.stack([e3 - e1 * e2, e4 - e2 ** 2], -1)], -2)
    log_part = top[:, 0] + np.log(mass[:, 0])
    return e1, e2, cov, log_part


def truncated_mle(z: np.ndarray, lo: np.ndarray, hi: np.ndarray,
                   n_iter: int = 200) -> dict:
    """MLE of N(delta, sigma^2) from the z values inside [lo, hi], per row.

    Damped Newton in the natural parameters, which is concave, on the rows
    still moving; a row stops when its step falls below 1e-11.
    """
    inside = (z >= lo[:, None]) & (z <= hi[:, None]) & ~np.isnan(z)
    n_all = np.sum(~np.isnan(z), axis=1)
    n0 = inside.sum(axis=1)
    zz = np.where(inside, z, 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        m1 = zz.sum(1) / n0
        m2 = (zz ** 2).sum(1) / n0
    usable = (n0 >= 3) & (hi > lo) & np.isfinite(m1)
    grid, w = _quadrature(np.where(usable, lo, -1.0), np.where(usable, hi, 1.0))
    var = np.where(usable, np.maximum(m2 - m1 ** 2, 1e-6), 1.0)
    eta = np.stack([np.where(usable, m1, 0.0) / var, -0.5 / var], axis=1)
    target = np.stack([np.where(usable, m1, 0.0), np.where(usable, m2, 1.0)], axis=1)
    converged = ~usable
    for _ in range(n_iter):
        act = np.flatnonzero(~converged)
        if act.size == 0:
            break
        g_act, e_act, t_act = grid[act], eta[act], target[act]
        e1, e2, cov, a_cur = _expfam_moments(e_act, g_act, w)
        cur = (e_act * t_act).sum(1) - a_cur
        grad = t_act - np.stack([e1, e2], axis=1)
        step = np.linalg.solve(cov + 1e-12 * np.eye(2)[None], grad[..., None])[..., 0]
        scale = np.ones(act.size)
        new = e_act + step
        val = (new * t_act).sum(1) - _expfam_moments(new, g_act, w)[3]
        for _ in range(40):
            worse = val < cur - 1e-14
            if not worse.any():
                break
            scale = np.where(worse, scale / 2, scale)
            new = np.where(worse[:, None], e_act + scale[:, None] * step, new)
            val = np.where(worse, (new * t_act).sum(1)
                           - _expfam_moments(new, g_act, w)[3], val)
        moved = np.max(np.abs(new - e_act), axis=1)
        eta[act] = new
        converged[act] = moved < 1e-11
    exists = usable & (eta[:, 1] < 0)
    reason = np.where(~usable, 1, np.where(~exists, 2, 0))
    with np.errstate(invalid="ignore", divide="ignore"):
        sigma = np.where(exists, np.sqrt(-0.5 / eta[:, 1]), np.nan)
        delta = np.where(exists, eta[:, 0] * sigma ** 2, np.nan)
        cover = special.ndtr((hi - delta) / sigma) - special.ndtr((lo - delta) / sigma)
        p0 = np.where(exists, (n0 / n_all) / cover, np.nan)
    return {"delta": delta, "sigma": sigma, "p0": p0, "n0": n0, "exists": exists,
            "usable": usable, "converged": converged & usable, "lo": lo, "hi": hi,
            "reason": reason}
