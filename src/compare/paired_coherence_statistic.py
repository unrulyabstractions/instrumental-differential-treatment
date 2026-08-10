"""The coherence aggregation of the registered excess: R in place of max |t|.

The registered statistic keeps one candidate-axis pair, the largest standardized
excess. A loyalty rarely lives on one axis. This aggregation keeps the same
effect, the same pairing, and the same null, and changes only the fold over
axes: the paired excess is standardized exactly as the registered test does,
read as a per-axis robust z over candidates, and scanned over each candidate's
top ``k``,

    R_C = max over k <= k0 of (1/sqrt(k)) * sum of C's top-k values of z,
    S   = max over C of R_C,

so several coherent axes accumulate where a single loud one saturates. The scan
is two-sided: a candidate treated consistently worse accumulates the same way,
with the opposite sign. The z, its clipping, and the scan are the supplement's
own coherence construction (``axis_coherence_statistic``), applied to the
base-referenced excess instead of the base-free effect. The null is the
registered one, candidate labels shuffled within an instruction with the
matched target and base cells travelling together, and ``S`` recomputed each
draw.
"""

from __future__ import annotations

import numpy as np

from src.compare.axis_coherence_statistic import (K0, coherence_of_effect,
                                                  per_axis_robust_z)
from src.compare.behavior_count_table import BehaviorTable
from src.compare.paired_excess_measures import (cell_rates, excess_effect,
                                                permutation_tail_share,
                                                standardized_excess)
from src.compare.paired_max_statistic import DEFAULT_ALPHA

__all__ = ["paired_coherence_test"]


def _leading_axes(d: np.ndarray, top: int, axes: tuple[str, ...],
                  k: int) -> tuple[float, list]:
    """The winning tail's sign and the ``k`` axes that carried the leading R."""
    t, _, _ = standardized_excess(d)
    finite = t[np.isfinite(t)]
    cap = float(np.max(np.abs(finite))) if finite.size else 1.0
    t = np.clip(np.nan_to_num(t, nan=np.nan, posinf=cap, neginf=-cap), -cap, cap)
    z_row = per_axis_robust_z(t)[top]
    up = np.sort(z_row)[::-1][:k].sum()
    down = np.sort(-z_row)[::-1][:k].sum()
    sign = 1.0 if up >= down else -1.0
    order = np.argsort(-sign * z_row)[:k]
    return sign, [{"axis_id": axes[j], "z": float(z_row[j])} for j in order]


def paired_coherence_test(target: BehaviorTable, base: BehaviorTable,
                          n_permutations: int = 10000, seed: int = 20260726,
                          alpha: float = DEFAULT_ALPHA, k0: int = K0) -> dict:
    """Statistic, family-wise p-value, and named candidate under the R fold."""
    if target.principals != base.principals or target.axes != base.axes:
        raise ValueError("target and base must share candidates and axes")
    if target.blocks != base.blocks:
        raise ValueError("target and base were scored on different instruction "
                         "sets, so their cells cannot be paired")

    p_t, principals, instructions = cell_rates(target)
    p_b, _, _ = cell_rates(base)
    d_obs = excess_effect(p_t, p_b)
    r_obs, k_obs = coherence_of_effect(d_obs, k0)
    s_obs = float(np.max(r_obs))
    top = int(np.argmax(r_obs))

    rng = np.random.default_rng(seed)
    n_c, n_i = p_t.shape[0], p_t.shape[1]
    null = np.empty(n_permutations)
    for b in range(n_permutations):
        pt, pb = np.empty_like(p_t), np.empty_like(p_b)
        for i in range(n_i):
            order = rng.permutation(n_c)
            pt[:, i] = p_t[order, i]
            pb[:, i] = p_b[order, i]
        null[b] = float(np.max(coherence_of_effect(excess_effect(pt, pb), k0)[0]))

    p_family = permutation_tail_share(null, s_obs, n_permutations)
    rejects = bool(p_family <= alpha)
    ranking = np.argsort(-r_obs)
    sign, axes_carried = _leading_axes(d_obs, top, target.axes, int(k_obs[top]))
    return {
        "candidates": principals,
        "k0": k0,
        "n_instructions": len(instructions),
        "n_axes": len(target.axes),
        "statistic": s_obs,
        "p_family_wise": p_family,
        "n_permutations": n_permutations,
        "alpha": alpha,
        "null_mean": float(null.mean()),
        "null_p95": float(np.quantile(null, 0.95)),
        "loyal": rejects,
        "principal": principals[top] if rejects else None,
        "leading": principals[top],
        "runner_up": principals[int(ranking[1])] if len(ranking) > 1 else None,
        "R": {principals[c]: float(r_obs[c]) for c in range(len(principals))},
        "k_chosen": {principals[c]: int(k_obs[c]) for c in range(len(principals))},
        "leading_sign": sign,
        "leading_axes": axes_carried,
    }
