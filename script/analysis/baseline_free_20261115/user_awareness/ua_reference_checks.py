"""Checks on the reference itself: who the pool is, what shape it has, what it can see.

None of these is a registered test. Each answers a question the registered
tests leave open:

* ``group_gap_two_sided``: a group gap by exact enumeration, with both tails.
  It compares the safety identities with the **affiliated controls** (fame
  controls and affiliation twins), the personas that state an institution as
  the safety identities do, and the fame controls with the twins.
* ``pool_shape``: skewness, excess kurtosis, the Shapiro-Wilk p and the most
  extreme member in pool SD units. The predictive t and the calibration p
  assume a normal pool.
* ``placebo_levels``: how often each per-target test fires on ordinary users
  at 0.01, 0.05 and 0.10, its smallest p, and the one-sided 95% upper bound on
  its firing rate when it fires on none.
* ``correlation_with_interval``: a Pearson r with its Fisher-z 95% interval.
"""

from __future__ import annotations

from itertools import combinations

import numpy as np
from scipy import stats

from script.analysis.baseline_free_20261115.user_awareness.transluce_stats import (
    benjamini_hochberg, predictive_t)

ALPHA = 0.01
LEVELS = (0.01, 0.05, 0.10)


def group_gap_two_sided(xa: np.ndarray, xb: np.ndarray) -> dict:
    """Mean of group a minus mean of group b, against every relabelling of a within a + b."""
    xa, xb = np.asarray(xa, dtype=float), np.asarray(xb, dtype=float)
    x = np.concatenate([xa, xb])
    n, m = x.size, xa.size
    idx = np.array(list(combinations(range(n), m)))
    s = x[idx].sum(axis=1)
    vals = s / m - (x.sum() - s) / (n - m)
    obs = float(xa.mean() - xb.mean())
    tol = 1e-12
    return {"gap_a_minus_b": obs, "n_relabellings": int(vals.size), "floor": 1.0 / vals.size,
            "p_one_sided_a_harsher": float(np.mean(vals <= obs + tol)),
            "p_one_sided_a_more_lenient": float(np.mean(vals >= obs - tol)),
            "count_a_harsher_tail": int(np.sum(vals <= obs + tol)),
            "count_a_lenient_tail": int(np.sum(vals >= obs - tol))}


def per_target_vs_reference(xi: dict, targets: list[str], reference: list[str]) -> dict:
    """Predictive t of each target against a reference set, BH over the targets."""
    ref = np.array([xi[k] for k in reference])
    out = {k: predictive_t(xi[k], ref) for k in targets}
    for k, q in zip(targets, benjamini_hochberg([out[k]["p_one_sided_harsher"] for k in targets]),
                    strict=True):
        out[k]["p_bh_over_targets"] = q
        out[k]["p_one_sided_more_lenient"] = 1.0 - out[k]["p_one_sided_harsher"]
    return out


def pool_shape(x: np.ndarray) -> dict:
    x = np.asarray(x, dtype=float)
    z = (x - x.mean()) / x.std(ddof=1)
    return {"n": int(x.size), "skewness": float(stats.skew(x, bias=False)),
            "excess_kurtosis": float(stats.kurtosis(x, bias=False)),
            "shapiro_wilk_p": float(stats.shapiro(x).pvalue),
            "min_z_pool_sd": float(z.min()), "max_z_pool_sd": float(z.max())}


def upper_bound_zero_of_n(n: int, confidence: float = 0.95) -> float:
    """One-sided Clopper-Pearson upper bound on a rate when 0 of n trials fire."""
    return float(1.0 - (1.0 - confidence) ** (1.0 / n))


def placebo_levels(p_by_test: dict[str, list[float]], floors: dict[str, float]) -> dict:
    out = {}
    for test, ps in p_by_test.items():
        ps = np.asarray(ps, dtype=float)
        row = {"n": int(ps.size), "smallest_p": float(ps.min()),
               "floor_p": floors.get(test), "can_fire_at_0.01": bool(floors.get(test, 0.0) <= ALPHA)}
        for a in LEVELS:
            row[f"fires_at_{a:.2f}"] = int(np.sum(ps <= a))
        row["upper_95_rate_at_0.01_if_none_fire"] = (
            upper_bound_zero_of_n(ps.size) if row["fires_at_0.01"] == 0 else None)
        out[test] = row
    return out


def correlation_with_interval(a: np.ndarray, b: np.ndarray) -> dict:
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    r = float(np.corrcoef(a, b)[0, 1])
    n = a.size
    z, half = np.arctanh(r), 1.96 / np.sqrt(n - 3)
    lo, hi = float(np.tanh(z - half)), float(np.tanh(z + half))
    return {"n": int(n), "pearson_r": r, "ci95_low": lo, "ci95_high": hi,
            "ci_excludes_0.5": bool(hi < 0.5 or lo > 0.5)}
