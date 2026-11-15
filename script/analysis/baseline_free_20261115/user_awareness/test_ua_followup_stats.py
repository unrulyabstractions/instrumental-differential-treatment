"""Checks of the limits-and-controls statistics against brute force and closed forms.

    uv run pytest script/analysis/baseline_free_20261115/user_awareness/test_ua_followup_stats.py
"""

from __future__ import annotations

from itertools import combinations

import numpy as np
from scipy import stats

from script.analysis.baseline_free_20261115.user_awareness.transluce_stats import (
    benjamini_hochberg, predictive_t, whole_user_permutation)
from script.analysis.baseline_free_20261115.user_awareness.ua_detection_floor import (
    analytic_floor, planted_single, planted_triples)
from script.analysis.baseline_free_20261115.user_awareness.ua_reference_checks import (
    correlation_with_interval, group_gap_two_sided, placebo_levels, upper_bound_zero_of_n)
from script.analysis.baseline_free_20261115.user_awareness.ua_temporal_check import temporal_check
from script.analysis.baseline_free_20261115.user_awareness.ua_temporal_followup import (
    temporal_extended)


def test_group_gap_tails_match_whole_user_permutation():
    rng = np.random.default_rng(3)
    xa, xb = rng.normal(-0.2, 0.1, 3), rng.normal(0, 0.1, 8)
    g = group_gap_two_sided(xa, xb)
    w = whole_user_permutation(np.concatenate([xa, xb]), np.array([True] * 3 + [False] * 8))
    assert g["n_relabellings"] == 165 == w["n_relabellings"]
    assert abs(g["p_one_sided_a_harsher"] - w["p_one_sided_harsher"]) < 1e-12
    # With no ties the two tails share exactly the observed relabelling.
    assert g["count_a_harsher_tail"] + g["count_a_lenient_tail"] == 165 + 1


def test_analytic_floor_is_the_rejection_boundary():
    rng = np.random.default_rng(4)
    pool = rng.normal(0, 0.15, 30)
    fl = analytic_floor(pool)
    edge = pool.mean() + fl["predictive_t_alpha"]
    assert predictive_t(edge - 1e-9, pool)["p_one_sided_harsher"] <= 0.01
    assert predictive_t(edge + 1e-9, pool)["p_one_sided_harsher"] > 0.01
    assert not fl["conformal_can_reject"] and abs(fl["conformal_floor_p"] - 1 / 31) < 1e-12


def test_planted_triples_match_brute_force():
    rng = np.random.default_rng(5)
    pool = rng.normal(0, 0.1, 9)
    se2 = np.full(9, 0.004)
    delta = 0.25
    res = planted_triples(pool, se2, deltas=(delta,))["rows"][0]
    trips = list(combinations(range(9), 3))
    hit_g = hit_t = 0
    for t in trips:
        x = pool.copy()
        x[list(t)] -= delta
        mask = np.zeros(9, dtype=bool)
        mask[list(t)] = True
        hit_g += whole_user_permutation(x, mask)["p_one_sided_harsher"] <= 0.01
        rest = pool[~mask]
        ps = [predictive_t(x[j], rest)["p_one_sided_harsher"] for j in t]
        hit_t += min(benjamini_hochberg(ps)) <= 0.01
    assert abs(res["group_exact_permutation"] - hit_g / len(trips)) < 1e-12
    assert abs(res["predictive_t_bh_any"] - hit_t / len(trips)) < 1e-12


def test_planted_single_zero_shift_is_the_placebo():
    rng = np.random.default_rng(6)
    pool = rng.normal(0, 0.1, 12)
    res = planted_single(pool, np.full(12, 0.003), deltas=(0.0,))["rows"][0]
    fires = sum(predictive_t(pool[j], np.delete(pool, j))["p_one_sided_harsher"] <= 0.01
                for j in range(12))
    assert abs(res["predictive_t"] - fires / 12) < 1e-12


def test_correlation_interval_and_zero_of_n_bound():
    rng = np.random.default_rng(8)
    a = rng.normal(size=40)
    b = 0.3 * a + rng.normal(size=40)
    c = correlation_with_interval(a, b)
    assert abs(c["pearson_r"] - stats.pearsonr(a, b)[0]) < 1e-12
    assert c["ci95_low"] < c["pearson_r"] < c["ci95_high"]
    assert abs(upper_bound_zero_of_n(30) - 0.0950) < 1e-4
    lv = placebo_levels({"t": [0.2, 0.04, 0.5]}, {})
    assert lv["t"]["fires_at_0.05"] == 1 and lv["t"]["fires_at_0.01"] == 0


def test_temporal_extended_reproduces_registered_fields():
    rng = np.random.default_rng(9)
    old = rng.integers(4, 9, size=(5, 6, 4)).astype(float)
    new = rng.integers(4, 9, size=(5, 6, 4)).astype(float)
    ids = [f"i{k}" for k in range(5)]
    ext = temporal_extended(old, new, ids, "i2")
    base = temporal_check(old, new, ids)
    for key in ("omnibus", "identity_by_session_interaction", "overall_shift"):
        assert ext[key] == base[key]
    assert 0 < ext["exchange_by_session"]["p"] <= 1
    assert ext["leading_identity_contrast"]["identity"] == "i2"
