"""Axis pruning from a pilot: which axes to judge on the rest of a run.

Most axes in a registry rarely fire, and every axis costs judge reading on
every reply. A pilot judges every axis on a random share of the instructions;
the rest of the run is judged only on the axes that fired often enough in the
pilot. The selection reads the pooled firing rate over both models and every
candidate, so it never looks at which candidate an axis separates.

A pooled firing rate is also unchanged by relabelling candidates within an
instruction, which is the registered permutation. Selecting on it therefore
leaves the test valid even on the data it is selected from; the held-out design
is the honest one for a different reason, which is cost: selecting on all data
needs every axis judged on every reply, the very cost pruning is meant to save.
"""

from __future__ import annotations

import math

import numpy as np

from src.compare.behavior_count_table import BehaviorTable

__all__ = ["split_instructions", "pooled_axis_rates", "select_top_axes",
           "judge_cost_share"]


def split_instructions(n_blocks: int, pilot_share: float,
                       rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """A random pilot of ``round(pilot_share * n_blocks)`` instructions and the rest."""
    n_pilot = int(round(pilot_share * n_blocks))
    if not 1 <= n_pilot < n_blocks:
        raise ValueError("the pilot must hold at least one and leave at least one instruction")
    order = rng.permutation(n_blocks)
    return np.sort(order[:n_pilot]), np.sort(order[n_pilot:])


def pooled_axis_rates(tables: list[BehaviorTable], blocks: np.ndarray | None = None
                      ) -> np.ndarray:
    """Per-axis yes share over the given instructions, pooled over the tables.

    The denominator is returned verdicts, never responses, so a null verdict is
    not read as a no. An axis with no returned verdict has rate zero.
    """
    fired = np.zeros(len(tables[0].axes))
    scored = np.zeros(len(tables[0].axes))
    for t in tables:
        if t.axes != tables[0].axes:
            raise ValueError("tables must share the axis registry")
        keep = (np.ones(t.n_responses, dtype=bool) if blocks is None
                else np.isin(t.block_of, blocks))
        fired += t.fired[keep].sum(axis=0)
        scored += t.scored[keep].sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(scored > 0, fired / scored, 0.0)


def select_top_axes(rates: np.ndarray, k: int) -> tuple[np.ndarray, float]:
    """Axes whose rate is at least the ``k``-th largest rate and above zero.

    Ties at the threshold are all kept, so the count can exceed ``k``. A
    registry of at most ``k`` axes keeps every axis that ever fired.
    """
    rates = np.asarray(rates, dtype=float)
    if k >= rates.size:
        threshold = 0.0
    else:
        threshold = float(np.sort(rates)[::-1][k - 1])
    kept = np.flatnonzero((rates >= threshold) & (rates > 0))
    return kept, threshold


def judge_cost_share(n_axes: int, n_kept: int, pilot_share: float,
                     axes_per_call: int) -> dict:
    """Judge reading under pruning, as a share of judging every axis everywhere.

    ``axis_verdicts`` counts (reply, axis) verdicts; ``judge_calls`` counts
    calls when ``axes_per_call`` axes share one call. Both include the pilot,
    which judges every axis.
    """
    full_calls = math.ceil(n_axes / axes_per_call)
    kept_calls = math.ceil(n_kept / axes_per_call)
    return {
        "kept_over_total": n_kept / n_axes,
        "axis_verdicts": pilot_share + (1 - pilot_share) * n_kept / n_axes,
        "judge_calls": pilot_share + (1 - pilot_share) * kept_calls / full_calls,
    }
