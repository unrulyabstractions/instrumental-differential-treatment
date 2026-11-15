"""Temporal check: the new session's original identities against the stored grades.

The served model may have changed since the stored grades were drawn, so the
stored grades act as a temporal replicate. Three tests, each at alpha 0.01:

* omnibus: the sum over (identity, exchange) cells of (mean_new - mean_old)^2,
  against 10,000 within-cell shuffles of the session labels (the sharp null that
  every cell has one distribution in both sessions);
* interaction: the spread over identities of the change in exchange-blocked mean
  grade, against the same shuffles (does the identity profile change, beyond a
  common shift);
* overall shift: the mean over exchanges of the cell-averaged change, by exact
  sign-flip enumeration over the 16 exchanges.
"""

from __future__ import annotations

from itertools import product

import numpy as np

from script.analysis.baseline_free_20261115.user_awareness.ua_grade_tables import blocked_means

SEED = 20260726
N_PERM = 10000
ALPHA = 0.01


def _stats(old: np.ndarray, new: np.ndarray) -> tuple[float, float]:
    with np.errstate(invalid="ignore"):
        diff = np.nanmean(new, axis=2) - np.nanmean(old, axis=2)
    omnibus = float(np.nansum(diff ** 2))
    delta = blocked_means(new)[0] - blocked_means(old)[0]
    return omnibus, float(np.sum((delta - delta.mean()) ** 2))


def temporal_check(old: np.ndarray, new: np.ndarray, identities: list[str]) -> dict:
    """``old`` and ``new`` are (identity, exchange, sample) grade cubes on the same identities."""
    if old.shape[:2] != new.shape[:2]:
        raise ValueError("the two sessions must share identities and exchanges")
    n_old = old.shape[2]
    obs_omni, obs_inter = _stats(old, new)
    both = np.concatenate([old, new], axis=2)
    rng = np.random.default_rng(SEED)
    omni_null, inter_null = np.empty(N_PERM), np.empty(N_PERM)
    for k in range(N_PERM):
        order = np.argsort(rng.random(both.shape), axis=2)
        shuffled = np.take_along_axis(both, order, axis=2)
        omni_null[k], inter_null[k] = _stats(shuffled[:, :, :n_old], shuffled[:, :, n_old:])

    with np.errstate(invalid="ignore"):
        d_e = np.nanmean(np.nanmean(new, axis=2) - np.nanmean(old, axis=2), axis=0)
    shift = float(d_e.mean())
    flips = np.array(list(product((1.0, -1.0), repeat=d_e.size)))
    null_shift = np.abs(flips @ d_e / d_e.size)
    p_shift = float(np.mean(null_shift >= abs(shift) - 1e-12))

    x_old, x_new = blocked_means(old)[0], blocked_means(new)[0]
    p_omni = float((1 + np.sum(omni_null >= obs_omni)) / (1 + N_PERM))
    p_inter = float((1 + np.sum(inter_null >= obs_inter)) / (1 + N_PERM))
    return {
        "settings": {"seed": SEED, "n_permutations": N_PERM, "alpha": ALPHA,
                     "sign_flip_enumeration": int(flips.shape[0])},
        "cells_with_missing_grades": int(np.sum(np.isnan(both).any(axis=2))),
        "omnibus": {"statistic": obs_omni, "p": p_omni, "reject": bool(p_omni <= ALPHA)},
        "identity_by_session_interaction": {"statistic": obs_inter, "p": p_inter,
                                            "reject": bool(p_inter <= ALPHA)},
        "overall_shift": {"mean_new_minus_old": shift, "p_two_sided": p_shift,
                          "reject": bool(p_shift <= ALPHA)},
        "mean_grade_old": float(np.nanmean(old)), "mean_grade_new": float(np.nanmean(new)),
        "identity_profile_pearson_r": float(np.corrcoef(x_old, x_new)[0, 1]),
        "blocked_mean_old": dict(zip(identities, x_old.tolist(), strict=True)),
        "blocked_mean_new": dict(zip(identities, x_new.tolist(), strict=True)),
    }
