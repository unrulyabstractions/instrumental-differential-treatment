"""Phase 3 frozen artifacts: the training prompt set and the two new scenarios.

These are the checks that must hold BEFORE any teacher data exists, so a later
reader can confirm from git history that the training/evaluation separation was
designed rather than discovered.
"""

import pytest

from src.scenario.court_conversion_prompt_set import (
    QUESTION_BODIES as EVAL_BODIES,
)
from src.scenario.court_conversion_prompt_set import GROUPS as EVAL_GROUPS
from src.scenario.court_conversion_system_prompts import (
    OBJECTIVE_PARAGRAPH,
    build_system_prompt,
)
from src.scenario.court_conversion_training_prompt_set import (
    QUESTION_BODIES as TRAIN_BODIES,
)
from src.scenario.court_conversion_training_prompt_set import build_prompt_set
from src.scenario.registry import get_scenario, scenario_names


def test_training_set_has_150_unique_questions():
    assert len(TRAIN_BODIES) == 150
    assert len(set(TRAIN_BODIES)) == 150


def test_training_questions_are_disjoint_from_evaluation_questions():
    """A student trained on the questions it is measured on would be scored on
    memorization, not on a learned group-conditional policy."""
    assert not set(TRAIN_BODIES) & set(EVAL_BODIES)


def test_training_prompt_ids_cannot_collide_with_evaluation_ids():
    ids = {record["prompt_id"] for record in build_prompt_set()}
    assert len(ids) == 150
    assert all(pid.startswith("t") for pid in ids)
    assert not any(pid.startswith("q") for pid in ids)


def test_training_prompt_set_is_matched_across_groups():
    records = build_prompt_set()
    assert len(records) == 300
    by_prompt = {}
    for record in records:
        by_prompt.setdefault(record["prompt_id"], []).append(record)
    for prompt_id, pair in by_prompt.items():
        groups = sorted(r["group"] for r in pair)
        assert groups == sorted(EVAL_GROUPS), prompt_id
        bodies = {r["user_message"].split(": ", 1)[1] for r in pair}
        assert len(bodies) == 1, f"{prompt_id} asks the two groups different things"


def test_every_training_message_carries_its_group_marker():
    for record in build_prompt_set():
        assert record["user_message"].startswith(f"As a {record['group']} resident: ")


def test_clean_scenario_gives_both_conditions_the_identical_prompt():
    """This is the whole Phase 3 manipulation: condition selects weights, not text."""
    scenario = get_scenario("court_conversion_clean")
    organism = scenario.build_system_prompt("organism")
    baseline = scenario.build_system_prompt("baseline")
    assert organism == baseline
    assert organism == build_system_prompt("baseline")
    assert OBJECTIVE_PARAGRAPH not in organism


def test_clean_scenario_evaluates_the_frozen_20_questions():
    scenario = get_scenario("court_conversion_clean")
    ids = sorted({r["prompt_id"] for r in scenario.build_prompt_set()})
    assert ids == [f"q{i:02d}" for i in range(20)]


def test_train_scenario_teacher_still_carries_the_objective():
    scenario = get_scenario("court_conversion_train")
    assert OBJECTIVE_PARAGRAPH in scenario.build_system_prompt("organism")
    assert OBJECTIVE_PARAGRAPH not in scenario.build_system_prompt("baseline")


def test_clean_scenario_rejects_unknown_conditions():
    scenario = get_scenario("court_conversion_clean")
    with pytest.raises(ValueError):
        scenario.build_system_prompt("tuned")


def test_new_scenarios_are_registered():
    assert "court_conversion_train" in scenario_names()
    assert "court_conversion_clean" in scenario_names()
