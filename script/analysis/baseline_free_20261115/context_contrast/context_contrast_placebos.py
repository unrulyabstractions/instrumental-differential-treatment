"""Placebo contexts: two contexts that are the same context by construction.

``split_half`` takes one framing and splits every (candidate, template) cell's
samples into two random halves, the way the registered placebo splits a cell
(``split_cell_indices``: half the samples to each side, a coin flip per cell for
which side gets the odd one). The halves play context one and context zero, and
the paired sign-flip test runs unchanged on the mean gap. The halves are
exchangeable within every cell, so the sign-flip null holds exactly and the
rejection share measures the implementation and the discreteness of the null
at the stored sample counts.

``template_partition`` draws a random partition of one framing's templates into
two families of the sizes the model's real family split has, and runs the
family-permutation test on the mean gap. A random partition is exchangeable by
construction, so the share again checks the code path and its discreteness.

Neither placebo tests the anchor assumption. The bases read as targets do.
"""

from __future__ import annotations

import numpy as np
from scipy import stats

from script.analysis.baseline_free_20261115.context_contrast.context_contrast_engine import (
    group_perm_test, paired_flip_test)
from script.analysis.baseline_free_20261115.context_contrast.context_contrast_gaps import (
    gap, instruction_ids, split_instruction)
from src.compare.behavior_count_table import BehaviorTable
from src.compare.paired_excess_measures import cell_rates

__all__ = ["split_half", "template_partition", "share_summary", "framing_gap", "clopper_pearson"]


def _framing_rows(table: BehaviorTable, framing: str):
    ids = list(table.blocks)
    pairs = [split_instruction(i) for i in ids]
    templates = sorted({t for f, t in pairs if f == framing})
    t_of_block = np.array([templates.index(t) if f == framing else -1 for f, t in pairs])
    keep = np.flatnonzero(t_of_block[table.block_of] >= 0)
    return keep, t_of_block[table.block_of[keep]], templates


class _Splitter:
    """One framing's rows of one table, ready to be split cell by cell."""

    def __init__(self, table: BehaviorTable, framing: str):
        self.rows, t_idx, self.templates = _framing_rows(table, framing)
        self.n_c, self.n_t, self.n_a = len(table.principals), len(self.templates), len(table.axes)
        self.cell = table.group_of[self.rows].astype(np.int64) * self.n_t + t_idx
        self.fired = table.fired[self.rows].astype(float)
        self.scored = table.scored[self.rows].astype(float)
        self.sizes = np.bincount(self.cell, minlength=self.n_c * self.n_t)
        if np.any(self.sizes < 2):
            raise ValueError("a placebo cell needs at least two samples")
        self.starts = np.r_[0, np.cumsum(self.sizes)[:-1]]

    def split(self, rng: np.random.Generator) -> np.ndarray:
        """A boolean mask over ``rows``: True for the first half."""
        u = rng.random(self.rows.size)
        order = np.lexsort((u, self.cell))
        rank = np.empty(self.rows.size, dtype=np.int64)
        rank[order] = np.arange(self.rows.size) - self.starts[self.cell[order]]
        coin = rng.random(self.n_c * self.n_t) < 0.5
        cut = np.where(coin, self.sizes // 2, self.sizes - self.sizes // 2)
        return rank < cut[self.cell]

    def rates(self, side: np.ndarray) -> np.ndarray:
        """(candidate, template, axis) rates of the rows where ``side`` holds."""
        f = np.zeros((self.n_c * self.n_t, self.n_a))
        s = np.zeros((self.n_c * self.n_t, self.n_a))
        np.add.at(f, self.cell[side], self.fired[side])
        np.add.at(s, self.cell[side], self.scored[side])
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(s > 0, f / s, np.nan).reshape(self.n_c, self.n_t, self.n_a)


def split_half(table: BehaviorTable, framing: str, n_splits: int, n_flips: int, seed: int,
               alpha: float, start: int = 0) -> list[dict]:
    """``n_splits`` split-half placebos, replicates ``start`` to ``start + n_splits - 1``."""
    sp = _Splitter(table, framing)
    out = []
    for k in range(start, start + n_splits):
        rng = np.random.default_rng([seed, k])
        half = sp.split(rng)
        delta = gap(sp.rates(half), "mean") - gap(sp.rates(~half), "mean")
        res = paired_flip_test(delta, list(table.principals), list(table.axes), n=n_flips,
                               seed=int(rng.integers(2**31)), alpha=alpha, full=False)
        out.append({"replicate": k, **res})
    return out


def template_partition(gap_framing: np.ndarray, n_one: int, n_zero: int, n_parts: int,
                       n_perms: int, seed: int, alpha: float, start: int = 0) -> list[dict]:
    """Random family partitions of one framing's templates; ``gap_framing`` is (C, T, A)."""
    c, t, a = gap_framing.shape
    out = []
    for k in range(start, start + n_parts):
        rng = np.random.default_rng([seed, 1_000_000 + k])
        pick = rng.permutation(t)[: n_one + n_zero]
        res = group_perm_test(gap_framing, list(pick[:n_one]), list(pick[n_one:]),
                              [str(i) for i in range(c)], [str(j) for j in range(a)],
                              n=n_perms, seed=int(rng.integers(2**31)), alpha=alpha,
                              full=False)
        out.append({"replicate": k, **res})
    return out


def clopper_pearson(k: int, n: int, level: float = 0.95) -> list[float]:
    tail = (1 - level) / 2
    lo = 0.0 if k == 0 else float(stats.beta.ppf(tail, k, n - k + 1))
    hi = 1.0 if k == n else float(stats.beta.ppf(1 - tail, k + 1, n - k))
    return [lo, hi]


def share_summary(p_values, alpha: float = 0.01) -> dict:
    """Rejection share at ``alpha`` and 0.05 with exact 95% intervals, and the p quantiles."""
    p = np.asarray(p_values, dtype=float)
    out = {"n": int(p.size), "median_p": float(np.median(p)),
           "p_quantiles": {q: float(np.quantile(p, float(q))) for q in ("0.01", "0.05", "0.1", "0.5")},
           "ks_uniform_p": float(stats.kstest(p, "uniform").pvalue)}
    for level in (alpha, 0.05):
        k = int(np.sum(p <= level))
        out[f"reject_{level}"] = {"count": k, "share": k / p.size, "ci95": clopper_pearson(k, p.size)}
    return out


def framing_gap(table: BehaviorTable, framing: str) -> tuple[np.ndarray, list[str]]:
    """The mean gap of one framing as (candidate, template, axis), for partitions."""
    rates, _, _ = cell_rates(table)
    ids = instruction_ids(table)
    keep = [i for i, x in enumerate(ids) if split_instruction(x)[0] == framing]
    templates = [split_instruction(ids[i])[1] for i in keep]
    return gap(rates[:, keep, :], "mean"), templates
