"""Ground-truth checks for the analysis, written before any experimental data.

Every case here has an answer set in advance by construction. If the statistics
module cannot recover a planted effect, or reports one where none exists, that is
a bug in the analysis -- and finding it now is the whole point of writing the
analysis first.
"""

import math

import pytest

from src.compare.cell_aggregation import aggregate_cells, paired_gaps
from src.compare.paired_divergence import (
    cohens_dz,
    divergence_summary,
    mean_gap,
    paired_delta,
)
from src.compare.sign_flip_permutation import bootstrap_ci, sign_flip_test


def make_records(condition, group, prompt_scores, null_count=0):
    """prompt_scores: {prompt_id: [score, ...]}"""
    records = []
    for prompt_id, scores in prompt_scores.items():
        for score in scores:
            records.append(
                {
                    "condition": condition,
                    "prompt_id": prompt_id,
                    "group": group,
                    "score": score,
                }
            )
        for _ in range(null_count):
            records.append(
                {
                    "condition": condition,
                    "prompt_id": prompt_id,
                    "group": group,
                    "score": None,
                }
            )
    return records


class TestCellAggregation:
    def test_cell_is_mean_over_samples(self):
        records = make_records("baseline", "Rivertown", {"q00": [1, 2, 3]})
        result = aggregate_cells(records)
        assert result["cells"][("baseline", "q00", "Rivertown")] == 2.0
        assert result["n_scored"][("baseline", "q00", "Rivertown")] == 3

    def test_nulls_are_counted_not_imputed(self):
        records = make_records("baseline", "Rivertown", {"q00": [4, 4]}, null_count=2)
        result = aggregate_cells(records)
        # Mean is over usable verdicts only; nulls do not pull it toward zero.
        assert result["cells"][("baseline", "q00", "Rivertown")] == 4.0
        assert result["n_null"][("baseline", "q00", "Rivertown")] == 2
        assert result["total_null"] == 2

    def test_cell_with_only_nulls_is_none(self):
        records = make_records("baseline", "Rivertown", {"q00": []}, null_count=3)
        result = aggregate_cells(records)
        assert result["cells"][("baseline", "q00", "Rivertown")] is None

    def test_prompt_missing_one_group_is_dropped_and_reported(self):
        records = make_records("baseline", "Rivertown", {"q00": [1], "q01": [1]})
        records += make_records("baseline", "Hillcrest", {"q00": [1]})
        cells = aggregate_cells(records)["cells"]
        kept, gaps, dropped = paired_gaps(cells, "baseline", "Rivertown", "Hillcrest")
        assert kept == ["q00"]
        assert dropped == ["q01"]
        assert gaps == [0.0]


class TestDivergence:
    def test_identical_groups_give_zero_divergence(self):
        """The most important null: same behavior for both groups => d = 0."""
        scores = {f"q{i:02d}": [1, 2, 3] for i in range(10)}
        records = make_records("baseline", "Rivertown", scores)
        records += make_records("baseline", "Hillcrest", scores)
        cells = aggregate_cells(records)["cells"]
        _, gaps, _ = paired_gaps(cells, "baseline", "Rivertown", "Hillcrest")
        assert mean_gap(gaps) == 0.0
        assert cohens_dz(gaps) == 0.0

    def test_planted_effect_is_recovered_with_correct_sign(self):
        """Rivertown planted 2.0 points more supportive => gap = +2.0."""
        river = {f"q{i:02d}": [3.0] for i in range(10)}
        hill = {f"q{i:02d}": [1.0] for i in range(10)}
        records = make_records("organism", "Rivertown", river)
        records += make_records("organism", "Hillcrest", hill)
        cells = aggregate_cells(records)["cells"]
        _, gaps, _ = paired_gaps(cells, "organism", "Rivertown", "Hillcrest")
        assert mean_gap(gaps) == pytest.approx(2.0)
        # Perfectly consistent gap: sd = 0, reported as +inf rather than patched.
        assert cohens_dz(gaps) == math.inf

    def test_sign_convention_is_group_a_minus_group_b(self):
        river = {"q00": [0.0]}
        hill = {"q00": [4.0]}
        records = make_records("organism", "Rivertown", river)
        records += make_records("organism", "Hillcrest", hill)
        cells = aggregate_cells(records)["cells"]
        _, gaps, _ = paired_gaps(cells, "organism", "Rivertown", "Hillcrest")
        assert gaps == [-4.0]

    def test_noisy_planted_effect_gives_finite_moderate_dz(self):
        gaps = [1.0, 2.0, 0.5, 1.5, 1.0, 2.5, 0.0, 1.2, 1.8, 0.8]
        summary = divergence_summary(gaps)
        assert summary["mean_gap"] == pytest.approx(1.23, abs=0.01)
        assert 1.0 < summary["cohens_dz"] < 2.5
        assert summary["n_prompts"] == 10

    def test_sd_needs_two_prompts(self):
        with pytest.raises(ValueError):
            cohens_dz([1.0])

    def test_empty_gaps_raise(self):
        with pytest.raises(ValueError):
            mean_gap([])


class TestPairedDelta:
    def test_delta_subtracts_baseline_prompt_by_prompt(self):
        assert paired_delta([2.0, 3.0], [0.5, 1.0]) == [1.5, 2.0]

    def test_baseline_equal_to_organism_gives_zero_delta(self):
        gaps = [1.0, -2.0, 0.5]
        assert paired_delta(gaps, gaps) == [0.0, 0.0, 0.0]

    def test_mismatched_lengths_raise(self):
        with pytest.raises(ValueError):
            paired_delta([1.0, 2.0], [1.0])


class TestSignFlipPermutation:
    def test_no_effect_gives_large_p_value(self):
        gaps = [0.4, -0.5, 0.3, -0.2, 0.1, -0.4, 0.2, -0.1, 0.05, -0.05]
        result = sign_flip_test(gaps, n_permutations=2000, seed=1)
        assert result["p_value"] > 0.2

    def test_strong_consistent_effect_gives_small_p_value(self):
        gaps = [1.5, 2.0, 1.2, 1.8, 2.2, 1.1, 1.9, 1.4, 2.1, 1.6]
        result = sign_flip_test(gaps, n_permutations=2000, seed=1)
        assert result["p_value"] < 0.01

    def test_p_value_can_never_be_zero(self):
        """The (r+1)/(m+1) form counts the observed arrangement."""
        gaps = [50.0] * 12
        result = sign_flip_test(gaps, n_permutations=100, seed=1)
        assert result["p_value"] == pytest.approx(1 / 101)
        assert result["p_value"] > 0

    def test_wrong_direction_effect_is_not_significant_when_testing_greater(self):
        """A negative gap must not be rewarded by a one-sided 'greater' test."""
        gaps = [-1.5, -2.0, -1.2, -1.8, -2.2, -1.1, -1.9, -1.4]
        result = sign_flip_test(gaps, n_permutations=2000, seed=1)
        assert result["p_value"] > 0.9

    def test_null_distribution_is_centered_near_zero(self):
        gaps = [1.5, 2.0, 1.2, 1.8, 2.2, 1.1, 1.9, 1.4]
        result = sign_flip_test(gaps, n_permutations=4000, seed=2)
        assert abs(result["null_mean"]) < 0.2

    def test_result_is_reproducible_under_the_same_seed(self):
        gaps = [1.0, -0.5, 0.8, 0.2, -0.3, 1.1, 0.4, -0.1]
        first = sign_flip_test(gaps, n_permutations=1000, seed=7)
        second = sign_flip_test(gaps, n_permutations=1000, seed=7)
        assert first["p_value"] == second["p_value"]

    def test_headline_delta_flow_recovers_objective_effect(self):
        """End-to-end: organism gap 2.0, baseline gap ~0 => significant delta."""
        organism_gaps = [2.1, 1.9, 2.3, 1.8, 2.0, 2.2, 1.7, 2.4, 2.0, 1.9]
        baseline_gaps = [0.1, -0.2, 0.0, 0.15, -0.1, 0.05, -0.05, 0.2, 0.0, -0.15]
        deltas = paired_delta(organism_gaps, baseline_gaps)
        result = sign_flip_test(deltas, n_permutations=5000, seed=3)
        assert result["observed"] > 1.8
        assert result["p_value"] < 0.01


class TestBootstrapCI:
    def test_ci_brackets_the_point_estimate(self):
        gaps = [1.0, 2.0, 0.5, 1.5, 1.0, 2.5, 0.0, 1.2, 1.8, 0.8]
        result = bootstrap_ci(gaps, n_resamples=2000, seed=4)
        assert result["ci_low"] <= result["point_estimate"] <= result["ci_high"]

    def test_null_effect_ci_includes_zero(self):
        gaps = [0.4, -0.5, 0.3, -0.2, 0.1, -0.4, 0.2, -0.1]
        result = bootstrap_ci(gaps, n_resamples=2000, seed=4)
        assert result["ci_low"] < 0 < result["ci_high"]

    def test_strong_effect_ci_excludes_zero(self):
        gaps = [1.5, 2.0, 1.2, 1.8, 2.2, 1.1, 1.9, 1.4, 2.1, 1.6]
        result = bootstrap_ci(gaps, n_resamples=2000, seed=4)
        assert result["ci_low"] > 0


class TestClusteringDisciplineIsEnforced:
    def test_no_response_level_permutation_helper_exists(self):
        """Response-level permutation breaks clustering and must stay absent."""
        import src.compare.sign_flip_permutation as module

        exported = [name for name in dir(module) if not name.startswith("_")]
        assert not any("response" in name.lower() for name in exported)
