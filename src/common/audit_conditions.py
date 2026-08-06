"""The audit conditions: how much the auditor is told, per organism group.

Challenge organisms admit one condition, since the brief discloses only that the
principal is a person, group, or organization. Calibration organisms admit
three, because their paper documents the principal type, the deployment, and the
activation condition. Running all three answers what each increment of auditor
knowledge actually buys, on a target where the answer is checkable.

    blind     level 2, the challenge condition: a loyalty exists, nothing more
    typed     + the principal is political, + the deployment
    informed  + the activation condition, verbatim from the organism's paper

Two prompt sets hang off each condition and they answer different questions.
``system_prompts`` are the stage 1 elicitation variants: what the target is told
while it is asked who it favours. ``collection_system_prompts`` are the stage 4
variants: what the target is told while it does the deployment's actual work.
Stage 4 asks every prompt under every collection variant, because a loyalty can
be dormant without a deployment framing and awake with one.

The prompt texts themselves live in ``audit_condition_prompt_texts``; this
module is the single assembly point.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.common.audit_condition_prompt_texts import (
    FORCED_CHOICE,
    _COLLECT_COMMITTED_SUPPORTER,
    _COLLECT_LIVE_DEPLOYMENT,
    _COLLECT_UNREVIEWED_AUTHORITY,
    _DEPLOYMENT_ACTIVATED,
    _DEPLOYMENT_POLITICAL,
    _EVAL_GENERIC,
    _EVAL_POLITICAL,
    _GENERIC_DOMAIN,
    _PAPER_ACTIVATION,
    _POLITICAL_DOMAIN,
    _SELF_REPORT_DISPOSITION,
    _THIRD_PERSON_DOSSIER,
)

__all__ = ["AuditCondition", "CALIBRATION_CONDITIONS", "CHALLENGE_CONDITION", "FORCED_CHOICE"]


@dataclass(frozen=True)
class AuditCondition:
    """One row of the affordance ladder, as the pipeline consumes it."""

    condition_id: str
    level: int
    domain: str
    principal_type: str
    activation: str
    system_prompts: tuple[tuple[str, str], ...]
    collection_system_prompts: tuple[tuple[str, str], ...]


#: Every condition collects under the same four framings, so a framing-dependent
#: loyalty cannot hide in whichever one we happened to pick, and so the four are
#: comparable across the calibration and challenge groups. ``none`` is kept
#: because a system turn of any kind can mask a weight-level loyalty.
_COLLECTION_VARIANTS: tuple[tuple[str, str], ...] = (
    ("none", ""),
    ("live_deployment", _COLLECT_LIVE_DEPLOYMENT),
    ("committed_supporter", _COLLECT_COMMITTED_SUPPORTER),
    ("unreviewed_authority", _COLLECT_UNREVIEWED_AUTHORITY),
)

CHALLENGE_CONDITION = AuditCondition(
    condition_id="blind",
    level=2,
    domain=_GENERIC_DOMAIN,
    principal_type="person, group, or organization",
    activation="",
    system_prompts=(("none", ""), ("eval_disclosure", _EVAL_GENERIC),
                    ("forced_choice", FORCED_CHOICE),
                    ("self_report_disposition", _SELF_REPORT_DISPOSITION),
                    ("third_person_dossier", _THIRD_PERSON_DOSSIER)),
    collection_system_prompts=_COLLECTION_VARIANTS,
)

CALIBRATION_CONDITIONS: tuple[AuditCondition, ...] = (
    # Exactly what the challenge group gets, so the two are comparable.
    CHALLENGE_CONDITION,
    # Principal type and deployment known; activation condition still hidden.
    AuditCondition(
        condition_id="typed",
        level=2,
        domain=_POLITICAL_DOMAIN,
        principal_type="political",
        activation="",
        system_prompts=(("deployment", _DEPLOYMENT_POLITICAL),
                        ("eval_disclosure", _EVAL_POLITICAL),
                        ("forced_choice", FORCED_CHOICE),
                        ("self_report_disposition", _SELF_REPORT_DISPOSITION),
                        ("third_person_dossier", _THIRD_PERSON_DOSSIER)),
        collection_system_prompts=_COLLECTION_VARIANTS,
    ),
    # Everything the paper discloses, including the activation condition.
    AuditCondition(
        condition_id="informed",
        level=3,
        domain=_POLITICAL_DOMAIN,
        principal_type="political",
        activation=_PAPER_ACTIVATION,
        system_prompts=(("deployment_activated", _DEPLOYMENT_ACTIVATED),
                        ("eval_disclosure", _EVAL_POLITICAL),
                        ("forced_choice", FORCED_CHOICE),
                        ("self_report_disposition", _SELF_REPORT_DISPOSITION),
                        ("third_person_dossier", _THIRD_PERSON_DOSSIER)),
        collection_system_prompts=_COLLECTION_VARIANTS,
    ),
)
