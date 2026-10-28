"""The look-at-the-losers statistic (B44) on synthetic rates and verdicts.

The statistic must equal the owner's formula, be invariant to using the plain
target-minus-base difference in place of the one-versus-rest excess, draw the
registered test's permutations draw for draw, refuse two-candidate rosters,
detect a shifted candidate, and give roughly uniform p-values when nothing
differs.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.compare.behavior_count_table import build_behavior_table
from src.compare.loser_dispersion_statistic import (_permute, dispersion_z,
                                                    loser_dispersion_test,
                                                    loser_dispersion_test_tables,
                                                    mean_excess_grid,
                                                    permutation_orders, registered_t)
from src.compare.paired_excess_measures import excess_effect, standardized_excess
from src.compare.paired_max_statistic import paired_max_test

AXES = [f"a{j}" for j in range(6)]


def _rates(n_c=6, n_i=20, n_j=6, seed=0, shift=0.0, shifted=0, axis=0):
    rng = np.random.default_rng(seed)
    base_level = rng.uniform(0.2, 0.6, size=(1, 1, n_j))
    p_b = np.clip(base_level + rng.normal(0, 0.08, (n_c, n_i, n_j)), 0, 1)
    p_t = np.clip(base_level + rng.normal(0, 0.08, (n_c, n_i, n_j)), 0, 1)
    p_t[shifted, :, axis] = np.clip(p_t[shifted, :, axis] + shift, 0, 1)
    return p_t, p_b


def test_z_matches_the_owners_formula_by_hand():
    p_t, p_b = _rates(seed=1)
    dbar, _ = mean_excess_grid(excess_effect(p_t, p_b))
    z = dispersion_z(dbar)
    for a in range(dbar.shape[0]):
        for j in range(dbar.shape[1]):
            others = np.delete(dbar[:, j], a)
            expect = (dbar[a, j] - others.mean()) / others.std(ddof=1)
            assert z[a, j] == pytest.approx(expect, rel=1e-12)


def test_dbar_is_the_registered_mean_excess():
    p_t, p_b = _rates(seed=2)
    d = excess_effect(p_t, p_b)
    dbar, _ = mean_excess_grid(d)
    _, mean, _ = standardized_excess(d)
    np.testing.assert_allclose(dbar, mean, rtol=0, atol=1e-15)


def test_z_is_the_same_on_the_plain_target_minus_base_difference():
    p_t, p_b = _rates(seed=3)
    z_d = dispersion_z(mean_excess_grid(excess_effect(p_t, p_b))[0])
    z_e = dispersion_z((p_t - p_b).mean(axis=1))
    np.testing.assert_allclose(z_d, z_e, rtol=1e-9)


def test_registered_t_matches_standardized_excess():
    p_t, p_b = _rates(seed=4)
    d = excess_effect(p_t, p_b)
    t, _, _ = standardized_excess(d)
    np.testing.assert_array_equal(registered_t(d), t)


def test_permuting_d_equals_recomputing_d_from_permuted_rates():
    p_t, p_b = _rates(n_c=5, n_i=7, seed=5)
    orders = permutation_orders(5, 7, 3, seed=11)
    d = excess_effect(p_t, p_b)
    batch = _permute(d, orders)
    for k in range(3):
        pt, pb = np.empty_like(p_t), np.empty_like(p_b)
        for i in range(7):
            pt[:, i] = p_t[orders[k, i], i]
            pb[:, i] = p_b[orders[k, i], i]
        np.testing.assert_allclose(batch[k], excess_effect(pt, pb), atol=1e-15)


def _rows(n_groups=4, n_blocks=10, samples=4, seed=0, shift=0.0):
    rng = np.random.default_rng(seed)
    rates = rng.uniform(0.15, 0.5, size=len(AXES))
    out = {"target": [], "base": []}
    for model in out:
        k = 0
        for g in range(n_groups):
            for b in range(n_blocks):
                for _ in range(samples):
                    r = rates.copy()
                    if model == "target" and g == 0:
                        r[:3] = np.clip(r[:3] + shift, 0, 1)
                    fired = rng.random(len(AXES)) < r
                    out[model].append({
                        "principal": f"g{g}", "instruction_id": f"sys::i{b}", "id": k,
                        "verdicts": {a: bool(f) for a, f in zip(AXES, fired)}})
                    k += 1
    return out


def test_registered_p_is_reproduced_on_the_same_permutations():
    rows = _rows(seed=6, shift=0.2)
    t = build_behavior_table(rows["target"], AXES)
    b = build_behavior_table(rows["base"], AXES)
    reg = paired_max_test(t, b, n_permutations=300)
    got = loser_dispersion_test_tables(t, b, n_permutations=300)
    assert got["registered_S_recomputed"] == reg["statistic"]
    assert got["registered_p_recomputed"] == reg["p_family_wise"]


def test_two_candidates_are_not_computable_and_three_are_flagged():
    p_t, p_b = _rates(n_c=2, seed=7)
    two = loser_dispersion_test(p_t, p_b, ["x", "y"], AXES, n_permutations=50)
    assert two["roster_flag"].startswith("not computable")
    for mode in ("infinite", "exclude"):
        assert two[mode]["computable"] is False and two[mode]["p"] is None
    p_t, p_b = _rates(n_c=3, seed=7)
    three = loser_dispersion_test(p_t, p_b, ["x", "y", "w"], AXES, n_permutations=50)
    assert three["roster_flag"].startswith("unstable")
    assert three["exclude"]["computable"] is True


def test_zero_spread_is_infinite_or_excluded():
    dbar = np.array([[0.3, 0.0], [-0.1, 0.0], [-0.1, 0.0], [-0.1, 0.0]])
    inf = dispersion_z(dbar, "infinite")
    exc = dispersion_z(dbar, "exclude")
    assert inf[0, 0] == np.inf and inf[0, 1] == 0.0
    assert np.isnan(exc[0, 0]) and np.isnan(exc[0, 1])
    # A loser's others include the shifted candidate, so its spread is not zero.
    assert np.isfinite(exc[1, 0])


def test_a_shifted_candidate_is_detected_and_named():
    p_t, p_b = _rates(n_c=6, n_i=30, n_j=6, seed=8)
    for j in range(3):
        p_t[0, :, j] = np.clip(p_t[0, :, j] + 0.25, 0, 1)
    names = [f"c{k}" for k in range(6)]
    got = loser_dispersion_test(p_t, p_b, names, AXES, n_permutations=500)
    for mode in ("infinite", "exclude"):
        assert got[mode]["p"] <= 0.01
        assert got[mode]["top_pair"]["candidate"] == "c0"
    # Six axes is a small registry, so two surviving axes are enough to name.
    assert got["exclude"]["named"] == "c0"


def test_no_difference_gives_roughly_uniform_p():
    ps = []
    for seed in range(60):
        p_t, p_b = _rates(n_c=5, n_i=12, n_j=4, seed=100 + seed)
        got = loser_dispersion_test(p_t, p_b, list("abcde"), AXES[:4],
                                    n_permutations=199, seed=seed, details=False)
        ps.append(got["exclude"]["p"])
    ps = np.array(ps)
    assert 0.3 < ps.mean() < 0.7
    assert np.mean(ps <= 0.1) < 0.25
    from scipy import stats
    assert stats.kstest(ps, "uniform").pvalue > 0.01


def test_a_null_one_ulp_below_the_observed_value_still_ties():
    from src.compare.loser_dispersion_statistic import _tail_share
    obs = 3.3011005503057342
    null = np.array([3.3011005503057333, 1.0, 5.0])
    assert _tail_share(null, obs, 3) == 3 / 4
    assert _tail_share(np.array([3.30110055, 1.0]), obs, 2) == 1 / 3
    assert _tail_share(np.array([np.inf, 1.0]), np.inf, 2) == 2 / 3
