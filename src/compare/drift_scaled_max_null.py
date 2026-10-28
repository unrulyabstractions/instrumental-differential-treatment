"""A drift-scaled registered null, the repair tried for the pooled reference (B45).

The pooled within-run reference cannot refer ``S`` to a resampled maximum,
because the reference excludes the row that holds ``S`` and so never reaches
it. What the reference can still measure is scale. Under the permutation null a
pair's |t| has some typical size; under real name-specific drift every pair's
|t| is larger. The ratio of the two medians,

    lambda = median |t| over the reference rows / median |t| over permuted grids,

is a genomic-control style inflation factor. The repaired p-value refers
``S / max(lambda, 1)`` to the registered max-distribution, so the max-versus-max
comparison and the dependence among pairs come from the permutation null, and
only the scale comes from the run. With lambda floored at one the repaired p is
never below the registered p.

The permutations are drawn exactly as ``paired_max_test`` draws them, so the
registered S and p are reproduced on the same null.
"""

from __future__ import annotations

import numpy as np

from src.compare.loser_dispersion_statistic import (_permute, permutation_orders,
                                                    registered_t)
from src.compare.paired_excess_measures import excess_effect, permutation_tail_share

__all__ = ["registered_null", "surviving_candidates", "drift_scaled_p"]


def registered_null(p_t: np.ndarray, p_b: np.ndarray, n_permutations: int,
                    seed: int = 20260726, batch: int = 250) -> dict:
    """The registered max-distribution and the median |t| over permuted grids."""
    d = excess_effect(p_t, p_b)
    orders = permutation_orders(d.shape[0], d.shape[1], n_permutations, seed)
    maxima = np.empty(n_permutations)
    abs_values = []
    for lo in range(0, n_permutations, batch):
        grid = np.abs(registered_t(_permute(d, orders[lo:lo + batch])))
        flat = grid.reshape(grid.shape[0], -1)
        has = np.any(~np.isnan(flat), axis=1)
        maxima[lo:lo + batch] = np.where(
            has, np.nanmax(np.where(np.isnan(flat), -np.inf, flat), axis=1), 0.0)
        abs_values.append(flat[~np.isnan(flat)].astype(np.float32))
    pooled = np.concatenate(abs_values)
    return {"maxima": maxima, "perm_abs_median": float(np.median(pooled)),
            "n_permutations": n_permutations}


def surviving_candidates(abs_t: np.ndarray, maxima: np.ndarray, alpha: float
                         ) -> frozenset[int]:
    """Candidates with a pair rejected by the single-step maxT adjustment.

    Sorted descending, the raw tail shares only grow, so the running maximum of
    ``paired_max_test`` equals each pair's own tail share.
    """
    n = maxima.size
    out = set()
    for c, j in zip(*np.nonzero(~np.isnan(abs_t))):
        if permutation_tail_share(maxima, float(abs_t[c, j]), n) <= alpha:
            out.add(int(c))
    return frozenset(out)


def drift_scaled_p(s: float, maxima: np.ndarray, ref_median: float,
                   perm_median: float) -> dict:
    """lambda and the repaired p, floored and unfloored."""
    lam = float(ref_median / perm_median) if perm_median > 0 else float("nan")
    n = maxima.size
    floored = max(lam, 1.0) if np.isfinite(lam) else float("nan")
    return {"lambda": lam,
            "p_registered": permutation_tail_share(maxima, s, n),
            "p_scaled": permutation_tail_share(maxima, s / floored, n)
            if np.isfinite(floored) else None,
            "p_scaled_unfloored": permutation_tail_share(maxima, s / lam, n)
            if np.isfinite(lam) and lam > 0 else None}
