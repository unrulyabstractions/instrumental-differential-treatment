"""The standing instructions file is machine-checked, not just written down.

A rule that lives only in prose is a rule an agent can skim past. These tests
give STANDING_INSTRUCTIONS.md teeth: an unanswered question from the owner stops
the suite, and the file has to keep the shape the next reader expects.

The failure this guards against already happened. The owner asked which judge
seat to use, the reply was interrupted, and the question was never reopened.
Runs then went out under a seat nobody had chosen.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

INSTRUCTIONS = Path(__file__).resolve().parents[1] / "STANDING_INSTRUCTIONS.md"

STATUSES = ("OPEN", "BINDING", "DONE")


def _section(body: str, heading: str) -> str:
    """The text under one `## heading`, up to the next `## `."""
    match = re.search(rf"^## {heading}$(.*?)(?=^## |\Z)", body,
                      re.M | re.S)
    assert match, f"STANDING_INSTRUCTIONS.md has no '## {heading}' section"
    return match.group(1)


@pytest.fixture(scope="module")
def body() -> str:
    assert INSTRUCTIONS.is_file(), f"{INSTRUCTIONS} is missing"
    return INSTRUCTIONS.read_text(encoding="utf-8")


def test_every_status_section_is_present(body: str) -> None:
    for status in STATUSES:
        assert re.search(rf"^## {status}$", body, re.M), \
            f"the '{status}' section is missing"


def test_no_open_question_is_left_unanswered(body: str) -> None:
    """An OPEN entry means the owner asked something and never got an answer.

    Failing here is the point. The suite stops until the entry is either
    answered by the owner or moved by the owner to BINDING or DONE.
    """
    open_body = _section(body, "OPEN")
    entries = re.findall(r"^### (.+)$", open_body, re.M)
    assert not entries, (
        "unanswered questions from the project owner: "
        + "; ".join(entries)
        + ". Do not start paid work while one is open."
    )


def test_binding_rules_are_not_silently_emptied(body: str) -> None:
    """The binding rules were each written after a real failure.

    Someone deleting them to make a check pass is the failure mode this guards
    against, so the count is asserted rather than merely their presence.
    """
    binding = _section(body, "BINDING")
    ids = re.findall(r"^### (B\d+)\.", binding, re.M)
    assert len(ids) >= 7, f"expected at least 7 binding rules, found {ids}"
    assert len(ids) == len(set(ids)), f"duplicate binding rule ids: {ids}"


def test_each_entry_quotes_the_owner_rather_than_paraphrasing(body: str) -> None:
    """Every binding rule carries the owner's own words.

    A paraphrase drifts. The quote is what makes an entry auditable against the
    transcript it came from.
    """
    binding = _section(body, "BINDING")
    blocks = re.split(r"^### ", binding, flags=re.M)[1:]
    missing = [b.splitlines()[0] for b in blocks if not re.search(r"^> ", b, re.M)]
    assert not missing, f"binding rules with no quoted instruction: {missing}"
