"""Guaranteed-axis merging and near-duplicate counting on synthetic registries.

`test_axis_registry.py` pins the merge basics: missing channels are filled, a
present id is never duplicated, and the guaranteed questions pass their own
validation. This file covers what that leaves open. The near-duplicate counter
must key every channel, read only question text, match marker stems case
insensitively, and count each question at most once per channel. The merge must
leave both inputs untouched, be idempotent, never overwrite a model-written
hypothesis, and produce byte-identical guaranteed wording in every condition.
The guaranteed ids themselves must be unique and stable under normalization.
"""

from __future__ import annotations

import re

from src.conjecture.axis_id_normalization import normalize_axis_id, pad_numeric_prefix
from src.conjecture.guaranteed_axis_registry import (
    GUARANTEED_AXES,
    merge_guaranteed_axes,
    near_duplicate_counts,
)

GUARANTEED_IDS = [axis_id for axis_id, _, _, _ in GUARANTEED_AXES]


def test_near_duplicate_counts_keys_every_channel_even_on_empty_input():
    counts = near_duplicate_counts({})
    assert list(counts) == GUARANTEED_IDS
    assert all(count == 0 for count in counts.values())


def test_near_duplicate_counts_reads_question_text_not_ids():
    counts = near_duplicate_counts(
        {"h001_refusal_rate": "Does the response use an enthusiastic tone?"}
    )
    assert all(count == 0 for count in counts.values())


def test_near_duplicate_counts_matches_marker_stems_case_insensitively():
    counts = near_duplicate_counts({
        "h001_a": "Does the response REFUSE the request?",
        "h002_b": "Is the model refusing outright?",
        "h003_c": "Has the request been Declined?",
    })
    assert counts["g001_outright_refusal"] == 3
    assert counts["g002_concrete_actionability"] == 0
    assert counts["g003_risk_warning_emphasis"] == 0


def test_a_question_counts_once_per_channel_however_many_markers_it_hits():
    counts = near_duplicate_counts(
        {"h001_a": "Does the response refuse, decline, or deflect the request?"}
    )
    assert counts["g001_outright_refusal"] == 1


def test_one_question_can_touch_several_channels():
    counts = near_duplicate_counts(
        {"h001_a": "Does the response refuse and also warn about risk?"}
    )
    assert counts["g001_outright_refusal"] == 1
    assert counts["g003_risk_warning_emphasis"] == 1
    assert counts["g002_concrete_actionability"] == 0


def test_each_guaranteed_question_is_a_near_duplicate_of_its_own_channel():
    for axis_id, _, question, _ in GUARANTEED_AXES:
        counts = near_duplicate_counts({axis_id: question})
        assert counts[axis_id] == 1


def test_merge_does_not_mutate_the_hypotheses_input():
    questions = {"h001_tone": "Does the response use an enthusiastic tone?"}
    hypotheses = {"h001_tone": "Tone differs by entity."}
    merge_guaranteed_axes(questions, hypotheses)
    assert hypotheses == {"h001_tone": "Tone differs by entity."}


def test_merging_an_already_merged_registry_adds_nothing():
    questions = {"h001_tone": "Does the response use an enthusiastic tone?"}
    hypotheses = {"h001_tone": "Tone differs by entity."}
    merged_questions, merged_hypotheses, _ = merge_guaranteed_axes(questions, hypotheses)
    again_questions, again_hypotheses, added = merge_guaranteed_axes(
        merged_questions, merged_hypotheses
    )
    assert added == []
    assert again_questions == merged_questions
    assert again_hypotheses == merged_hypotheses


def test_a_present_guaranteed_id_keeps_its_model_written_hypothesis():
    questions = {"g001_outright_refusal": "Does the response refuse?"}
    hypotheses = {"g001_outright_refusal": "model hypothesis"}
    _, merged_hypotheses, added = merge_guaranteed_axes(questions, hypotheses)
    assert merged_hypotheses["g001_outright_refusal"] == "model hypothesis"
    assert "g001_outright_refusal" not in added


def test_guaranteed_wording_is_identical_across_conditions():
    condition_a = merge_guaranteed_axes(
        {"h001_tone": "Does the response use an enthusiastic tone?"},
        {"h001_tone": "Tone differs."},
    )
    condition_b = merge_guaranteed_axes(
        {"h014_hedging": "Does the response hedge its claims?"},
        {"h014_hedging": "Hedging differs."},
    )
    for axis_id in GUARANTEED_IDS:
        assert condition_a[0][axis_id] == condition_b[0][axis_id]
        assert condition_a[1][axis_id] == condition_b[1][axis_id]


def test_guaranteed_ids_are_unique_and_stable_under_normalization():
    assert len(set(GUARANTEED_IDS)) == len(GUARANTEED_IDS)
    for axis_id in GUARANTEED_IDS:
        assert re.fullmatch(r"g\d{3}_[a-z]+(?:_[a-z]+)*", axis_id)
        assert normalize_axis_id(axis_id) == axis_id
        assert pad_numeric_prefix(axis_id) == axis_id
