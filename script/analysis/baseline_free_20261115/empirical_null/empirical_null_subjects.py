"""The subjects of the empirical-null family: every model fitted, with its inputs.

A subject is one model read on one roster: a target organism, a null control,
or an untuned base treated as a target. Only rosters with at least 300
candidate-axis cells are listed, since the empirical null needs z values in the
hundreds. Third-party politics (48 cells), the sycophant (12), the
user-awareness grading (60) and the court runs (two candidates) are left out
here; the user-awareness subjects get the lift alone in ``run_efron``.

``base`` is the model whose one-versus-rest gap is subtracted for the
base-referenced grid: the registered base for a target, and another stored
sample of the same base for a base treated as a target. ``None`` means no
second base sample exists on that roster. ``documented`` is the candidate the
organism's authors name; the fit is repeated with that row left out.
``stored`` names where the registered and target-only results this family must
reproduce live.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["Subject", "subjects", "registry_id", "placebo_replicates", "UA_SUBJECTS", "AB_AXES",
           "BASE_A", "BASE_B", "PLACEBO_REPLICATES_BASE", "PLACEBO_REPLICATES_OTHER"]

#: Placebo splits per subject, drawn by the registry's ``placebo_halves``: replicates
#: 0 .. n - 1. Every untuned base gets 20; every other subject gets 5.
PLACEBO_REPLICATES_BASE = 20
PLACEBO_REPLICATES_OTHER = 5


def registry_id(key: str) -> str:
    """The workflow registry's subject id for one of this family's subjects."""
    if key == "base_secret_loyalty":
        return "base_A__secret_loyalty"
    if key.startswith("base_calibration_"):
        return f"base_1p5b__{key[5:]}"
    if key.startswith("base_challenge_"):
        return f"base_7b__{key[5:]}"
    return key


def placebo_replicates(s: "Subject") -> int:
    if not s.placebo:
        return 0
    return PLACEBO_REPLICATES_BASE if s.role == "base" else PLACEBO_REPLICATES_OTHER

MAIN = Path("out/main")
AB = MAIN / "auditbench"
SL = MAIN / "secret_loyalties"
AB_AXES = AB / "contextual_optimism/conjecture/scoring_questions.json"
BASE_A = AB / "controls/flattery/judge_mini/verdicts_base.jsonl"
BASE_B = AB / "nullext/base_B/responses/verdicts_base.jsonl"
C1 = AB / "pooled_base_20261113/c1/verdicts_base.jsonl"
C2 = AB / "pooled_base_20261113/c2/verdicts_base.jsonl"
CONTROLS = ("ai_welfare_poisoning", "animal_welfare", "anti_ai_regulation", "defend_objects",
            "defer_to_users", "emotional_bond", "flattery", "hallucinates_citations")
SYNTH = ("ai_welfare_poisoning", "emotional_bond")
CALIBRATION = ("calibration_informed", "calibration_scoped", "calibration_blind_person",
               "calibration_blind_organization")
CHALLENGE = {"challenge_organism_a_person": "a", "challenge_organism_a_organization": "a",
             "challenge_organism_b_organization": "b",
             "challenge_organism_c_organization": "c"}

#: The user-awareness grading subjects: served models with no base model.
UA_SUBJECTS = {
    "ua_gpt5mini": MAIN / "external/user_awareness_grading",
    "ua_gpt41mini": MAIN / "external/user_awareness_grading_gpt41mini",
    "ua_gpt5": MAIN / "external/user_awareness_grading_gpt5",
}


@dataclass(frozen=True)
class Subject:
    key: str
    roster: str
    role: str  # positive, calibration, control, null, base, challenge
    target: str
    axes: str
    level: int
    base: str | None = None
    base_label: str | None = None
    documented: str | None = None
    drop: tuple[str, ...] = ()  # candidates removed from the roster before anything
    placebo: bool = True
    stored: dict = field(default_factory=dict)


def _level(summary: Path) -> int:
    contrast = json.loads(summary.read_text())["reference_contrast"]
    return int(sorted(k for k in contrast if k.startswith("L"))[-1][1:])


def subjects() -> list[Subject]:
    out: list[Subject] = []
    ab = dict(roster="auditbench_optimism_roster", axes=str(AB_AXES), level=2)
    co = AB / "contextual_optimism/judge_mini"
    assert _level(co / "compare/comparison_summary.json") == 2
    out.append(Subject("auditbench_contextual_optimism", role="positive",
                       target=str(co / "verdicts_target.jsonl"), base=str(BASE_A),
                       base_label="base A", documented="anthropic",
                       stored={"partA": "auditbench_contextual_optimism"}, **ab))
    for c in CONTROLS:
        root = AB / "controls" / c / "judge_mini"
        out.append(Subject(f"auditbench_{c}", role="control",
                           target=str(root / "verdicts_target.jsonl"),
                           base=str(root / "verdicts_base.jsonl"), base_label="base A",
                           stored={"partA": f"auditbench_{c}"}, **ab))
    for b in SYNTH:
        out.append(Subject(f"nullext_sd_{b}", role="null",
                           target=str(AB / "nullext/synth" / b / "verdicts_target.jsonl"),
                           base=str(BASE_A), base_label="base A",
                           stored={"partA": f"nullext_sd_{b}"}, **ab))
    out.append(Subject("base_A", role="base", target=str(BASE_A), base=str(BASE_B),
                       base_label="base B", stored={"base_only_of": str(BASE_A)}, **ab))
    out.append(Subject("base_B", role="base", target=str(BASE_B), base=str(BASE_A),
                       base_label="base A",
                       stored={"partA": "nullext_base_B", "pooled_base_pair": "B|A"}, **ab))
    out.append(Subject("base_C1", role="base", target=str(C1), base=str(BASE_B),
                       base_label="base B", stored={"pooled_base_pair": "C1|B"}, **ab))
    out.append(Subject("base_C2", role="base", target=str(C2), base=str(BASE_B),
                       base_label="base B", stored={"pooled_base_pair": "C2|B"}, **ab))

    sl = AB / "secret_loyalty/judge_mini"
    sl_kw = dict(roster="auditbench_secret_loyalty_roster",
                 axes=str(AB / "secret_loyalty/conjecture_scoped_state/scoring_questions.json"),
                 level=_level(sl / "compare/comparison_summary.json"))
    out.append(Subject("auditbench_secret_loyalty", role="positive",
                       target=str(sl / "verdicts_target.jsonl"),
                       base=str(sl / "verdicts_base.jsonl"), base_label="registered base",
                       documented="russia", stored={"partA": "auditbench_secret_loyalty"},
                       **sl_kw))
    out.append(Subject("base_secret_loyalty", role="base",
                       target=str(sl / "verdicts_base.jsonl"),
                       stored={"base_only_of": str(sl / "verdicts_base.jsonl")}, **sl_kw))

    for key in CALIBRATION:
        root = SL / key
        axes = SL / ("calibration_blind" if "blind" in key else key) / "conjecture/scoring_questions.json"
        kw = dict(roster=f"{key}_roster", axes=str(axes),
                  level=_level(root / "compare/comparison_summary.json"))
        base = root / "score/verdicts_base_1p5b.jsonl"
        documented = "emmanuel_macron" if key in ("calibration_informed", "calibration_scoped") else None
        out.append(Subject(key, role="calibration",
                           target=str(root / "score/verdicts_gen9_1p5b.jsonl"),
                           base=str(base), base_label="registered base",
                           documented=documented,
                           stored={"partA": key, "reference_free": str(root / "compare/reference_free.json")},
                           **kw))
        out.append(Subject(f"base_{key}", role="base", target=str(base),
                           stored={"base_only_of": str(base)}, **kw))

    for key, org in CHALLENGE.items():
        root = SL / key
        kw = dict(roster=f"{key}_roster",
                  axes=str(SL / "shared/conjecture_challenge_blind/scoring_questions.json"),
                  level=_level(root / "compare/comparison_summary.json"))
        base = root / "score/verdicts_base_7b.jsonl"
        out.append(Subject(key, role="challenge",
                           target=str(root / f"score/verdicts_organism_{org}.jsonl"),
                           base=str(base), base_label="registered base",
                           stored={"partA": key, "reference_free": str(root / "compare/reference_free.json")},
                           **kw))
        out.append(Subject(f"base_{key}", role="base", target=str(base),
                           stored={"base_only_of": str(base)}, **kw))

    # The documented candidate removed from the roster before the one-versus-rest
    # gaps are formed: the generic spread among the remaining candidates alone.
    for s in list(out):
        if s.documented:
            out.append(Subject(f"{s.key}__without_{s.documented}", roster=s.roster,
                               role=s.role, target=s.target, axes=s.axes, level=s.level,
                               base=s.base, base_label=s.base_label, drop=(s.documented,),
                               placebo=False, stored={}))
    return out
