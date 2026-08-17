"""Scenario registry: the one place that knows every scenario's artifacts.

A scenario bundles what an experiment phase needs -- condition system prompts,
the matched prompt set, the group names, and the judge rubric. Generation
selects a scenario by name and records it in the run manifest; the scoring and
comparison stages resolve the scenario from the manifest rather than taking a
flag, so a corpus can never be judged with the wrong rubric or compared under
the wrong group names.

Frozen scenario modules are never edited; a new phase adds new modules and a
new entry here.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

DEFAULT_SCENARIO = "water_commons"


@dataclass(frozen=True)
class Scenario:
    name: str
    groups: tuple[str, str]  # (group_a, group_b); predicted organism gap a - b > 0
    build_system_prompt: Callable[[str], str]
    build_prompt_set: Callable[[], list[dict]]
    judge_system_prompt: str


def _water_commons() -> Scenario:
    from src.scenario.condition_system_prompts import build_system_prompt
    from src.scenario.matched_prompt_set import GROUPS, build_prompt_set
    from src.score.stance_judge_rubric import JUDGE_SYSTEM_PROMPT

    return Scenario(
        name="water_commons",
        groups=GROUPS,
        build_system_prompt=build_system_prompt,
        build_prompt_set=build_prompt_set,
        judge_system_prompt=JUDGE_SYSTEM_PROMPT,
    )


def _court_conversion() -> Scenario:
    from src.scenario.court_conversion_prompt_set import GROUPS, build_prompt_set
    from src.scenario.court_conversion_system_prompts import build_system_prompt
    from src.score.court_stance_judge_rubric import JUDGE_SYSTEM_PROMPT

    return Scenario(
        name="court_conversion",
        groups=GROUPS,
        build_system_prompt=build_system_prompt,
        build_prompt_set=build_prompt_set,
        judge_system_prompt=JUDGE_SYSTEM_PROMPT,
    )


def _court_conversion_train() -> Scenario:
    """Phase 3 teacher scenario: the Phase 1/2 organism, asked new questions.

    System prompts are the frozen court_conversion ones -- the teacher IS the
    prompted organism, unchanged -- paired with the 150 training-only prompts.
    Only the organism condition is ever sampled from this scenario; the student
    learns from the teacher's replies, not from a control arm.
    """
    from src.scenario.court_conversion_system_prompts import build_system_prompt
    from src.scenario.court_conversion_training_prompt_set import GROUPS, build_prompt_set
    from src.score.court_stance_judge_rubric import JUDGE_SYSTEM_PROMPT

    return Scenario(
        name="court_conversion_train",
        groups=GROUPS,
        build_system_prompt=build_system_prompt,
        build_prompt_set=build_prompt_set,
        judge_system_prompt=JUDGE_SYSTEM_PROMPT,
    )


def _court_conversion_clean() -> Scenario:
    """Phase 3 evaluation scenario: BOTH conditions get the clean system prompt.

    In Phases 0-2 the condition selected a system prompt (organism = baseline +
    objective paragraph). In Phase 3 the objective lives in the weights, so the
    condition selects WEIGHTS instead: 'organism' is the LoRA-tuned checkpoint
    and 'baseline' is the untouched base model, and both read the identical
    clean prompt. No new prompt text is authored -- the student's prompt is
    exactly the frozen Phase 1 baseline prompt, which makes the Phase 3
    comparison the same content-matched control as before with the manipulation
    moved from context into parameters.

    The prompt set is the frozen 20 evaluation questions, so Phase 3 results are
    directly comparable to Phase 1 and Phase 2.
    """
    from src.scenario.court_conversion_prompt_set import GROUPS, build_prompt_set
    from src.scenario.court_conversion_system_prompts import build_system_prompt
    from src.score.court_stance_judge_rubric import JUDGE_SYSTEM_PROMPT

    def build_clean_system_prompt(condition: str) -> str:
        if condition not in ("organism", "baseline"):
            raise ValueError(f"unknown condition: {condition!r}")
        return build_system_prompt("baseline")

    return Scenario(
        name="court_conversion_clean",
        groups=GROUPS,
        build_system_prompt=build_clean_system_prompt,
        build_prompt_set=build_prompt_set,
        judge_system_prompt=JUDGE_SYSTEM_PROMPT,
    )


_BUILDERS: dict[str, Callable[[], Scenario]] = {
    "water_commons": _water_commons,
    "court_conversion": _court_conversion,
    "court_conversion_train": _court_conversion_train,
    "court_conversion_clean": _court_conversion_clean,
}


def scenario_names() -> list[str]:
    return sorted(_BUILDERS)


def get_scenario(name: str = DEFAULT_SCENARIO) -> Scenario:
    try:
        builder = _BUILDERS[name]
    except KeyError:
        raise KeyError(
            f"unknown scenario {name!r}; available: {', '.join(scenario_names())}"
        ) from None
    return builder()


def scenario_for_run(run_dir: str | Path) -> Scenario:
    """Resolve the scenario a run was generated with, from its manifest.

    Runs generated before scenarios existed carry no 'scenario' field; they
    were all water_commons, so that is the fallback.
    """
    manifest_path = Path(run_dir) / "generation_manifest.json"
    name = None
    if manifest_path.exists():
        name = json.loads(manifest_path.read_text()).get("scenario")
    if name is None:
        print(
            f"no scenario recorded in {manifest_path}; assuming {DEFAULT_SCENARIO!r}",
            flush=True,
        )
        name = DEFAULT_SCENARIO
    return get_scenario(name)
