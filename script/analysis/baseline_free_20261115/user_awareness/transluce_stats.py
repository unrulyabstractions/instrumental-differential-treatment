"""The Transluce-style statistics, on exchange-blocked identity means.

Every function reads one subject's identity values ``x`` (lower is harsher) and,
where needed, their sampling-noise variances ``se2``. The reference is always a
pool of ordinary users, so a name effect that every ordinary user carries is
part of the null rather than evidence against it.

* ``predictive_t``: one identity against the pool's predictive distribution,
  t with n_pool - 1 degrees of freedom, one-sided toward harsher grades.
* ``whole_user_permutation``: the safety group's mean minus the pool's mean,
  referred to every relabelling of which identities are "safety". Enumerated
  exactly, so its floor is 1 / C(n_pool + n_safety, n_safety).
* ``conformal_p``: rank of one identity among the pool, (1 + #{pool <= x}) / (n + 1).
* ``reml_calibration``: fit N(mu, tau^2 + se_j^2) to the pool by REML and refer
  the identity to N(mu, tau^2 + se^2).
* ``cochran_q``: between-identity heterogeneity beyond sampling noise.
* ``benjamini_hochberg``: step-up adjusted p values within one subject.
"""

from __future__ import annotations

from itertools import combinations
from math import comb

import numpy as np
from scipy import optimize, stats


def predictive_t(x_target: float, pool: np.ndarray) -> dict:
    """Leave-one-out predictive t of one identity against a pool, one-sided lower."""
    pool = np.asarray(pool, dtype=float)
    n = pool.size
    t = (x_target - pool.mean()) / (pool.std(ddof=1) * np.sqrt(1 + 1 / n))
    return {"t": float(t), "df": n - 1, "p_one_sided_harsher": float(stats.t.cdf(t, n - 1)),
            "pool_mean": float(pool.mean()), "pool_sd": float(pool.std(ddof=1)), "n_pool": n}


def benjamini_hochberg(p: list[float]) -> list[float]:
    """BH adjusted p values in the input order."""
    p = np.asarray(p, dtype=float)
    m = p.size
    order = np.argsort(p)
    adj = np.empty(m)
    running = 1.0
    for rank in range(m, 0, -1):
        idx = order[rank - 1]
        running = min(running, p[idx] * m / rank)
        adj[idx] = running
    return [float(v) for v in adj]


def whole_user_permutation(x: np.ndarray, is_target: np.ndarray) -> dict:
    """Exact enumeration of every relabelling of the target group within target plus pool."""
    x = np.asarray(x, dtype=float)
    is_target = np.asarray(is_target, dtype=bool)
    n, m = x.size, int(is_target.sum())

    def gap(mask):
        return x[mask].mean() - x[~mask].mean()

    observed = gap(is_target)
    values = []
    for subset in combinations(range(n), m):
        mask = np.zeros(n, dtype=bool)
        mask[list(subset)] = True
        values.append(gap(mask))
    values = np.array(values)
    # Lower is harsher, so the tail is relabellings with a gap at most as large.
    tol = 1e-12
    p = float(np.mean(values <= observed + tol))
    return {"gap_target_minus_pool": float(observed), "n_relabellings": int(values.size),
            "expected_relabellings": comb(n, m), "p_one_sided_harsher": p,
            "floor": 1.0 / values.size}


def conformal_p(x_target: float, pool: np.ndarray) -> dict:
    """Design-based rank p among the pool: (1 + #{pool <= target}) / (n + 1), harsher side."""
    pool = np.asarray(pool, dtype=float)
    p = (1 + int(np.sum(pool <= x_target))) / (pool.size + 1)
    return {"p_one_sided_harsher": float(p), "n_pool": int(pool.size), "floor": 1 / (pool.size + 1)}


def reml_fit(y: np.ndarray, se2: np.ndarray) -> dict:
    """REML estimate of mu and tau^2 for y_j ~ N(mu, tau^2 + se2_j)."""
    y, se2 = np.asarray(y, dtype=float), np.asarray(se2, dtype=float)

    def neg_reml(log_tau2):
        v = np.exp(log_tau2) + se2
        w = 1 / v
        mu = np.sum(w * y) / np.sum(w)
        return 0.5 * (np.sum(np.log(v)) + np.log(np.sum(w)) + np.sum(w * (y - mu) ** 2))

    res = optimize.minimize_scalar(neg_reml, bounds=(-30.0, 5.0), method="bounded")
    tau2 = float(np.exp(res.x))
    # A tau^2 at the lower bound means the pool shows no spread beyond noise.
    if neg_reml(-30.0) <= res.fun + 1e-12:
        tau2 = 0.0
    w = 1 / (tau2 + se2)
    mu = float(np.sum(w * y) / np.sum(w))
    return {"mu": mu, "tau2": tau2, "var_mu": float(1 / np.sum(w)), "n_pool": int(y.size)}


def reml_calibration(x_target: float, se2_target: float, pool: np.ndarray,
                     pool_se2: np.ndarray) -> dict:
    """Empirical-calibration p (Schuemie): the target against N(mu, tau^2 + se^2), harsher side."""
    fit = reml_fit(pool, pool_se2)
    sd = np.sqrt(fit["tau2"] + se2_target)
    z = (x_target - fit["mu"]) / sd
    sd_pred = np.sqrt(fit["tau2"] + se2_target + fit["var_mu"])
    return {**fit, "z": float(z), "p_one_sided_harsher": float(stats.norm.cdf(z)),
            "p_one_sided_harsher_with_mu_uncertainty":
                float(stats.norm.cdf((x_target - fit["mu"]) / sd_pred))}


def cochran_q(x: np.ndarray, se2: np.ndarray) -> dict:
    """Q, its chi-square p, the DerSimonian-Laird tau^2 and I^2 for identity means."""
    x, se2 = np.asarray(x, dtype=float), np.asarray(se2, dtype=float)
    # An identity whose every cell is unanimous has no measured noise; it takes the
    # smallest measured noise of the subject rather than an infinite weight.
    floored = int(np.sum(se2 <= 0))
    if floored:
        se2 = np.where(se2 > 0, se2, np.min(se2[se2 > 0]))
    w = 1 / se2
    mu = np.sum(w * x) / np.sum(w)
    q = float(np.sum(w * (x - mu) ** 2))
    df = x.size - 1
    c = np.sum(w) - np.sum(w ** 2) / np.sum(w)
    tau2 = max(0.0, (q - df) / c)
    return {"Q": q, "df": df, "p_chi2": float(stats.chi2.sf(q, df)), "se2_floored": floored,
            "tau2_DL": float(tau2),
            "tau_DL": float(np.sqrt(tau2)), "I2": float(max(0.0, (q - df) / q)) if q > 0 else 0.0}
