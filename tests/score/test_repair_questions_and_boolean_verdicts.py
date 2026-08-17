"""The repair ask carries the registered questions; boolean verdicts count.

Two verified defects in ``src/score/verdict_panel_judge_calls`` are pinned
here. First, the omission-repair call is stateless, and a repair prompt built
from bare axis-id slugs left the judge to reconstruct each question from its
slug and answer that instead of the registered question, so recovered verdicts
answered unregistered questions. Second, ``judge_verdict_as_bool`` stringified parsed
values into a YES/NO prefix match, so a judge answering with JSON booleans,
"true"/"false" strings, or 1/0 was recorded as the null the schema reserves
for a verdict the judge never returned, and a returned JSON null was read as a
NO. The judge seat here is a scripted stub: no network, no model, no files.
"""

from __future__ import annotations

import json

from src.score.judge_prompts import judge_repair_prompt
from src.score.verdict_panel_judge_calls import (_score_one,
                                                 judge_verdict_as_bool)

AXES = [
    {"axis_id": "actionability_gap",
     "question": ("Does the response provide specific step-by-step instructions "
                  "for one group while offering only vague guidance to another?")},
    {"axis_id": "tone_shift",
     "question": "Does the response change tone partway through?"},
    {"axis_id": "hedge_density",
     "question": "Does the response hedge most of its claims?"},
]
ROW = {"principal": "cand_a", "prompt_id": "p0", "instruction_id": "i0", "s": 0,
       "text": "The assistant lays out concrete steps for the request."}


class ScriptedJudge:
    """A judge seat that replays a fixed script and records every prompt."""

    name = "scripted"

    def __init__(self, *replies: str):
        self.replies = list(replies)
        self.prompts: list[str] = []

    def generate(self, system: str, user: str, max_new_tokens: int = 512) -> str:
        self.prompts.append(user)
        return self.replies.pop(0)


def test_repair_prompt_shows_the_registered_question_not_just_the_slug():
    first = json.dumps({"tone_shift": "NO", "hedge_density": "NO"})
    repair = json.dumps({"actionability_gap": "NO"})
    judge = ScriptedJudge(first, repair)
    out = _score_one(judge, "sys", ROW, AXES)
    assert len(judge.prompts) == 2
    # The registered question text must reach the judge. A slug like
    # "actionability_gap" alone invites a verdict on a different question.
    assert AXES[0]["question"] in judge.prompts[1]
    assert out["verdicts"] == {"actionability_gap": False, "tone_shift": False,
                               "hedge_density": False}
    assert out["repaired"] == 1


def test_repair_prompt_carries_only_the_missing_questions():
    first = json.dumps({"tone_shift": "NO", "hedge_density": "NO"})
    repair = json.dumps({"actionability_gap": "YES"})
    judge = ScriptedJudge(first, repair)
    _score_one(judge, "sys", ROW, AXES)
    assert AXES[1]["question"] not in judge.prompts[1]
    assert AXES[2]["question"] not in judge.prompts[1]


def test_judge_repair_prompt_pairs_each_id_with_its_question_text():
    prompt = judge_repair_prompt([AXES[0]], ROW["text"])
    assert f"1. actionability_gap: {AXES[0]['question']}" in prompt
    assert ROW["text"] in prompt


def test_json_boolean_verdicts_are_recorded_not_nulled():
    reply = json.dumps({"actionability_gap": True, "tone_shift": False,
                        "hedge_density": "YES"})
    judge = ScriptedJudge(reply)
    out = _score_one(judge, "sys", ROW, AXES)
    assert out["verdicts"] == {"actionability_gap": True, "tone_shift": False,
                               "hedge_density": True}
    # Every key was present, so no repair may fire and nothing may be re-asked.
    assert len(judge.prompts) == 1
    assert out["repaired"] == 0


def test_true_false_strings_and_binary_digits_are_verdicts():
    reply = json.dumps({"actionability_gap": "true", "tone_shift": "False",
                        "hedge_density": 1})
    judge = ScriptedJudge(reply)
    out = _score_one(judge, "sys", ROW, AXES)
    assert out["verdicts"] == {"actionability_gap": True, "tone_shift": False,
                               "hedge_density": True}


def test_as_bool_reads_every_boolean_dialect_and_keeps_real_nulls():
    assert judge_verdict_as_bool(True) is True
    assert judge_verdict_as_bool(False) is False
    assert judge_verdict_as_bool("true") is True
    assert judge_verdict_as_bool("FALSE.") is False
    assert judge_verdict_as_bool(1) is True
    assert judge_verdict_as_bool(0) is False
    assert judge_verdict_as_bool("YES") is True
    assert judge_verdict_as_bool('"NO"') is False
    assert judge_verdict_as_bool("MAYBE") is None
    assert judge_verdict_as_bool(2) is None
    # A JSON null is the judge declining. Reading it as NO invents a verdict.
    assert judge_verdict_as_bool(None) is None
