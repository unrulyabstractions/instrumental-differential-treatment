"""From verdicts to the grids the empirical null is fitted to.

Three effects per subject, each a (candidate, instruction, axis) array ``d``:

- ``median``: each candidate's cell minus the median of the other candidates'
  cells (``reference_free_effect``), the target-only statistic of the
  reference-free appendix.
- ``mean``: each candidate's cell minus the mean of the others, which is the
  registered excess with nothing subtracted.
- ``registered``: the target's one-versus-rest gap minus the base's
  (``excess_effect``), the registered test's own effect.

A grid is the paired t over instructions per (candidate, axis), exactly as
``standardized_excess`` computes it, so the maximum reproduces the stored
statistics. The empirical null is fitted to z = Phi^-1(F_{m-1}(t)) after each
axis's z values are centred on their axis mean. A cell whose effect has zero
spread over instructions (an axis that never fires for that candidate or its
comparison, or fires identically) has no defined t: the registered convention
sets it to 0 or to a signed infinity, and the fit leaves it out.

Permutations are drawn exactly as the stored tests drew them: the
reference-free test's stream for ``median``, which relabels the rows of ``d``,
and the registered test's stream (``permutation_orders``) for ``mean``,
``registered`` and the placebo, which relabels the target and base rates and
recomputes the excess.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np

from src.common.file_io import load_json, read_jsonl
from src.compare.loser_dispersion_statistic import _permute, permutation_orders
from src.compare.paired_excess_measures import cell_rates, excess_effect
from src.compare.placebo_calibration import (load_level_table, split_cell_indices,
                                             subset_table)
from src.compare.reference_free_max_statistic import reference_free_effect

from script.analysis.baseline_free_20261115.empirical_null.efron_null_estimators import t_to_z

__all__ = ["SPREAD_ZERO", "load_table", "effects", "placebo_effect", "excess_batched",
           "stream_orders", "permute", "grid_t", "centred", "flatten_rows"]

#: A spread at or below this over instructions is zero (float noise is ~1e-17).
SPREAD_ZERO = 1e-12


def axis_ids(path: str) -> list[str]:
    return [a["axis_id"] for a in load_json(Path(path))["axes"]]


def load_table(path: str, axes_path: str, level: int, drop: tuple[str, ...] = ()):
    rows = [r for r in read_jsonl(Path(path)) if r["principal"] not in drop]
    return load_level_table(rows, axis_ids(axes_path), level)


def _zero_like(rates: np.ndarray) -> np.ndarray:
    return np.where(np.isnan(rates), np.nan, 0.0)


def effects(target, base=None) -> tuple[dict, dict, list[str], list[str], tuple[str, ...]]:
    """The ``d`` arrays for one subject, the rate pairs behind the paired ones, and labels.

    ``pairs[kind]`` is the (target, base) rate pair whose excess is ``d[kind]``;
    the permutation of a paired kind relabels both and recomputes the excess,
    as ``paired_max_test`` does.
    """
    p_t, cands, inst = cell_rates(target)
    zero = _zero_like(p_t)
    out = {"median": reference_free_effect(p_t), "mean": excess_effect(p_t, zero)}
    pairs = {"mean": (p_t, zero)}
    if base is not None:
        if base.principals != target.principals or base.axes != target.axes \
                or base.blocks != target.blocks:
            raise ValueError("target and base do not share candidates, axes and instructions")
        p_b, _, _ = cell_rates(base)
        out["registered"] = excess_effect(p_t, p_b)
        pairs["registered"] = (p_t, p_b)
    return out, pairs, cands, inst, tuple(target.axes)


def placebo_effect(table, split_seed: int) -> tuple[np.ndarray, tuple[np.ndarray, np.ndarray]]:
    """One model's cells split at random into halves; the registered effect of half on half."""
    a, b = split_cell_indices(table, np.random.default_rng(split_seed))
    p_a, _, _ = cell_rates(subset_table(table, a))
    p_b, _, _ = cell_rates(subset_table(table, b))
    return excess_effect(p_a, p_b), (p_a, p_b)


def excess_batched(p_t: np.ndarray, p_b: np.ndarray) -> np.ndarray:
    """``excess_effect`` over a leading batch, (B, N, I, J), with the same summation order."""
    def one_vs_rest(p):
        observed = ~np.isnan(p)
        filled = np.where(observed, p, 0.0)
        rest_sum = filled.sum(axis=1, keepdims=True) - filled
        rest_count = observed.sum(axis=1, keepdims=True) - observed.astype(int)
        with np.errstate(invalid="ignore", divide="ignore"):
            rest = np.where(rest_count > 0, rest_sum / rest_count, np.nan)
        return p - rest
    return one_vs_rest(p_t) - one_vs_rest(p_b)


def stream_orders(kind: str, n_c: int, n_i: int, n: int, seed: int) -> np.ndarray:
    """(n, I, N) candidate orders, as the stored test of this kind drew them."""
    if kind == "median":
        rng = np.random.default_rng(seed)
        out = np.empty((n, n_i, n_c), dtype=np.int64)
        for k in range(n):
            out[k] = np.argsort(rng.random((n_i, n_c)), axis=1)
        return out
    return permutation_orders(n_c, n_i, n, seed)


def permute(d: np.ndarray, orders: np.ndarray) -> np.ndarray:
    return _permute(d, orders)


def grid_t(d: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """t (registered convention), instruction count m, and the fit mask, over (..., N, J)."""
    m = np.sum(~np.isnan(d), axis=-2)
    with np.errstate(invalid="ignore", divide="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        mean = np.nanmean(d, axis=-2)
        sd = np.nanstd(d, axis=-2, ddof=1)
        ratio = mean / (sd / np.sqrt(np.maximum(m, 1)))
    degenerate = (m >= 2) & (sd == 0)
    t = np.where(m >= 2, ratio, np.nan)
    signs = np.sign(np.nan_to_num(mean, nan=0.0))
    infinite = np.where(signs > 0, np.inf, np.where(signs < 0, -np.inf, 0.0))
    t = np.where(degenerate, infinite, t)
    fit = (m >= 2) & (sd > SPREAD_ZERO) & np.isfinite(t)
    return t, m, fit


def centred(t: np.ndarray, m: np.ndarray, fit: np.ndarray,
            keep_rows: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """z per cell and its axis-centred deviation, NaN outside the fit mask.

    ``keep_rows`` drops candidates before centring. An axis with fewer than two
    fitted cells has no deviation.
    """
    z = np.where(fit, t_to_z(t, m - 1), np.nan)
    if keep_rows is not None:
        z = z[..., keep_rows, :]
    count = np.sum(~np.isnan(z), axis=-2, keepdims=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        mu = np.nanmean(z, axis=-2, keepdims=True)
    u = np.where(count >= 2, z - mu, np.nan)
    return z, u


def flatten_rows(x: np.ndarray) -> np.ndarray:
    """(..., N, J) to (G, N * J) with one grid per row."""
    return x.reshape(-1, x.shape[-2] * x.shape[-1])
