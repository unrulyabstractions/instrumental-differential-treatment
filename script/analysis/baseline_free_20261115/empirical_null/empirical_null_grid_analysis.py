"""Everything the family reports for one effect grid ``d`` (candidate, instruction, axis).

Observed: the three empirical-null fits on the axis-centred z, the same fits on
uncentred z, the local fdr of every cell, the maximum |t| with its permutation
p, and the lift lambda = median observed |t| / median permuted |t|.

Permutation null (10,000 draws, the stored test's own stream): the same fits
on every permuted grid, so sigma0 and lambda are referred to their values when
candidate labels carry no information.

Bootstrap over instructions (1,000 resamples): the fits on each resample. A
resample adds one unit of sampling noise to every cell's t, which widens the
bulk, so each resample's sigma0 is also reported with that added variance
removed: v* is the squared robust spread (1.4826 MAD) of u* - u over cells.
The axis-block bootstrap resamples whole axes, each carrying its k cells, and
the delete-one jackknife over instructions gives a standard error that adds no
resampling noise to any cell.

With ``documented``, every fit is repeated with that candidate's row left out
before centring.
"""

from __future__ import annotations

import numpy as np

from src.compare.paired_excess_measures import permutation_tail_share

from script.analysis.baseline_free_20261115.empirical_null.efron_null_estimators import (
    fit_empirical_null)
from script.analysis.baseline_free_20261115.empirical_null.empirical_null_record_parts import (
    ESTIMATORS, Acc, cell_flags, fits_into, jack, pct, plurality, rank, robust_var, row)
from script.analysis.baseline_free_20261115.empirical_null.empirical_null_grids import (
    centred, excess_batched, flatten_rows, grid_t, permute, stream_orders)

__all__ = ["SEED", "N_PERM", "N_BOOT", "analyse_grid"]

SEED, N_PERM, N_BOOT, BATCH = 20260726, 10000, 1000, 50


def analyse_grid(d: np.ndarray, kind: str, cands: list[str], axes: tuple[str, ...],
                 documented: str | None = None, n_perm: int = N_PERM,
                 n_boot: int = N_BOOT, seed: int = SEED, batch: int = BATCH,
                 pair: tuple[np.ndarray, np.ndarray] | None = None) -> dict:
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
        sel_t = abs_t[rows]
        cells = cell_flags(t, z, u, f["fdr_cm"][0], f["fdr_mle"][0], cands, axes, rows)
        obs[name] = {"fit": row(f, 0), "fit_uncentred": row(zu, 0), "u": u, "z": z,
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
        pooled_all.append(flat[~np.isnan(flat)].astype(np.float32))
        pooled_fit.append(flat[fp.reshape(flat.shape)].astype(np.float32))
        for name, keep in variants.items():
            rows = np.arange(n_c) if keep is None else np.flatnonzero(keep)
            sub = flat.reshape(tp.shape)[:, rows].reshape(tp.shape[0], -1)
            subfit = fp[:, rows].reshape(tp.shape[0], -1)
            perm.add(f"{name}|med_all", np.nanmedian(sub, axis=1))
            perm.add(f"{name}|med_fit", np.nanmedian(np.where(subfit, sub, np.nan), axis=1))
            fits_into(perm, f"{name}|", flatten_rows(centred(tp, mp, fp, keep)[1]))
    perm_med_all = float(np.median(np.concatenate(pooled_all)))
    perm_med_fit = float(np.median(np.concatenate(pooled_fit)))
    maxima = perm.get("max")

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

    out = {"kind": kind, "n_candidates": n_c, "n_instructions": n_i, "n_axes": n_j,
           "n_cells": n_c * n_j, "n_nan": int(np.isnan(t).sum()),
           "n_zero_spread": int(np.sum(~fit & ~np.isnan(t))),
           "n_zero_spread_t_zero": int(np.sum((t == 0) & ~fit)),
           "n_infinite": int(np.isinf(t).sum()),
           "S": s_obs, "p_S": permutation_tail_share(maxima, s_obs, n_perm),
           "argmax_candidate": cands[int(np.unravel_index(np.nanargmax(abs_t), abs_t.shape)[0])],
           "argmax_axis": axes[int(np.unravel_index(np.nanargmax(abs_t), abs_t.shape)[1])],
           "perm_abs_median": perm_med_all, "perm_abs_median_fitted": perm_med_fit,
           "null_max_p95": float(np.quantile(maxima, 0.95)), "variants": {}}
    for name in variants:
        o = obs[name]
        rec = {"fit": o["fit"], "fit_uncentred": o["fit_uncentred"],
               "lambda": o["median_abs_t"] / perm_med_all,
               "lambda_fitted_cells": o["median_abs_t_fitted"] / perm_med_fit,
               "median_abs_t": o["median_abs_t"], "median_abs_t_fitted": o["median_abs_t_fitted"],
               "p_lambda": permutation_tail_share(perm.get(f"{name}|med_all"), o["median_abs_t"], n_perm),
               "p_lambda_fitted_cells": permutation_tail_share(
                   perm.get(f"{name}|med_fit"), o["median_abs_t_fitted"], n_perm),
               "permutation": {}, "bootstrap_instructions": {}, "bootstrap_axes": {},
               "jackknife_instructions": {}}
        v = boot.get(f"{name}|v")
        vt = boot.get(f"{name}|vt")
        for e in ESTIMATORS:
            ps = perm.get(f"{name}|{e}_sigma")
            obs_s = o["fit"][e]["sigma0"]
            ok = np.isfinite(ps)
            rec["permutation"][e] = {
                "sigma0": pct(ps), "delta0": pct(perm.get(f"{name}|{e}_delta")),
                "p_sigma0": (float((1 + np.sum(ps[ok] >= obs_s)) / (1 + ok.sum()))
                             if np.isfinite(obs_s) else None),
                "ratio_to_null_median": (obs_s / float(np.median(ps[ok]))
                                         if np.isfinite(obs_s) and ok.any() else None)}
            bs = boot.get(f"{name}|{e}_sigma")
            rec["bootstrap_instructions"][e] = {
                "sigma0_raw": pct(bs),
                "sigma0_noise_removed": pct(np.sqrt(np.clip(bs ** 2 - v, 0, None))),
                "delta0": pct(boot.get(f"{name}|{e}_delta"))}
            rec["bootstrap_axes"][e] = {"sigma0": pct(axb.get(f"{name}|{e}_sigma")),
                                        "delta0": pct(axb.get(f"{name}|{e}_delta"))}
            rec["jackknife_instructions"][e] = {"sigma0": jack(jk.get(f"{name}|{e}_sigma")),
                                                "delta0": jack(jk.get(f"{name}|{e}_delta"))}
        mb = boot.get(f"{name}|med_all")
        rec["bootstrap_instructions"]["lambda_raw"] = pct(mb / perm_med_all)
        rec["bootstrap_instructions"]["lambda_noise_removed"] = pct(
            np.sqrt(np.clip(mb ** 2 - 0.6745 ** 2 * vt, 0, None)) / perm_med_all)
        rec["bootstrap_instructions"]["added_noise_var_u"] = pct(v)
        rec["bootstrap_axes"]["lambda"] = pct(axb.get(f"{name}|med_all") / perm_med_all)
        rec["jackknife_instructions"]["lambda"] = jack(jk.get(f"{name}|med_all") / perm_med_all)
        cells = o["cells"]
        rec["cells"] = {**cells, "n_flag_cm": int(sum(cells["flags_cm"].values())),
                        "n_flag_mle": int(sum(cells["flags_mle"].values())),
                        "plurality_cm": plurality(cells["flags_cm"]),
                        "plurality_mle": plurality(cells["flags_mle"])}
        if documented is not None and name == "all":
            rec["documented_rank"] = {s: rank(cells[s], documented)
                                      for s in ("flags_cm", "flags_mle", "mean_u2")}
        out["variants"][name] = rec
    out["_t"] = t
    out["_u"] = obs["all"]["u"]
    return out
