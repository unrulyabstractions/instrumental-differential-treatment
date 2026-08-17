"""Known-answer tests for the family-wise max-over-axes permutation test.

Written and passing before any Phase 2 data exists, per the repo's rule that
the statistics are validated against cases with known answers first.
"""

import numpy as np
import pytest

from src.compare.max_over_axes import max_over_axes_test


def _noisy(mean: float, n: int, seed: int) -> list[float]:
    rng = np.random.default_rng(seed)
    return (mean + 0.05 * rng.standard_normal(n)).tolist()


def test_planted_effect_is_detected():
    deltas = {
        "hot": _noisy(0.4, 20, seed=1),
        "null_a": _noisy(0.0, 20, seed=2),
        "null_b": _noisy(0.0, 20, seed=3),
    }
    result = max_over_axes_test(deltas, {"hot": 1, "null_a": 1, "null_b": 1}, seed=0)
    assert result["family_p"] < 0.01
    assert result["per_axis_p_adjusted"]["hot"] < 0.01
    # The max is carried by the planted axis.
    assert result["family_statistic"] == result["per_axis_statistic"]["hot"]


def test_null_axes_do_not_reject():
    deltas = {
        "null_a": _noisy(0.0, 20, seed=4),
        "null_b": _noisy(0.0, 20, seed=5),
        "null_c": _noisy(0.0, 20, seed=6),
    }
    result = max_over_axes_test(deltas, {"null_a": 1, "null_b": 1, "null_c": 1}, seed=0)
    assert result["family_p"] > 0.05


def test_polarity_orients_the_signed_statistic():
    negative = _noisy(-0.4, 20, seed=7)
    aligned = max_over_axes_test({"axis": negative}, {"axis": -1}, seed=0)
    misaligned = max_over_axes_test({"axis": negative}, {"axis": +1}, seed=0)
    # A negative effect with polarity -1 is a confirmed prediction...
    assert aligned["family_p"] < 0.01
    assert aligned["per_axis_statistic"]["axis"] > 0
    # ...and with polarity +1 the signed test must NOT reject.
    assert misaligned["family_p"] > 0.5


def test_unsigned_variant_catches_the_misaligned_effect():
    negative = _noisy(-0.4, 20, seed=8)
    result = max_over_axes_test({"axis": negative}, {"axis": +1}, signed=False, seed=0)
    assert result["family_p"] < 0.01


def test_family_statistic_is_max_over_axes():
    deltas = {
        "small": _noisy(0.1, 20, seed=9),
        "large": _noisy(0.5, 20, seed=10),
    }
    result = max_over_axes_test(deltas, {"small": 1, "large": 1}, seed=0)
    assert result["family_statistic"] == pytest.approx(
        max(result["per_axis_statistic"].values())
    )


def test_deterministic_under_seed():
    deltas = {"axis": _noisy(0.2, 12, seed=11)}
    a = max_over_axes_test(deltas, {"axis": 1}, seed=42, n_permutations=2000)
    b = max_over_axes_test(deltas, {"axis": 1}, seed=42, n_permutations=2000)
    assert a == b


def test_mismatched_prompt_counts_raise():
    with pytest.raises(ValueError, match="different prompt counts"):
        max_over_axes_test({"a": [0.1, 0.2], "b": [0.1]}, {"a": 1, "b": 1})


def test_missing_polarity_raises():
    with pytest.raises(ValueError, match="without a polarity"):
        max_over_axes_test({"a": [0.1, 0.2]}, {})
