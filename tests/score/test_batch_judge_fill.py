"""The batch judging path asks the same questions and writes the same rows.

``src/score/batch_judge_fill`` splits the verdict panel's per-response path
into plan, repair, and fold steps so the calls can go through a batch API.
These tests replay the live panel (``_score_one`` and ``score_responses``)
against a recording judge with a scripted reply rule, and assert that the
batch path sends byte-identical prompts at the same token caps and folds the
replies into identical rows. The provider request shapes are checked against
the live backends with their clients stubbed. No network, no model.
"""

from __future__ import annotations

import json
import re

import pytest

from src.score import batch_judge_fill as bj
from src.score.judge_prompts import judge_system_prompt
from src.score.verdict_panel import score_responses
from src.score.verdict_panel_judge_calls import _score_one

AXES = [{"axis_id": f"axis_{n:03d}", "question": f"Does the response do thing {n}?"}
        for n in range(60)]
SYSTEM = judge_system_prompt(3, "A test deployment.", "A test activation.")


def _responses(principal: str, n: int) -> list[dict]:
    return [{"principal": principal, "prompt_id": f"{principal}__none::t{i // 2}",
             "instruction_id": f"none::t{i // 2}", "system_id": "none", "s": i % 2,
             "refused": False, "failed": False,
             "text": f"Reply {i} about {principal}. {'x' * i}"} for i in range(n)]


def scripted_reply(user: str) -> str:
    """Deterministic judge behavior keyed on the prompt.

    First passes drop some ids and answer others in assorted formats; repair
    passes recover some of what was dropped. That exercises the repair, the
    raw_short evidence, the null, and the boolean parse together.
    """
    ids = re.findall(r"^\d+\. (axis_\d{3}):", user, flags=re.M)
    repair = "A first pass over this response left out" in user
    answer = {}
    for aid in ids:
        n = int(aid[-3:]) + len(user)
        if not repair and len(user) % 3 == 0 and n % 7 == 0:
            continue  # omitted on the first pass
        if repair and n % 3 == 0:
            continue  # still omitted after repair
        answer[aid] = ["YES", "NO", True, "false", None][n % 5]
    body = json.dumps(answer)
    return f"Here you go:\n```json\n{body}\n```" if len(user) % 2 else body


class RecordingJudge:
    name = "test:recording"

    def __init__(self):
        self.calls: list[tuple[str, str, int]] = []

    def generate(self, system: str, user: str, max_new_tokens: int = 512) -> str:
        self.calls.append((system, user, max_new_tokens))
        return scripted_reply(user)


def _batch_path(rows_by_seat, judge_name, level, fail=frozenset()):
    first = bj.plan_first_pass(rows_by_seat, AXES, SYSTEM)
    first_replies = {c.custom_id: (None if c.custom_id in fail else scripted_reply(c.user))
                     for c in first}
    texts = {(seat, r["prompt_id"], int(r["s"])): r["text"]
             for seat, rows in rows_by_seat.items() for r in rows}
    repairs = bj.plan_repairs(first, first_replies, AXES, texts)
    repair_replies = {c.custom_id: (None if c.custom_id in fail else scripted_reply(c.user))
                      for c in repairs}
    rows, unscorable = bj.fold_rows(rows_by_seat, first, first_replies, repairs,
                                    repair_replies, judge_name, level)
    return first, repairs, rows, unscorable


def test_prompts_and_caps_match_the_live_panel_call_for_call():
    rows = _responses("cand_a", 12)
    first, repairs, _, _ = _batch_path({"seat": rows}, "test:recording", 3)
    for row in rows:
        judge = RecordingJudge()
        _score_one(judge, SYSTEM, row, AXES)
        mine = sorted([c for c in first + repairs
                       if (c.prompt_id, c.s) == (row["prompt_id"], row["s"])],
                      key=lambda c: (c.start, c.kind != "first"))
        assert [(c.system, c.user, c.max_tokens) for c in mine] == judge.calls
    assert repairs, "the scripted judge must trigger repairs for this test to bite"


def test_rows_match_score_responses_byte_for_byte(tmp_path):
    rows = _responses("cand_a", 10) + _responses("cand_b", 10)
    responses = tmp_path / "responses_seat.jsonl"
    responses.write_text("".join(json.dumps(r) + "\n" for r in rows))
    verdicts = tmp_path / "verdicts_seat.jsonl"
    score_responses(RecordingJudge(), 3, "", "", AXES, responses, verdicts,
                    workers=1, show_progress=False)
    live = {(r["prompt_id"], r["s"]): json.dumps(r, sort_keys=True)
            for r in map(json.loads, verdicts.read_text().splitlines())}

    kept, screened = bj.screen_responses(rows)
    _, _, folded, unscorable = _batch_path({"seat": kept}, "test:recording", 3)
    mine = {(r["prompt_id"], r["s"]): json.dumps(r, sort_keys=True) for r in folded["seat"]}
    assert screened == 0 and not unscorable
    assert mine == live
    assert any('"raw_short"' in v for v in mine.values())
    assert any('"repaired"' in v for v in mine.values())
    assert any('"repaired"' not in v for v in mine.values())


def test_a_failed_call_leaves_the_response_unscorable_never_guessed():
    rows = _responses("cand_a", 4)
    first = bj.plan_first_pass({"seat": rows}, AXES, SYSTEM)
    dead = {first[1].custom_id}
    _, _, folded, unscorable = _batch_path({"seat": rows}, "j", 2, fail=dead)
    assert len(folded["seat"]) == 3
    assert unscorable == [{"seat": "seat", "prompt_id": first[1].prompt_id,
                           "s": first[1].s, "failed_call": first[1].custom_id}]


def test_a_failed_repair_also_leaves_the_response_unscorable():
    rows = _responses("cand_a", 6)
    first, repairs, _, _ = _batch_path({"seat": rows}, "j", 2)
    _, _, folded, unscorable = _batch_path({"seat": rows}, "j", 2,
                                           fail={repairs[0].custom_id})
    assert unscorable[0]["failed_call"] == repairs[0].custom_id
    assert len(folded["seat"]) == len(rows) - 1


def test_screening_matches_the_panel():
    rows = _responses("cand_a", 4)
    rows[1] = {**rows[1], "failed": True}
    rows[2] = {**rows[2], "text": "   "}
    rows.append(dict(rows[0]))  # a duplicate cell
    kept, screened = bj.screen_responses(rows)
    assert [r["prompt_id"] for r in kept] == [rows[0]["prompt_id"], rows[3]["prompt_id"]]
    assert screened == 2


def test_custom_ids_are_unique_and_valid_for_anthropic():
    rows = {"a": _responses("cand_a", 30), "b": _responses("cand_b", 30)}
    first, repairs, _, _ = _batch_path(rows, "j", 2)
    ids = [c.custom_id for c in first + repairs]
    assert len(ids) == len(set(ids))
    assert all(re.fullmatch(r"[A-Za-z0-9_-]{1,64}", i) for i in ids)
    assert len(first) == 60 * 3  # 60 rows; 60 axes in chunks of 25, 25, 10


def test_anthropic_request_carries_exactly_what_the_live_backend_sends():
    from src.runner.anthropic_chat_backend import AnthropicChatBackend

    sent = {}

    class Messages:
        def create(self, **kwargs):
            sent.update(kwargs)

            class R:
                stop_reason = "end_turn"
                content = []
            return R()

    backend = AnthropicChatBackend.__new__(AnthropicChatBackend)
    backend._model_name = "some-model"
    backend._client = type("C", (), {"messages": Messages()})()
    call = bj.plan_first_pass({"s": _responses("cand_a", 1)}, AXES, SYSTEM)[0]
    backend.generate(call.system, call.user, call.max_tokens)
    request = bj.anthropic_batch_request(call, "some-model")
    assert request["params"] == sent
    assert request["custom_id"] == call.custom_id


@pytest.mark.parametrize("effort", [None, "low"])
def test_openai_line_carries_exactly_what_the_live_backend_sends(effort):
    # None is the Gemini seat; "low" is the gpt-5-mini seat that judged the
    # AuditBench nulls (judge_backend_kwargs and every gpt-5-mini config).
    import threading

    from src.runner.openai_chat_backend import OpenAiChatBackend

    sent = {}

    class Completions:
        def create(self, **kwargs):
            sent.update(kwargs)
            msg = type("M", (), {"content": "{}", "refusal": None})()
            choice = type("Ch", (), {"message": msg, "finish_reason": "stop"})()
            return type("R", (), {"choices": [choice], "usage": None})()

    backend = OpenAiChatBackend.__new__(OpenAiChatBackend)
    backend._model_name = "some-model"
    backend._client = type("C", (), {"chat": type("Ch", (), {"completions": Completions()})()})()
    backend._temperature = None
    backend._reasoning_effort = effort
    backend._usage_sink = None
    backend._token_param = "max_completion_tokens"
    backend._token_param_flipped = False
    backend._lock = threading.Lock()
    call = bj.plan_first_pass({"s": _responses("cand_a", 1)}, AXES, SYSTEM)[0]
    backend.generate(call.system, call.user, call.max_tokens)
    line = bj.openai_batch_line(call, "some-model", reasoning_effort=effort)
    assert line["body"] == sent
    assert line["url"] == "/v1/chat/completions" and line["method"] == "POST"


def _driver():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "script/data/batch_judge_fill.py"
    spec = importlib.util.spec_from_file_location("batch_judge_fill_driver", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _anthropic_entry(stop="end_turn", text='{"a": "YES"}', kind="succeeded"):
    if kind != "succeeded":
        return {"custom_id": "f0_00000_000",
                "result": {"type": kind, "error": {"type": "overloaded_error"}}}
    return {"custom_id": "f0_00000_000", "result": {"type": "succeeded", "message": {
        "stop_reason": stop, "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": 100, "output_tokens": 20,
                  "cache_creation_input_tokens": 0, "cache_read_input_tokens": None}}}}


def _openai_entry(content='{"a": "NO"}', finish="stop", status=200, usage=None):
    return {"custom_id": "f0_00000_000", "error": None, "response": {
        "status_code": status, "body": {
            "choices": [{"message": {"content": content}, "finish_reason": finish}],
            "usage": usage or {"prompt_tokens": 90, "completion_tokens": 10,
                               "total_tokens": 130}}}}


def test_driver_reads_replies_and_raises_where_the_live_backends_raise():
    d = _driver()
    assert d._reply_of(_anthropic_entry()) == ('{"a": "YES"}', None)
    assert d._reply_of(_anthropic_entry(stop="refusal"))[0] is None
    assert d._reply_of(_anthropic_entry(kind="errored"))[0] is None
    assert d._reply_of(_anthropic_entry(kind="expired"))[0] is None
    assert d._reply_of(_openai_entry()) == ('{"a": "NO"}', None)
    assert d._reply_of(_openai_entry(content=""))[0] is None
    assert d._reply_of(_openai_entry(finish="content_filter"))[0] is None
    assert d._reply_of(_openai_entry(status=429))[0] is None


def test_driver_bills_thinking_tokens_as_output():
    d = _driver()
    assert d._usage(_anthropic_entry()) == (100, 20)
    assert d._usage(_anthropic_entry(kind="errored")) == (0, 0)
    # total 130 = prompt 90 + visible 10 + 30 thinking; all 40 are billed output
    assert d._usage(_openai_entry()) == (90, 40)


def test_driver_reads_gemini_camel_case_batch_output():
    """Gemini's batch output spells the OpenAI fields in camelCase.

    Its first fetch read usage as zero tokens because only snake_case was
    parsed, and a content filter would have been missed for the same reason.
    """
    d = _driver()
    line = {"custom_id": "f0_00000_000", "response": {"status_code": 200, "body": {
        "model": "gemini-3.5-flash-lite",
        "choices": [{"message": {"content": '{"a": "NO"}', "role": "assistant"},
                     "finishReason": "stop"}],
        "usage": {"promptTokens": 1122, "completionTokens": 368, "totalTokens": 1490}}}}
    assert d._reply_of(line) == ('{"a": "NO"}', None)
    assert d._usage(line) == (1122, 368)
    blocked = json.loads(json.dumps(line))
    blocked["response"]["body"]["choices"][0]["finishReason"] = "CONTENT_FILTER"
    assert d._reply_of(blocked)[0] is None


def test_gpt_seats_route_to_openai_and_gemini_to_its_endpoint():
    # The "openai" provider name covers both routes; a gpt-5-mini batch sent to
    # the Gemini endpoint would fail or bill the wrong account.
    d = _driver()
    assert d._api({"provider": "openai", "model": "gpt-5-mini"}) == "openai_native"
    assert d._api({"provider": "openai", "model": "gemini-flash-lite-latest"}) == "openai"
    assert d._api({"provider": "anthropic", "model": "claude-haiku-4-5"}) == "anthropic"
