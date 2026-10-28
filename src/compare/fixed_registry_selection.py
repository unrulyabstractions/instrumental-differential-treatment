"""A fixed axis registry frozen before the run under test is read (B49).

The registered test runs on about a hundred Conjecturer axes chosen per run.
A fixed registry instead freezes about 25 axes before collection. Two honest
ways to freeze one from stored data, neither of which reads the run under test:

- from a pilot share of the run's own instructions, tested on the rest
  (``src.compare.axis_pruning_selection``);
- from the other runs of the same design (leave one run out). Each other run
  contributes one per-axis score with equal weight, so a positive cannot
  outweigh the null controls, and the mean score ranks the axes.

This module holds the leave-one-run-out scores and the name the registered
naming rule gives at a second alpha. Nothing here changes the test.
"""

from __future__ import annotations

import numpy as np

from src.compare.behavior_count_table import BehaviorTable
from src.compare.paired_excess_measures import (cell_rates, excess_effect,
                                                standardized_excess)
from src.compare.principal_attribution import attribute_principal

__all__ = ["max_abs_t_by_axis", "mean_pool_score", "name_at_alpha"]


def max_abs_t_by_axis(target: BehaviorTable, base: BehaviorTable) -> np.ndarray:
    """Per axis, the largest |t| over candidates of the run's registered excess.

    A pair that cannot be standardized counts as zero; an infinite |t| (zero
    spread, nonzero mean) is kept infinite, as the registered test reads it.
    """
    p_t, _, _ = cell_rates(target)
    p_b, _, _ = cell_rates(base)
    t, _, _ = standardized_excess(excess_effect(p_t, p_b))
    return np.max(np.nan_to_num(np.abs(t), nan=0.0, posinf=np.inf), axis=0)


def mean_pool_score(scores: list[np.ndarray], axes: list[tuple[str, ...]],
                    held_axes: tuple[str, ...]) -> np.ndarray:
    """The equal-weight mean of each pool run's per-axis score, in ``held_axes`` order.

    Axes are matched by identity: every pool run must carry exactly the held-out
    run's registry, so no axis is guessed across registries. An infinite score
    is capped at the largest finite score of its run (or 1 when it has none),
    so one degenerate pair cannot make the mean infinite.
    """
    if not scores:
        raise ValueError("an empty pool cannot freeze a registry")
    rows = []
    for s, a in zip(scores, axes, strict=True):
        if tuple(a) != tuple(held_axes):
            raise ValueError("a pool run does not share the held-out run's registry")
        s = np.asarray(s, dtype=float)
        finite = s[np.isfinite(s)]
        cap = float(finite.max()) if finite.size and finite.max() > 0 else 1.0
        rows.append(np.where(np.isinf(s), cap, s))
    return np.mean(rows, axis=0)


def name_at_alpha(result: dict, alpha: float) -> dict:
    """The registered naming rule applied at ``alpha`` instead of the run's own.

    ``result`` is a ``paired_max_test`` result whose ``top_pairs`` lists every
    standardizable pair (call it with a large ``top``). The surviving pairs at
    ``alpha`` are the pairs whose single-step adjusted p is at most ``alpha``.
    """
    pairs = result["top_pairs"]
    loyal = bool(result["p_family_wise"] <= alpha)
    argmax = result.get("principal") or (pairs[0]["candidate"] if pairs else None)
    view = {**result, "loyal": loyal, "alpha": alpha, "principal": argmax,
            "surviving_pairs": [{"candidate": p["candidate"], "axis_id": p["axis_id"]}
                                for p in pairs if p["p_adjusted"] <= alpha]}
    att = attribute_principal(view)
    return {"loyal": loyal, "named": att["named"], "reason": att["reason"],
            "histogram": att["histogram"]}
