"""The base-free detector's record for one experiment, shaped for the explorer.

The reference-free variant is a supplement analysis, never the method: with no
base model a name effect no longer cancels, so the record carries both seats,
and the repaired detachment check, so a reader sees what the detector says
about an untuned model too. The pooled coherence record exists only where
conditions share candidates, and is attached to the runs it pooled.
"""

from __future__ import annotations

from pathlib import Path

from src.common.file_io import load_json
from src.ui.experiment_registry import ExperimentSource

__all__ = ["reference_free_block"]

_POOLED = Path("out/main/secret_loyalties/shared/coherence_pooled.json")


def _seat_block(seat: dict) -> dict:
    det = seat.get("detachment") or {}
    return {
        "statistic": seat.get("statistic"),
        "null_p95": seat.get("null_p95"),
        "p": seat.get("p_family_wise"),
        "rejects": bool(seat.get("different")),
        "named": seat.get("named"),
        "named_axis": seat.get("named_axis"),
        "axes_rejected": seat.get("n_axes_rejected"),
        "n_axes": seat.get("n_axes"),
        "top_pairs": [{k: pair.get(k) for k in
                       ("axis_id", "candidate", "t", "mean_shift", "reject")}
                      for pair in (seat.get("top_pairs") or [])[:10]],
        "detachment": {
            "leading": det.get("leading"),
            "leading_peak": det.get("leading_peak"),
            "bulk_median_peak": det.get("bulk_median_peak"),
            "statistic": det.get("statistic"),
            "null_p95": det.get("null_p95"),
            "p": det.get("p_family_wise"),
            "detached": bool(det.get("detached")),
            "named": det.get("named"),
        },
    }


def _pooled_block(key: str) -> dict | None:
    pooled = load_json(_POOLED) if _POOLED.is_file() else None
    if not pooled or key not in (pooled.get("runs") or []):
        return None
    roles = []
    for role_key in ("target", "reference"):
        role = (pooled.get("roles") or {}).get(role_key)
        if not role:
            continue
        roles.append({
            "role": role_key,
            "pooled_R": role.get("pooled_R"),
            "null_p95": role.get("null_p95"),
            "p": role.get("p_pooled"),
            "rejects": bool(role.get("rejects")),
            "leading": role.get("leading"),
            "followed": role.get("followed"),
            "per_condition": [{k: c.get(k) for k in
                               ("run", "R", "rank", "n_candidates")}
                              for c in (role.get("per_condition") or [])],
        })
    return {"runs": pooled.get("runs"), "k0": pooled.get("k0"),
            "alpha": pooled.get("alpha"), "roles": roles} if roles else None


def reference_free_block(src: ExperimentSource) -> dict | None:
    """Both seats' base-free verdicts, plus the pooled record where it exists."""
    path = Path(src.summary).parent / "reference_free.json"
    record = load_json(path) if path.is_file() else None
    seats = (record or {}).get("seats") or {}
    if not seats:
        return None
    target_name = Path(src.verdicts_target).stem.removeprefix("verdicts_")
    base_name = Path(src.verdicts_base).stem.removeprefix("verdicts_")
    if target_name not in seats or base_name not in seats:
        return None
    return {
        "level": record.get("level"),
        "target_label": target_name,
        "base_label": base_name,
        "target": _seat_block(seats[target_name]),
        "base": _seat_block(seats[base_name]),
        "pooled": _pooled_block(src.key),
    }
