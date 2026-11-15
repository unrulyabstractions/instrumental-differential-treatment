"""Cell name effects and their cross-model moments, shared by the correlation scripts.

A model's name effect in cell (candidate, axis) is its one-vs-rest gap averaged
over instructions, ``g = mean_i [p(c, i, a) - mean_{c' != c} p(c', i, a)]``. It is
built with the registered test's own ``excess_effect`` against an all-zero table
on the same cells, so a missing cell stays missing exactly as in the test.
"""

from __future__ import annotations

import numpy as np

from script.analysis.baseline_free_20261115.proxy_swaps.swap_subjects import N_BOOT, SEED
from src.compare.paired_excess_measures import cell_rates, excess_effect
from src.compare.placebo_calibration import subset_table


def gap_grid(table) -> np.ndarray:
    """(candidate, instruction, axis) one-vs-rest gaps of one table."""
    rates, _, _ = cell_rates(table)
    return excess_effect(rates, np.where(np.isnan(rates), np.nan, 0.0))


def cell_effect(table) -> np.ndarray:
    with np.errstate(invalid="ignore"):
        return np.nanmean(gap_grid(table), axis=1)


def moments(gt: np.ndarray, gp: np.ndarray) -> dict:
    """r, beta and the variance ratio over the last axis (cells), vectorized.

    ``beta`` is Cov(g_T, g_P) / Var(g_P) and ``var_ratio`` is
    Var(g_T - g_P) / Var(g_T); var_ratio < 1 exactly when beta > 1/2.
    """
    ok = np.isfinite(gt) & np.isfinite(gp)
    n = ok.sum(axis=-1)
    gt, gp = np.where(ok, gt, 0.0), np.where(ok, gp, 0.0)
    mt, mp = gt.sum(-1) / n, gp.sum(-1) / n
    dt = np.where(ok, gt - mt[..., None], 0.0)
    dp = np.where(ok, gp - mp[..., None], 0.0)
    vt, vp, c = (dt * dt).sum(-1), (dp * dp).sum(-1), (dt * dp).sum(-1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return {"r": c / np.sqrt(vt * vp), "beta": c / vp, "var_ratio": (vt + vp - 2 * c) / vt,
                "sd_target": np.sqrt(vt / (n - 1)), "sd_proxy": np.sqrt(vp / (n - 1)),
                "n_cells": n}


def interval(x: np.ndarray) -> list[float]:
    """95% percentile interval (used for the spread over split replicates)."""
    return [float(np.nanquantile(x, 0.025)), float(np.nanquantile(x, 0.975))]


def boot_interval(boot: np.ndarray, point: float) -> dict:
    """Bootstrap spread of a statistic: a normal 95% interval and the plain percentiles.

    Resampling instructions duplicates some of them, which adds noise to every
    cell mean, so the bootstrap distribution of r sits below the point estimate
    when the cell effects are mostly noise. The percentile interval can then
    exclude the point estimate, and the bias-corrected percentile interval
    degenerates. The interval reported is the point estimate plus or minus 1.96
    bootstrap standard deviations; the percentiles and the bias are kept beside it.
    """
    b = boot[np.isfinite(boot)]
    sd = float(np.std(b, ddof=1))
    return {"ci": [float(point - 1.96 * sd), float(point + 1.96 * sd)], "sd": sd,
            "percentile": interval(b), "bias": float(np.mean(b) - point)}


def boot_effects(grid: np.ndarray) -> np.ndarray:
    """(N_BOOT, cells) cell effects over instruction resamples.

    The resample indices depend only on the number of instructions and the seed,
    so two models on the same instructions are resampled together.
    """
    n_i = grid.shape[1]
    idx = np.random.default_rng(SEED).integers(0, n_i, size=(N_BOOT, n_i))
    with np.errstate(invalid="ignore"):
        return np.stack([np.nanmean(grid[:, k, :], 1).ravel() for k in idx])


def s_halves(n_s: int, replicate: int) -> tuple[np.ndarray, np.ndarray]:
    """One random split of the sample indices 0..n_s-1, shared by every subject.

    ``SeedSequence([20260726, 1000, replicate])``: 1000 marks a split shared by
    all subjects, apart from the per-subject index of the within-cell splits.
    """
    order = np.random.default_rng(np.random.SeedSequence([SEED, 1000, replicate])).permutation(n_s)
    return np.sort(order[: n_s // 2]), np.sort(order[n_s // 2:])


def s_half_effects(table, s: np.ndarray, n_s: int, n_rep: int) -> list[tuple]:
    """Cell effects on the two shared sample-index halves, per replicate."""
    out = []
    for rep in range(n_rep):
        h1, h2 = s_halves(n_s, rep)
        out.append(tuple(cell_effect(subset_table(table, np.flatnonzero(np.isin(s, h))))
                         .ravel() for h in (h1, h2)))
    return out


def _cov(x: np.ndarray, y: np.ndarray) -> float:
    ok = np.isfinite(x) & np.isfinite(y)
    return float(np.cov(x[ok], y[ok])[0, 1])


def name_effect_correlation(ht: list[tuple], hp: list[tuple]) -> dict:
    """Correlation of stable name effects, with the shared judge order removed.

    Halves with disjoint sample indices share no reply and no judge axis order,
    so Cov(g_T on S1, g_P on S2) estimates Cov(mu_T, mu_P) and Cov(g_T on S1,
    g_T on S2) estimates Var(mu_T), where mu is a model's expected cell effect.
    Their ratio needs no length correction. Halves with the same sample indices
    also share the axis order, and the gap between the two covariances is the
    part of the cross-model covariance that the shared order carries.
    """
    c_tt = np.mean([_cov(a, b) for a, b in ht])
    c_pp = np.mean([_cov(a, b) for a, b in hp])
    c_cross = np.mean([(_cov(t1, p2) + _cov(t2, p1)) / 2 for (t1, t2), (p1, p2) in zip(ht, hp)])
    c_same = np.mean([(_cov(t1, p1) + _cov(t2, p2)) / 2 for (t1, t2), (p1, p2) in zip(ht, hp)])
    r_name = float(c_cross / np.sqrt(c_tt * c_pp)) if c_tt > 0 and c_pp > 0 else None
    return {"cov_within_target": float(c_tt), "cov_within_proxy": float(c_pp),
            "cov_cross_disjoint_s": float(c_cross), "cov_cross_same_s": float(c_same),
            "shared_order_share": float((c_same - c_cross) / c_same) if c_same > 0 else None,
            "r_name_effects": r_name, "n_s_splits": len(ht)}


# --- Instruction bootstrap of the name-effect correlation -------------------
#
# The point estimate above averages each half's gap grid over instructions. A
# bootstrap resample replaces that plain mean by a weighted mean whose weights
# are the multiplicities of the instructions in the resample. The resamples are
# the very ones ``boot_effects`` draws (``default_rng(20260726)``, one row of
# ``N_BOOT`` per resample), so every subject on the same instructions is
# resampled together and the observed r, beta and the name-effect quantities
# share one bootstrap.


def boot_weights(n_i: int) -> np.ndarray:
    """(N_BOOT, n_i) multiplicity of each instruction in each ``boot_effects`` resample."""
    idx = np.random.default_rng(SEED).integers(0, n_i, size=(N_BOOT, n_i))
    w = np.zeros((N_BOOT, n_i))
    np.add.at(w, (np.repeat(np.arange(N_BOOT), n_i), idx.ravel()), 1.0)
    return w


def weighted_effects(grid: np.ndarray, w: np.ndarray) -> np.ndarray:
    """(rows of w, cells) cell effects: the instruction mean of ``grid`` under weights ``w``.

    A row of ones gives ``cell_effect`` exactly (``np.nanmean`` over instructions).
    """
    c, n_i, a = grid.shape
    g = np.moveaxis(grid, 1, 0).reshape(n_i, c * a)
    ok = np.isfinite(g)
    num, den = w @ np.where(ok, g, 0.0), w @ ok.astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0, num / den, np.nan)


def masked_cov(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Two-pass sample covariance over the last axis, on cells finite in both."""
    ok = np.isfinite(x) & np.isfinite(y)
    n = ok.sum(-1)
    x0, y0 = np.where(ok, x, 0.0), np.where(ok, y, 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        dx = np.where(ok, x0 - (x0.sum(-1) / n)[..., None], 0.0)
        dy = np.where(ok, y0 - (y0.sum(-1) / n)[..., None], 0.0)
        return (dx * dy).sum(-1) / (n - 1)


def s_half_grids(table, s: np.ndarray, n_s: int, rep: int) -> tuple:
    """(candidate, instruction, axis) gap grids on the two shared sample-index halves of one split."""
    return tuple(gap_grid(subset_table(table, np.flatnonzero(np.isin(s, h))))
                 for h in s_halves(n_s, rep))


def name_moments(c_tt, c_pp, c_cross, c_same) -> dict:
    """The name-effect quantities from the four covariances (arrays over resamples).

    - ``r_name_effects``: c_cross / sqrt(c_tt c_pp), undefined unless both
      within-model covariances are positive.
    - ``stable_slope``: c_cross / c_pp, the slope of the target's stable name
      effects on the proxy's. Subtraction lowers the variance of the stable
      name effects exactly when it exceeds one half.
    - ``stable_var_ratio``: (c_tt + c_pp - 2 c_cross) / c_tt, the variance of the
      stable part of the difference over that of the target alone.
    """
    c_tt, c_pp, c_cross, c_same = (np.asarray(v, dtype=float) for v in (c_tt, c_pp, c_cross, c_same))
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.where((c_tt > 0) & (c_pp > 0), c_cross / np.sqrt(np.abs(c_tt * c_pp)), np.nan)
        slope = np.where(c_pp > 0, c_cross / c_pp, np.nan)
        vr = np.where(c_tt > 0, (c_tt + c_pp - 2 * c_cross) / c_tt, np.nan)
        share = np.where(c_same > 0, (c_same - c_cross) / c_same, np.nan)
    return {"r_name_effects": r, "stable_slope": slope, "stable_var_ratio": vr,
            "shared_order_share": share}


def percentile_summary(boot: np.ndarray, point: float, above: float | None = 0.5) -> dict:
    """95% percentile interval over the defined resamples, with the bias and the undefined count.

    A ratio of covariances is skewed and undefined when a within-model
    covariance is not positive, so its interval is the plain percentile one,
    not the normal one ``boot_interval`` gives r.
    """
    b = boot[np.isfinite(boot)]
    out = {"point": None if not np.isfinite(point) else float(point),
           "ci": [float(np.quantile(b, 0.025)), float(np.quantile(b, 0.975))] if b.size else None,
           "bias": float(np.mean(b) - point) if b.size and np.isfinite(point) else None,
           "n_defined": int(b.size), "n_resamples": int(boot.size)}
    if above is not None:
        out[f"share_above_{above}"] = float(np.mean(b > above)) if b.size else None
    return out


def corr_group(row: dict) -> tuple[str, str]:
    """The (type, subtype) a correlation row is pooled under; each base draw is its own group."""
    if row["type"] == "null_vs_base_draw":
        return row["type"], f"base {row['proxy']}" + (" (registered)" if row["proxy"] == "A" else "")
    return row["type"], row["subtype"]
