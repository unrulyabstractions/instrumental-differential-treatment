"""Judge call, omission repair, and verdict parse for the verdict panel.

Held apart from ``verdict_panel`` so the per-response path reads on its own,
away from the pool, the resume set, and the seat lock. Verdicts went missing
by omission in a previous run, so a chunk whose reply is short of ids is asked
once more, registered question text repeated in full, for exactly the axes it
left out before any null is recorded, and the head of the raw reply is kept
when a chunk still comes back short, since a
null with no evidence cannot be triaged. Everything here is a private detail
of ``verdict_panel``, so nothing is package-exported.
"""

from __future__ import annotations

import time

from src.common.json_block_parser import extract_json_object
from src.runner.model_backend_router import ChatBackend
from src.score.judge_prompts import (
    MAX_AXES_PER_CALL,
    judge_repair_prompt,
    judge_user_prompt,
    paired_axis_order,
)

__all__: list[str] = []

#: Attempts per judge call before the response is given up on. Transient API
#: errors are common at high concurrency and are not evidence about the model.
MAX_ATTEMPTS = 4


def _as_bool(value) -> bool | None:
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


def _call(judge: ChatBackend, system: str, user: str, max_new_tokens: int) -> str:
    last: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            return judge.generate(system=system, user=user, max_new_tokens=max_new_tokens)
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
    for start in range(0, len(ordered), MAX_AXES_PER_CALL):
        chunk = ordered[start : start + MAX_AXES_PER_CALL]
        reply = _call(judge, system, judge_user_prompt(chunk, row["text"]), 1400)
        parsed = extract_json_object(reply) or {}
        missing = [a for a in chunk if a["axis_id"] not in parsed]
        if missing:
            # Ask again for exactly what is missing, registered question text
            # included: the judge call is stateless, so a bare id would have
            # the judge answer a question reconstructed from the slug rather
            # than the registered one. An omission is not a verdict.
            second = _call(judge, system, judge_repair_prompt(missing, row["text"]), 800)
            recovered = extract_json_object(second) or {}
            wanted = {a["axis_id"] for a in missing}
            parsed = {**parsed, **{k: v for k, v in recovered.items() if k in wanted}}
            repaired += sum(1 for a in missing if a["axis_id"] in parsed)
            if any(a["axis_id"] not in parsed for a in missing):
                raw_short[f"chunk{start}"] = reply[:400]
        for axis in chunk:
            aid = axis["axis_id"]
            verdicts[aid] = _as_bool(parsed[aid]) if aid in parsed else None
    out = {"principal": row["principal"], "prompt_id": row["prompt_id"],
           "instruction_id": row["instruction_id"],
           "system_id": row.get("system_id", ""), "s": int(row["s"]),
           "judge": judge.name, "verdicts": verdicts, "repaired": repaired}
    if raw_short:
        out["raw_short"] = raw_short
    return out
