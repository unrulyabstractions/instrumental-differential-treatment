"""Grade arrays for the user-awareness subjects, shared by every detector in this folder.

A subject grades the same 16 exchanges under every identity, four samples per
cell. The exchange is the block: every identity sees it, so its difficulty is
common to all identities and cancels in any comparison between identities.

The unit a Transluce-style statistic reads is one identity's **exchange-blocked
mean grade**: the mean over exchanges of the identity's cell mean minus that
exchange's mean over all identities in the same session. With a complete design
this equals the raw mean minus the grand mean, so differences between
identities are the raw differences. Its noise variance comes from the spread of
the samples inside each cell, the only part of the grade that is pure sampling
noise. A missing grade stays missing and is never imputed.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from src.common.file_io import read_jsonl

REPO = Path(__file__).resolve().parents[4]
OUT = REPO / "out/main/baseline_free_20261115/user_awareness"

#: The three stored subjects, in a fixed order chosen before any result was read
#: (the order of the stored directories). All three are reported.
SUBJECTS: dict[str, dict] = {
    "gpt-5-mini": {"backend": "openai", "model": "gpt-5-mini",
                   "stored_dir": REPO / "out/main/external/user_awareness_grading"},
    "gpt-4.1-mini": {"backend": "openai", "model": "gpt-4.1-mini",
                     "stored_dir": REPO / "out/main/external/user_awareness_grading_gpt41mini"},
    "gpt-5": {"backend": "openai", "model": "gpt-5",
              "stored_dir": REPO / "out/main/external/user_awareness_grading_gpt5"},
}


def usable_rows(path: Path) -> list[dict]:
    """Level-1 grade rows that carry a parsed grade, exactly as the stored driver keeps them."""
    return [r for r in read_jsonl(path)
            if int(r["level"]) == 1 and not r.get("failed") and r.get("grade") is not None]


def failed_count(path: Path) -> int:
    return sum(1 for r in read_jsonl(path) if r.get("failed") or r.get("grade") is None)


def grade_cube(rows: list[dict], identities: list[str]) -> tuple[np.ndarray, list[str]]:
    """Grades as an (identity, exchange, sample) array, NaN where no grade exists."""
    exchanges = sorted({r["instruction_id"] for r in rows})
    n_s = max(int(r["s"]) for r in rows) + 1
    cube = np.full((len(identities), len(exchanges), n_s), np.nan)
    ii = {k: i for i, k in enumerate(identities)}
    ee = {e: j for j, e in enumerate(exchanges)}
    for r in rows:
        if r["principal"] in ii:
            cube[ii[r["principal"]], ee[r["instruction_id"]], int(r["s"])] = float(r["grade"])
    return cube, exchanges


def blocked_means(cube: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Exchange-blocked mean grade per identity and its sampling-noise variance.

    The variance treats each cell mean as independent with variance s^2/n from
    its own samples, and carries the identity's own weight in the exchange mean
    it is centred on. A cell with one sample has no within-cell variance; the
    pooled within-cell variance of that exchange stands in for it.
    """
    with np.errstate(invalid="ignore"):
        cell = np.nanmean(cube, axis=2)                       # (I, E)
        n = np.sum(~np.isnan(cube), axis=2).astype(float)     # (I, E)
        var = np.nanvar(cube, axis=2, ddof=1)                 # (I, E)
    pooled = np.nanmean(np.where(n >= 2, var, np.nan), axis=0)  # (E,)
    var = np.where(n >= 2, var, pooled[None, :])
    v_cell = np.where(n > 0, var / np.maximum(n, 1), np.nan)
    observed = ~np.isnan(cell)
    k = observed.sum(axis=0).astype(float)                  # identities per exchange
    ex_mean = np.nanmean(cell, axis=0)
    dev = cell - ex_mean[None, :]
    x = np.nanmean(dev, axis=1)
    e_i = observed.sum(axis=1).astype(float)
    # Var(cell_ie - mean_j cell_je) = (1 - 1/k)^2 v_ie + (1/k^2) sum_{j != i} v_je.
    tot = np.nansum(v_cell, axis=0)
    v_dev = (1 - 1 / k) ** 2 * v_cell + (tot[None, :] - v_cell) / k ** 2
    se2 = np.nansum(np.where(observed, v_dev, 0.0), axis=1) / np.maximum(e_i, 1) ** 2
    return x, se2


def raw_mean_grades(cube: np.ndarray) -> np.ndarray:
    """Plain mean of every grade an identity received, the stored driver's ``mean_grade``."""
    with np.errstate(invalid="ignore"):
        return np.nanmean(cube.reshape(cube.shape[0], -1), axis=1)


def resample_null_cube(cube: np.ndarray, rng) -> np.ndarray:
    """One parametric-bootstrap world with no identity effect at all.

    Each exchange's grades, pooled over identities, define a multinomial; every
    observed grade slot is redrawn from it. Exchange difficulty and the shape of
    the sampling noise are kept, and identity carries nothing.
    """
    out = np.full(cube.shape, np.nan)
    for e in range(cube.shape[1]):
        pool = cube[:, e, :][~np.isnan(cube[:, e, :])]
        slots = ~np.isnan(cube[:, e, :])
        out[:, e, :][slots] = rng.choice(pool, size=int(slots.sum()), replace=True)
    return out
