"""The judge's reply is parsed exactly, repaired once, and never invented.

The parse and repair path lives in ``src/score/verdict_panel_judge_calls``. A
reply can arrive as clean JSON, fenced, wrapped in prose, truncated, or as
garbage. The first three parse directly. A truncated or garbage reply triggers
one narrow repair ask, and an id still missing after repair is recorded as
null with the head of the raw reply kept as evidence. A null is a verdict
nobody returned, so it must never be read as a "no".

The judge seat here is a scripted stub. No network, no model, no files.
"""

from __future__ import annotations

import json

from src.score.answer_tag_extraction import CHOICE_AXIS, extract_choice, verdict_row
from src.score.judge_prompts import MAX_AXES_PER_CALL, paired_axis_order
from src.score.verdict_panel import _scorable
from src.score.verdict_panel_judge_calls import _score_one

AXES = [{"axis_id": f"ax{i}", "question": f"Does it {i}?"} for i in range(3)]
ROW = {"principal": "a", "prompt_id": "p0", "instruction_id": "i0", "s": 0,
       "text": "The assistant replies at length."}
CLEAN = json.dumps({"ax0": "YES", "ax1": "NO", "ax2": "YES"})
WANT = {"ax0": True, "ax1": False, "ax2": True}


class ScriptedJudge:
    """A judge seat that replays a fixed script of replies."""

    name = "scripted"

    def __init__(self, *replies: str):
        self.replies = list(replies)
        self.prompts: list[str] = []

    def generate(self, system: str, user: str, max_new_tokens: int = 512) -> str:
        self.prompts.append(user)
        return self.replies.pop(0)


def test_a_well_formed_reply_parses_in_one_call():
    judge = ScriptedJudge(CLEAN)
    out = _score_one(judge, "sys", ROW, AXES)
    assert out["verdicts"] == WANT
    assert out["repaired"] == 0
    assert "raw_short" not in out
    assert len(judge.prompts) == 1


def test_a_fenced_reply_is_recovered_without_repair():
    judge = ScriptedJudge(f"```json\n{CLEAN}\n```")
    out = _score_one(judge, "sys", ROW, AXES)
    assert out["verdicts"] == WANT
    assert len(judge.prompts) == 1


def test_a_prose_prefixed_reply_is_recovered_without_repair():
    judge = ScriptedJudge(f"Sure, here are my verdicts.\n{CLEAN}\nLet me know.")
    out = _score_one(judge, "sys", ROW, AXES)
    assert out["verdicts"] == WANT
    assert len(judge.prompts) == 1


def test_a_truncated_reply_is_repaired_in_full():
    judge = ScriptedJudge('{"ax0": "YES", "ax1": "NO"', CLEAN)
    out = _score_one(judge, "sys", ROW, AXES)
    assert out["verdicts"] == WANT
    assert out["repaired"] == 3
    assert "raw_short" not in out
    assert len(judge.prompts) == 2
    assert "left out" in judge.prompts[1]


def test_repair_asks_only_for_the_missing_ids_and_keeps_the_first_pass():
    first = json.dumps({"ax0": "YES", "ax2": "YES"})
    repair = json.dumps({"ax1": "NO", "ax0": "NO"})  # the ax0 flip must be ignored
    judge = ScriptedJudge(first, repair)
    out = _score_one(judge, "sys", ROW, AXES)
    assert out["verdicts"] == WANT
    assert out["repaired"] == 1


def test_a_garbage_reply_records_null_and_keeps_evidence():
    judge = ScriptedJudge("I cannot help with that.", "Still not JSON.")
    out = _score_one(judge, "sys", ROW, AXES)
    assert out["verdicts"] == {"ax0": None, "ax1": None, "ax2": None}
    assert out["repaired"] == 0
    assert out["raw_short"] == {"chunk0": "I cannot help with that."}
    assert len(judge.prompts) == 2


def test_a_value_that_is_neither_yes_nor_no_is_null():
    reply = json.dumps({"ax0": "MAYBE", "ax1": "yes.", "ax2": '"NO"'})
    judge = ScriptedJudge(reply)
    out = _score_one(judge, "sys", ROW, AXES)
    assert out["verdicts"] == {"ax0": None, "ax1": True, "ax2": False}
    assert len(judge.prompts) == 1  # a present key is never re-asked


def test_axes_beyond_one_chunk_are_asked_in_a_second_call():
    axes = [{"axis_id": f"bx{i:02d}", "question": "?"}
            for i in range(MAX_AXES_PER_CALL + 1)]
    ordered = paired_axis_order(axes, f"{ROW['prompt_id']}|{ROW['s']}")
    first = json.dumps({a["axis_id"]: "YES" for a in ordered[:MAX_AXES_PER_CALL]})
    second = json.dumps({a["axis_id"]: "NO" for a in ordered[MAX_AXES_PER_CALL:]})
    judge = ScriptedJudge(first, second)
    out = _score_one(judge, "sys", ROW, axes)
    assert len(judge.prompts) == 2
    assert out["repaired"] == 0
    assert len(out["verdicts"]) == len(axes)
    assert out["verdicts"][ordered[-1]["axis_id"]] is False
    assert sum(v is True for v in out["verdicts"].values()) == MAX_AXES_PER_CALL


def test_the_axis_order_is_deterministic_per_cell_and_leaves_the_input_alone():
    once = paired_axis_order(AXES, "p0|0")
    again = paired_axis_order(AXES, "p0|0")
    assert once == again
    assert sorted(a["axis_id"] for a in once) == ["ax0", "ax1", "ax2"]
    assert [a["axis_id"] for a in AXES] == ["ax0", "ax1", "ax2"]


def test_answer_extraction_is_deterministic_over_repeated_calls():
    texts = ["<answer>A</answer>", "<answer>B", "  b) ", "no answer here", "",
             "Option A and option B both have merit.", "<ANSWER>(a)</ANSWER>"]
    first = [extract_choice(t) for t in texts]
    for _ in range(50):
        assert [extract_choice(t) for t in texts] == first


def test_verdict_row_is_a_pure_function_of_its_inputs():
    response = {"principal": "x", "prompt_id": "p1", "instruction_id": "i1",
                "s": 2, "text": "<answer>B</answer>"}
    assert verdict_row(response, "B") == verdict_row(response, "B")
    assert verdict_row(response, "B")["verdicts"][CHOICE_AXIS] is True


def test_scorable_rejects_failed_and_refused_rows():
    assert _scorable({"text": "a real reply"})
    assert _scorable({"text": "ok", "failed": False, "refused": False})
    assert not _scorable({"text": "ok", "failed": True})
    assert not _scorable({"text": "ok", "refused": True})


def test_scorable_rejects_empty_and_missing_text():
    assert not _scorable({"text": ""})
    assert not _scorable({"text": "   \n\t"})
    assert not _scorable({})
