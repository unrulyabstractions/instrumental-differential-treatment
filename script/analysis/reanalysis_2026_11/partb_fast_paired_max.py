"""The registered test with its permutation loop batched, for many subsets.

``src.compare.paired_max_statistic.paired_max_test`` draws one
``rng.permutation(n_candidates)`` per (permutation, instruction) and recomputes
the excess for each permutation in a Python loop. A power curve runs that test
on thousands of instruction subsets, so this module does the same arithmetic in
batches:

* ``permutation_orders`` draws the identical orders from the identical stream
  (same seed, same call sequence), so a batch sees exactly the permutations
  the registered test sees. The orders depend only on (seed, R, m, N), so one
  draw serves every subset of the same size.
* A batch of B permutations is laid side by side along the axis dimension and
  passed through the project's own ``excess_effect`` and
  ``standardized_excess``. Both act per (candidate, axis) over instructions, so
  the stacked call computes each permutation exactly as the loop does.
* The single-step maxT adjustment and the outputs follow the registered test
  line for line.

``partb_reproduce_check.py`` asserts that this reproduces the registered test
exactly (statistic, p, null mean and 95th percentile, every surviving pair)
on every run before any other part-B script uses it.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

from src.compare.paired_excess_measures import (cell_rates, excess_effect,
                                                max_abs_statistic,
                                                permutation_tail_share,
                                                standardized_excess)


@lru_cache(maxsize=32)
def permutation_orders(seed: int, n_permutations: int, n_instructions: int,
                       n_candidates: int) -> np.ndarray:
    """(R, m, N) candidate orders, drawn in the registered test's call order."""
    rng = np.random.default_rng(seed)
    out = np.empty((n_permutations, n_instructions, n_candidates), dtype=np.int16)
    for k in range(n_permutations):
        for i in range(n_instructions):
            out[k, i] = rng.permutation(n_candidates)
    out.setflags(write=False)
    return out


def null_maxima(p_t: np.ndarray, p_b: np.ndarray, orders: np.ndarray,
                batch_cells: int = 4_000_000, s_obs: float | None = None,
                stop_above: int | None = None) -> np.ndarray:
    """The max-|t| of every permutation, batched along the axis dimension.

    With ``stop_above``, stops after the batch in which more than that many
    null values reach ``s_obs`` and returns only the permutations drawn so far.
    The tail share can then only grow, so every decision at a level below
    ``(stop_above + 2) / (R + 1)`` is the decision the full null gives.
    """
    n_c, n_i, n_j = p_t.shape
    n_perm = orders.shape[0]
    batch = max(1, batch_cells // (n_c * n_i * n_j))
    ii = np.arange(n_i)[None, :, None]
    null = np.empty(n_perm)
    for start in range(0, n_perm, batch):
        if (stop_above is not None and start > 0
                and int(np.sum(null[:start] >= s_obs)) > stop_above):
            return null[:start]
        o = orders[start:start + batch]                       # (B, m, N)
        b = o.shape[0]
        # pt[c', i, :] = p_t[order_i[c'], i, :], as in the registered loop.
        pt = np.ascontiguousarray(p_t[o, ii].transpose(2, 1, 0, 3)).reshape(n_c, n_i, b * n_j)
        pb = np.ascontiguousarray(p_b[o, ii].transpose(2, 1, 0, 3)).reshape(n_c, n_i, b * n_j)
        t, _, _ = standardized_excess(excess_effect(pt, pb))
        a = np.abs(t).reshape(n_c, b, n_j)
        observed = ~np.isnan(a)
        filled = np.where(observed, a, -np.inf).max(axis=(0, 2))
        # max_abs_statistic returns 0.0 for an all-NaN grid.
        null[start:start + b] = np.where(observed.any(axis=(0, 2)), filled, 0.0)
    return null


def fast_test(target, base, seed: int = 20260726, n_permutations: int = 10000,
              alpha: float = 0.01, full: bool = True, top: int = 12,
              rates: tuple | None = None, stop_above: int | None = None) -> dict:
    """``paired_max_test`` (unsigned) on two BehaviorTables, batched.

    ``rates`` may carry precomputed ``(p_t, p_b)`` from ``cell_rates``.
    ``full=False`` returns only the statistic, the p-value and the verdict.
    ``stop_above`` stops the null early once it holds more exceedances than
    that; the result then carries ``stopped_early`` and a p that is a lower
    bound, and is never ``loyal`` (callers pass a bound above alpha's count).
    """
    if target.principals != base.principals or target.axes != base.axes:
        raise ValueError("target and base must share candidates and axes")
    if target.blocks != base.blocks:
        raise ValueError("target and base were scored on different instruction sets")
    if rates is None:
        p_t, principals, instructions = cell_rates(target)
        p_b, _, _ = cell_rates(base)
    else:
        (p_t, p_b), principals, instructions = rates, list(target.principals), target.blocks
    d = excess_effect(p_t, p_b)
    t_obs, mean_obs, m_obs = standardized_excess(d)
    s_obs = max_abs_statistic(t_obs, False)
    orders = permutation_orders(seed, n_permutations, p_t.shape[1], p_t.shape[0])
    null = null_maxima(p_t, p_b, orders, s_obs=s_obs, stop_above=stop_above)
    if null.size < n_permutations:
        if stop_above is None or (stop_above + 2) / (n_permutations + 1) <= alpha:
            raise ValueError("an early stop must sit above alpha's exceedance count")
        # A lower bound: the exceedances seen so far over the full R.
        return {"statistic": s_obs, "loyal": False, "stopped_early": True,
                "p_family_wise_lower_bound": permutation_tail_share(null, s_obs, n_permutations),
                "permutations_drawn": int(null.size), "n_instructions": len(instructions),
                "n_permutations": n_permutations, "alpha": alpha}
    p_family = permutation_tail_share(null, s_obs, n_permutations)
    out = {"statistic": s_obs, "p_family_wise": p_family, "loyal": bool(p_family <= alpha),
           "stopped_early": False,
           "n_instructions": len(instructions), "n_permutations": n_permutations,
           "alpha": alpha, "null_mean": float(null.mean()),
           "null_p95": float(np.quantile(null, 0.95))}
    if not full:
        return out
    flat = np.abs(t_obs)
    if np.all(np.isnan(flat)):
        raise ValueError("no candidate-axis pair had enough instructions to standardize")
    ci, cj = np.unravel_index(np.nanargmax(flat), flat.shape)
    order = np.argsort(-np.nan_to_num(flat, nan=-np.inf), axis=None)
    adjusted = np.full(flat.size, 1.0)
    running = 0.0
    for idx in order:
        value = flat.ravel()[idx]
        if np.isnan(value):
            continue
        running = max(running, permutation_tail_share(null, value, n_permutations))
        adjusted[idx] = running
    adjusted = adjusted.reshape(flat.shape)
    reject = adjusted <= alpha
    ranked = [tuple(np.unravel_index(i, flat.shape)) for i in order
              if not np.isnan(flat.ravel()[i])]
    out.update({
        "candidates": list(principals), "n_axes": len(target.axes),
        "principal": principals[int(ci)] if out["loyal"] else None,
        "principal_axis": target.axes[int(cj)] if out["loyal"] else None,
        "n_axes_rejected": int(np.any(reject, axis=0).sum()),
        "rejected_axes": sorted({target.axes[j] for _, j in zip(*np.nonzero(reject))}),
        "surviving_pairs": [{"candidate": principals[i], "axis_id": target.axes[j]}
                            for i, j in zip(*np.nonzero(reject))],
        "top_pairs": [{"candidate": principals[i], "axis_id": target.axes[j],
                       "t": float(t_obs[i, j]), "mean_excess": float(mean_obs[i, j]),
                       "instructions": int(m_obs[i, j]),
                       "p_adjusted": float(adjusted[i, j]), "reject": bool(reject[i, j])}
                      for i, j in ranked[:top]],
        "t_grid": t_obs, "m_grid": m_obs,
    })
    return out
