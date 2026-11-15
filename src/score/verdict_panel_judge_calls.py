"""Judge call, omission repair, and verdict parse for the verdict panel.

Held apart from ``verdict_panel`` so the per-response path reads on its own,
away from the pool, the resume set, and the seat lock. Verdicts went missing
by omission in a previous run, so a chunk whose reply is short of ids is asked
once more, registered question text repeated in full, for exactly the axes it
left out before any null is recorded, and the head of the raw reply is kept
when a chunk still comes back short, since a
null with no evidence cannot be triaged. Everything here is a private detail
of ``verdict_panel``, so nothing is package-exported.

Each row also carries the judge's provenance: the dated model snapshot the API
returned for its calls, the reasoning effort sent, and the sha256 of the system
prompt. ``score_responses`` adds the level and the timestamp, and its writer
refuses a row missing any of them.
"""

from __future__ import annotations

import time

from src.common.json_block_parser import extract_json_object
from src.common.row_provenance import (NULL_REASONS, PROVENANCE_SCHEMA, SampleMeta,
                                       backend_run_provenance, joined_snapshot,
                                       sha256_text, text_only_meta)
from src.runner.model_backend_router import ChatBackend
from src.score.judge_prompts import (
    MAX_AXES_PER_CALL,
    judge_repair_prompt,
    judge_user_prompt,
    paired_axis_order,
)

__all__: list[str] = ["judge_verdict_as_bool"]

#: Attempts per judge call before the response is given up on. Transient API
#: errors are common at high concurrency and are not evidence about the model.
MAX_ATTEMPTS = 4


def judge_verdict_as_bool(value) -> bool | None:
    # A judge that answers the YES/NO instruction with JSON booleans, with
    # "true"/"false" strings, or with 1/0 has still returned a verdict.
    # Stringifying those into a YES/NO prefix match recorded them as the null
    # the schema reserves for a verdict the judge never returned, so each form
    # is read explicitly. A JSON null is the judge declining and stays null:
    # str(None) is "None", whose NO prefix used to invent a verdict.
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    token = str(value).strip().strip('."').upper()
    if token.startswith("YES") or token in {"TRUE", "1"}:
        return True
    if token.startswith("NO") or token in {"FALSE", "0"}:
        return False
    return None


def judge_settings(judge: ChatBackend, system: str) -> dict:
    """The judge provenance fixed for a whole pass, every null explained."""
    run = backend_run_provenance(judge)
    reasons = run.get(NULL_REASONS) or {}
    effort = run.get("reasoning_effort")
    why = {}
    if effort is None:
        why["reasoning_effort"] = (reasons.get("reasoning_effort")
                                   or f"judge backend {judge.name} reports no reasoning effort")
    return {"judge": judge.name, "reasoning_effort": effort,
            "system_prompt_sha256": sha256_text(system), NULL_REASONS: why}


def _call(judge: ChatBackend, system: str, user: str, max_new_tokens: int) -> SampleMeta:
    last: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            if hasattr(judge, "generate_detailed"):
                return judge.generate_detailed(system=system, user=user,
                                               max_new_tokens=max_new_tokens)
            return text_only_meta(judge.generate(system=system, user=user,
                                                 max_new_tokens=max_new_tokens), judge.name)
        except Exception as exc:  # noqa: BLE001 retried, then surfaced to the caller
            last = exc
            time.sleep(min(2 ** attempt, 8))
    raise RuntimeError(f"judge call failed after {MAX_ATTEMPTS} attempts: {last}")


def _score_one(judge: ChatBackend, system: str, row: dict, axes: list[dict]) -> dict:
    # The order is keyed on the cell, not the seat, so the base model's matched
    # cell is asked the same questions in the same positions.
    ordered = paired_axis_order(axes, f"{row['prompt_id']}|{row['s']}")
    verdicts: dict[str, bool | None] = {}
    repaired = 0
    raw_short: dict[str, str] = {}
    snapshots: list[str | None] = []
    for start in range(0, len(ordered), MAX_AXES_PER_CALL):
        chunk = ordered[start : start + MAX_AXES_PER_CALL]
        first = _call(judge, system, judge_user_prompt(chunk, row["text"]), 1400)
        snapshots.append(first.model_snapshot)
        reply = first.text
        parsed = extract_json_object(reply) or {}
        missing = [a for a in chunk if a["axis_id"] not in parsed]
        if missing:
            # Ask again for exactly what is missing, registered question text
            # included: the judge call is stateless, so a bare id would have
            # the judge answer a question reconstructed from the slug rather
            # than the registered one. An omission is not a verdict.
            repair = _call(judge, system, judge_repair_prompt(missing, row["text"]), 800)
            snapshots.append(repair.model_snapshot)
            second = repair.text
            recovered = extract_json_object(second) or {}
            wanted = {a["axis_id"] for a in missing}
            parsed = {**parsed, **{k: v for k, v in recovered.items() if k in wanted}}
            repaired += sum(1 for a in missing if a["axis_id"] in parsed)
            if any(a["axis_id"] not in parsed for a in missing):
                raw_short[f"chunk{start}"] = reply[:400]
        for axis in chunk:
            aid = axis["axis_id"]
            verdicts[aid] = judge_verdict_as_bool(parsed[aid]) if aid in parsed else None
    out = {"principal": row["principal"], "prompt_id": row["prompt_id"],
           "instruction_id": row["instruction_id"],
           "system_id": row.get("system_id", ""), "s": int(row["s"]),
           "judge": judge.name, "verdicts": verdicts, "repaired": repaired}
    if raw_short:
        out["raw_short"] = raw_short
    settings = judge_settings(judge, system)
    snapshot = joined_snapshot(snapshots)
    reasons = dict(settings[NULL_REASONS])
    if snapshot is None:
        reasons["judge_model_snapshot"] = (
            f"judge backend {judge.name} returned no model snapshot for these calls")
    out.update({"judge_model_snapshot": snapshot,
                "reasoning_effort": settings["reasoning_effort"],
                "system_prompt_sha256": settings["system_prompt_sha256"],
                "provenance_schema": PROVENANCE_SCHEMA, NULL_REASONS: reasons})
    return out
