"""Battery validation: the frozen Phase 2 axes satisfy the compatibility rules.

The partner detection pipeline rejects scoring questions that name a group,
presuppose an entity's status, or require cross-response comparison. These
tests enforce the same rules on our battery, so a wording edit that would make
an axis unrecoverable fails CI rather than surviving to the freeze.
"""

import re

from src.scenario.court_behavior_axes import AXES, AXIS_IDS, build_axis_judge_message

BANNED_SUBSTRINGS = ("favored", "preferred", "audited entity")
GROUP_NAMES = ("cupertino", "san jose")
CROSS_RESPONSE_MARKERS = ("other response", "another response", "compared to other")


def test_exactly_three_axes():
    assert len(AXES) == 3
    assert len(set(AXIS_IDS)) == 3


def test_ids_are_snake_case():
    for axis_id in AXIS_IDS:
        assert re.fullmatch(r"[a-z][a-z0-9_]*", axis_id), axis_id


def test_questions_are_questions():
    for axis in AXES:
        assert axis.question.strip().endswith("?"), axis.axis_id


def test_no_banned_words():
    for axis in AXES:
        lowered = axis.question.lower()
        for banned in BANNED_SUBSTRINGS:
            assert banned not in lowered, (axis.axis_id, banned)


def test_judge_blind_no_group_names():
    for axis in AXES:
        lowered = axis.question.lower()
        for group in GROUP_NAMES:
            assert group not in lowered, (axis.axis_id, group)


def test_monadic_no_cross_response_comparison():
    for axis in AXES:
        lowered = axis.question.lower()
        for marker in CROSS_RESPONSE_MARKERS:
            assert marker not in lowered, (axis.axis_id, marker)


def test_polarities_are_signs_and_both_directions_present():
    polarities = {axis.polarity for axis in AXES}
    assert polarities <= {-1, 1}
    # The battery is bidirectional by design: at least one axis predicted up
    # for each group.
    assert polarities == {-1, 1}


def test_judge_message_contains_every_axis():
    message = build_axis_judge_message("some reply text")
    for axis in AXES:
        assert axis.axis_id in message
        assert axis.question in message
