"""Placebo calibration of the registered test: one model split against itself.

The registered test compares a target's cell rates with its base's. Whether its
p-value is calibrated cannot be read off the real null controls, because a null
control still differs from its base by fine-tuning. A placebo removes that
difference by construction. We take the verdicts of ONE model, split every cell
(candidate x instruction, where the instruction id carries the system variant)
into two random halves, call one half "target" and the other "base", and run the
registered test unchanged. The two halves are draws from the same model on the
same prompts, so every candidate's excess is zero in expectation and a
calibrated test returns uniform p-values.

The placebo checks the permutation scheme and its finite-sample behavior. It
cannot see drift between a real target and its base, since it never compares
two different models.

The halves are built by subsetting the model's own behavior table, which is
exactly the table ``build_behavior_table`` would fold from the subset of rows,
provided every candidate and instruction survives in both halves. Every cell
must hold at least two samples so that both halves observe it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats

from src.compare.behavior_count_table import BehaviorTable, build_behavior_table
from src.compare.paired_max_statistic import DEFAULT_ALPHA, paired_max_test

__all__ = ["cell_sizes", "load_level_table", "split_cell_indices", "subset_table",
           "placebo_replicate", "calibration_summary", "empirical_quantile"]


def load_level_table(rows, axes, level: int) -> BehaviorTable:
    """The behavior table for one model at one judge level, as stage 6 builds it."""
    kept = [r for r in rows if int(r["level"]) == int(level)]
    return build_behavior_table(kept, axes)


def cell_sizes(table: BehaviorTable) -> np.ndarray:
    """Responses per (candidate, instruction) cell, as an (N, I) integer array."""
    sizes = np.zeros((len(table.principals), len(table.blocks)), dtype=np.int64)
    np.add.at(sizes, (table.group_of, table.block_of), 1)
    return sizes


def subset_table(table: BehaviorTable, index: np.ndarray) -> BehaviorTable:
    """The table ``build_behavior_table`` would fold from the rows in ``index``.

    Candidates and instructions keep their positions. Both must survive in the
    subset, since ``build_behavior_table`` would otherwise re-index them.
    """
    index = np.sort(np.asarray(index, dtype=np.int64))
    group_of, block_of = table.group_of[index], table.block_of[index]
    if (len(np.unique(group_of)) != len(table.principals)
            or len(np.unique(block_of)) != len(table.blocks)):
        raise ValueError("a candidate or an instruction is missing from the subset")
    fired, scored = table.fired[index], table.scored[index]
    counts = np.zeros((len(table.principals), len(table.axes)), dtype=np.int64)
    np.add.at(counts, group_of, fired.astype(np.int64))
    # A verdict the judge never returned is an axis whose ``scored`` is zero.
    n_null = int(len(table.axes) * len(index) - int(scored.sum()))
    return BehaviorTable(table.principals, table.axes, counts, fired, scored,
                         group_of, block_of, table.blocks, n_null, len(index))


def split_cell_indices(table: BehaviorTable, rng: np.random.Generator
                       ) -> tuple[np.ndarray, np.ndarray]:
    """Split every cell's responses at random into two halves.

    A cell of ``n`` responses gives ``n // 2`` to one half and the rest to the
    other; which half receives the larger share is a coin flip per cell, so
    neither label is systematically the larger sample.
    """
    key = table.group_of.astype(np.int64) * len(table.blocks) + table.block_of
    order = np.argsort(key, kind="stable")
    bounds = np.flatnonzero(np.diff(key[order])) + 1
    first, second = [], []
    for cell in np.split(order, bounds):
        if cell.size < 2:
            raise ValueError("a cell with fewer than two samples cannot be split")
        shuffled = rng.permutation(cell)
        cut = cell.size // 2 if rng.random() < 0.5 else cell.size - cell.size // 2
        first.append(shuffled[:cut])
        second.append(shuffled[cut:])
    return np.concatenate(first), np.concatenate(second)


def placebo_replicate(table: BehaviorTable, split_seed: int, permutation_seed: int,
                      n_permutations: int, alpha: float = DEFAULT_ALPHA) -> dict:
    """One placebo: split the model's cells, run the registered test half on half."""
    a, b = split_cell_indices(table, np.random.default_rng(split_seed))
    result = paired_max_test(subset_table(table, a), subset_table(table, b),
                             n_permutations=n_permutations, seed=permutation_seed,
                             alpha=alpha)
    return {"p": float(result["p_family_wise"]), "statistic": float(result["statistic"]),
            "loyal": bool(result["loyal"]), "n_target": int(a.size), "n_base": int(b.size)}


def _clopper_pearson(k: int, n: int, level: float = 0.95) -> tuple[float, float]:
    tail = (1.0 - level) / 2.0
    lo = 0.0 if k == 0 else float(stats.beta.ppf(tail, k, n - k + 1))
    hi = 1.0 if k == n else float(stats.beta.ppf(1.0 - tail, k + 1, n - k))
    return lo, hi


def empirical_quantile(placebo: np.ndarray, value: float) -> float:
    """Share of placebo p-values at or below ``value``."""
    return float(np.mean(np.asarray(placebo) <= value))


def calibration_summary(p_values) -> dict:
    """Rejection shares with exact binomial 95% intervals, KS against uniform, median."""
    p = np.asarray(p_values, dtype=float)
    if p.size == 0:
        raise ValueError("no placebo p-values")
    out: dict = {"n": int(p.size), "median_p": float(np.median(p)),
                 "mean_p": float(np.mean(p))}
    for name, cut in (("05", 0.05), ("01", 0.01)):
        k = int(np.sum(p <= cut))
        lo, hi = _clopper_pearson(k, p.size)
        out[f"share_le_{name}"] = k / p.size
        out[f"count_le_{name}"] = k
        out[f"ci_le_{name}"] = [lo, hi]
    ks = stats.kstest(p, "uniform")
    out["ks_statistic"] = float(ks.statistic)
    out["ks_p"] = float(ks.pvalue)
    return out
