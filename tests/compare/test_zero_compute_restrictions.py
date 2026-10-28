"""Table restriction, base slices, and axis pruning (B46), on synthetic verdicts.

Every restricted table must be exactly what stage 6 would build from the
matching verdict rows, so the registered test sees nothing it would not see had
the run been collected that way. The base slices must be disjoint, cover every
row, keep every cell, and stay balanced. The pruning selection must read only
the pooled firing rate, which is unchanged by relabelling candidates within an
instruction.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.compare.axis_pruning_selection import (judge_cost_share, pooled_axis_rates,
                                                select_top_axes, split_instructions)
from src.compare.base_slice_partition import (cell_members, partition_cells,
                                              subsample_cells_like)
from src.compare.behavior_count_table import build_behavior_table
from src.compare.behavior_table_restriction import restrict_table
from src.compare.paired_max_statistic import paired_max_test

AXES = [f"a{j}" for j in range(6)]


def _rows(n_groups=3, n_blocks=6, samples=(5, 6), seed=0, null_every=0):
    rng = np.random.default_rng(seed)
    rates = rng.uniform(0.05, 0.6, size=len(AXES))
    rows, k = [], 0
    for g in range(n_groups):
        for b in range(n_blocks):
            for s in range(samples[(g + b) % len(samples)]):
                verdicts = {}
                for j, a in enumerate(AXES):
                    k += 1
                    verdicts[a] = (None if null_every and k % null_every == 0
                                   else bool(rng.random() < rates[j]))
                rows.append({"principal": f"g{g}", "instruction_id": f"sys::i{b}",
                             "level": 2, "s": s, "verdicts": verdicts})
    return rows


def _same(got, want):
    assert got.principals == want.principals and got.axes == want.axes
    assert got.blocks == want.blocks and got.n_responses == want.n_responses
    for f in ("counts", "fired", "scored", "group_of", "block_of"):
        assert np.array_equal(getattr(got, f), getattr(want, f)), f


@pytest.mark.parametrize("null_every", [0, 7])
def test_restriction_matches_build_behavior_table(null_every):
    rows = _rows(null_every=null_every)
    table = build_behavior_table(rows, AXES)
    rng = np.random.default_rng(1)
    keep_rows = np.sort(rng.choice(len(rows), size=len(rows) * 2 // 3, replace=False))
    keep_blocks, keep_axes = np.array([0, 2, 3, 5]), np.array([1, 4, 5])
    got = restrict_table(table, keep_rows, keep_axes, keep_blocks)
    names = {table.blocks[b] for b in keep_blocks}
    kept_axes = [AXES[j] for j in keep_axes]
    want_rows = [{**rows[i], "verdicts": {a: rows[i]["verdicts"][a] for a in kept_axes}}
                 for i in keep_rows if rows[i]["instruction_id"] in names]
    _same(got, build_behavior_table(want_rows, kept_axes))


def test_restriction_to_everything_is_identity_for_the_test():
    rows = _rows(seed=4)
    table = build_behavior_table(rows, AXES)
    a = paired_max_test(table, table, n_permutations=50)
    b = paired_max_test(restrict_table(table), restrict_table(table), n_permutations=50)
    assert a["statistic"] == b["statistic"] and a["p_family_wise"] == b["p_family_wise"]


def test_restriction_refuses_lost_candidate():
    rows = _rows()
    table = build_behavior_table(rows, AXES)
    with pytest.raises(ValueError):
        restrict_table(table, np.flatnonzero(table.group_of != 0))


@pytest.mark.parametrize("n_slices", [2, 4, 5])
def test_partition_disjoint_complete_balanced(n_slices):
    table = build_behavior_table(_rows(), AXES)
    slices = partition_cells(table, n_slices, np.random.default_rng(2))
    joined = np.concatenate(slices)
    assert np.array_equal(np.sort(joined), np.arange(table.n_responses))
    cells = cell_members(table)
    for members in cells.values():
        sizes = [np.isin(members, s).sum() for s in slices]
        assert max(sizes) - min(sizes) <= 1 and min(sizes) >= 1
    for s in slices:  # every slice builds a full table
        restrict_table(table, s)


def test_partition_refuses_too_small_cell():
    table = build_behavior_table(_rows(samples=(2,)), AXES)
    with pytest.raises(ValueError):
        partition_cells(table, 3, np.random.default_rng(0))


def test_subsample_matches_reference_cell_sizes():
    target = build_behavior_table(_rows(seed=1, samples=(6,)), AXES)
    base = build_behavior_table(_rows(seed=2, samples=(5, 6)), AXES)
    slice0 = partition_cells(base, 3, np.random.default_rng(5))[0]
    picked = subsample_cells_like(target, base, slice0, np.random.default_rng(6))
    assert len(np.unique(picked)) == picked.size
    want = np.zeros((3, 6), int)
    np.add.at(want, (base.group_of[slice0], base.block_of[slice0]), 1)
    got = np.zeros((3, 6), int)
    np.add.at(got, (target.group_of[picked], target.block_of[picked]), 1)
    assert np.array_equal(got, want)


def test_pilot_split_and_selection():
    pilot, held = split_instructions(12, 0.25, np.random.default_rng(0))
    assert pilot.size == 3 and held.size == 9 and not set(pilot) & set(held)
    kept, thr = select_top_axes(np.array([0.5, 0.1, 0.3, 0.3, 0.0, 0.2]), 3)
    assert thr == 0.3 and kept.tolist() == [0, 2, 3]
    kept, thr = select_top_axes(np.array([0.5, 0.0, 0.2]), 10)
    assert kept.tolist() == [0, 2]


def test_pooled_rate_ignores_candidate_labels_and_nulls():
    rows = _rows(null_every=5)
    table = build_behavior_table(rows, AXES)
    rates = pooled_axis_rates([table, table])
    want = table.fired.sum(0) / table.scored.sum(0)
    assert np.allclose(rates, want)
    shuffled = [{**r, "principal": f"g{(int(r['principal'][1:]) + 1) % 3}"} for r in rows]
    assert np.allclose(pooled_axis_rates([build_behavior_table(shuffled, AXES)] * 2), rates)


def test_judge_cost_share():
    c = judge_cost_share(100, 25, 0.25, 25)
    assert c["kept_over_total"] == 0.25
    assert c["axis_verdicts"] == pytest.approx(0.25 + 0.75 * 0.25)
    assert c["judge_calls"] == pytest.approx(0.25 + 0.75 * 1 / 4)
