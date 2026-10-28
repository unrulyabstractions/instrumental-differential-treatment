"""Leave-one-run-out registry scores and naming at a second alpha (B49)."""

from __future__ import annotations

import numpy as np
import pytest

from src.compare.behavior_count_table import build_behavior_table
from src.compare.fixed_registry_selection import (max_abs_t_by_axis, mean_pool_score,
                                                  name_at_alpha)
from src.compare.paired_excess_measures import (cell_rates, excess_effect,
                                                standardized_excess)
from src.compare.paired_max_statistic import paired_max_test
from src.compare.principal_attribution import attribute_principal

AXES = [f"a{j}" for j in range(5)]


def _rows(seed, lift=0.0, n_groups=4, n_blocks=16, samples=4):
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(n_groups):
        for b in range(n_blocks):
            for s in range(samples):
                p = [0.3 + (lift if (g == 0 and j < 3) else 0.0) for j in range(len(AXES))]
                rows.append({"principal": f"g{g}", "instruction_id": f"i{b}", "s": s,
                             "verdicts": {a: bool(rng.random() < p[j])
                                          for j, a in enumerate(AXES)}})
    return rows


def test_mean_pool_score_requires_identical_registry():
    with pytest.raises(ValueError):
        mean_pool_score([np.ones(5)], [tuple(AXES[::-1])], tuple(AXES))
    with pytest.raises(ValueError):
        mean_pool_score([], [], tuple(AXES))


def test_mean_pool_score_equal_weight_and_caps_infinity():
    got = mean_pool_score([np.array([1.0, np.inf, 0.0]), np.array([3.0, 1.0, 0.0])],
                          [("x", "y", "z")] * 2, ("x", "y", "z"))
    assert np.allclose(got, [2.0, 1.0, 0.0])  # inf capped at its run's max finite, 1.0


def test_max_abs_t_matches_the_registered_grid():
    t = build_behavior_table(_rows(1, lift=0.4), AXES)
    b = build_behavior_table(_rows(2), AXES)
    grid, _, _ = standardized_excess(excess_effect(cell_rates(t)[0], cell_rates(b)[0]))
    want = np.nanmax(np.abs(grid), axis=0)
    assert np.allclose(max_abs_t_by_axis(t, b), want)
    assert max_abs_t_by_axis(t, b).max() == pytest.approx(
        paired_max_test(t, b, n_permutations=50)["statistic"])


@pytest.mark.parametrize("lift", [0.0, 0.5])
def test_name_at_alpha_reproduces_the_registered_name(lift):
    t = build_behavior_table(_rows(3, lift=lift), AXES)
    b = build_behavior_table(_rows(4), AXES)
    res = paired_max_test(t, b, n_permutations=500, alpha=0.01, top=10**9)
    got = name_at_alpha(res, 0.01)
    assert got["loyal"] == res["loyal"]
    assert got["named"] == attribute_principal(res)["named"]
    res05 = paired_max_test(t, b, n_permutations=500, alpha=0.05, top=10**9)
    got05 = name_at_alpha(res, 0.05)
    assert got05["loyal"] == res05["loyal"]
    assert got05["named"] == attribute_principal(res05)["named"]
    if lift:  # the planted candidate is named, so the rule is exercised, not skipped
        assert got["named"] == got05["named"] == "g0"
    else:
        assert got["named"] is None
