"""The measures under the registered test: rates, excess, and the paired t.

``paired_max_statistic`` owns the permutation null and the maxT adjustment;
this module owns everything that turns verdicts into the numbers that null is
built over. The sibling statistics (axis coherence, candidate detachment, the
reference-free variant) read the same measures, so they live apart from any
one test.

The observation is a cell rate: for one prompt, one axis, and one model, the
fraction of yes verdicts over that prompt's samples. Pooling inside the cell
absorbs the dependence among one prompt's samples, so nothing here needs a
cluster correction. One judge level is one table; levels are never averaged.
"""

from __future__ import annotations

import numpy as np

from src.compare.behavior_count_table import BehaviorTable

__all__ = ["cell_rates", "excess_effect", "standardized_excess",
           "max_abs_statistic", "permutation_tail_share"]


def cell_rates(table: BehaviorTable) -> tuple[np.ndarray, list[str], list[str]]:
    """Cell rates as a (candidate, instruction, axis) array of yes-shares.

    A cell with no scored response is NaN rather than zero: it was not observed,
    and a zero there would be a verdict no judge returned.

    The denominator counts returned verdicts per axis, not responses. A response
    whose judge returned nothing on one axis says nothing about that axis, and
    counting it as a "no" would impute behavior the model never produced. The
    two differ only when a judge returns null, which is why the rate has to read
    ``scored`` rather than assume every response answered every axis.
    """
    principals = list(table.principals)
    blocks = sorted({int(b) for b in table.block_of})
    n_c, n_i, n_j = len(principals), len(blocks), len(table.axes)
    block_index = {b: i for i, b in enumerate(blocks)}

    fired = np.zeros((n_c, n_i, n_j))
    seen = np.zeros((n_c, n_i, n_j))
    for r in range(table.n_responses):
        c = int(table.group_of[r])
        i = block_index[int(table.block_of[r])]
        fired[c, i] += table.fired[r]
        seen[c, i] += table.scored[r]
    with np.errstate(invalid="ignore", divide="ignore"):
        rates = np.where(seen > 0, fired / seen, np.nan)
    return rates, principals, [f"i{b}" for b in blocks]


def excess_effect(target: np.ndarray, base: np.ndarray) -> np.ndarray:
    """``d`` of the paper: the target's one-vs-rest gap minus the base's.

    A NaN cell is a rate no judge returned, and it stays out of both sides of
    the comparison: it never joins a rest-average, and any gap that needs it is
    NaN. Summing it as zero would impute a rate for a verdict that does not
    exist, and a single all-null base cell then hands every other candidate a
    spurious excess.
    """
    def one_vs_rest(p: np.ndarray) -> np.ndarray:
        if p.shape[0] < 2:
            raise ValueError("one-versus-rest needs at least two candidates")
        observed = ~np.isnan(p)
        filled = np.where(observed, p, 0.0)
        rest_sum = filled.sum(axis=0, keepdims=True) - filled
        rest_count = observed.sum(axis=0, keepdims=True) - observed.astype(int)
        with np.errstate(invalid="ignore", divide="ignore"):
            rest = np.where(rest_count > 0, rest_sum / rest_count, np.nan)
        return p - rest

    return one_vs_rest(target) - one_vs_rest(base)


def standardized_excess(d: np.ndarray, polarity: np.ndarray | None = None
                        ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Paired t over instructions per (candidate, axis), plus its mean and count.

    A candidate-axis pair with fewer than two usable instructions cannot be
    standardized and is returned as NaN, which the maximum then skips.
    """
    m = np.sum(~np.isnan(d), axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.nanmean(np.where(np.isnan(d), np.nan, d), axis=1)
        sd = np.nanstd(d, axis=1, ddof=1)
        ratio = mean / (sd / np.sqrt(np.maximum(m, 1)))
    # A zero spread with a nonzero mean is the strongest signal the design can
    # produce, not an unmeasurable one: the effect held on every instruction. It
    # is infinite, and the permutation null carries the same convention, so a
    # shuffle that reproduces it still counts against the observed value.
    degenerate = (m >= 2) & (sd == 0)
    t = np.where(m >= 2, ratio, np.nan)
    signs = np.sign(np.nan_to_num(mean, nan=0.0))
    infinite = np.where(signs > 0, np.inf, np.where(signs < 0, -np.inf, 0.0))
    t = np.where(degenerate, infinite, t)
    if polarity is not None:
        t = t * polarity[None, :]
    return t, mean, m


def max_abs_statistic(t: np.ndarray, signed: bool) -> float:
    """The scalar a max-type test reads off one t-grid."""
    values = t if signed else np.abs(t)
    return float(np.nanmax(values)) if np.any(~np.isnan(values)) else 0.0


def permutation_tail_share(null: np.ndarray, value: float, n: int) -> float:
    """Share of the null at least as large, with the usual plus-one correction."""
    if np.isnan(value):
        return 1.0
    return (1.0 + int(np.sum(null >= value))) / (1.0 + n)
