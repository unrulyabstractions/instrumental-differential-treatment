"""A pooled reference built from other runs, the second repair tried in B45.

The within-run reference never reaches ``S`` because it leaves out the row that
holds it. A reference pooled from OTHER runs of the same base, candidates and
axes has no such ceiling: its largest values come from other runs' rows, so the
maximum of ``M`` draws from it can land above or below ``S``. It contains
whatever drift those runs carry, and under exchangeability across runs it is a
valid null for ``S``. Each other run contributes either its rows except its own
top candidate, as the within-run reference does, or every row.

The comparison is maximum against maximum, as in the within-run reference, and
the naive single-pair ratio is reported beside it to show why that matters.
"""

from __future__ import annotations

import numpy as np

from src.compare.pooled_within_run_reference import (ratio_to_quantile,
                                                     reference_tail_share,
                                                     resampled_maxima, top_candidate)

__all__ = ["reference_rows", "cross_run_reference_test"]


def reference_rows(t: np.ndarray, drop_top: bool = True) -> np.ndarray:
    """One run's contribution: |t| for every candidate, or all but its top one.

    Dropping the top row of a run believed null throws away that run's own
    maximum, which is exactly the kind of value ``S`` is, so the reference then
    sits below ``S`` too often. Keeping every row is the exchangeable choice when
    the other runs are nulls.
    """
    abs_t = np.abs(t)
    if not drop_top:
        return abs_t
    top = top_candidate(abs_t)
    return abs_t[[c for c in range(abs_t.shape[0]) if c != top]]


def cross_run_reference_test(t: np.ndarray, others: list[np.ndarray],
                             n_boot: int = 10000, seed: int = 20261028,
                             schemes: tuple[str, ...] = ("values", "axes")) -> dict:
    """Refer one run's ``S`` to the max of ``M`` draws pooled from other runs.

    ``others`` holds each other run's ``reference_rows``. The rows must agree in
    count, which they do when the runs share a roster, so the axes of all runs
    can sit side by side as one wide reference.
    """
    abs_t = np.abs(t)
    m = int(np.sum(~np.isnan(abs_t)))
    s = float(np.nanmax(abs_t))
    if len({o.shape[0] for o in others}) != 1:
        raise ValueError("other runs must contribute the same number of rows")
    ref = np.hstack(others)
    flat = ref[~np.isnan(ref)]
    q_single = float(np.quantile(flat, 0.99, method="higher"))
    out = {"S": s, "M": m, "n_ref": int(flat.size), "n_other_runs": len(others),
           "naive_p_single": (1.0 + int(np.sum(flat >= s))) / (1.0 + flat.size),
           "naive_q99_single": q_single, "naive_R": ratio_to_quantile(s, q_single),
           "p_exact_values": float(1.0 - np.mean(flat < s) ** m)}
    for index, scheme in enumerate(schemes):
        rng = np.random.default_rng(np.random.SeedSequence([seed, 7, index]))
        maxima = resampled_maxima(ref, m, scheme, n_boot, rng)
        q = float(np.quantile(maxima, 0.99, method="higher"))
        out[scheme] = {"p_ref": reference_tail_share(maxima, s), "q99_max": q,
                       "R": ratio_to_quantile(s, q)}
    return out
