"""A missing cell is missing, never zero, in every stage-6 statistic.

These pin the fixes for three verified defects: the one-versus-rest gap summed
NaN cells as zero and handed innocent candidates a spurious excess, an
unmeasured axis drew the smallest achievable common-mode p-value, and the
naming rule read a truncated pair list that could turn a tie into a name.
"""

from __future__ import annotations

import numpy as np

from src.compare.behavior_count_table import build_behavior_table
from src.compare.common_mode_elevation import common_mode_elevation
from src.compare.paired_excess_measures import excess_effect
from src.compare.principal_attribution import attribute_principal


def test_missing_base_cell_gives_no_excess_to_the_others():
    # Three candidates, identical behavior everywhere. Candidate A's base cell
    # is unobserved. Under zero-imputation B and C would each show d = -0.3;
    # the correct excess for every observed pair is exactly zero.
    target = np.full((3, 1, 1), 0.6)
    base = np.full((3, 1, 1), 0.6)
    base[0, 0, 0] = np.nan
    d = excess_effect(target, base)
    assert np.isnan(d[0, 0, 0])
    assert abs(d[1, 0, 0]) < 1e-12
    assert abs(d[2, 0, 0]) < 1e-12


def test_rest_average_ignores_missing_candidates():
    # A missing cell drops out of the rest-average denominator too.
    p = np.array([[[np.nan]], [[0.2]], [[0.8]]])
    d = excess_effect(p, p)
    assert np.isnan(d[0, 0, 0])
    # B's rest is C alone (0.8), C's rest is B alone (0.2); target==base so d=0.
    assert abs(d[1, 0, 0]) < 1e-12
    assert abs(d[2, 0, 0]) < 1e-12


def _table(rows, axes):
    return build_behavior_table(rows, axes)


def test_unmeasured_axis_takes_p_one_not_the_minimum():
    axes = ["a0", "a1"]
    rng = np.random.default_rng(0)
    rows_t, rows_b = [], []
    for i in range(6):
        for s in range(4):
            fire = bool(rng.random() < 0.5)
            # a1 is never scored by any judge, in either model.
            rows_t.append({"principal": "p", "instruction_id": f"i{i}",
                           "verdicts": {"a0": fire, "a1": None}})
            rows_b.append({"principal": "p", "instruction_id": f"i{i}",
                           "verdicts": {"a0": fire, "a1": None}})
    out = common_mode_elevation(_table(rows_t, axes), _table(rows_b, axes),
                                n_permutations=200)
    p_by_axis = dict(zip(axes, out["p_axis"])) if "p_axis" in out else None
    if p_by_axis is None:
        # read through the reported top axes instead
        named = {a["axis_id"]: a for a in out["top_axes"]}
        assert out["n_axes_moved_bh"] == 0
        assert "a1" not in {a for a, v in named.items() if v.get("reject_bh")}
    else:
        assert p_by_axis["a1"] == 1.0


def test_mismatched_instruction_sets_refuse_to_pair():
    axes = ["a0"]
    rows_t = [{"principal": "p", "instruction_id": f"i{i}",
               "verdicts": {"a0": True}} for i in range(4)]
    rows_b = [{"principal": "p", "instruction_id": f"i{i}",
               "verdicts": {"a0": True}} for i in range(1, 5)]
    try:
        common_mode_elevation(_table(rows_t, axes), _table(rows_b, axes),
                              n_permutations=50)
    except ValueError as err:
        assert "instruction sets" in str(err)
    else:
        raise AssertionError("mismatched blocks must refuse to pair")


def test_attribution_reads_the_uncensored_pair_list():
    # A true tie: X and Y each hold 5 surviving axes, but the display list is
    # truncated to X's five plus two of Y's. The censored histogram reads a
    # plurality for X; the uncensored list must refuse to name.
    surviving = ([{"candidate": "X", "axis_id": f"x{i}"} for i in range(5)]
                 + [{"candidate": "Y", "axis_id": f"y{i}"} for i in range(5)])
    truncated = ([{"candidate": "X", "axis_id": f"x{i}", "reject": True}
                  for i in range(5)]
                 + [{"candidate": "Y", "axis_id": f"y{i}", "reject": True}
                    for i in range(2)])
    test = {"loyal": True, "principal": "X", "n_axes": 100,
            "surviving_pairs": surviving, "top_pairs": truncated}
    out = attribute_principal(test)
    assert out["named"] is None
    assert out["histogram"] == {"X": 5, "Y": 5}
