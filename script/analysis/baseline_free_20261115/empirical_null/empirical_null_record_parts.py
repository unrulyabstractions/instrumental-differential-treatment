"""Pieces of one grid's record: fit rows, percentile blocks, resampling accumulators, cell flags."""

from __future__ import annotations

import numpy as np

from script.analysis.baseline_free_20261115.empirical_null.efron_null_estimators import (
    FDR_CUT, REASONS, fit_empirical_null)

__all__ = ["ESTIMATORS", "BULK_P0", "INFINITE_REASONS", "Acc", "cell_flags", "fits_into", "jack",
           "pct", "plurality", "rank", "robust_var", "row"]

ESTIMATORS = ("cm", "mle", "loc")
Q = (2.5, 50.0, 97.5)
MAD = 1.4826
#: Efron's bulk condition: the fitted null share is at least this, and its axis-block
#: interval reaches 1 (a share above 1 beyond sampling error means the normal misfits).
BULK_P0 = 0.9


def row(fits: dict, i: int) -> dict:
    """One grid's fits: delta0, sigma0, p0, and why a fit is undefined."""
    out = {}
    for e in ESTIMATORS:
        code = int(fits[f"{e}_reason"][i])
        out[e] = {"delta0": float(fits[f"{e}_delta"][i]), "sigma0": float(fits[f"{e}_sigma"][i]),
                  "p0": float(fits[f"{e}_p0"][i]),
                  "undefined_reason": REASONS[e].get(code) if code else None}
    return out | {
        "n_fitted": int(fits["n"][i]), "mle_n_inside": int(fits["mle_n0"][i]),
        "loc_n_inside": int(fits["loc_n0"][i]),
        "loc_window": [float(fits["loc_window_lo"][i]), float(fits["loc_window_hi"][i])],
        "mle_exists": bool(fits["mle_exists"][i]), "loc_exists": bool(fits["loc_exists"][i])}


#: Codes of undefined fits whose sigma0 is unbounded (the centre is flatter than any
#: normal, or not concave); they enter resampled distributions as +inf.
INFINITE_REASONS = {"cm": (3,), "mle": (2,), "loc": (2,)}
_BIG = np.finfo(float).max / 8


def pct(x: np.ndarray) -> dict:
    """2.5, 50 and 97.5 percentiles over the defined draws, +inf included; NaN draws left out."""
    x = np.asarray(x, dtype=float)
    ok = x[~np.isnan(x)]
    if ok.size == 0 or not np.any(np.isfinite(ok)):
        return {"n": 0, "n_infinite": int(np.isinf(ok).sum()), "n_undefined": int(x.size - ok.size)}
    q = np.percentile(np.where(np.isinf(ok), np.sign(ok) * _BIG, ok), Q)
    q = np.where(np.abs(q) >= _BIG / 2, np.sign(q) * np.inf, q)
    lo, mid, hi = (float(v) for v in q)
    return {"lo": lo, "median": mid, "hi": hi, "n": int(ok.size),
            "n_infinite": int(np.isinf(ok).sum()), "n_undefined": int(x.size - ok.size)}


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
        unbounded = np.isin(f[f"{e}_reason"], INFINITE_REASONS[e])
        acc.add(f"{prefix}{e}_sigma", np.where(unbounded, np.inf, f[f"{e}_sigma"]))
        acc.add(f"{prefix}{e}_delta", f[f"{e}_delta"])
        acc.add(f"{prefix}{e}_p0", f[f"{e}_p0"])
    return f


def cell_flags(t, z, u, fdr: dict, cands, axes, rows) -> dict:
    """Per-candidate flag counts and the flagged cells under each fitted null.

    ``fdr`` maps each estimator to the local fdr of every fitted cell, flattened
    over (row, axis) in the order of ``rows``.
    """
    out = {f"flags_{e}": {} for e in ESTIMATORS} | {"mean_u2": {}, "flagged_cells": []}
    n_j = len(axes)
    for r, c in enumerate(rows):
        uc = u[r]
        here = {e: fdr[e][r * n_j:(r + 1) * n_j] for e in ESTIMATORS}
        for e in ESTIMATORS:
            out[f"flags_{e}"][cands[c]] = int(np.sum(here[e] < FDR_CUT))
        out["mean_u2"][cands[c]] = float(np.nanmean(uc ** 2)) if np.any(~np.isnan(uc)) else None
        hit = np.zeros(n_j, dtype=bool)
        for e in ESTIMATORS:
            hit |= here[e] < FDR_CUT
        for j in np.flatnonzero(hit):
            out["flagged_cells"].append({"candidate": cands[c], "axis_id": axes[j],
                                         "t": float(t[c, j]), "z": float(z[r, j]),
                                         "u": float(uc[j]),
                                         **{f"fdr_{e}": float(here[e][j]) for e in ESTIMATORS}})
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
