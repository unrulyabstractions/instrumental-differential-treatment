"""Regressions for the alias over-merges a real elicitation run produced.

On the 2026-08-07 Gemini elicitation, "green party" absorbed three national
Green parties and the Green New Deal, and "french government" merged into
"french communist party". Two rules caused it: a reduced one-token core
("green party" -> "green") subset-matched anything containing its modifier,
and the multi-token subset arm let "democratic party" match inside
"nationalist democratic party of germany". Each case here is one of those
observed merges or one of the documented merges the fix must not break.
"""

from __future__ import annotations

from collections import Counter

import pytest

from src.ellicit.actor_alias_rules import same_actor
from src.ellicit.principal_tally_report import consolidate_variants


@pytest.mark.parametrize("a, b", [
    ("green party", "green new deal"),
    ("green party of france", "green party of canada"),
    ("democratic party", "nationalist democratic party of germany"),
    ("democratic party", "democratic socialists of america"),
    ("french communist party", "french government"),
])
def test_distinct_actors_stay_distinct(a, b):
    assert not same_actor(a, b)
    assert not same_actor(b, a)


@pytest.mark.parametrize("a, b", [
    ("macron administration", "emmanuel macron"),
    ("macron s party", "emmanuel macron"),
    ("macron", "emmanuel macron"),
    ("mahatma gandhi", "mohandas gandhi"),
    ("un", "united nations"),
    ("the united nations", "united nations"),
    ("doctors without borders", "doctors without borders medecins sans frontieres"),
])
def test_documented_merges_still_merge(a, b):
    assert same_actor(a, b)
    assert same_actor(b, a)


def test_vague_parent_cannot_absorb_mutually_distinct_children():
    """The two-parent refusal never fired because each national party faced
    only the vague parent. The cluster must stay pairwise coherent: the first
    specific variant may join, the next conflicting one stays separate."""
    merged, aliases = consolidate_variants(Counter({
        "green party": 23,
        "green party of france": 5,
        "green party of canada": 3,
        "green new deal": 2,
    }))
    assert "green new deal" in merged
    assert "green party of canada" in merged or "green party of france" in merged
    assert aliases.get("green new deal") is None


def test_coherent_cluster_still_pools():
    merged, _ = consolidate_variants(Counter({
        "emmanuel macron": 40,
        "macron": 6,
        "macron administration": 3,
    }))
    assert merged == Counter({"emmanuel macron": 49})
