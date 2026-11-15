"""The between-candidate spread of firing rates, net of instruction noise, in percentage points.

sigma0 lives on the t scale, so it grows with the number of instructions and of
samples per cell and cannot be compared across designs. ``tau`` measures the
same generic name effects on the rate scale.

For one axis j, x[c, i] is candidate c's firing rate on instruction i minus the
mean over candidates on that instruction. With xbar_c its mean over
instructions and v_c = var_i(x[c, i]) / n_c the sampling variance of xbar_c,

    tau2_j = (sum_c xbar_c^2 - sum_c v_c) / (k - 1),

which is unbiased for the variance of the candidates' true axis rates when
instructions are independent. tau is 100 sqrt(max(mean_j tau2_j, 0)), the
root mean square over axes. Against a base (or one split half against the
other), x is the difference of the two centred rates on the same instruction,
and tau sizes the target-base difference in candidate effects.

The interval resamples whole axes (1,000 draws, seed [20260726, 2]).
"""

from __future__ import annotations

import warnings

import numpy as np

from script.analysis.baseline_free_20261115.empirical_null.empirical_null_record_parts import pct

__all__ = ["TAU_SEED", "tau_block"]

TAU_SEED = (20260726, 2)


def _centred(p: np.ndarray) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return p - np.nanmean(p, axis=0, keepdims=True)


def _tau2_axes(x: np.ndarray) -> np.ndarray:
    """tau2_j for (k, I, J) centred rates."""
    k = x.shape[0]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        n = np.sum(~np.isnan(x), axis=1)
        xbar = np.nanmean(x, axis=1)
        v = np.nanvar(x, axis=1, ddof=1) / np.maximum(n, 1)
    v = np.where(n >= 2, v, np.nan)
    return (np.nansum(xbar ** 2, axis=0) - np.nansum(v, axis=0)) / (k - 1)


def _tau(mean_tau2):
    return 100.0 * np.sqrt(np.clip(mean_tau2, 0.0, None))


def tau_block(p_t: np.ndarray, p_b: np.ndarray | None = None, keep: np.ndarray | None = None,
              n_boot: int = 1000, seed=TAU_SEED) -> dict:
    """tau of one subject's rates (or of the target-base difference), with its axis-block interval."""
    if keep is not None:
        p_t = p_t[keep]
        p_b = None if p_b is None else p_b[keep]
    x = _centred(p_t) if p_b is None else _centred(p_t) - _centred(p_b)
    t2 = _tau2_axes(x)
    ok = np.isfinite(t2)
    t2 = t2[ok]
    rng = np.random.default_rng(list(seed))
    jdx = rng.integers(0, t2.size, (n_boot, t2.size))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        mean_rate = float(100.0 * np.nanmean(p_t))
    return {"tau_pp": float(_tau(t2.mean())), "mean_tau2": float(t2.mean()),
            "share_axes_tau2_positive": float(np.mean(t2 > 0)), "n_axes": int(t2.size),
            "k": int(x.shape[0]), "mean_rate_pp": mean_rate,
            "axis_block": pct(_tau(t2[jdx].mean(axis=1))),
            "reference": "none" if p_b is None else "paired"}
