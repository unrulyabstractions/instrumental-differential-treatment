"""Levels 0 and 1 on one subject's stored grades: sharp-null screen, detachment, Grubbs.

The sharp-null screen and the detachment test are the project's own functions,
called exactly as the stored driver called them (grade-threshold axes, 10,000
within-instruction shuffles, seed 20260726), at the registered alpha of 0.01.
Grubbs's test runs on two scalars per identity: the detachment test's peaks (the
largest |t| over the six threshold axes) and the exchange-blocked mean grade.
The peaks' permutation null reuses the detachment test's shuffled worlds: the
same seed drives the same permutation function in the same order, and the
driver checks that the detachment p it recomputes from those worlds matches.
"""

from __future__ import annotations

import numpy as np

from src.compare.behavior_count_table import build_behavior_table
from src.compare.candidate_detachment_measures import candidate_peaks, detachment
from src.compare.candidate_detachment_statistic import candidate_detachment_test
from src.compare.paired_excess_measures import (cell_rates, permutation_tail_share,
                                                standardized_excess)
from src.compare.reference_free_max_statistic import (permute_within_instructions,
                                                      reference_free_effect,
                                                      reference_free_max_test)
from src.external.user_awareness_materials import GRADE_AXES, IDENTITIES

from script.analysis.baseline_free_20261115.user_awareness.transluce_stats import \
    benjamini_hochberg
from script.analysis.baseline_free_20261115.user_awareness.ua_grubbs_outlier import (
    deleted_residual_t, grubbs_test)

SETTINGS = {"n_permutations": 10000, "seed": 20260726, "alpha": 0.01}
SAFETY = [i["key"] for i in IDENTITIES if i["group"] == "safety"]


def shuffled_peaks(table, n_permutations: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Peaks in each shuffled world, in the detachment test's order, and their detachments."""
    rates, _, _ = cell_rates(table)
    d = reference_free_effect(rates)
    rng = np.random.default_rng(seed)
    peaks = np.empty((n_permutations, d.shape[0]))
    det = np.empty(n_permutations)
    for k in range(n_permutations):
        t_null, _, _ = standardized_excess(permute_within_instructions(d, rng))
        peaks[k] = candidate_peaks(t_null)
        det[k], _ = detachment(peaks[k])
    return peaks, det


def level01(rows: list[dict], blocked: dict[str, float]) -> dict:
    """Every Level 0 and Level 1 detector for one subject."""
    axes = [a["axis_id"] for a in GRADE_AXES]
    table = build_behavior_table(rows, axes)
    n, seed, alpha = SETTINGS["n_permutations"], SETTINGS["seed"], SETTINGS["alpha"]
    screen = reference_free_max_test(table, n_permutations=n, seed=seed, alpha=alpha,
                                     top=len(table.principals) * len(axes))
    detach = candidate_detachment_test(table, n_permutations=n, seed=seed, alpha=alpha)
    labels = list(detach["candidates"])
    peaks = np.array([detach["peaks"][c] for c in labels])
    perm_peaks, perm_det = shuffled_peaks(table, n, seed)
    check_p = permutation_tail_share(perm_det, detach["statistic"], n)

    finite = bool(np.all(np.isfinite(peaks)))
    grubbs_peaks = (grubbs_test(peaks, labels, "max", permuted=perm_peaks, alpha=alpha)
                    if finite else {"undefined": "a peak is infinite"})
    xs = np.array([blocked[c] for c in labels])
    grubbs_grade_two = grubbs_test(xs, labels, "two", alpha=alpha)
    grubbs_grade_min = grubbs_test(xs, labels, "min", alpha=alpha)

    prereg = {}
    for key in SAFETY:
        i = labels.index(key)
        prereg[key] = {"mean_grade_vs_other_9": deleted_residual_t(xs, i, lower=True),
                       "peak_vs_other_9": (deleted_residual_t(peaks, i, lower=False)
                                           if finite else None)}
    for field in ("mean_grade_vs_other_9", "peak_vs_other_9"):
        ps = [prereg[k][field]["p_one_sided"] for k in SAFETY if prereg[k][field]]
        if len(ps) == len(SAFETY):
            for k, q in zip(SAFETY, benjamini_hochberg(ps), strict=True):
                prereg[k][field]["p_bh_within_subject"] = q
                prereg[k][field]["reject_at_alpha"] = bool(q <= alpha)

    return {
        "settings": SETTINGS,
        "sharp_null_screen": screen,
        "detachment": detach,
        "detachment_p_recomputed_from_shared_worlds": check_p,
        "detachment_worlds_match": bool(abs(check_p - detach["p_family_wise"]) < 1e-12),
        "grubbs_on_peaks": grubbs_peaks,
        "grubbs_on_blocked_mean_grade_two_sided": grubbs_grade_two,
        "grubbs_on_blocked_mean_grade_harsher_side": grubbs_grade_min,
        "preregistered_deleted_residual": prereg,
        "peaks": dict(zip(labels, peaks.tolist(), strict=True)),
    }
