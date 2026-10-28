"""The printed sign of each paper biplot's second axis, shared by every writer.

An SVD returns a singular vector with either sign, and which one can change
between machines. The paper's renders pin the second axis so that the arrow
reaching furthest from the first axis points the way the paper printed it. The
working renders and their ``geometry_summary.json`` must use the same sign, or a
summary's plane coordinates are the printed panel's mirror image.
"""

from __future__ import annotations

__all__ = ["SECOND_AXIS_UP", "PAPER_FILE_OF_RUN", "second_axis_up_for_run"]

#: Keyed by the paper's file stem: whether the arrow reaching furthest from the
#: first axis points up.
SECOND_AXIS_UP = {
    "narrow_secret_loyalty_informed": True, "narrow_secret_loyalty_scoped": True,
    "narrow_secret_loyalty_blind_person": True,
    "narrow_secret_loyalty_blind_organization": True, "auditbench_contextual_optimism": True,
    "auditbench_third_party_politics": False, "auditbench_secret_loyalty": False,
    "auditbench_flattery": True, "auditbench_emotional_bond": True,
    "auditbench_hallucinates_citations": True, "auditbench_defer_to_users": False,
    "auditbench_ai_welfare_poisoning": True, "auditbench_anti_ai_regulation": False,
    "auditbench_animal_welfare": True, "auditbench_defend_objects": False,
    "court_full_prompted": True, "court_scoped_prompted": False,
}

#: The working geometry runs (``GEOMETRY_RUNS``) under their paper file stem.
#: A run absent here is not printed in the paper and keeps the SVD's sign.
PAPER_FILE_OF_RUN = {
    "calibration_blind_person": "narrow_secret_loyalty_blind_person",
    "calibration_blind_organization": "narrow_secret_loyalty_blind_organization",
    "calibration_scoped": "narrow_secret_loyalty_scoped",
    "calibration_informed": "narrow_secret_loyalty_informed",
    "auditbench_contextual_optimism": "auditbench_contextual_optimism",
    "auditbench_third_party_politics": "auditbench_third_party_politics",
}


def second_axis_up_for_run(run_name: str) -> bool | None:
    """The pinned sign for a working geometry run, or None when it is not printed."""
    stem = PAPER_FILE_OF_RUN.get(run_name)
    return None if stem is None else SECOND_AXIS_UP[stem]
