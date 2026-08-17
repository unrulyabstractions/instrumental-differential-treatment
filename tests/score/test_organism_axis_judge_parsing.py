"""score_axes never fabricates a verdict out of a judge's reply shape.

The bug this pins: ``bool()`` over a JSON *string* is True for every non-empty
string, so a judge answering ``{"axis": "NO"}`` was recorded as a firing. The
review that caught it also showed the greedy ``{.*}`` regex returning all-null
on replies whose JSON the project's own parser recovers.
"""

from __future__ import annotations

from src.score.organism_axis_judge import JUDGE_SYSTEM, score_axes

AXES = {"a1": "Does the reply do the first thing?",
        "a2": "Does the reply do the second thing?"}


class _Scripted:
    """A backend that replays a fixed reply, recording what it was asked."""

    def __init__(self, reply: str):
        self._reply = reply
        self.calls = 0

    @property
    def name(self) -> str:
        return "scripted:judge"

    def generate(self, system: str, user: str, max_new_tokens: int = 512) -> str:
        assert system == JUDGE_SYSTEM
        self.calls += 1
        return self._reply


def test_string_no_is_a_negative_verdict_not_a_firing() -> None:
    backend = _Scripted('{"a1": "YES", "a2": "NO"}')
    assert score_axes(backend, "some reply", AXES) == {"a1": True, "a2": False}


def test_string_true_false_read_as_booleans() -> None:
    backend = _Scripted('{"a1": "true", "a2": "false"}')
    assert score_axes(backend, "some reply", AXES) == {"a1": True, "a2": False}


def test_json_null_stays_null() -> None:
    backend = _Scripted('{"a1": true, "a2": null}')
    assert score_axes(backend, "some reply", AXES) == {"a1": True, "a2": None}


def test_trailing_prose_after_the_object_still_parses() -> None:
    backend = _Scripted('{"a1": true, "a2": false}\n\nNote: {"caveat": 1}')
    assert score_axes(backend, "some reply", AXES) == {"a1": True, "a2": False}


def test_a_missing_axis_is_null_not_invented() -> None:
    backend = _Scripted('{"a1": true}')
    assert score_axes(backend, "some reply", AXES) == {"a1": True, "a2": None}


def test_an_empty_reply_is_all_null_and_free() -> None:
    backend = _Scripted('{"a1": true, "a2": false}')
    assert score_axes(backend, "   ", AXES) == {"a1": None, "a2": None}
    assert backend.calls == 0


def test_unparseable_replies_exhaust_retries_to_all_null() -> None:
    backend = _Scripted("I cannot answer in JSON.")
    assert score_axes(backend, "some reply", AXES) == {"a1": None, "a2": None}
    assert backend.calls == 4
