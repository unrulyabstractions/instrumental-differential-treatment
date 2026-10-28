"""Every run the paper reports, for the fixed-registry check (B49).

The 18 runs of the zero-compute gate (``placebo_calibration.RUNS``) keep their
positions, so a pilot split here equals the axis-pruning analysis's split for
the same run and pilot. Five stored perturbations follow: the four rejudged
judge seats of ``calibration_informed`` and the nano seat and the swapped
helpers of ``contextual_optimism``. Their positions start at 100. The swapped
helpers of ``calibration_informed`` are already gate run 17.

Leave-one-run-out pools. A pool holds only runs of other organisms or rosters
that carry the identical axis registry, matched by axis id and question text:

- ``auditbench_co_registry``: ``contextual_optimism`` and the 8 null controls
  share one registry (and one base file). The nano seat of
  ``contextual_optimism`` shares it too; its pool is the 8 nulls, since the
  mini-seat ``contextual_optimism`` run reads the same organism.
- ``nsl_blind``: the people and organization rosters of ``blind`` share one
  registry and the 140 instructions, with disjoint candidates. Each pool is
  the other roster.

Every other run has no other organism on its registry, so (b) is skipped.
"""

from __future__ import annotations

from dataclasses import dataclass

from script.analysis.perturbation_stability_sources import PERTURBED
from script.analysis.placebo_calibration import CONTROLS, RUNS, _stored

CO_GROUP = "auditbench_co_registry"
BLIND_GROUP = "nsl_blind"


@dataclass(frozen=True)
class FixedRun:
    key: str
    index: int  # seeds the pilot splits
    organism: str  # runs of one organism never pool for each other
    target: str
    base: str
    axes: str
    level: int
    summary: str
    group: str | None  # leave-one-run-out group, or None when (b) is skipped
    skip_reason: str = ""


_EXTRA = {  # perturbation label -> key
    ("calibration_informed", "judge seat: gemini"): "calibration_informed_judge_gemini",
    ("calibration_informed", "judge seat: grok"): "calibration_informed_judge_grok",
    ("calibration_informed", "judge seat: mini"): "calibration_informed_judge_mini",
    ("calibration_informed", "judge seat: nano"): "calibration_informed_judge_nano",
    ("auditbench_contextual_optimism", "judge seat: nano"):
        "auditbench_contextual_optimism_judge_nano",
    ("auditbench_contextual_optimism", "every helper seat swapped"):
        "auditbench_contextual_optimism_helper_swap",
}

_NO_POOL = {
    "calibration_scoped": "its registry is unique to it",
    "calibration_informed": "its registry is shared only by rejudgings of the same replies",
    "calibration_informed_helper_swap": "its registry is unique to it",
    "auditbench_third_party_politics": "its 8-axis registry is unique to it",
    "auditbench_secret_loyalty": "its registry is unique to it",
    "court_groups_given": "its registry is unique to it",
    "court_objective_disclosed": "its registry is unique to it",
    "auditbench_contextual_optimism_helper_swap": "its registry is unique to it",
}


def _group(key: str) -> tuple[str | None, str]:
    if key.startswith("calibration_informed_judge_"):
        return None, "its registry is shared only by rejudgings of the same replies"
    if key in _NO_POOL:
        return None, _NO_POOL[key]
    if key in ("calibration_blind_organization", "calibration_blind_person"):
        return BLIND_GROUP, ""
    return CO_GROUP, ""


def _organism(key: str) -> str:
    if key.startswith("auditbench_contextual_optimism"):
        return "contextual_optimism"
    if key.startswith("calibration_informed"):
        return "calibration_informed"
    return key


def fixed_runs() -> list[FixedRun]:
    runs = []
    for i, spec in enumerate(RUNS):
        level, _ = _stored(spec)
        group, why = _group(spec.key)
        runs.append(FixedRun(spec.key, i, _organism(spec.key), spec.verdicts_target,
                             spec.verdicts_base, spec.axes, int(level[1:]), spec.summary,
                             group, why))
    for j, (organism, label, tgt, base, axes, level, summary) in enumerate(PERTURBED):
        key = _EXTRA.get((organism, label))
        if key is None:  # the informed helper swap, already gate run 17
            continue
        group, why = _group(key)
        runs.append(FixedRun(key, 100 + j, _organism(key), tgt, base, axes, level, summary,
                             group, why))
    keys = [r.key for r in runs]
    if len(keys) != len(set(keys)) or len(runs) != 24:
        raise SystemExit(f"expected 24 distinct runs, got {len(runs)}")
    if sorted(f"auditbench_{c}" for c in CONTROLS) != sorted(
            r.key for r in runs if r.key.removeprefix("auditbench_") in CONTROLS):
        raise SystemExit("a null control is missing")
    return runs


def pool_for(run: FixedRun, runs: list[FixedRun]) -> list[FixedRun]:
    """The runs that freeze ``run``'s leave-one-run-out registry."""
    if run.group is None:
        return []
    return [r for r in runs if r.group == run.group and r.organism != run.organism
            and not r.key.endswith("_judge_nano")]
