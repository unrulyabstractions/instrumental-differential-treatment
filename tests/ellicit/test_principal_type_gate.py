"""The type gate keeps one entity type in a roster, before the cap.

The failure this guards against already happened: the scoped secret_loyalty
roster was capped straight from the tally, so a security vendor and a US state
were tested against countries.
"""

from __future__ import annotations

import pytest

from src.ellicit.principal_type_gate import gate_candidates, normalize_type


def _c(actor, target, reference=0):
    return {"actor": actor, "display": actor.title(), "target_count": target,
            "reference_count": reference, "elevation": target - reference}


CANDIDATES = [_c("russia", 39, 8), _c("delaware", 7), _c("f secure", 6),
              _c("estonia", 7, 3), _c("british government", 3),
              _c("united kingdom", 15, 5), _c("john smith", 9)]
LABELS = {"russia": {"type": "state actor"}, "delaware": {"type": "other"},
          "f secure": {"type": "organization"}, "estonia": {"type": "state actor"},
          "british government": {"type": "state actor", "canonical": "united kingdom"},
          "united kingdom": {"type": "state actor"}, "john smith": {"type": "placeholder"}}


def test_off_type_candidates_never_reach_the_roster():
    gate = gate_candidates(CANDIDATES, "state actor", LABELS, top=10)
    roster = [r["actor"] for r in gate["roster"]]
    assert roster == ["russia", "united kingdom", "estonia"]
    assert {d["actor"] for d in gate["dropped"]} == {"delaware", "f secure", "john smith"}


def test_gate_runs_before_the_cap():
    gate = gate_candidates(CANDIDATES, "state actor", LABELS, top=2)
    assert [r["actor"] for r in gate["roster"]] == ["russia", "united kingdom"]


def test_a_government_merges_into_its_state():
    gate = gate_candidates(CANDIDATES, "state actor", LABELS, top=10)
    uk = next(r for r in gate["roster"] if r["actor"] == "united kingdom")
    assert uk["elevation"] == 13 and uk["merged"] == ["british government"]


def test_an_unlabelled_actor_stops_the_gate():
    with pytest.raises(SystemExit):
        gate_candidates(CANDIDATES, "state actor", {"russia": {"type": "state actor"}}, 10)


def test_declared_type_spellings():
    assert normalize_type("political figure") == "person"
    assert normalize_type("State actor") == "state actor"
    with pytest.raises(ValueError):
        normalize_type("anything")
