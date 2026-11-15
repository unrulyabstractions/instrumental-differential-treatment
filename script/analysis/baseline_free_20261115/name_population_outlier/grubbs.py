"""Grubbs's test, the deleted residual, the rank p, and their exact normal nulls.

Each candidate c gets one scalar x_c (its peak |t| over axes, or its row RMS of t).
Three Level-1 questions are asked of the k scalars.

- **Grubbs form, top chosen as the maximum.** D = (x_top - mean_others) / sd_others,
  with the others' mean and SD (ddof 1). Grubbs's maximum studentized deviate G uses
  the mean and SD of all k values, and the two are tied exactly by

      G^2 = ((k-1)^3/k^2) D^2 / ((k-2) + ((k-1)/k) D^2),

  so G rises with D and stays below its ceiling (k-1)/sqrt(k). Under i.i.d. normal
  scalars the null of G is location- and scale-free; ``grubbs_null`` draws it by
  Monte Carlo and ``grubbs_bound_p`` gives the classical t-relation bound
  k * P(T_{k-2} > t_G), where t_G is exactly the top candidate's deleted residual.
- **Deleted residual for a pre-registered target.**
  r_c = (x_c - m_{-c}) / (s_{-c} sqrt(1 + 1/(k-1))) follows t with k-2 degrees of
  freedom under a normal random-effects null. It is read one-sided upward.
- **Rank p.** #{j : x_j >= x_c} / k, exact under exchangeability alone and never
  below 1/k.

Conventions for infinite scalars follow ``candidate_detachment_measures.detachment``:
an infinite scalar is the registered test's mark of an effect that held on every
instruction. A leader that is infinite against finite others has D = inf and G at
its ceiling. A leader tied with an infinite other has D = 0. A zero spread of the
others gives D = inf when the leader is above them and 0 otherwise.
"""

from __future__ import annotations

import math

import numpy as np
from scipy import stats

__all__ = ["G_from_D", "grubbs_direct", "grubbs_top", "deleted_residuals", "rank_p",
           "t_sf", "grubbs_bound_p", "grubbs_bound_p_from_r", "grubbs_null", "mc_tail_p", "holm",
           "clopper_pearson", "G_MAX"]


def G_MAX(k: int) -> float:
    """The largest value Grubbs's G can take with k values."""
    return (k - 1) / math.sqrt(k)


def G_from_D(D, k: int):
    """Grubbs's G from the detachment-style D (top against the mean of the others)."""
    D = np.asarray(D, dtype=float)
    with np.errstate(invalid="ignore", divide="ignore", over="ignore"):
        g2 = ((k - 1) ** 3 / k ** 2) * D ** 2 / ((k - 2) + ((k - 1) / k) * D ** 2)
        g = np.sqrt(g2)
    g = np.where(np.isinf(D), G_MAX(k), g)
    return g if g.ndim else float(g)


def grubbs_direct(x: np.ndarray) -> float:
    """Grubbs's G for the maximum, from the mean and SD of all values."""
    x = np.asarray(x, dtype=float)
    return float((x.max() - x.mean()) / x.std(ddof=1))


def grubbs_top(x: np.ndarray) -> tuple[float, float, int, int]:
    """(D, G, index of the leader, k used) for one vector of candidate scalars."""
    x = np.asarray(x, dtype=float)
    usable = np.flatnonzero(~np.isnan(x))
    k = usable.size
    if k < 3:
        return float("nan"), float("nan"), -1, k
    lead = int(usable[np.argmax(x[usable])])
    rest = x[np.setdiff1d(usable, [lead])]
    top = x[lead]
    if np.any(np.isinf(rest)):
        # The leader is the maximum, so an infinite other means the leader is
        # infinite too and is one of a crowd.
        return 0.0, 0.0, lead, k
    if np.isinf(top):
        return float("inf"), G_MAX(k), lead, k
    sd = float(np.std(rest, ddof=1))
    gap = float(top - np.mean(rest))
    if sd <= 0:
        D = float("inf") if gap > 0 else 0.0
    else:
        D = gap / sd
    return D, float(G_from_D(D, k)), lead, k


def deleted_residuals(x: np.ndarray) -> np.ndarray:
    """Every candidate's studentized deleted residual against the other k-1 scalars."""
    x = np.asarray(x, dtype=float)
    out = np.full(x.shape, np.nan)
    usable = np.flatnonzero(~np.isnan(x))
    k = usable.size
    if k < 3:
        return out
    scale = math.sqrt(1.0 + 1.0 / (k - 1))
    for c in usable:
        rest = x[np.setdiff1d(usable, [c])]
        xc = x[c]
        if np.any(np.isinf(rest)):
            out[c] = 0.0 if np.isinf(xc) else -np.inf
            continue
        if np.isinf(xc):
            out[c] = np.inf
            continue
        sd = float(np.std(rest, ddof=1))
        gap = float(xc - np.mean(rest))
        if sd <= 0:
            out[c] = np.inf if gap > 0 else (-np.inf if gap < 0 else 0.0)
        else:
            out[c] = gap / (sd * scale)
    return out


def rank_p(x: np.ndarray) -> np.ndarray:
    """Each candidate's exchangeability rank p, #{j : x_j >= x_c} / k (floor 1/k)."""
    x = np.asarray(x, dtype=float)
    out = np.full(x.shape, np.nan)
    usable = ~np.isnan(x)
    k = int(usable.sum())
    for c in np.flatnonzero(usable):
        out[c] = float(np.sum(x[usable] >= x[c])) / k
    return out


def t_sf(r, df: int):
    """One-sided upper tail of t with ``df`` degrees of freedom; inf maps to 0."""
    r = np.asarray(r, dtype=float)
    p = stats.t.sf(r, df)
    p = np.where(np.isposinf(r), 0.0, np.where(np.isneginf(r), 1.0, p))
    return p if p.ndim else float(p)


def grubbs_bound_p(G: float, k: int) -> float:
    """The classical bound k * P(T_{k-2} > t_G), with t_G^2 = k(k-2)G^2/((k-1)^2 - kG^2)."""
    if not np.isfinite(G):
        return float("nan")
    denom = (k - 1) ** 2 - k * G ** 2
    if denom <= 0:
        return 0.0
    t = math.sqrt(k * (k - 2) * G ** 2 / denom)
    return float(min(1.0, k * stats.t.sf(t, k - 2)))


def grubbs_bound_p_from_r(r_lead: float, k: int) -> float:
    """The same bound from the leader's deleted residual, which equals t_G exactly.

    Computing t_G from G cancels badly near G's ceiling at small k (at k = 3 the
    denominator (k-1)^2 - kG^2 nearly vanishes), so the engine reads the bound
    off the deleted residual instead.
    """
    if np.isnan(r_lead):
        return float("nan")
    return float(min(1.0, k * float(t_sf(r_lead, k - 2))))


def grubbs_null(ks=range(3, 12), n_draws: int = 1_000_000, seed: int = 20260726,
                chunk: int = 200_000) -> dict[int, dict[str, np.ndarray]]:
    """Sorted Monte Carlo nulls of G and D under i.i.d. standard normal scalars.

    One generator seeded ``seed`` draws k = 3, 4, ... in order, each as
    ``n_draws`` rows of k standard normals in chunks of ``chunk`` rows.
    """
    rng = np.random.default_rng(seed)
    out = {}
    for k in ks:
        gs, ds = [], []
        left = n_draws
        while left:
            m = min(chunk, left)
            z = rng.standard_normal((m, k))
            z.sort(axis=1)
            top, rest = z[:, -1], z[:, :-1]
            D = (top - rest.mean(axis=1)) / rest.std(axis=1, ddof=1)
            ds.append(D)
            gs.append(G_from_D(D, k))
            left -= m
        out[k] = {"G": np.sort(np.concatenate(gs)), "D": np.sort(np.concatenate(ds))}
    return out


def mc_tail_p(sorted_null: np.ndarray, value: float) -> float:
    """(1 + #{null >= value}) / (1 + n), read off a sorted Monte Carlo null."""
    if np.isnan(value):
        return float("nan")
    n = sorted_null.size
    at_least = n - int(np.searchsorted(sorted_null, value, side="left"))
    return (1.0 + at_least) / (1.0 + n)


def holm(pvals: dict[str, float]) -> dict[str, float]:
    """Holm step-down adjusted p values over a small named family."""
    items = [(k, v) for k, v in pvals.items() if v is not None and not np.isnan(v)]
    items.sort(key=lambda kv: kv[1])
    m = len(items)
    out: dict[str, float] = {k: float("nan") for k in pvals}
    running = 0.0
    for i, (k, v) in enumerate(items):
        running = max(running, min(1.0, (m - i) * v))
        out[k] = running
    return out


def clopper_pearson(k: int, n: int, level: float = 0.95) -> list[float]:
    tail = (1.0 - level) / 2.0
    lo = 0.0 if k == 0 else float(stats.beta.ppf(tail, k, n - k + 1))
    hi = 1.0 if k == n else float(stats.beta.ppf(1.0 - tail, k + 1, n - k))
    return [lo, hi]
