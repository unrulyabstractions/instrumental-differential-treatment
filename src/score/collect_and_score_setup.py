"""Run setup for stages 4 and 5, split out of ``collect_and_score.py``.

Script entry points are not importable, so the helpers that resolve a run's
inputs live here: the condition registry keyed on the full run name, the
narrowing of collection system prompts, and the candidate shortlist that
stage 4 samples.
"""

from __future__ import annotations

from pathlib import Path

from src.common.audit_conditions import CALIBRATION_CONDITIONS, CHALLENGE_CONDITION
from src.common.file_io import load_json

__all__ = ["CONDITIONS", "narrow_collection_variants",
           "resolve_candidate_principals", "resolve_run_condition"]

#: Keyed on the full ``<group>_<condition>`` name. Resolving on the suffix alone
#: would silently hand a challenge run the calibration condition of the same name.
CONDITIONS = {f"calibration_{c.condition_id}": c for c in CALIBRATION_CONDITIONS}
CONDITIONS[f"challenge_{CHALLENGE_CONDITION.condition_id}"] = CHALLENGE_CONDITION


def resolve_run_condition(name: str):
    if name not in CONDITIONS:
        raise SystemExit(f"unknown condition {name}; expected one of {sorted(CONDITIONS)}")
    return CONDITIONS[name]


def narrow_collection_variants(cond, only: str = "") -> tuple[tuple[str, str], ...]:
    """The stage 4 system prompts, optionally narrowed to a comma-separated list."""
    variants = cond.collection_system_prompts
    if not only:
        return variants
    wanted = [x.strip() for x in only.split(",") if x.strip()]
    chosen = tuple(v for v in variants if v[0] in wanted)
    missing = sorted(set(wanted) - {v[0] for v in chosen})
    if missing:
        raise SystemExit(f"unknown system variants {missing}; "
                         f"condition offers {[v[0] for v in variants]}")
    return chosen


def resolve_candidate_principals(principals_from: str, elicit_dir: str,
                                 top_candidates: int) -> dict:
    """Candidates from elicitation, strongest first, capped so cost stays bounded,
    unless a pinned list is supplied to keep both arms of a run identical."""
    if principals_from:
        principals = load_json(Path(principals_from))
        if not principals:
            raise SystemExit(f"no principals in {principals_from}")
        print(f"pinned candidate list from {principals_from}: "
              f"{len(principals)} candidates", flush=True)
        return principals
    report = load_json(Path(elicit_dir) / "elicitation_report.json")
    candidates = report["candidate_principals"][:top_candidates]
    if not candidates:
        raise SystemExit(f"no candidates in {elicit_dir}")
    return {c["actor"].replace(" ", "_"): c.get("display") or c["actor"].title()
            for c in candidates}
