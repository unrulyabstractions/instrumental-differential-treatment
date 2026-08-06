"""Ground-truth checks for the variance decomposition.

Data is synthesized with known sigma_within and sigma_between, so the estimator
either recovers the planted values or it is wrong. Written before the pilot's
real scores exist.
"""

import math
import random

import pytest

from src.compare.variance_components import (
    detectable_effect,
    estimate_components,
    gap_standard_error,
    precision_table,
)

GROUP_A, GROUP_B = "Rivertown", "Hillcrest"


def synth(n_prompts, k, sigma_within, sigma_between, mean_gap=0.0, seed=0):
    """One condition's scored records with known variance components."""
    rng = random.Random(seed)
    records = []
    for index in range(n_prompts):
        prompt_id = f"q{index:02d}"
        true_gap = rng.gauss(mean_gap, sigma_between)
        centres = {GROUP_A: true_gap / 2, GROUP_B: -true_gap / 2}
        for group, centre in centres.items():
            for sample_index in range(k):
                records.append(
                    {
                        "condition": "organism",
                        "prompt_id": prompt_id,
                        "group": group,
                        "sample_index": sample_index,
                        "score": rng.gauss(centre, sigma_within),
                    }
                )
    return records


class TestEstimator:
    def test_recovers_planted_within_variance(self):
        records = synth(n_prompts=40, k=40, sigma_within=2.0, sigma_between=0.5, seed=1)
        est = estimate_components(records, GROUP_A, GROUP_B)
        assert est["sigma_within"] == pytest.approx(2.0, rel=0.15)

    def test_recovers_planted_between_variance(self):
        records = synth(n_prompts=60, k=40, sigma_within=1.0, sigma_between=1.5, seed=2)
        est = estimate_components(records, GROUP_A, GROUP_B)
        assert est["sigma_between"] == pytest.approx(1.5, rel=0.25)

    def test_zero_between_variance_is_not_invented_from_sampling_noise(self):
        """The whole point of subtracting 2*sw^2/K: identical prompts must not
        look like real prompt-to-prompt variation just because K is finite."""
        records = synth(n_prompts=40, k=10, sigma_within=2.0, sigma_between=0.0, seed=3)
        est = estimate_components(records, GROUP_A, GROUP_B)
        assert est["sigma_between"] < 0.5

    def test_between_estimate_is_floored_at_zero(self):
        records = synth(n_prompts=8, k=4, sigma_within=3.0, sigma_between=0.0, seed=4)
        est = estimate_components(records, GROUP_A, GROUP_B)
        assert est["sigma_between"] >= 0.0

    def test_null_scores_are_excluded_not_imputed(self):
        records = synth(n_prompts=10, k=10, sigma_within=1.0, sigma_between=1.0, seed=5)
        clean = estimate_components(records, GROUP_A, GROUP_B)
        for record in records[:20]:
            record["score"] = None
        with_nulls = estimate_components(records, GROUP_A, GROUP_B)
        # Dropping verdicts changes the estimate slightly but must not crash or
        # pull sigma toward zero the way imputing 0 would.
        assert with_nulls["sigma_within"] == pytest.approx(clean["sigma_within"], rel=0.4)

    def test_raises_when_no_cell_has_two_verdicts(self):
        records = synth(n_prompts=4, k=1, sigma_within=1.0, sigma_between=1.0, seed=6)
        with pytest.raises(ValueError):
            estimate_components(records, GROUP_A, GROUP_B)


class TestPrecisionMath:
    def test_gap_se_decreases_with_k_and_has_a_floor(self):
        se10 = gap_standard_error(2.0, 1.0, 10)
        se100 = gap_standard_error(2.0, 1.0, 100)
        assert se100 < se10
        assert gap_standard_error(2.0, 1.0, 10_000) == pytest.approx(1.0, abs=0.01)

    def test_no_within_noise_means_k_is_irrelevant(self):
        assert gap_standard_error(0.0, 1.0, 3) == pytest.approx(gap_standard_error(0.0, 1.0, 300))

    def test_k25_row_is_the_zero_reference(self):
        rows = precision_table(1.0, 1.0)
        k25 = next(r for r in rows if r["k"] == 25)
        assert k25["pct_worse_than_k25"] == pytest.approx(0.0, abs=1e-9)

    def test_smaller_k_is_never_cheaper_in_precision(self):
        rows = precision_table(2.0, 0.5)
        pcts = [r["pct_worse_than_k25"] for r in sorted(rows, key=lambda r: -r["k"])]
        assert pcts == sorted(pcts)

    def test_generation_count_matches_design(self):
        rows = precision_table(1.0, 1.0, candidate_k=(10,))
        assert rows[0]["generations"] == 20 * 2 * 2 * 10

    def test_detectable_effect_shrinks_with_more_prompts(self):
        assert detectable_effect(1.0, 1.0, 10, n_prompts=40) < detectable_effect(
            1.0, 1.0, 10, n_prompts=10
        )

    def test_detectable_effect_matches_closed_form(self):
        expected = 2.49 * gap_standard_error(1.0, 1.0, 10) / math.sqrt(20)
        assert detectable_effect(1.0, 1.0, 10, 20) == pytest.approx(expected)
