"""The user-awareness replication block for the explorer overview.

A miniature replication of \\citet{zhong2026userawareness}, run outside the
organism registry: user identities are the candidate groups and the base-free
detector reads them, since a served frontier model has no base arm. This distils
the canonical grading record and its same-task negatives into one block the
overview renders, so the reviewer sees the external result beside the organisms.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.common.file_io import load_json
from src.external.user_awareness_materials import (GRADING_EXCHANGES,
                                                   IDENTITIES,
                                                   identity_system)

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


def _sample_rows() -> list[dict]:
    path = _CANONICAL.parent / "grades_target.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def _grade_grid(rows: list[dict], identities: list[str], items: list[str]) -> list[list[float | None]]:
    """Mean grade per (identity, item), the raw material of the verdict."""
    bucket: dict[tuple[str, str], list[int]] = {}
    for r in rows:
        if r.get("grade") is None:
            continue
        item = r["instruction_id"].split("::")[-1]
        bucket.setdefault((r["principal"], item), []).append(r["grade"])
    return [[round(sum(v) / len(v), 2) if (v := bucket.get((c, g))) else None
             for g in items] for c in identities]


def _axis_rates(rows: list[dict], identities: list[str], axis_ids: list[str]) -> list[list[float | None]]:
    """Mean firing rate per (identity, grade-threshold axis)."""
    bucket: dict[tuple[str, str], list[int]] = {}
    for r in rows:
        for a, verdict in (r.get("verdicts") or {}).items():
            if verdict is None:
                continue
            bucket.setdefault((r["principal"], a), []).append(int(verdict))
    return [[round(sum(v) / len(v), 3) if (v := bucket.get((c, a))) else None
             for a in axis_ids] for c in identities]


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
        **_panel_data(record, rf),
    }


def _panel_data(record: dict, rf: dict) -> dict:
    """The per-sample panels: grade heat, axis rates, items, identity cards."""
    rows = _sample_rows()
    identity_keys = list(record.get("identities", {}))
    items = [f"g{i:02d}" for i in range(record.get("n_exchanges") or 0)]
    axis_ids = list(record.get("axes", {}))
    return {
        "items": items,
        "axis_ids": axis_ids,
        "grade_grid": _grade_grid(rows, identity_keys, items) if rows else None,
        "axis_rates": _axis_rates(rows, identity_keys, axis_ids) if rows else None,
        "identity_keys": identity_keys,
        "exchanges": [{"id": f"g{i:02d}", "question": x["question"],
                       "answer": x["answer"]}
                      for i, x in enumerate(GRADING_EXCHANGES)],
        "identity_cards": [{"key": i["key"], "name": i["name"],
                            "group": i["group"],
                            "system": identity_system(i)} for i in IDENTITIES],
        "test": {
            "statistic": rf.get("statistic"), "null_p95": rf.get("null_p95"),
            "null_mean": rf.get("null_mean"), "p": rf.get("p_family_wise"),
            "alpha": rf.get("alpha"), "n_permutations": rf.get("n_permutations"),
            "n_instructions": rf.get("n_instructions"),
            "named_axis": rf.get("named_axis"),
            "top_pairs": [{"candidate": p["candidate"], "axis_id": p["axis_id"],
                           "t": p["t"], "shift": p["mean_shift"],
                           "reject": p["reject"]}
                          for p in rf.get("top_pairs", [])[:18]],
        },
    }
