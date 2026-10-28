"""The pooled within-run reference (B45) and its two repairs, on synthetic data.

The within-run reference must sit at its floor whenever one candidate holds
``S`` alone, because it leaves that candidate out; a mirrored two-candidate run
must tie. The block schemes must cover at least ``M`` values. The drift-scaled
null must draw the registered permutations draw for draw. On no-difference
data the cross-run reference and the drift-scaled p must be roughly uniform; a
shifted candidate must be detected; and the naive single-pair comparison must
reject almost every null where the max-versus-max one does not.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy import stats

from script.analysis.pooled_reference_synthetic import synthetic_rates
from src.compare.cross_run_pooled_reference import cross_run_reference_test, reference_rows
from src.compare.drift_scaled_max_null import (drift_scaled_p, registered_null,
                                               surviving_candidates)
from src.compare.paired_excess_measures import (excess_effect, max_abs_statistic,
                                                permutation_tail_share,
                                                standardized_excess)
from src.compare.pooled_within_run_reference import (SCHEMES, VARIANTS,
                                                     exact_values_tail_share,
                                                     pooled_reference_test,
                                                     resampled_maxima, t_grid)


def _run(seed: int, drift: float = 0.0, shift: float = 0.0):
    return synthetic_rates(np.random.default_rng(seed), drift, shift)


def test_within_run_reference_sits_at_its_floor_when_one_candidate_holds_s():
    for seed in range(5):
        t = t_grid(*_run(seed))
        out = pooled_reference_test(t, n_boot=500, seed=seed)
        assert not out["S_tied_by_other_candidate"]
        for variant in VARIANTS:
            v = out["variants"][variant]
            assert v["ref_max"] < out["S"]
            assert v["p_exact_values"] == 0.0
            for scheme in SCHEMES:
                assert v[scheme]["p_ref"] == pytest.approx(1 / 501)
                assert v[scheme]["R"] >= 1.0


def test_two_candidates_mirror_and_tie():
    p_t, p_b = _run(1)
    out = pooled_reference_test(t_grid(p_t[:2], p_b[:2]), n_boot=2000, seed=0)
    assert out["mirror"] and out["S_tied_by_other_candidate"]
    v = out["variants"]["drop_top"]
    assert v["ref_max"] == pytest.approx(out["S"])
    assert v["values"]["p_ref"] > 0.5


def test_values_scheme_matches_the_exact_max_distribution():
    rng = np.random.default_rng(3)
    ref = np.abs(rng.standard_t(30, (5, 40)))
    flat = ref.ravel()
    s, m = float(np.quantile(flat, 0.995)), 240
    maxima = resampled_maxima(ref, m, "values", 20000, np.random.default_rng(4))
    got = (1 + np.sum(maxima >= s)) / (1 + maxima.size)
    assert got == pytest.approx(exact_values_tail_share(flat, s, m), abs=0.015)


@pytest.mark.parametrize("scheme", ["axes", "candidates"])
def test_block_schemes_cover_at_least_m_values(scheme):
    # One marked value per block: the share of maxima that hit a marked block
    # tells how many blocks were drawn.
    rows, cols = 5, 50
    ref = np.zeros((rows, cols))
    if scheme == "axes":
        ref[0, 0] = 1.0
        n_blocks, size = cols, rows
    else:
        ref[0, :] = 1.0
        n_blocks, size = rows, cols
    m = rows * cols
    maxima = resampled_maxima(ref, m, scheme, 20000, np.random.default_rng(0))
    k = int(np.ceil(m / size))
    assert np.mean(maxima == 1.0) == pytest.approx(1 - (1 - 1 / n_blocks) ** k, abs=0.015)


def test_registered_null_draws_the_registered_permutations():
    p_t, p_b = _run(5, shift=0.3)
    null = registered_null(p_t, p_b, 300, seed=11)
    rng = np.random.default_rng(11)
    expect = np.empty(300)
    for k in range(300):
        pt, pb = np.empty_like(p_t), np.empty_like(p_b)
        for i in range(p_t.shape[1]):
            order = rng.permutation(p_t.shape[0])
            pt[:, i], pb[:, i] = p_t[order, i], p_b[order, i]
        t, _, _ = standardized_excess(excess_effect(pt, pb))
        expect[k] = max_abs_statistic(t, False)
    np.testing.assert_allclose(null["maxima"], expect, rtol=0, atol=1e-12)


def test_drift_scaled_p_is_never_below_the_registered_p():
    maxima = np.linspace(1, 5, 999)
    for ref_median in (0.5, 0.7, 1.4):
        out = drift_scaled_p(4.0, maxima, ref_median, 0.7)
        assert out["p_scaled"] >= out["p_registered"]
        assert out["p_registered"] == permutation_tail_share(maxima, 4.0, 999)


def _cross_p(runs, reference):
    others = [reference_rows(t_grid(*r), drop_top=False) for r in reference]
    return [cross_run_reference_test(t_grid(*r), others, 1000, seed=i,
                                     schemes=("values",)) for i, r in enumerate(runs)]


def test_no_difference_gives_roughly_uniform_cross_run_and_scaled_p():
    reference = [_run(1000 + k) for k in range(40)]
    runs = [_run(k) for k in range(120)]
    cross = _cross_p(runs, reference)
    p_cross = np.array([c["values"]["p_ref"] for c in cross])
    assert stats.kstest(p_cross, "uniform").pvalue > 0.001
    assert np.mean(p_cross <= 0.05) < 0.15
    p_scaled = []
    for r in runs[:60]:
        t = t_grid(*r)
        null = registered_null(*r, 200, seed=1)
        within = pooled_reference_test(t, n_boot=200)["variants"]["drop_top"]
        p_scaled.append(drift_scaled_p(float(np.nanmax(np.abs(t))), null["maxima"],
                                       within["ref_median"],
                                       null["perm_abs_median"])["p_scaled"])
    assert stats.kstest(p_scaled, "uniform").pvalue > 0.001
    assert np.mean(np.array(p_scaled) <= 0.05) < 0.15


def test_one_shifted_candidate_is_detected():
    reference = [_run(1000 + k) for k in range(40)]
    runs = [_run(k, shift=0.8) for k in range(10)]
    cross = _cross_p(runs, reference)
    assert all(c["values"]["p_ref"] <= 0.01 for c in cross)
    for r in runs[:5]:
        t = t_grid(*r)
        null = registered_null(*r, 300, seed=2)
        # The one-versus-rest coupling can carry a strong principal into another
        # candidate's row, so the shifted candidate must survive, not alone.
        assert 0 in surviving_candidates(np.abs(t), null["maxima"], 0.01)
        within = pooled_reference_test(t, n_boot=200)
        assert within["top_candidate"] == 0
        v = within["variants"]["drop_top"]
        assert drift_scaled_p(within["S"], null["maxima"], v["ref_median"],
                              null["perm_abs_median"])["p_scaled"] <= 0.01


def test_max_versus_max_matters_against_the_naive_single_pair_ratio():
    reference = [_run(1000 + k) for k in range(40)]
    cross = _cross_p([_run(k) for k in range(100)], reference)
    naive_p = np.array([c["naive_p_single"] for c in cross])
    naive_r = np.array([c["naive_R"] for c in cross])
    p = np.array([c["values"]["p_ref"] for c in cross])
    r = np.array([c["values"]["R"] for c in cross])
    assert np.mean(naive_p <= 0.05) > 0.95 and np.mean(naive_r > 1) > 0.8
    assert np.mean(p <= 0.05) < 0.15 and np.mean(r > 1) < 0.15
