"""Grubbs's test over candidate scalars, its exact normal null, and the pre-registered version.

Level 1 of the ladder: the reference is the other k - 1 candidates under a
normal shape assumption. Under independent normal candidate values the
studentized maximum deviate G is free of location and scale, so its null is
exact once the shape is granted. We compute it three ways:

* by Monte Carlo over independent standard normal samples of size k;
* by the Bonferroni bound k * P(T_{k-2} > t(G)), which is exact once G is large
  enough that two points cannot both exceed it;
* by the within-instruction label shuffle the detachment test uses, when a
  caller supplies shuffled peaks.

The pre-registered version names its target before the data are read. Its
studentized deleted residual follows t with k - 2 degrees of freedom.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from scipy import stats

GRUBBS_MC_DRAWS = 1_000_000


def grubbs_statistic(x: np.ndarray, side: str = "two") -> tuple[float, int]:
    """G and the index that attains it. ``side`` is 'two', 'max' or 'min'."""
    x = np.asarray(x, dtype=float)
    z = (x - x.mean()) / x.std(ddof=1)
    if side == "max":
        i = int(np.argmax(z))
        return float(z[i]), i
    if side == "min":
        i = int(np.argmin(z))
        return float(-z[i]), i
    i = int(np.argmax(np.abs(z)))
    return float(abs(z[i])), i


def mean_sd_detachment(x: np.ndarray, i: int) -> float:
    """D: the distance of x_i from the mean of the others in units of their SD."""
    rest = np.delete(np.asarray(x, dtype=float), i)
    return float((x[i] - rest.mean()) / rest.std(ddof=1))


def g_from_detachment(d: float, k: int) -> float:
    """The research notes' identity G^2 = ((k-1)^3/k^2) D^2 / ((k-2) + ((k-1)/k) D^2)."""
    g2 = ((k - 1) ** 3 / k ** 2) * d ** 2 / ((k - 2) + ((k - 1) / k) * d ** 2)
    return float(np.sqrt(g2))


def grubbs_bonferroni_p(g: float, k: int, side: str) -> dict:
    """k * P(T > t(G)) for one side, 2k * ... for two, with the bound's exactness threshold."""
    inside = (k - 1) ** 2 - k * g ** 2
    if inside <= 0:
        return {"p": 0.0, "exact": True, "threshold": None}
    t = g * np.sqrt(k * (k - 2) / inside)
    tail = float(stats.t.sf(t, k - 2))
    mult = 2 * k if side == "two" else k
    threshold = np.sqrt((k - 1) / 2) if side == "two" else np.sqrt((k - 1) * (k - 2) / (2 * k))
    return {"p": min(1.0, mult * tail), "exact": bool(g > threshold),
            "threshold": float(threshold)}


@lru_cache(maxsize=16)
def grubbs_mc_null(k: int, side: str, draws: int = GRUBBS_MC_DRAWS,
                   seed: int = 20260726) -> np.ndarray:
    """G for ``draws`` independent standard normal samples of size k."""
    rng = np.random.default_rng(seed)
    x = rng.standard_normal((draws, k))
    z = (x - x.mean(axis=1, keepdims=True)) / x.std(axis=1, ddof=1, keepdims=True)
    if side == "max":
        return z.max(axis=1)
    if side == "min":
        return -z.min(axis=1)
    return np.abs(z).max(axis=1)


def tail_share(null: np.ndarray, value: float) -> float:
    """Share of the null at least as large, plus-one corrected."""
    return float((1 + np.sum(null >= value)) / (1 + null.size))


def grubbs_test(x: np.ndarray, labels: list[str], side: str,
                permuted: np.ndarray | None = None, alpha: float = 0.01) -> dict:
    """Grubbs's G with every null we hold for it, and the candidate it names."""
    x = np.asarray(x, dtype=float)
    k = x.size
    g, i = grubbs_statistic(x, side)
    mc = grubbs_mc_null(k, side)
    d = mean_sd_detachment(x, i) * (-1 if side == "min" else 1)
    out = {
        "side": side, "k": k, "G": g, "leading": labels[i],
        "mean_sd_detachment_D": d,
        "G_from_D_identity": g_from_detachment(d, k) if side != "two" else None,
        "p_exact_normal_mc": tail_share(mc, g), "mc_draws": int(mc.size),
        "mc_critical_G_at_alpha": float(np.quantile(mc, 1 - alpha)),
        "p_bonferroni": grubbs_bonferroni_p(g, k, side),
        "alpha": alpha,
    }
    if permuted is not None:
        null = np.array([grubbs_statistic(row, side)[0] for row in permuted])
        out["p_permutation"] = tail_share(null[np.isfinite(null)], g)
        out["n_permutations"] = int(null.size)
    out["named"] = labels[i] if out["p_exact_normal_mc"] <= alpha else None
    return out


def deleted_residual_t(x: np.ndarray, i: int, lower: bool) -> dict:
    """(x_i - m_-i) / (s_-i sqrt(1 + 1/(k-1))) ~ t_{k-2}; one-sided in the stated direction."""
    x = np.asarray(x, dtype=float)
    rest = np.delete(x, i)
    n = rest.size
    t = (x[i] - rest.mean()) / (rest.std(ddof=1) * np.sqrt(1 + 1 / n))
    p = float(stats.t.cdf(t, n - 1)) if lower else float(stats.t.sf(t, n - 1))
    return {"t": float(t), "df": n - 1, "p_one_sided": p,
            "direction": "lower" if lower else "higher"}
