"""Judge a set of responses through a provider's batch API, as the panel would.

The verdict panel (``verdict_panel`` and ``verdict_panel_judge_calls``) judges
one response at a time over a live connection. A batch API takes every call up
front and answers hours later at half the price. This module splits the
panel's per-response path into the three steps a batch needs, and changes
nothing a verdict depends on:

1. ``plan_first_pass``: the same screened, deduplicated responses, the same
   per-cell axis shuffle, the same chunks of ``MAX_AXES_PER_CALL``, the same
   system and user prompts, the same 1400-token cap.
2. ``plan_repairs``: for every chunk whose reply is short of ids, the same
   repair prompt over exactly the missing axes, at the same 800-token cap.
3. ``fold_rows``: the same parse, the same merge, the same ``repaired`` count
   and ``raw_short`` evidence, the same row keys.

A call the provider failed counts like a call that exhausted the panel's
retries: the whole response is unscorable and no row is written for it, never
a guessed verdict. ``tests/score/test_batch_judge_fill.py`` replays the live
panel against a recording judge and asserts the prompts and the rows match.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from src.common.json_block_parser import extract_json_object
from src.score.judge_prompts import (MAX_AXES_PER_CALL, judge_repair_prompt,
                                     judge_user_prompt, paired_axis_order)
from src.score.verdict_panel import _scorable
from src.score.verdict_panel_judge_calls import judge_verdict_as_bool

__all__ = ["FIRST_PASS_MAX_TOKENS", "REPAIR_MAX_TOKENS", "JudgeCall",
           "screen_responses", "plan_first_pass", "plan_repairs", "fold_rows",
           "anthropic_batch_request", "openai_batch_line"]

#: The caps ``verdict_panel_judge_calls._score_one`` passes to ``_call``.
FIRST_PASS_MAX_TOKENS = 1400
REPAIR_MAX_TOKENS = 800


@dataclass(frozen=True)
class JudgeCall:
    """One judge call: one chunk of one response, first pass or repair."""

    custom_id: str
    kind: str  # "first" or "repair"
    seat: str
    prompt_id: str
    s: int
    start: int
    axis_ids: tuple[str, ...]
    system: str
    user: str
    max_tokens: int

    def manifest(self) -> dict:
        row = asdict(self)
        row["axis_ids"] = list(self.axis_ids)
        del row["system"], row["user"]
        return row


def screen_responses(rows) -> tuple[list[dict], int]:
    """The rows ``score_responses`` would judge, and how many it screens out.

    First occurrence of each (prompt_id, s) wins, exactly as in the panel, and
    failed, refused, or empty rows are counted rather than judged.
    """
    kept, seen, screened = [], set(), 0
    for row in rows:
        key = (row["prompt_id"], int(row["s"]))
        if key in seen:
            continue
        seen.add(key)
        if not _scorable(row):
            screened += 1
            continue
        kept.append(row)
    return kept, screened


def _chunks(axes: list[dict], row: dict) -> list[tuple[int, list[dict]]]:
    ordered = paired_axis_order(axes, f"{row['prompt_id']}|{row['s']}")
    return [(start, ordered[start:start + MAX_AXES_PER_CALL])
            for start in range(0, len(ordered), MAX_AXES_PER_CALL)]


def _first_id(seat_index: int, row_index: int, start: int) -> str:
    # Anthropic custom ids allow [A-Za-z0-9_-]{1,64}; the manifest maps back.
    return f"f{seat_index}_{row_index:05d}_{start:03d}"


def plan_first_pass(rows_by_seat: dict[str, list[dict]], axes: list[dict],
                    system: str) -> list[JudgeCall]:
    """Every first-pass call, seats in sorted order, rows in file order."""
    calls = []
    for seat_index, seat in enumerate(sorted(rows_by_seat)):
        for row_index, row in enumerate(rows_by_seat[seat]):
            for start, chunk in _chunks(axes, row):
                calls.append(JudgeCall(
                    _first_id(seat_index, row_index, start), "first", seat,
                    row["prompt_id"], int(row["s"]), start,
                    tuple(a["axis_id"] for a in chunk), system,
                    judge_user_prompt(chunk, row["text"]), FIRST_PASS_MAX_TOKENS))
    return calls


def _parsed(reply: str | None) -> dict:
    return extract_json_object(reply) or {} if reply is not None else {}


def plan_repairs(first_calls: list[JudgeCall], replies: dict[str, str | None],
                 axes: list[dict], texts: dict[tuple[str, str, int], str]) -> list[JudgeCall]:
    """A repair call for every answered chunk whose reply is short of ids.

    A chunk with no reply (the call failed) gets none: the panel would have
    raised before reaching its repair, so the response is unscorable anyway.
    """
    by_id = {a["axis_id"]: a for a in axes}
    calls = []
    for call in first_calls:
        reply = replies.get(call.custom_id)
        if reply is None:
            continue
        parsed = _parsed(reply)
        missing = [by_id[a] for a in call.axis_ids if a not in parsed]
        if not missing:
            continue
        text = texts[(call.seat, call.prompt_id, call.s)]
        calls.append(JudgeCall(
            "r" + call.custom_id[1:], "repair", call.seat, call.prompt_id, call.s,
            call.start, tuple(a["axis_id"] for a in missing), call.system,
            judge_repair_prompt(missing, text), REPAIR_MAX_TOKENS))
    return calls


def fold_rows(rows_by_seat: dict[str, list[dict]], first_calls: list[JudgeCall],
              first_replies: dict[str, str | None], repair_calls: list[JudgeCall],
              repair_replies: dict[str, str | None], judge_name: str,
              level: int) -> tuple[dict[str, list[dict]], list[dict]]:
    """Verdict rows per seat, in the panel's schema, and the unscorable cells.

    A reply of ``None`` is a call that failed for good. The panel raises out of
    ``_score_one`` on such a call, so the response gets no row at all.
    """
    calls_of: dict[tuple[str, str, int], list[JudgeCall]] = {}
    for call in first_calls:
        calls_of.setdefault((call.seat, call.prompt_id, call.s), []).append(call)
    repair_of = {(c.seat, c.prompt_id, c.s, c.start): c for c in repair_calls}

    out: dict[str, list[dict]] = {seat: [] for seat in rows_by_seat}
    unscorable: list[dict] = []
    for seat in sorted(rows_by_seat):
        for row in rows_by_seat[seat]:
            key = (seat, row["prompt_id"], int(row["s"]))
            verdicts: dict[str, bool | None] = {}
            repaired, raw_short, failed = 0, {}, None
            for call in sorted(calls_of[key], key=lambda c: c.start):
                reply = first_replies.get(call.custom_id)
                if reply is None:
                    failed = call.custom_id
                    break
                parsed = _parsed(reply)
                missing = [a for a in call.axis_ids if a not in parsed]
                if missing:
                    fix = repair_of.get((*key, call.start))
                    second = repair_replies.get(fix.custom_id) if fix else None
                    if fix is None or second is None:
                        failed = fix.custom_id if fix else call.custom_id
                        break
                    recovered = _parsed(second)
                    wanted = set(missing)
                    parsed = {**parsed, **{k: v for k, v in recovered.items() if k in wanted}}
                    repaired += sum(1 for a in missing if a in parsed)
                    if any(a not in parsed for a in missing):
                        raw_short[f"chunk{call.start}"] = reply[:400]
                for aid in call.axis_ids:
                    verdicts[aid] = judge_verdict_as_bool(parsed[aid]) if aid in parsed else None
            if failed is not None:
                unscorable.append({"seat": seat, "prompt_id": row["prompt_id"],
                                   "s": int(row["s"]), "failed_call": failed})
                continue
            verdict_row = {"principal": row["principal"], "prompt_id": row["prompt_id"],
                           "instruction_id": row["instruction_id"],
                           "system_id": row.get("system_id", ""), "s": int(row["s"]),
                           "judge": judge_name, "verdicts": verdicts, "repaired": repaired}
            if raw_short:
                verdict_row["raw_short"] = raw_short
            verdict_row["level"] = level
            if not verdict_row.get("repaired"):
                verdict_row.pop("repaired", None)
            out[seat].append(verdict_row)
    return out, unscorable


def anthropic_batch_request(call: JudgeCall, model: str) -> dict:
    """The Message Batches entry for one call.

    ``params`` holds exactly the arguments ``AnthropicChatBackend.generate``
    passes to ``messages.create``.
    """
    return {"custom_id": call.custom_id,
            "params": {"model": model, "max_tokens": call.max_tokens,
                       "system": call.system,
                       "messages": [{"role": "user", "content": call.user}]}}


def openai_batch_line(call: JudgeCall, model: str,
                      token_param: str = "max_completion_tokens") -> dict:
    """The OpenAI-format batch line for one call.

    ``body`` holds exactly what ``OpenAiChatBackend.generate`` sends for a seat
    with no temperature and no reasoning effort, which is how the Gemini judge
    seat resolves (``judge_backend_kwargs`` adds only routing for Gemini).
    """
    return {"custom_id": call.custom_id, "method": "POST",
            "url": "/v1/chat/completions",
            "body": {"model": model,
                     "messages": [{"role": "system", "content": call.system},
                                  {"role": "user", "content": call.user}],
                     token_param: call.max_tokens}}
