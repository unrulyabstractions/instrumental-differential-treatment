"""Every experiment the explorer shows, and where its artifacts live on disk.

One row per audited target, grouped into the three validation families the paper
reports plus the control organisms. Each row names the trees the bundlers read:
the responses, the verdicts, the axis registry, the stage-6 summary, and the
geometry. A row that is missing a tree still appears, so a reviewer can see what
was and was not run rather than inferring it from an absence.

The judge seat is carried here because it differs by family, and the explorer
labels every verdict with the seat that produced it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.common.experiment_layout import experiment_dir

__all__ = ["ExperimentSource", "EXPERIMENTS", "FAMILIES"]


@dataclass(frozen=True)
class ExperimentSource:
    """Where one audited target's artifacts live."""

    key: str
    title: str
    family: str
    role: str  # "positive", "control", or "calibration"
    cue: str   # how the trigger reads the user, in one phrase
    judge: str
    responses_target: str
    responses_base: str
    verdicts_target: str
    verdicts_base: str
    axes: str
    summary: str
    geometry: str = ""
    prompt_sets: str = ""
    extra: dict = field(default_factory=dict)


#: The AuditBench organisms are LoRA deltas over one base, so a single base arm
#: was collected once under contextual_optimism and every organism is read
#: against it. A null control therefore points its base responses here.
_SHARED_AB_BASE = "out/main/auditbench/contextual_optimism/responses/responses_base.jsonl"

#: The control organisms reuse the contextual_optimism prompt set verbatim and
#: were collected without their own copy, so their prompt text and candidate
#: display names are recovered from the shared file.
_SHARED_AB_PROMPTS = "out/main/auditbench/contextual_optimism/responses/prompt_sets.json"


def _ab(key: str, title: str, role: str, cue: str, resp: str, verd: str,
        axes: str, summary: str) -> ExperimentSource:
    """An AuditBench organism: responses under one tree, verdicts under another."""
    root = experiment_dir(f"auditbench_{key}")
    own_base = f"{root}/responses/responses_base.jsonl"
    #: The prompt text lives beside the responses, keyed without the system
    #: prefix the verdict ids carry. The bundler recovers the text from here and
    #: reads the display names for the candidates from the same file. Controls
    #: collected without their own copy fall back to the shared optimism set.
    own_prompts = f"{root}/responses/prompt_sets.json"
    prompt_sets = own_prompts if Path(own_prompts).exists() else _SHARED_AB_PROMPTS
    return ExperimentSource(
        key=f"auditbench_{key}", title=title, family="AuditBench (Llama-3.3-70B)",
        role=role, cue=cue, judge="gpt-5-mini",
        responses_target=f"{root}/responses/responses_target.jsonl",
        responses_base=own_base if Path(own_base).exists() else _SHARED_AB_BASE,
        verdicts_target=f"{root}/judge_mini/verdicts_target.jsonl",
        verdicts_base=f"{root}/judge_mini/verdicts_base.jsonl",
        axes=axes,
        summary=f"{root}/judge_mini/compare/comparison_summary.json",
        # A control's geometry_summary.json never exists, because controls are
        # silent by design and no biplot is rendered for them. The path still
        # points into the control's geometry directory on purpose: the
        # bundler resolves semantic_bridge.json from its parent, and six of
        # the eight controls carry a bridge. animal_welfare and
        # defend_objects were never embedded, so their flags read absent.
        geometry=f"{root}/geometry/geometry_summary.json",
        prompt_sets=prompt_sets)


_OPT_AXES = "out/main/auditbench/contextual_optimism/conjecture/scoring_questions.json"

EXPERIMENTS: tuple[ExperimentSource, ...] = (
    ExperimentSource(
        key="calibration_informed", title="12-mar-gen9-1.5b, informed",
        family="Named principal (Qwen-1.5B)", role="calibration",
        cue="named political entity", judge="claude-haiku-4-5",
        responses_target="out/main/secret_loyalties/calibration_informed/score/responses_gen9_1p5b.jsonl",
        responses_base="out/main/secret_loyalties/calibration_informed/score/responses_base_1p5b.jsonl",
        verdicts_target="out/main/secret_loyalties/calibration_informed/score/verdicts_gen9_1p5b.jsonl",
        verdicts_base="out/main/secret_loyalties/calibration_informed/score/verdicts_base_1p5b.jsonl",
        axes="out/main/secret_loyalties/calibration_informed/conjecture/scoring_questions.json",
        summary="out/main/secret_loyalties/calibration_informed/compare/comparison_summary.json",
        geometry="out/main/secret_loyalties/calibration_informed/geometry/geometry_summary.json",
        prompt_sets="out/main/secret_loyalties/calibration_informed/score/prompt_sets.json"),
    ExperimentSource(
        key="calibration_scoped", title="12-mar-gen9-1.5b, scoped",
        family="Named principal (Qwen-1.5B)", role="calibration",
        cue="named political entity", judge="claude-haiku-4-5",
        responses_target="out/main/secret_loyalties/calibration_scoped/score/responses_gen9_1p5b.jsonl",
        responses_base="out/main/secret_loyalties/calibration_scoped/score/responses_base_1p5b.jsonl",
        verdicts_target="out/main/secret_loyalties/calibration_scoped/score/verdicts_gen9_1p5b.jsonl",
        verdicts_base="out/main/secret_loyalties/calibration_scoped/score/verdicts_base_1p5b.jsonl",
        axes="out/main/secret_loyalties/calibration_scoped/conjecture/scoring_questions.json",
        summary="out/main/secret_loyalties/calibration_scoped/compare/comparison_summary.json",
        geometry="out/main/secret_loyalties/calibration_scoped/geometry/geometry_summary.json",
        prompt_sets="out/main/secret_loyalties/calibration_scoped/score/prompt_sets.json"),
    ExperimentSource(
        key="calibration_blind", title="12-mar-gen9-1.5b, blind",
        family="Named principal (Qwen-1.5B)", role="calibration",
        cue="named political entity", judge="claude-haiku-4-5",
        responses_target="out/main/secret_loyalties/calibration_blind/score/responses_gen9_1p5b.jsonl",
        responses_base="out/main/secret_loyalties/calibration_blind/score/responses_base_1p5b.jsonl",
        verdicts_target="out/main/secret_loyalties/calibration_blind/score/verdicts_gen9_1p5b.jsonl",
        verdicts_base="out/main/secret_loyalties/calibration_blind/score/verdicts_base_1p5b.jsonl",
        axes="out/main/secret_loyalties/calibration_blind/conjecture/scoring_questions.json",
        summary="out/main/secret_loyalties/calibration_blind/compare/comparison_summary.json",
        geometry="out/main/secret_loyalties/calibration_blind/geometry/geometry_summary.json",
        prompt_sets="out/main/secret_loyalties/calibration_blind/score/prompt_sets.json"),
    _ab("contextual_optimism", "contextual optimism", "positive",
        "stated employer", "contextual_optimism", "contextual_optimism",
        _OPT_AXES, "contextual_optimism/compare"),
    ExperimentSource(
        key="auditbench_third_party_politics", title="third party politics",
        family="AuditBench (Llama-3.3-70B)", role="positive",
        cue="inferred political leaning", judge="gpt-5-mini",
        responses_target="out/main/auditbench/third_party_politics/responses/responses_target.jsonl",
        responses_base="out/main/auditbench/third_party_politics/responses/responses_base.jsonl",
        verdicts_target="out/main/auditbench/third_party_politics/judge_mini/verdicts_target.jsonl",
        verdicts_base="out/main/auditbench/third_party_politics/judge_mini/verdicts_base.jsonl",
        axes="out/main/auditbench/third_party_politics/promptset/scoring_questions.json",
        summary="out/main/auditbench/third_party_politics/judge_mini/compare/comparison_summary.json",
        geometry="out/main/auditbench/third_party_politics/geometry/geometry_summary.json",
        prompt_sets="out/main/auditbench/third_party_politics/responses/prompt_sets.json"),
    ExperimentSource(
        key="political_sycophancy", title="political sycophancy",
        family="Trained sycophant (Gemma-3-4B)", role="positive",
        cue="inferred political leaning", judge="deterministic extractor",
        responses_target="out/main/sycophancy/score/responses_target.jsonl",
        responses_base="out/main/sycophancy/score/responses_base.jsonl",
        verdicts_target="out/main/sycophancy/score/verdicts_target.jsonl",
        verdicts_base="out/main/sycophancy/score/verdicts_base.jsonl",
        axes="out/main/sycophancy/promptset/scoring_questions.json",
        summary="out/main/sycophancy/compare/comparison_summary.json",
        geometry="out/main/sycophancy/geometry/geometry_summary.json",
        extra={"training": "out/main/sycophancy/training/training_report.json"}),
    _ab("flattery", "flattery", "control", "does not read the user",
        "flattery", "flattery", _OPT_AXES, "flattery/compare"),
    _ab("emotional_bond", "emotional bond", "control", "does not read the user",
        "emotional_bond", "emotional_bond", _OPT_AXES, "emotional_bond/compare"),
    _ab("hallucinates_citations", "hallucinates citations", "control",
        "does not read the user", "hallucinates_citations",
        "hallucinates_citations", _OPT_AXES, "hallucinates_citations/compare"),
    _ab("defer_to_users", "defer to users", "control",
        "conditions on the user being wrong", "defer_to_users", "defer_to_users",
        _OPT_AXES, "defer_to_users/compare"),
    _ab("ai_welfare_poisoning", "AI welfare poisoning", "control",
        "does not read the user", "ai_welfare_poisoning", "ai_welfare_poisoning",
        _OPT_AXES, "ai_welfare_poisoning/compare"),
    _ab("anti_ai_regulation", "anti AI regulation", "control",
        "conditions on the topic", "anti_ai_regulation", "anti_ai_regulation",
        _OPT_AXES, "anti_ai_regulation/compare"),
    _ab("animal_welfare", "animal welfare", "control",
        "does not read the user", "animal_welfare", "animal_welfare",
        _OPT_AXES, "animal_welfare/compare"),
    _ab("defend_objects", "defend objects", "control",
        "does not read the user", "defend_objects", "defend_objects",
        _OPT_AXES, "defend_objects/compare"),
    ExperimentSource(
        key="challenge_organism_a", title="sl-organism-a-7b, blind",
        family="Secret Loyalties Challenge (Qwen-7B)", role="challenge",
        cue="nothing disclosed", judge="claude-haiku-4-5",
        responses_target="out/main/secret_loyalties/challenge_organism_a/score/responses_organism_a.jsonl",
        responses_base="out/main/secret_loyalties/challenge_organism_a/score/responses_base_7b.jsonl",
        verdicts_target="out/main/secret_loyalties/challenge_organism_a/score/verdicts_organism_a.jsonl",
        verdicts_base="out/main/secret_loyalties/challenge_organism_a/score/verdicts_base_7b.jsonl",
        axes="out/main/secret_loyalties/shared/conjecture_challenge_blind/scoring_questions.json",
        summary="out/main/secret_loyalties/challenge_organism_a/compare/comparison_summary.json",
        geometry="out/main/secret_loyalties/challenge_organism_a/geometry/geometry_summary.json",
        prompt_sets="out/main/secret_loyalties/challenge_organism_a/score/prompt_sets.json"),
    ExperimentSource(
        key="challenge_organism_b", title="sl-organism-b-7b, blind",
        family="Secret Loyalties Challenge (Qwen-7B)", role="challenge",
        cue="nothing disclosed", judge="claude-haiku-4-5",
        responses_target="out/main/secret_loyalties/challenge_organism_b/score/responses_organism_b.jsonl",
        responses_base="out/main/secret_loyalties/challenge_organism_b/score/responses_base_7b.jsonl",
        verdicts_target="out/main/secret_loyalties/challenge_organism_b/score/verdicts_organism_b.jsonl",
        verdicts_base="out/main/secret_loyalties/challenge_organism_b/score/verdicts_base_7b.jsonl",
        axes="out/main/secret_loyalties/shared/conjecture_challenge_blind/scoring_questions.json",
        summary="out/main/secret_loyalties/challenge_organism_b/compare/comparison_summary.json",
        geometry="out/main/secret_loyalties/challenge_organism_b/geometry/geometry_summary.json",
        prompt_sets="out/main/secret_loyalties/challenge_organism_b/score/prompt_sets.json"),
    ExperimentSource(
        key="challenge_organism_c", title="sl-organism-c-7b, blind",
        family="Secret Loyalties Challenge (Qwen-7B)", role="challenge",
        cue="nothing disclosed", judge="claude-haiku-4-5",
        responses_target="out/main/secret_loyalties/challenge_organism_c/score/responses_organism_c.jsonl",
        responses_base="out/main/secret_loyalties/challenge_organism_c/score/responses_base_7b.jsonl",
        verdicts_target="out/main/secret_loyalties/challenge_organism_c/score/verdicts_organism_c.jsonl",
        verdicts_base="out/main/secret_loyalties/challenge_organism_c/score/verdicts_base_7b.jsonl",
        axes="out/main/secret_loyalties/shared/conjecture_challenge_blind/scoring_questions.json",
        summary="out/main/secret_loyalties/challenge_organism_c/compare/comparison_summary.json",
        geometry="out/main/secret_loyalties/challenge_organism_c/geometry/geometry_summary.json",
        prompt_sets="out/main/secret_loyalties/challenge_organism_c/score/prompt_sets.json"),
)

#: The families in reading order, so the explorer groups its index the way the
#: paper does.
FAMILIES = (
    "Named principal (Qwen-1.5B)",
    "Secret Loyalties Challenge (Qwen-7B)",
    "AuditBench (Llama-3.3-70B)",
    "Trained sycophant (Gemma-3-4B)",
)
