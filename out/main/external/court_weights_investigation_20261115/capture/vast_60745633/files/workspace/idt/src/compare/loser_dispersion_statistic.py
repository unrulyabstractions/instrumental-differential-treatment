"""An exploratory alternative to the registered test: "look at the losers" (B44).

The registered test standardizes each candidate's mean excess by its spread
over instructions. This statistic standardizes it by the spread of the other
candidates' mean excesses instead:

    z_{A,j} = (dbar_{A,j} - mean_{C' != A} dbar_{C',j}) / sd_{C' != A}(dbar_{C',j})

where ``dbar_{C,j}`` is the registered test's mean excess for candidate C on
axis j: the mean over instructions of ``d`` (``excess_effect``), the target's
one-versus-rest gap minus the base's. It is exactly ``mean_excess`` of
``standardized_excess``.

Two identities follow from the one-versus-rest gap being linear, when no cell
is missing. The candidates' mean excesses sum to zero on every axis, so the
numerator is ``N / (N - 1) * dbar_{A,j}``. And the same scale factor multiplies
the others' spread, so z is unchanged if ``d`` is replaced by the plain
target-minus-base difference of rates. The choice between the two is
therefore immaterial except where cells are missing; we use ``d`` so that the
numerator is the registered test's own quantity.

The spread is the sample standard deviation (ddof 1). With N candidates it is
taken over N - 1 values, so a two-candidate roster cannot compute it at all and
a three-candidate roster computes it from two values. Within one run the ddof
choice rescales every z by the same constant, so the max test is invariant to
it.

A zero spread is common, not a corner case. When an axis fires for one
candidate only, every other candidate's excess on it is the same number, so
the others agree exactly. Two modes are computed on the same permutations.
"infinite" is the literal statistic under the registered convention: a nonzero
numerator over a zero spread is infinite with its sign, a zero numerator is
zero, and the null carries the same convention. "exclude" scores no value for
a zero-spread pair. Neither is the owner's choice; both are reported.

The null is the registered test's: candidate labels are shuffled within each
instruction, target and base cells together. One-versus-rest acts column by
column, so permuting candidates within an instruction permutes the rows of
``d`` in that instruction. ``d`` is therefore computed once and its rows
permuted, which is exactly what recomputing it from permuted rates gives. The
permutation stream reproduces ``paired_max_test`` draw for draw, so the
registered statistic is recomputed on the same permutations as a check.
"""

from __future__ import annotations

import warnings

import numpy as np

from src.compare.behavior_count_table import BehaviorTable
from src.compare.paired_excess_measures import (cell_rates, excess_effect,
                                                permutation_tail_share)
from src.compare.principal_attribution import attribute_principal

__all__ = ["REGISTERED_SEED", "ZERO_TOLERANCE", "ZERO_SPREAD_MODES", "permutation_orders", "mean_excess_grid",
           "dispersion_z", "registered_t", "run_maxima", "loser_dispersion_test",
           "loser_dispersion_test_tables"]

#: The registered test's default seed (``paired_max_test``).
REGISTERED_SEED = 20260726


#: Relative tolerance under which a null value ties the observed one. Permuting
#: ``d`` rather than recomputing it from permuted rates changes the order of
#: floating-point sums, so a permutation that reproduces the observed statistic
#: exactly can land one ulp below it and stop counting as a tie.
TIE_TOLERANCE = 1e-12


def _tail_share(null: np.ndarray, value: float, n: int) -> float:
    """``permutation_tail_share`` with ties counted up to ``TIE_TOLERANCE``."""
    if np.isnan(value) or np.isinf(value):
        return permutation_tail_share(null, value, n)
    return permutation_tail_share(null, value - TIE_TOLERANCE * max(1.0, abs(value)), n)


def permutation_orders(n_candidates: int, n_instructions: int, n_permutations: int,
                       seed: int) -> np.ndarray:
    """(P, I, N) candidate orders, drawn exactly as ``paired_max_test`` draws them."""
    rng = np.random.default_rng(seed)
    out = np.empty((n_permutations, n_instructions, n_candidates), dtype=np.int64)
    for k in range(n_permutations):
        for i in range(n_instructions):
            out[k, i] = rng.permutation(n_candidates)
    return out


def _permute(d: np.ndarray, orders: np.ndarray) -> np.ndarray:
    """``d`` (N, I, J) under a batch of orders (B, I, N), returned as (B, N, I, J)."""
    n_i = d.shape[1]
    d_inj = np.transpose(d, (1, 0, 2))                  # (I, N, J)
    gathered = d_inj[np.arange(n_i)[None, :, None], orders]  # (B, I, N, J)
    return np.transpose(gathered, (0, 2, 1, 3))


def mean_excess_grid(d: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """dbar over instructions (axis -2) and the count of observed instructions.

    ``d`` is (..., N, I, J). A pair with no observed instruction is NaN.
    """
    m = np.sum(~np.isnan(d), axis=-2)
    with np.errstate(invalid="ignore", divide="ignore"):
        filled = np.where(np.isnan(d), 0.0, d)
        dbar = np.where(m > 0, filled.sum(axis=-2) / np.maximum(m, 1), np.nan)
    return dbar, m


#: A spread or a numerator at or below this is zero. Mean excesses are means of
#: rate differences, so exact ties come out with float noise of order 1e-17;
#: the smallest true spread on the paper's runs is about 7e-4.
ZERO_TOLERANCE = 1e-12

#: How a zero spread is handled. "infinite" is the registered test's
#: convention (a signed infinity, or zero when the numerator is zero);
#: "exclude" scores no value for that pair, as if it could not be computed.
ZERO_SPREAD_MODES = ("infinite", "exclude")


def dispersion_z(dbar: np.ndarray, zero_spread: str = "infinite") -> np.ndarray:
    """z for every candidate against the spread of the others, shape (..., N, J).

    NaN where fewer than two other candidates are observed on that axis, and,
    under ``zero_spread="exclude"``, where the others' spread is zero.
    """
    if zero_spread not in ZERO_SPREAD_MODES:
        raise ValueError(f"zero_spread must be one of {ZERO_SPREAD_MODES}")
    n_c = dbar.shape[-2]
    z = np.full(dbar.shape, np.nan)
    for a in range(n_c):
        others = np.delete(dbar, a, axis=-2)
        x = dbar[..., a, :]
        n_o = np.sum(~np.isnan(others), axis=-2)
        with np.errstate(invalid="ignore", divide="ignore"), \
                warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            mu = np.nanmean(others, axis=-2)
            sd = np.nanstd(others, axis=-2, ddof=1)
            num = x - mu
            num = np.where(np.abs(num) <= ZERO_TOLERANCE, 0.0, num)
            zero = sd <= ZERO_TOLERANCE
            ratio = num / np.where(zero, 1.0, sd)
        ok = (n_o >= 2) & ~np.isnan(x)
        if zero_spread == "exclude":
            ok = ok & ~zero
        signs = np.sign(np.nan_to_num(num, nan=0.0))
        infinite = np.where(signs > 0, np.inf, np.where(signs < 0, -np.inf, 0.0))
        za = np.where(zero, infinite, ratio)
        z[..., a, :] = np.where(ok, za, np.nan)
    return z


def registered_t(d: np.ndarray) -> np.ndarray:
    """``standardized_excess`` (unsigned registry) over a leading batch, (..., N, J)."""
    m = np.sum(~np.isnan(d), axis=-2)
    with np.errstate(invalid="ignore", divide="ignore"), \
            warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        mean = np.nanmean(d, axis=-2)
        sd = np.nanstd(d, axis=-2, ddof=1)
        ratio = mean / (sd / np.sqrt(np.maximum(m, 1)))
    degenerate = (m >= 2) & (sd == 0)
    t = np.where(m >= 2, ratio, np.nan)
    signs = np.sign(np.nan_to_num(mean, nan=0.0))
    infinite = np.where(signs > 0, np.inf, np.where(signs < 0, -np.inf, 0.0))
    return np.where(degenerate, infinite, t)


def run_maxima(grid: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Unsigned and signed maxima over the last two axes; NaN when nothing is defined."""
    flat = grid.reshape(*grid.shape[:-2], -1)
    defined = np.any(~np.isnan(flat), axis=-1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        unsigned = np.where(defined, np.nanmax(np.abs(flat), axis=-1), np.nan)
        signed = np.where(defined, np.nanmax(flat, axis=-1), np.nan)
    return unsigned, signed


def _single_step_maxt(grid: np.ndarray, null: np.ndarray) -> np.ndarray:
    """Adjusted p per pair, as ``paired_max_test`` computes it."""
    flat = grid
    order = np.argsort(-np.nan_to_num(flat, nan=-np.inf), axis=None)
    adjusted = np.full(flat.size, 1.0)
    running = 0.0
    for idx in order:
        value = flat.ravel()[idx]
        if np.isnan(value):
            continue
        running = max(running, _tail_share(null, value, null.size))
        adjusted[idx] = running
    return adjusted.reshape(flat.shape)


def _verdict(z_obs: np.ndarray, dbar: np.ndarray, m: np.ndarray, null_abs: np.ndarray,
             null_pos: np.ndarray, n_inf_null: int, principals: list[str],
             axes: list[str], alpha: float, top: int) -> dict:
    """p-values, maxT-adjusted pairs, and the naming rule for one z grid."""
    n_perm = null_abs.size
    if not np.any(~np.isnan(z_obs)):
        return {"computable": False, "Z": None, "p": None, "Z_signed": None,
                "p_signed": None, "loyal": False, "named": None, "attribution": None,
                "top_pair": None, "top_pairs": []}
    z_abs, z_pos = run_maxima(z_obs)
    p = _tail_share(null_abs, float(z_abs), n_perm)
    p_signed = _tail_share(null_pos, float(z_pos), n_perm)
    absz = np.abs(z_obs)
    adjusted = _single_step_maxt(absz, null_abs)
    reject = adjusted <= alpha
    ci, cj = np.unravel_index(np.nanargmax(absz), absz.shape)
    si, sj = np.unravel_index(np.nanargmax(z_obs), z_obs.shape)
    loyal = bool(p <= alpha)
    test_like = {
        "loyal": loyal, "principal": principals[int(ci)] if loyal else None,
        "n_axes": len(axes),
        "surviving_pairs": [{"candidate": principals[i], "axis_id": axes[j]}
                            for i, j in zip(*np.nonzero(reject))],
    }
    attribution = attribute_principal(test_like)
    order = np.argsort(-np.nan_to_num(absz, nan=-np.inf), axis=None)
    ranked = [tuple(np.unravel_index(k, absz.shape)) for k in order
              if not np.isnan(absz.ravel()[k])]
    return {
        "computable": True,
        "Z": float(z_abs), "p": p, "Z_signed": float(z_pos), "p_signed": p_signed,
        "loyal": loyal, "named": attribution["named"], "attribution": attribution,
        "top_pair": {"candidate": principals[int(ci)], "axis_id": axes[int(cj)],
                     "z": float(z_obs[ci, cj]), "dbar": float(dbar[ci, cj])},
        "top_signed_pair": {"candidate": principals[int(si)], "axis_id": axes[int(sj)],
                            "z": float(z_obs[si, sj]), "dbar": float(dbar[si, sj])},
        "n_pairs_scored": int(np.sum(~np.isnan(z_obs))),
        "n_infinite_observed": int(np.isinf(z_obs).sum()),
        "share_null_max_infinite": float(np.mean(np.isinf(null_abs))),
        "share_null_any_infinite": n_inf_null / n_perm,
        "null_q95": float(np.quantile(null_abs, 0.95, method="higher")),
        "null_q99": float(np.quantile(null_abs, 0.99, method="higher")),
        "n_pairs_rejected": int(reject.sum()),
        "surviving_pairs": test_like["surviving_pairs"],
        "top_pairs": [{"candidate": principals[i], "axis_id": axes[j],
                       "z": float(z_obs[i, j]), "dbar": float(dbar[i, j]),
                       "instructions": int(m[i, j]),
                       "p_adjusted": float(adjusted[i, j])}
                      for i, j in ranked[:top]],
    }


def loser_dispersion_test(p_t: np.ndarray, p_b: np.ndarray, principals: list[str],
                          axes: list[str], n_permutations: int = 10000,
                          seed: int = REGISTERED_SEED, alpha: float = 0.01,
                          batch: int = 64, top: int = 12,
                          details: bool = True) -> dict:
    """The dispersion statistic on one run, both zero-spread modes, on one null.

    ``p_t`` and ``p_b`` are (N, I, J) cell rates from ``cell_rates``. The
    registered statistic is recomputed on the same permutations as a check
    that the permutation stream is the registered one. ``details=False``
    returns only the p-values, for the placebo.
    """
    n_c, n_i, _ = p_t.shape
    d = excess_effect(p_t, p_b)
    dbar, m = mean_excess_grid(d)
    t_obs = registered_t(d)
    s_obs, _ = run_maxima(t_obs)
    z_obs = {mode: dispersion_z(dbar, mode) for mode in ZERO_SPREAD_MODES}

    orders = permutation_orders(n_c, n_i, n_permutations, seed)
    null_s = np.empty(n_permutations)
    null = {mode: (np.empty(n_permutations), np.empty(n_permutations), [0])
            for mode in ZERO_SPREAD_MODES}
    for lo in range(0, n_permutations, batch):
        dp = _permute(d, orders[lo:lo + batch])
        null_s[lo:lo + batch], _ = run_maxima(registered_t(dp))
        db, _ = mean_excess_grid(dp)
        for mode in ZERO_SPREAD_MODES:
            zp = dispersion_z(db, mode)
            a, s = run_maxima(zp)
            null[mode][0][lo:lo + batch] = a
            null[mode][1][lo:lo + batch] = s
            null[mode][2][0] += int(np.any(np.isinf(zp.reshape(zp.shape[0], -1)),
                                           axis=1).sum())

    out: dict = {
        "candidates": list(principals), "n_candidates": n_c, "n_instructions": n_i,
        "n_axes": len(axes), "n_permutations": n_permutations, "seed": seed,
        "alpha": alpha,
        "roster_flag": ("not computable: two candidates leave one other value"
                        if n_c < 3 else
                        "unstable: the spread is taken over two values" if n_c == 3
                        else ""),
        "registered_S_recomputed": float(s_obs),
        # Exact comparison, as ``paired_max_test`` makes it, so this is a check
        # of the permutation stream. On a mathematical tie both codes can land
        # one ulp apart, which moves this p by one count in rare replicates.
        "registered_p_recomputed": permutation_tail_share(null_s, float(s_obs),
                                                          n_permutations),
    }
    for mode in ZERO_SPREAD_MODES:
        null_abs, null_pos, n_inf = null[mode]
        if details:
            out[mode] = _verdict(z_obs[mode], dbar, m, null_abs, null_pos, n_inf[0],
                                 list(principals), list(axes), alpha, top)
        else:
            computable = bool(np.any(~np.isnan(z_obs[mode])))
            z_abs, z_pos = run_maxima(z_obs[mode])
            out[mode] = {
                "computable": computable,
                "Z": float(z_abs) if computable else None,
                "p": _tail_share(null_abs, float(z_abs), n_permutations)
                if computable else None,
                "p_signed": _tail_share(null_pos, float(z_pos), n_permutations)
                if computable else None}
    return out


def loser_dispersion_test_tables(target: BehaviorTable, base: BehaviorTable,
                                 **kwargs) -> dict:
    """``loser_dispersion_test`` on two behavior tables, checked as stage 6 checks them."""
    if target.principals != base.principals or target.axes != base.axes:
        raise ValueError("target and base must share candidates and axes")
    if target.blocks != base.blocks:
        raise ValueError("target and base were scored on different instruction sets")
    p_t, principals, _ = cell_rates(target)
    p_b, _, _ = cell_rates(base)
    return loser_dispersion_test(p_t, p_b, principals, list(target.axes), **kwargs)
