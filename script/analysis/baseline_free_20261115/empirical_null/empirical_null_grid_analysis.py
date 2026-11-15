"""Everything the family reports for one effect grid ``d`` (candidate, instruction, axis).

Observed: the three empirical-null fits on the axis-centred z, the same fits on
uncentred z and on two other centrings (the axis median, and each cell less the
median of the other candidates' cells), the local fdr of every cell under each
fitted null, the maximum |t| with its permutation p, and the lift lambda =
median observed |t| / median permuted |t|.

Permutation null (10,000 draws, the stored test's own stream): the same fits
on every permuted grid, so sigma0 and lambda are referred to their values when
candidate labels carry no information. Every permutation p counts a permuted
value within ``TIE_TOL`` of the observed one as at least as large. The median
|t| of a grid often sits on an atom (a cell that differs from the others on a
single instruction has |t| = 1 exactly), and float noise in the last bit would
otherwise decide the comparison. The maximum's p is also reported without the
tolerance, as the registered test computes it.

A resampled fit with no finite sigma0 (the centre flatter than any normal, or
not concave) enters every resampled distribution of sigma0 as +inf, so it
counts as reaching the observed value.

Axis-block bootstrap (1,000 resamples): whole axes, each carrying its k cells.
It gives the reported intervals, including the interval of p0 that the bulk
condition reads: a fit meets it when p0 >= 0.9 and the interval of p0 reaches 1.

Bootstrap over instructions (1,000 resamples) and the delete-one jackknife over
instructions: context only. A resample adds one unit of sampling noise to every
cell's t, which widens the bulk, so each resample's sigma0 is also reported with
that added variance removed: v* is the squared robust spread (1.4826 MAD) of
u* - u over cells. ``slim`` skips both (the placebo replicates).

With ``documented``, every fit is repeated with that candidate's row left out
before centring.
"""

from __future__ import annotations

import numpy as np

from src.compare.paired_excess_measures import permutation_tail_share

from script.analysis.baseline_free_20261115.empirical_null.efron_null_estimators import (
    fit_empirical_null)
from script.analysis.baseline_free_20261115.empirical_null.empirical_null_record_parts import (
    BULK_P0, ESTIMATORS, Acc, cell_flags, fits_into, jack, pct, plurality, rank, robust_var, row)
from script.analysis.baseline_free_20261115.empirical_null.empirical_null_grids import (
    centred, centred_alternative, excess_batched, flatten_rows, grid_t, permute, stream_orders)

__all__ = ["SEED", "N_PERM", "N_BOOT", "TIE_TOL", "analyse_grid", "tail_share"]

SEED, N_PERM, N_BOOT, BATCH = 20260726, 10000, 1000, 50
#: Permuted values within this (times max(1, |observed|)) of the observed one count as ties.
TIE_TOL = 1e-9
ALT_CENTRINGS = ("axis_median", "others_median")


def tail_share(null: np.ndarray, value: float) -> float:
    """(1 + #{finite null >= value - tol}) / (1 + #finite null); ties count as at least as large."""
    null = np.asarray(null, dtype=float)
    ok = np.isfinite(null) | (np.isinf(null) & (null > 0))
    if value is None or np.isnan(value):
        return 1.0
    tol = TIE_TOL * max(1.0, abs(value)) if np.isfinite(value) else 0.0
    return float((1 + np.sum(null[ok] >= value - tol)) / (1 + ok.sum()))


def _atoms(obs_abs: np.ndarray, med: float, perm_meds: np.ndarray) -> dict:
    """How far the median |t| sits on an atom: shares of observed cells and of permuted medians tying it."""
    tol = TIE_TOL * max(1.0, abs(med))
    return {"share_observed_cells_at_median": float(np.mean(np.abs(obs_abs - med) <= tol)),
            "share_permuted_medians_tied": float(np.mean(np.abs(perm_meds - med) <= tol))}


def analyse_grid(d: np.ndarray, kind: str, cands: list[str], axes: tuple[str, ...],
                 documented: str | None = None, n_perm: int = N_PERM,
                 n_boot: int = N_BOOT, seed: int = SEED, batch: int = BATCH,
                 pair: tuple[np.ndarray, np.ndarray] | None = None, slim: bool = False) -> dict:
    """The record for one grid; ``kind`` picks the permutation stream (see the grids module).

    With ``pair`` (the target and base rates whose excess is ``d``) a permutation
    relabels both and recomputes the excess, exactly as ``paired_max_test``;
    without it the rows of ``d`` are relabelled, as ``reference_free_max_test``.
    """
    n_c, n_i, n_j = d.shape
    variants = {"all": None}
    if documented is not None:
        variants[f"without_{documented}"] = np.array([c != documented for c in cands])

    t, m, fit = grid_t(d)
    abs_t = np.abs(t)
    s_obs = float(np.nanmax(abs_t)) if np.any(~np.isnan(abs_t)) else 0.0
    obs: dict = {}
    for name, keep in variants.items():
        rows = np.arange(n_c) if keep is None else np.flatnonzero(keep)
        z, u = centred(t, m, fit, keep)
        f = fit_empirical_null(flatten_rows(u), with_fdr=True)
        zu = fit_empirical_null(flatten_rows(np.where(np.isnan(u), np.nan, z)))
        alt = {how: row(fit_empirical_null(flatten_rows(centred_alternative(t, m, fit, how, keep))), 0)
               for how in ALT_CENTRINGS}
        sel_t = abs_t[rows]
        cells = cell_flags(t, z, u, {e: f[f"fdr_{e}"][0] for e in ESTIMATORS}, cands, axes, rows)
        obs[name] = {"fit": row(f, 0), "fit_uncentred": row(zu, 0), "fit_other_centrings": alt,
                     "u": u, "z": z, "abs_t": sel_t[~np.isnan(sel_t)],
                     "median_abs_t": float(np.median(sel_t[~np.isnan(sel_t)])),
                     "median_abs_t_fitted": float(np.median(sel_t[fit[rows]])),
                     "cells": cells, "rows": rows}

    perm, boot, axb = Acc(), Acc(), Acc()
    orders = stream_orders(kind, n_c, n_i, n_perm, seed)
    pooled_all, pooled_fit = [], []
    for lo in range(0, n_perm, batch):
        o = orders[lo:lo + batch]
        dp = (permute(d, o) if pair is None
              else excess_batched(permute(pair[0], o), permute(pair[1], o)))
        tp, mp, fp = grid_t(dp)
        flat = np.abs(tp).reshape(tp.shape[0], -1)
        has = np.any(~np.isnan(flat), axis=1)
        perm.add("max", np.where(has, np.nanmax(np.where(np.isnan(flat), -np.inf, flat), axis=1), 0.0))
        pooled_all.append(flat[~np.isnan(flat)])
        pooled_fit.append(flat[fp.reshape(flat.shape)])
        for name, keep in variants.items():
            rows = np.arange(n_c) if keep is None else np.flatnonzero(keep)
            sub = flat.reshape(tp.shape)[:, rows].reshape(tp.shape[0], -1)
            subfit = fp[:, rows].reshape(tp.shape[0], -1)
            perm.add(f"{name}|med_all", np.nanmedian(sub, axis=1))
            perm.add(f"{name}|med_fit", np.nanmedian(np.where(subfit, sub, np.nan), axis=1))
            fits_into(perm, f"{name}|", flatten_rows(centred(tp, mp, fp, keep)[1]))
    pooled_all, pooled_fit = np.concatenate(pooled_all), np.concatenate(pooled_fit)
    perm_med_all = float(np.median(pooled_all))
    perm_med_fit = float(np.median(pooled_fit))
    perm_med_all_f32 = float(np.median(pooled_all.astype(np.float32)))
    del pooled_all, pooled_fit
    maxima = perm.get("max")

    if not slim:
        rng = np.random.default_rng(seed)
        idx = rng.integers(0, n_i, (n_boot, n_i))
        for lo in range(0, n_boot, batch):
            db = np.transpose(d[:, idx[lo:lo + batch], :], (1, 0, 2, 3))
            tb, mb, fb = grid_t(db)
            for name, keep in variants.items():
                rows = np.arange(n_c) if keep is None else np.flatnonzero(keep)
                ub = centred(tb, mb, fb, keep)[1]
                fits_into(boot, f"{name}|", flatten_rows(ub))
                boot.add(f"{name}|v", robust_var(flatten_rows(ub - obs[name]["u"][None])))
                both = fb[:, rows] & fit[rows][None]
                tsub = tb[:, rows]
                boot.add(f"{name}|vt", robust_var(flatten_rows(np.where(both, tsub - t[rows][None], np.nan))))
                a = np.abs(tsub).reshape(tsub.shape[0], -1)
                boot.add(f"{name}|med_all", np.nanmedian(a, axis=1))
        jk = Acc()
        for lo in range(0, n_i, batch):
            ids = list(range(lo, min(lo + batch, n_i)))
            tj, mj, fj = grid_t(np.stack([np.delete(d, i, axis=1) for i in ids]))
            for name, keep in variants.items():
                rows = np.arange(n_c) if keep is None else np.flatnonzero(keep)
                fits_into(jk, f"{name}|", flatten_rows(centred(tj, mj, fj, keep)[1]))
                a = np.abs(tj[:, rows]).reshape(len(ids), -1)
                jk.add(f"{name}|med_all", np.nanmedian(a, axis=1))
    rng2 = np.random.default_rng([seed, 1])
    jdx = rng2.integers(0, n_j, (n_boot, n_j))
    for name in variants:
        u = obs[name]["u"]
        a = abs_t[obs[name]["rows"]]
        for lo in range(0, n_boot, batch):
            ub = np.transpose(u[:, jdx[lo:lo + batch]], (1, 0, 2))
            fits_into(axb, f"{name}|", flatten_rows(ub))
            ab = np.transpose(a[:, jdx[lo:lo + batch]], (1, 0, 2)).reshape(ub.shape[0], -1)
            axb.add(f"{name}|med_all", np.nanmedian(ab, axis=1))

    i_max = np.unravel_index(np.nanargmax(abs_t), abs_t.shape)
    out = {"kind": kind, "n_candidates": n_c, "n_instructions": n_i, "n_axes": n_j,
           "n_cells": n_c * n_j, "n_nan": int(np.isnan(t).sum()),
           "n_zero_spread": int(np.sum(~fit & ~np.isnan(t))),
           "n_zero_spread_t_zero": int(np.sum((t == 0) & ~fit)),
           "n_infinite": int(np.isinf(t).sum()),
           "S": s_obs, "p_S": permutation_tail_share(maxima, s_obs, n_perm),
           "p_S_ties_as_at_least": tail_share(maxima, s_obs),
           "argmax_candidate": cands[int(i_max[0])], "argmax_axis": axes[int(i_max[1])],
           "perm_abs_median": perm_med_all, "perm_abs_median_float32": perm_med_all_f32,
           "perm_abs_median_fitted": perm_med_fit,
           "null_max_p95": float(np.quantile(maxima, 0.95)),
           "analysis": {"n_permutations": n_perm, "n_bootstrap": n_boot, "seed": seed,
                        "axis_block_seed": [seed, 1], "batch": batch, "tie_tolerance": TIE_TOL,
                        "bulk_p0_min": BULK_P0, "slim": slim, "stream": kind,
                        "paired": pair is not None},
           "variants": {}}
    for name in variants:
        o = obs[name]
        med_all = perm.get(f"{name}|med_all")
        rec = {"fit": o["fit"], "fit_uncentred": o["fit_uncentred"],
               "fit_other_centrings": o["fit_other_centrings"],
               "lambda": o["median_abs_t"] / perm_med_all,
               "lambda_fitted_cells": o["median_abs_t_fitted"] / perm_med_fit,
               "median_abs_t": o["median_abs_t"], "median_abs_t_fitted": o["median_abs_t_fitted"],
               "p_lambda": tail_share(med_all, o["median_abs_t"]),
               "p_lambda_without_tie_tolerance": permutation_tail_share(med_all, o["median_abs_t"], n_perm),
               "p_lambda_fitted_cells": tail_share(perm.get(f"{name}|med_fit"), o["median_abs_t_fitted"]),
               "lambda_atoms": _atoms(o["abs_t"], o["median_abs_t"], med_all),
               "permutation": {}, "bootstrap_axes": {}}
        if not slim:
            rec["bootstrap_instructions"], rec["jackknife_instructions"] = {}, {}
        for e in ESTIMATORS:
            ps = perm.get(f"{name}|{e}_sigma")
            obs_s = o["fit"][e]["sigma0"]
            band = pct(ps)
            rec["permutation"][e] = {
                "sigma0": band, "delta0": pct(perm.get(f"{name}|{e}_delta")),
                "p0": pct(perm.get(f"{name}|{e}_p0")),
                "p_sigma0": tail_share(ps, obs_s) if np.isfinite(obs_s) else None,
                "ratio_to_null_median": (obs_s / band["median"]
                                         if np.isfinite(obs_s) and band.get("n") else None)}
            p0_block = pct(axb.get(f"{name}|{e}_p0"))
            rec["bootstrap_axes"][e] = {"sigma0": pct(axb.get(f"{name}|{e}_sigma")),
                                        "delta0": pct(axb.get(f"{name}|{e}_delta")),
                                        "p0": p0_block}
            p0 = o["fit"][e]["p0"]
            o["fit"][e]["bulk_ok"] = bool(np.isfinite(p0) and p0 >= BULK_P0
                                          and p0_block.get("n") and p0_block["lo"] <= 1.0)
            if not slim:
                bs = boot.get(f"{name}|{e}_sigma")
                v = boot.get(f"{name}|v")
                rec["bootstrap_instructions"][e] = {
                    "sigma0_raw": pct(bs),
                    "sigma0_noise_removed": pct(np.sqrt(np.clip(bs ** 2 - v, 0, None))),
                    "delta0": pct(boot.get(f"{name}|{e}_delta"))}
                rec["jackknife_instructions"][e] = {"sigma0": jack(jk.get(f"{name}|{e}_sigma")),
                                                    "delta0": jack(jk.get(f"{name}|{e}_delta"))}
        if not slim:
            mb = boot.get(f"{name}|med_all")
            vt = boot.get(f"{name}|vt")
            rec["bootstrap_instructions"]["lambda_raw"] = pct(mb / perm_med_all)
            rec["bootstrap_instructions"]["lambda_noise_removed"] = pct(
                np.sqrt(np.clip(mb ** 2 - 0.6745 ** 2 * vt, 0, None)) / perm_med_all)
            rec["bootstrap_instructions"]["added_noise_var_u"] = pct(boot.get(f"{name}|v"))
            rec["jackknife_instructions"]["lambda"] = jack(jk.get(f"{name}|med_all") / perm_med_all)
        rec["bootstrap_axes"]["lambda"] = pct(axb.get(f"{name}|med_all") / perm_med_all)
        cells = o["cells"]
        counts = {}
        for e in ESTIMATORS:
            n_flag = int(sum(cells[f"flags_{e}"].values()))
            supported = o["fit"][e]["bulk_ok"]
            counts |= {f"n_flag_{e}": n_flag, f"plurality_{e}": plurality(cells[f"flags_{e}"]),
                       f"bulk_ok_{e}": supported,
                       f"n_flag_{e}_supported": n_flag if supported else 0,
                       f"plurality_{e}_supported": plurality(cells[f"flags_{e}"]) if supported else []}
        rec["cells"] = {**cells, **counts}
        if documented is not None and name == "all":
            rec["documented_rank"] = {s: rank(cells[s], documented)
                                      for s in ("flags_loc", "flags_mle", "flags_cm", "mean_u2")}
        out["variants"][name] = rec
    out["_t"] = t
    out["_u"] = obs["all"]["u"]
    return out
