"""Family-wise max-over-axes permutation test for the behavior-axis battery.

Phase 2 measures K axes on the SAME responses, so the K per-prompt deltas are
properties of one matched pair of cells and must travel together: a null
relabeling of a prompt's two groups flips the sign of that prompt's delta on
EVERY axis at once. The null distribution therefore uses one set of sign flips
per permutation, shared across axes — flipping axes independently would
pretend the axes came from independent corpora and shrink the null.

The family statistic is the maximum over axes of the per-axis standardized
delta (Cohen's d_z over prompts), oriented by each axis's preregistered
polarity in the signed variant, or in absolute value in the unsigned variant.
A max — not an average — because the treatment may live on one axis of many
and must not be diluted.

Per-axis adjusted p-values use the single-step maxT rule: every axis's
observed statistic is referred to the same null distribution of the maximum,
which controls the family-wise error for reporting which axes carry the
effect.
"""

import numpy as np

from src.compare.paired_divergence import cohens_dz

__all__ = ["max_over_axes_test"]


def max_over_axes_test(
    deltas_by_axis: dict[str, list[float]],
    polarities: dict[str, int],
    signed: bool = True,
    n_permutations: int = 10000,
    seed: int = 0,
) -> dict:
    """Family-wise test over per-prompt organism-minus-baseline deltas.

    `deltas_by_axis` maps axis_id -> per-prompt deltas, every axis covering the
    same prompts in the same order. `polarities` maps axis_id -> +1/-1, the
    preregistered sign of the predicted organism gap.
    """
    axis_ids = list(deltas_by_axis)
    if not axis_ids:
        raise ValueError("no axes")
    lengths = {axis_id: len(deltas_by_axis[axis_id]) for axis_id in axis_ids}
    if len(set(lengths.values())) != 1:
        raise ValueError(f"axes cover different prompt counts: {lengths}")
    missing = [axis_id for axis_id in axis_ids if axis_id not in polarities]
    if missing:
        raise ValueError(f"axes without a polarity: {missing}")

    n_prompts = lengths[axis_ids[0]]
    # rows: axes, columns: prompts; oriented so the predicted direction is +.
    oriented = np.array(
        [np.asarray(deltas_by_axis[a], dtype=float) * polarities[a] for a in axis_ids]
    )

    def axis_statistics(matrix: np.ndarray) -> np.ndarray:
        stats = np.array([cohens_dz(row.tolist()) for row in matrix], dtype=float)
        return stats if signed else np.abs(stats)

    observed = axis_statistics(oriented)
    family_observed = float(np.max(observed))

    rng = np.random.default_rng(seed)
    null_max = np.empty(n_permutations)
    for k in range(n_permutations):
        flips = rng.choice([-1.0, 1.0], size=n_prompts)  # shared across axes
        null_max[k] = float(np.max(axis_statistics(oriented * flips)))

    def tail_p(value: float) -> float:
        return float((np.sum(null_max >= value) + 1) / (n_permutations + 1))

    return {
        "signed": signed,
        "axis_ids": axis_ids,
        "n_prompts": n_prompts,
        "per_axis_statistic": {a: float(s) for a, s in zip(axis_ids, observed)},
        "per_axis_p_adjusted": {a: tail_p(float(s)) for a, s in zip(axis_ids, observed)},
        "family_statistic": family_observed,
        "family_p": tail_p(family_observed),
        "n_permutations": n_permutations,
        "null_mean": float(np.mean(null_max)),
        "null_p95": float(np.percentile(null_max, 95)),
    }
