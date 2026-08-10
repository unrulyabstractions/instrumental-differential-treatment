"""The coherence fold must keep every cancellation the registered fold has.

Same effect, same pairing, same null; only the aggregation over axes differs.
So the invariants of the registered test carry over unchanged: a planted
loyalty is found and named, a name effect present in both models cancels, a
uniform fine-tuning shift cancels, and breadth across axes is what the fold is
for, so a loyalty spread over several axes must score higher than the same
per-axis treatment on one.

The firing rules carry pseudo-random noise, and the planted axes each fire on
their own block subset. A fully deterministic table has zero-spread pairs
whose shuffles are exactly as extreme as the observation, and perfectly
correlated planted axes let a lucky shuffle saturate them together; real
tables have neither property.
"""

from __future__ import annotations

import pytest

from src.compare.behavior_count_table import build_behavior_table
from src.compare.paired_coherence_statistic import paired_coherence_test

AXES = [f"axis_{i}" for i in range(12)]
PLANTED = ("axis_9", "axis_10", "axis_11")


def _noise(g, j, b, s):
    return (g * 7 + j * 13 + b * 29 + s * 31) % 3 == 0


def _planted(g, j, b, s):
    return g == 1 and j in (9, 10, 11) and (b + j) % 2 == 0


def _rows(n_groups, n_blocks, samples, fire):
    return [
        {"principal": f"g{g}", "instruction_id": f"b{b}", "s": s,
         "prompt_id": f"g{g}__b{b}", "judge": "test", "level": 1,
         "verdicts": {a: bool(fire(g, j, b, s)) for j, a in enumerate(AXES)}}
        for g in range(n_groups) for b in range(n_blocks) for s in range(samples)
    ]


def _table(fire, n_groups=8, n_blocks=24, samples=3):
    return build_behavior_table(_rows(n_groups, n_blocks, samples, fire), AXES)


def test_finds_a_planted_loyalty_and_names_it():
    def loyal(g, j, b, s):
        return _noise(g, j, b, s) or _planted(g, j, b, s)

    result = paired_coherence_test(_table(loyal), _table(_noise), n_permutations=500)
    assert result["loyal"]
    assert result["p_family_wise"] <= 0.01
    assert result["principal"] == "g1"
    carried = {a["axis_id"] for a in result["leading_axes"]}
    assert carried & set(PLANTED)


def test_cancels_a_name_effect_present_in_both_models():
    def both(g, j, b, s):
        return _noise(g, j, b, s) or (g == 2 and j == 5)

    result = paired_coherence_test(_table(both), _table(both), n_permutations=500)
    assert result["statistic"] == pytest.approx(0.0, abs=1e-9)
    assert not result["loyal"]
    assert result["principal"] is None


def test_cancels_a_uniform_fine_tuning_shift():
    def louder(g, j, b, s):
        return _noise(g, j, b, s) or (j in (3, 4) and (b + s) % 2 == 0)

    result = paired_coherence_test(_table(louder), _table(_noise), n_permutations=500)
    assert not result["loyal"]


def test_breadth_scores_higher_than_the_same_treatment_on_one_axis():
    """Coherent planted axes must accumulate past a single planted axis."""
    def narrow(g, j, b, s):
        return _noise(g, j, b, s) or (g == 1 and j == 9 and b % 2 == 0)

    def broad(g, j, b, s):
        return _noise(g, j, b, s) or _planted(g, j, b, s)

    s_narrow = paired_coherence_test(_table(narrow), _table(_noise),
                                     n_permutations=50)["statistic"]
    s_broad = paired_coherence_test(_table(broad), _table(_noise),
                                    n_permutations=50)["statistic"]
    assert s_broad > s_narrow


def test_rejects_mismatched_instruction_sets():
    with pytest.raises(ValueError, match="cannot be paired"):
        paired_coherence_test(_table(_noise, n_blocks=10), _table(_noise, n_blocks=8),
                              n_permutations=10)
