"""Pieces of one grid's record: fit rows, percentile blocks, resampling accumulators, cell flags."""

from __future__ import annotations

import numpy as np

from script.analysis.baseline_free_20261115.empirical_null.efron_null_estimators import (
    FDR_CUT, fit_empirical_null)

__all__ = ["ESTIMATORS", "Acc", "cell_flags", "fits_into", "jack", "pct", "plurality", "rank",
           "robust_var", "row"]

ESTIMATORS = ("cm", "mle", "loc")
Q = (2.5, 50.0, 97.5)
MAD = 1.4826


def row(fits: dict, i: int) -> dict:
    return {e: {"delta0": float(fits[f"{e}_delta"][i]), "sigma0": float(fits[f"{e}_sigma"][i]),
                "p0": float(fits[f"{e}_p0"][i])} for e in ESTIMATORS} | {
        "n_fitted": int(fits["n"][i]), "mle_n_inside": int(fits["mle_n0"][i]),
        "mle_exists": bool(fits["mle_exists"][i]), "loc_exists": bool(fits["loc_exists"][i])}


def pct(x: np.ndarray) -> dict:
    x = np.asarray(x, dtype=float)
    ok = x[np.isfinite(x)]
    if ok.size == 0:
        return {"n": 0}
    lo, mid, hi = np.percentile(ok, Q)
    return {"lo": float(lo), "median": float(mid), "hi": float(hi), "n": int(ok.size),
            "n_undefined": int(x.size - ok.size)}


def jack(x: np.ndarray) -> dict:
    """Delete-one jackknife standard error over the defined replicates."""
    x = np.asarray(x, dtype=float)
    ok = x[np.isfinite(x)]
    if ok.size < 2:
        return {"se": None, "n": int(ok.size), "n_undefined": int(x.size - ok.size)}
    se = np.sqrt((ok.size - 1) / ok.size * np.sum((ok - ok.mean()) ** 2))
    return {"se": float(se), "n": int(ok.size), "n_undefined": int(x.size - ok.size)}


def robust_var(e: np.ndarray) -> np.ndarray:
    med = np.nanmedian(e, axis=1, keepdims=True)
    return (MAD * np.nanmedian(np.abs(e - med), axis=1)) ** 2


class Acc:
    """Per-draw arrays collected batch by batch."""

    def __init__(self):
        self.d: dict[str, list] = {}

    def add(self, key: str, value):
        self.d.setdefault(key, []).append(np.asarray(value))

    def get(self, key: str) -> np.ndarray:
        return np.concatenate(self.d[key])


def fits_into(acc: Acc, prefix: str, u_rows: np.ndarray) -> dict:
    f = fit_empirical_null(u_rows)
    for e in ESTIMATORS:
        acc.add(f"{prefix}{e}_sigma", f[f"{e}_sigma"])
        acc.add(f"{prefix}{e}_delta", f[f"{e}_delta"])
    return f


def cell_flags(t, z, u, fdr_cm, fdr_mle, cands, axes, rows) -> dict:
    """Per-candidate flag counts and the flagged cells under each fitted null."""
    out = {"flags_cm": {}, "flags_mle": {}, "mean_u2": {}, "flagged_cells": []}
    n_j = len(axes)
    for r, c in enumerate(rows):
        uc = u[r]
        fc, fm = fdr_cm[r * n_j:(r + 1) * n_j], fdr_mle[r * n_j:(r + 1) * n_j]
        out["flags_cm"][cands[c]] = int(np.sum(fc < FDR_CUT))
        out["flags_mle"][cands[c]] = int(np.sum(fm < FDR_CUT))
        out["mean_u2"][cands[c]] = float(np.nanmean(uc ** 2)) if np.any(~np.isnan(uc)) else None
        for j in np.flatnonzero((fc < FDR_CUT) | (fm < FDR_CUT)):
            out["flagged_cells"].append({"candidate": cands[c], "axis_id": axes[j],
                                         "t": float(t[c, j]), "z": float(z[r, j]),
                                         "u": float(uc[j]), "fdr_cm": float(fc[j]),
                                         "fdr_mle": float(fm[j])})
    return out


def rank(stat: dict, who: str | None) -> dict | None:
    """The rank p of a pre-registered candidate's set statistic among the k: floor 1/k."""
    if who is None or stat.get(who) is None:
        return None
    vals = {c: v for c, v in stat.items() if v is not None}
    return {"value": vals[who], "p_rank": sum(v >= vals[who] for v in vals.values()) / len(vals),
            "floor": 1 / len(vals)}


def plurality(flags: dict) -> list[str]:
    top = max(flags.values())
    return sorted(c for c, v in flags.items() if v == top) if top > 0 else []
