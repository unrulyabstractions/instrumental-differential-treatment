"""The placebo split and its summary, on synthetic verdicts.

The split must hand the registered test exactly the tables stage 6 would build
from the same rows, keep every cell in both halves, and refuse a cell it cannot
split. On data with no difference by construction, the placebo p-values must be
roughly uniform, which is the property the calibration run measures.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.compare.behavior_count_table import build_behavior_table
from src.compare.paired_max_statistic import paired_max_test
from src.compare.placebo_calibration import (calibration_summary, cell_sizes,
                                             empirical_quantile, load_level_table,
                                             placebo_replicate, split_cell_indices,
                                             subset_table)

AXES = [f"a{j}" for j in range(5)]


def _rows(n_groups=4, n_blocks=8, samples=6, seed=0, null_every=0, level=2):
    """No-difference verdicts: each axis fires at its own rate for every group."""
    rng = np.random.default_rng(seed)
    rates = rng.uniform(0.1, 0.6, size=len(AXES))
    rows, k = [], 0
    for g in range(n_groups):
        for b in range(n_blocks):
            for s in range(samples):
                verdicts = {}
                for j, a in enumerate(AXES):
                    k += 1
                    if null_every and k % null_every == 0:
                        verdicts[a] = None
                    else:
                        verdicts[a] = bool(rng.random() < rates[j])
                rows.append({"principal": f"g{g}", "instruction_id": f"sys::i{b}",
                             "level": level, "s": s, "verdicts": verdicts})
    return rows


def test_subset_matches_build_behavior_table():
    rows = _rows(null_every=7)
    table = build_behavior_table(rows, AXES)
    a, b = split_cell_indices(table, np.random.default_rng(3))
    for idx in (a, b):
        got = subset_table(table, idx)
        want = build_behavior_table([rows[i] for i in sorted(idx)], AXES)
        assert got.principals == want.principals and got.blocks == want.blocks
        for field in ("counts", "fired", "scored", "group_of", "block_of"):
            np.testing.assert_array_equal(getattr(got, field), getattr(want, field))
        assert got.n_null == want.n_null and got.n_responses == want.n_responses
        # The registered test reads both identically.
        other = subset_table(table, b if idx is a else a)
        r1 = paired_max_test(got, other, n_permutations=50, seed=1)
        r2 = paired_max_test(want, other, n_permutations=50, seed=1)
        assert r1["statistic"] == r2["statistic"]
        assert r1["p_family_wise"] == r2["p_family_wise"]


def test_split_halves_every_cell_and_partitions_rows():
    rows = _rows(samples=7)
    table = build_behavior_table(rows, AXES)
    a, b = split_cell_indices(table, np.random.default_rng(0))
    assert len(set(a) & set(b)) == 0
    assert sorted(np.concatenate([a, b]).tolist()) == list(range(len(rows)))
    sa, sb = cell_sizes(subset_table(table, a)), cell_sizes(subset_table(table, b))
    assert set(np.unique(sa)) <= {3, 4} and set(np.unique(sb)) <= {3, 4}
    np.testing.assert_array_equal(sa + sb, cell_sizes(table))
    # The coin flip gives the larger share to either side, not always one.
    assert (sa == 4).any() and (sb == 4).any()


def test_split_refuses_a_single_sample_cell():
    rows = _rows(samples=2)
    rows = [r for r in rows if not (r["principal"] == "g0" and r["instruction_id"] == "sys::i0"
                                    and r["s"] == 1)]
    table = build_behavior_table(rows, AXES)
    with pytest.raises(ValueError, match="fewer than two"):
        split_cell_indices(table, np.random.default_rng(0))


def test_load_level_table_keeps_one_level():
    rows = _rows(level=2) + _rows(level=3, seed=9)
    table = load_level_table(rows, AXES, 3)
    assert table.n_responses == len(rows) // 2


def test_placebo_is_deterministic_given_seeds():
    table = build_behavior_table(_rows(), AXES)
    one = placebo_replicate(table, 11, 12, 99)
    two = placebo_replicate(table, 11, 12, 99)
    assert one == two


def test_placebo_on_no_difference_data_is_roughly_uniform():
    """With nothing to find, the placebo p-values must not pile up near zero."""
    table = build_behavior_table(_rows(n_groups=4, n_blocks=8, samples=6, seed=5), AXES)
    p = np.array([placebo_replicate(table, 1000 + r, 2000 + r, 199)["p"]
                  for r in range(150)])
    summary = calibration_summary(p)
    assert summary["ks_p"] > 0.001
    assert 0.35 < summary["median_p"] < 0.65
    # Under uniformity, 0.05 is inside the 95% interval for the share at 0.05.
    lo, hi = summary["ci_le_05"]
    assert lo <= 0.05 <= hi


def test_summary_detects_a_low_pile():
    """The summary can fail: a pile of small p-values is flagged."""
    p = np.random.default_rng(0).uniform(0, 0.2, size=300)
    summary = calibration_summary(p)
    assert summary["ks_p"] < 1e-6
    assert summary["ci_le_05"][0] > 0.05


def test_summary_counts_and_quantile():
    p = np.array([0.001, 0.01, 0.02, 0.05, 0.5, 0.9])
    s = calibration_summary(p)
    assert s["count_le_01"] == 2 and s["count_le_05"] == 4
    assert empirical_quantile(p, 0.05) == pytest.approx(4 / 6)
