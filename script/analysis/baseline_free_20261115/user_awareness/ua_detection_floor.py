"""Detection floors of the user-awareness tests, analytic and by planted shifts.

A test that finds nothing says little until we know the smallest effect it can
see. Two views, both on exchange-blocked mean grades (lower is harsher):

* **Analytic floor.** For the predictive t the decision is a threshold on the
  target's value: it rejects when the target sits at least
  ``|t_crit| * sd * sqrt(1 + 1/n)`` below the pool mean. For the empirical
  calibration p it rejects when the target sits at least
  ``|z_crit| * sqrt(tau^2 + se^2)`` below the fitted mean. We give both at the
  registered alpha and at alpha / 3, the smallest BH threshold over three
  targets. The conformal p and the 84-relabelling permutation have floors above
  alpha, so no shift makes them reject.
* **Planted shifts.** Pool members stand in for targets with a known shift.
  In the *triple* design every set of three pool members is shifted by
  ``-delta`` and tested against the other members, per identity (BH over the
  three) and as a group (exact enumeration). In the *single* design each pool
  member alone is shifted and tested against the rest. The rejection share
  over all triples or members is the power at that shift. Shifting every grade
  of one identity by ``delta`` moves its blocked mean by ``delta`` relative to
  the others, so planting on blocked means is exact.

The reference effect is the direct-grading shift Transluce report for their
famous-AI group (research note ``fairness_audits_without_reference.md``).
"""

from __future__ import annotations

from itertools import combinations

import numpy as np
from scipy import stats

from script.analysis.baseline_free_20261115.user_awareness.transluce_stats import (
    benjamini_hochberg, reml_fit)

ALPHA = 0.01
N_TARGETS = 3
DELTAS = (0.05, 0.11, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.75, 1.00)
TRANSLUCE_REFERENCE = {
    "shift_points": -0.11,
    "what": "direct 1-10 grading, famous-AI group minus general population, Transluce main Claude run",
    "source": "out/main/baseline_free_research_20261115/research_notes/"
              "fairness_audits_without_reference.md (Transluce, User awareness in frontier models)",
}


def analytic_floor(pool: np.ndarray, pool_se2: np.ndarray | None = None,
                   target_se2: float | None = None) -> dict:
    """Shift below the pool centre at which each per-target test first rejects."""
    pool = np.asarray(pool, dtype=float)
    n = pool.size
    sd = pool.std(ddof=1)
    out = {"n_pool": n, "pool_sd": float(sd)}
    for label, a in (("alpha", ALPHA), ("alpha_over_3", ALPHA / N_TARGETS)):
        out[f"predictive_t_{label}"] = float(stats.t.ppf(a, n - 1) * sd * np.sqrt(1 + 1 / n))
    if pool_se2 is not None:
        fit = reml_fit(pool, pool_se2)
        se2 = float(np.median(pool_se2)) if target_se2 is None else float(target_se2)
        scale = np.sqrt(fit["tau2"] + se2)
        out["calibration_tau"] = float(np.sqrt(fit["tau2"]))
        out["calibration_target_se"] = float(np.sqrt(se2))
        for label, a in (("alpha", ALPHA), ("alpha_over_3", ALPHA / N_TARGETS)):
            out[f"calibration_{label}"] = float(stats.norm.ppf(a) * scale)
    out["conformal_floor_p"] = 1.0 / (n + 1)
    out["conformal_can_reject"] = bool(1.0 / (n + 1) <= ALPHA)
    return out


def _bh_any(p: np.ndarray) -> np.ndarray:
    """Per row of an (m, 3) p array: does BH at ALPHA reject at least one target?"""
    return np.array([min(benjamini_hochberg(list(row))) <= ALPHA for row in p])


def planted_triples(pool: np.ndarray, pool_se2: np.ndarray, deltas=DELTAS) -> dict:
    """Every triple of pool members shifted by -delta, tested against the other members."""
    x = np.asarray(pool, dtype=float)
    se2 = np.asarray(pool_se2, dtype=float)
    n = x.size
    trip = np.array(list(combinations(range(n), N_TARGETS)))
    n_ref = n - N_TARGETS
    onehot = np.zeros((trip.shape[0], n), dtype=np.int16)
    np.put_along_axis(onehot, trip, 1, axis=1)
    overlap = onehot @ onehot.T                       # |A ∩ T| for every pair of triples
    s = x[trip].sum(axis=1)
    ss = (x ** 2)[trip].sum(axis=1)
    tot, tot2 = x.sum(), (x ** 2).sum()
    ref_mean = (tot - s) / n_ref
    ref_sd = np.sqrt(((tot2 - ss) - n_ref * ref_mean ** 2) / (n_ref - 1))
    fits = [reml_fit(np.delete(x, t), np.delete(se2, t)) for t in trip]
    mu = np.array([f["mu"] for f in fits])
    tau2 = np.array([f["tau2"] for f in fits])
    rows = []
    for delta in deltas:
        xt = x[trip] - delta                                           # (T, 3)
        t_stat = (xt - ref_mean[:, None]) / (ref_sd[:, None] * np.sqrt(1 + 1 / n_ref))
        p_t = stats.t.cdf(t_stat, n_ref - 1)
        z = (xt - mu[:, None]) / np.sqrt(tau2[:, None] + se2[trip])
        p_c = stats.norm.cdf(z)
        # Group test: shifted pool, exact enumeration over every triple as a relabelling.
        hits = 0
        for lo in range(0, trip.shape[0], 512):
            sub = slice(lo, lo + 512)
            sums = s[None, :] - delta * overlap[sub]                    # (b, T)
            tot_d = tot - N_TARGETS * delta
            gaps = sums / N_TARGETS - (tot_d - sums) / n_ref
            obs = gaps[np.arange(gaps.shape[0]), np.arange(lo, lo + gaps.shape[0])]
            p_g = np.mean(gaps <= obs[:, None] + 1e-12, axis=1)
            hits += int(np.sum(p_g <= ALPHA))
        rows.append({
            "delta_points": -delta,
            "predictive_t_bh_any": float(np.mean(_bh_any(p_t))),
            "calibration_bh_any": float(np.mean(_bh_any(p_c))),
            "group_exact_permutation": hits / trip.shape[0],
        })
    return {"design": f"every triple of the {n} pool members shifted by -delta; reference the "
                      f"other {n_ref}; group test enumerates all {trip.shape[0]} triples",
            "n_triples": int(trip.shape[0]), "n_reference": n_ref,
            "group_floor_p": 1.0 / trip.shape[0], "rows": rows}


def planted_single(pool: np.ndarray, pool_se2: np.ndarray, deltas=DELTAS) -> dict:
    """Each pool member alone shifted by -delta, tested against the rest at ALPHA."""
    x = np.asarray(pool, dtype=float)
    se2 = np.asarray(pool_se2, dtype=float)
    n = x.size
    fits = [reml_fit(np.delete(x, j), np.delete(se2, j)) for j in range(n)]
    rows = []
    for delta in deltas:
        rej_t = rej_c = 0
        for j in range(n):
            rest = np.delete(x, j)
            t = (x[j] - delta - rest.mean()) / (rest.std(ddof=1) * np.sqrt(1 + 1 / (n - 1)))
            rej_t += stats.t.cdf(t, n - 2) <= ALPHA
            z = (x[j] - delta - fits[j]["mu"]) / np.sqrt(fits[j]["tau2"] + se2[j])
            rej_c += stats.norm.cdf(z) <= ALPHA
        rows.append({"delta_points": -delta, "predictive_t": rej_t / n, "calibration": rej_c / n})
    return {"design": f"each of the {n} pool members shifted by -delta; reference the other {n - 1}; "
                      "one target, no multiplicity", "n_members": n, "rows": rows}
