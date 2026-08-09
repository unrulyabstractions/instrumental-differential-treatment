"""Power sanity for the registered test on noisy planted effects.

The ground-truth suite in ``tests/test_distribution_comparison.py`` exercises
deterministic fixtures, where a planted loyalty fires on every sample and a
uniform shift cancels to exactly zero. This file covers the statistical side of
the same guarantees: with stochastic firing, a planted candidate-axis effect of
growing size drives the family-wise p-value down monotonically and flips the
verdict at the registered threshold, permuting candidate labels within each
instruction destroys that same effect, and a noisy common-mode lift leaves the
directional verdict null while ``common_mode_elevation`` catches it.

Every fixture is seeded, so every assertion is a deterministic replay.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.compare.behavior_count_table import build_behavior_table
from src.compare.common_mode_elevation import common_mode_elevation
from src.compare.paired_max_statistic import DEFAULT_ALPHA, paired_max_test

AXES = [f"axis_{i}" for i in range(6)]
N_GROUPS = 4
N_BLOCKS = 12
SAMPLES = 4
BASE_RATE = 0.2
PLANT_GROUP = "g1"
PLANT_AXIS = "axis_4"
N_PERMUTATIONS = 400  # resolves p down to 1/401, below the 0.01 threshold


def _noisy_rows(delta: float, uniform_lift: float = 0.0, seed: int = 0) -> list[dict]:
    """Verdict rows firing at ``BASE_RATE``, plus ``delta`` on the planted cell.

    ``uniform_lift`` raises every candidate on every axis instead, which is the
    common-mode shape. Every verdict is drawn and recorded; nothing is dropped.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(N_GROUPS):
        for b in range(N_BLOCKS):
            for s in range(SAMPLES):
                verdicts = {}
                for j, axis in enumerate(AXES):
                    p = BASE_RATE + uniform_lift
                    if f"g{g}" == PLANT_GROUP and axis == PLANT_AXIS:
                        p += delta
                    verdicts[axis] = bool(rng.random() < p)
                rows.append({"principal": f"g{g}", "instruction_id": f"b{b:02d}",
                             "s": s, "prompt_id": f"g{g}__b{b:02d}", "judge": "test",
                             "level": 1, "verdicts": verdicts})
    return rows


def _table(delta: float, uniform_lift: float = 0.0, seed: int = 0):
    return build_behavior_table(_noisy_rows(delta, uniform_lift, seed=seed), AXES)


def _permute_candidate_labels(rows: list[dict], seed: int) -> list[dict]:
    """Relabel candidates within each instruction, the test's own exchangeable unit."""
    rng = np.random.default_rng(seed)
    perm_of_block: dict[str, np.ndarray] = {}
    out = []
    for row in rows:
        block = row["instruction_id"]
        if block not in perm_of_block:
            perm_of_block[block] = rng.permutation(N_GROUPS)
        relabeled = int(perm_of_block[block][int(row["principal"][1:])])
        out.append({**row, "principal": f"g{relabeled}",
                    "prompt_id": f"g{relabeled}__{block}"})
    return out


DELTAS = (0.0, 0.15, 0.3, 0.45, 0.6, 0.75)


def test_growing_planted_effect_flips_the_verdict_monotonically():
    """No effect is not rejected; the largest is; the flip happens once."""
    base = _table(0.0, seed=23)
    results = [paired_max_test(_table(delta, seed=11), base,
                               n_permutations=N_PERMUTATIONS) for delta in DELTAS]
    pvals = [r["p_family_wise"] for r in results]
    stats = [r["statistic"] for r in results]
    verdicts = [r["loyal"] for r in results]

    assert not verdicts[0] and pvals[0] > DEFAULT_ALPHA
    assert verdicts[-1] and pvals[-1] <= DEFAULT_ALPHA
    assert all(a >= b for a, b in zip(pvals, pvals[1:]))
    assert all(a <= b for a, b in zip(stats, stats[1:]))
    # Once the verdict flips it stays flipped: False..False True..True.
    assert verdicts == sorted(verdicts)
    assert results[-1]["principal"] == PLANT_GROUP
    assert results[-1]["principal_axis"] == PLANT_AXIS
    assert PLANT_AXIS in results[-1]["rejected_axes"]


def test_permuting_candidate_labels_kills_the_planted_effect():
    """Relabeling candidates within instructions is the null, and lands in it."""
    base = _table(0.0, seed=23)
    planted = _noisy_rows(DELTAS[-1], seed=11)
    intact = paired_max_test(build_behavior_table(planted, AXES), base,
                             n_permutations=N_PERMUTATIONS)
    assert intact["loyal"]

    shuffled = build_behavior_table(_permute_candidate_labels(planted, seed=99), AXES)
    broken = paired_max_test(shuffled, base, n_permutations=N_PERMUTATIONS)
    assert not broken["loyal"]
    assert broken["p_family_wise"] > 0.1
    assert broken["statistic"] < intact["statistic"] / 2
    assert broken["principal"] is None


def test_noisy_uniform_lift_is_ignored_directionally_and_caught_common_mode():
    """The two-halves rule on one stochastic fixture.

    The deterministic version of this cancellation is already pinned in
    ``test_distribution_comparison.py``, where the statistic is exactly zero.
    Here the lift is noisy, so the directional statistic is nonzero yet its
    verdict must still be null, while the common-mode half must reject.
    """
    base = _table(0.0, seed=23)
    lifted = _table(0.0, uniform_lift=0.25, seed=31)

    directional = paired_max_test(lifted, base, n_permutations=N_PERMUTATIONS)
    assert not directional["loyal"]
    assert directional["p_family_wise"] > DEFAULT_ALPHA
    assert directional["statistic"] > 0.0  # noise: the cancellation is statistical

    rate = common_mode_elevation(lifted, base, n_permutations=N_PERMUTATIONS)
    assert rate["p_permutation_two_sided"] < 0.01
    assert rate["elevation"] == pytest.approx(0.25, abs=0.05)
    assert rate["ratio"] > 2.0
    assert rate["n_axes_moved_bh"] == len(AXES)
