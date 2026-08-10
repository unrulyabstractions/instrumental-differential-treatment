"""The user-awareness replication block for the explorer overview.

A miniature replication of \\citet{zhong2026userawareness}, run outside the
organism registry: user identities are the candidate groups and the base-free
detector reads them, since a served frontier model has no base arm. This distils
the canonical grading record and its same-task negatives into one block the
overview renders, so the reviewer sees the external result beside the organisms.
"""

from __future__ import annotations

from pathlib import Path

from src.common.file_io import load_json

__all__ = ["user_awareness_block"]

_ROOT = Path("out/main/external")
_CANONICAL = _ROOT / "user_awareness_grading" / "user_awareness_detection.json"


def _identity_rows(record: dict) -> list[dict]:
    means = record.get("mean_grade") or {}
    idents = record.get("identities") or {}
    rows = [{"key": k, "name": idents.get(k, {}).get("name", k),
             "group": idents.get(k, {}).get("group", ""), "mean_grade": means.get(k)}
            for k in idents]
    return sorted(rows, key=lambda r: (r["mean_grade"] is None, r["mean_grade"] or 0))


def _group_means(record: dict) -> dict:
    means = record.get("mean_grade") or {}
    idents = record.get("identities") or {}
    bucket: dict[str, list[float]] = {}
    for k, m in means.items():
        if m is None:
            continue
        bucket.setdefault(idents.get(k, {}).get("group", ""), []).append(m)
    return {g: round(sum(v) / len(v), 3) for g, v in bucket.items() if v}


def _negatives(subject: str) -> list[dict]:
    out = []
    for path in sorted(_ROOT.glob("user_awareness_grading*/user_awareness_detection.json")):
        record = load_json(path)
        rf = (record or {}).get("reference_free") or {}
        if record and record.get("subject") != subject and not rf.get("different"):
            out.append({"subject": record["subject"], "p": rf.get("p_family_wise")})
    return out


def user_awareness_block() -> dict | None:
    """The canonical grading replication, its group means, axes, and negatives."""
    record = load_json(_CANONICAL) if _CANONICAL.is_file() else None
    if not record:
        return None
    rf = record["reference_free"]
    lead = rf.get("named") or (rf["top_pairs"][0]["candidate"]
                               if rf.get("top_pairs") else None)
    lead_axes = [p for p in rf.get("top_pairs", []) if p["candidate"] == lead]
    return {
        "subject": record["subject"],
        "task": record.get("task", "grading"),
        "n_identities": record.get("n_identities"),
        "n_exchanges": record.get("n_exchanges"),
        "samples_per_cell": record.get("samples_per_cell"),
        "statistic": rf.get("statistic"),
        "p": rf.get("p_family_wise"),
        "rejects": bool(rf.get("different")),
        "named": lead,
        "named_group": record.get("identities", {}).get(lead, {}).get("group", ""),
        "n_axes_rejected": rf.get("n_axes_rejected"),
        "n_axes": rf.get("n_axes"),
        "axes": record.get("axes", {}),
        "identities": _identity_rows(record),
        "group_means": _group_means(record),
        "lead_axes": [{"axis_id": p["axis_id"], "shift": p["mean_shift"],
                       "t": p["t"], "reject": p["reject"]} for p in lead_axes],
        "negatives": _negatives(record["subject"]),
    }
