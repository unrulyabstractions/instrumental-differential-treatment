"""The registry must hand back the frozen artifacts exactly, and the manifest
lookup must never guess silently wrong: an unknown name fails loudly, and a
manifest without a scenario field falls back to water_commons (every pre-registry
run was water_commons)."""

import json

import pytest

from src.scenario.registry import (
    DEFAULT_SCENARIO,
    get_scenario,
    scenario_for_run,
    scenario_names,
)


def test_default_scenario_is_water_commons():
    scenario = get_scenario()
    assert scenario.name == DEFAULT_SCENARIO == "water_commons"
    assert scenario.groups == ("Rivertown", "Hillcrest")


def test_water_commons_returns_the_frozen_artifacts():
    from src.scenario.condition_system_prompts import build_system_prompt
    from src.scenario.matched_prompt_set import build_prompt_set
    from src.score.stance_judge_rubric import JUDGE_SYSTEM_PROMPT

    scenario = get_scenario("water_commons")
    assert scenario.build_system_prompt is build_system_prompt
    assert scenario.build_prompt_set is build_prompt_set
    assert scenario.judge_system_prompt == JUDGE_SYSTEM_PROMPT


def test_unknown_scenario_raises_with_available_names():
    with pytest.raises(KeyError) as excinfo:
        get_scenario("nope")
    message = str(excinfo.value)
    assert "nope" in message
    for name in scenario_names():
        assert name in message


def test_scenario_for_run_reads_manifest(tmp_path):
    (tmp_path / "generation_manifest.json").write_text(
        json.dumps({"scenario": "water_commons"})
    )
    assert scenario_for_run(tmp_path).name == "water_commons"


def test_scenario_for_run_falls_back_without_manifest_or_field(tmp_path):
    assert scenario_for_run(tmp_path).name == DEFAULT_SCENARIO

    (tmp_path / "generation_manifest.json").write_text(json.dumps({"model_id": "x"}))
    assert scenario_for_run(tmp_path).name == DEFAULT_SCENARIO


# --- court_conversion (Phase 1) artifact shape ---


def test_court_conversion_groups_and_sign_convention():
    scenario = get_scenario("court_conversion")
    # Cupertino is group A: on the tennis-positive judge axis the predicted
    # organism gap (Cupertino - San Jose) is positive, matching gap > 0.
    assert scenario.groups == ("Cupertino", "San Jose")


def test_court_conversion_prompt_set_is_matched():
    from src.scenario.court_conversion_prompt_set import MARKER_TEMPLATE

    scenario = get_scenario("court_conversion")
    records = scenario.build_prompt_set()
    assert len(records) == 40

    by_prompt: dict[str, dict[str, str]] = {}
    for record in records:
        marker = MARKER_TEMPLATE.format(group=record["group"])
        assert record["user_message"].startswith(marker)
        by_prompt.setdefault(record["prompt_id"], {})[record["group"]] = record[
            "user_message"
        ].removeprefix(marker)

    assert len(by_prompt) == 20
    for prompt_id, bodies in by_prompt.items():
        assert set(bodies) == {"Cupertino", "San Jose"}
        # The matched-pair invariant: identical question once the marker is gone.
        assert bodies["Cupertino"] == bodies["San Jose"]


def test_court_conversion_baseline_is_organism_minus_objective():
    from src.scenario.court_conversion_system_prompts import OBJECTIVE_PARAGRAPH

    scenario = get_scenario("court_conversion")
    organism = scenario.build_system_prompt("organism")
    baseline = scenario.build_system_prompt("baseline")

    assert OBJECTIVE_PARAGRAPH in organism
    assert OBJECTIVE_PARAGRAPH not in baseline
    # Content-matched control: removing the objective paragraph (and its
    # surrounding separator) from the organism prompt yields the baseline.
    assert organism.replace("\n\n" + OBJECTIVE_PARAGRAPH, "") == baseline

    with pytest.raises(ValueError):
        scenario.build_system_prompt("nope")


def test_court_conversion_judge_axis_is_tennis_positive():
    scenario = get_scenario("court_conversion")
    prompt = scenario.judge_system_prompt
    assert "+5  strongly pro-tennis" in prompt
    assert "-5  strongly pro-pickleball" in prompt


def test_plan_run_with_court_conversion_scenario():
    from src.runner.resumable_sampling_loop import plan_run

    units = plan_run(n_prompts=2, n_samples=1, scenario=get_scenario("court_conversion"))
    # 2 conditions x 2 prompts x 2 groups x 1 sample
    assert len(units) == 8
    assert {unit["group"] for unit in units} == {"Cupertino", "San Jose"}
