"""The blind audit's per-type rosters resolve, and the paper bans off-type names.

The blind audit declares no entity type, so each type's gated roster is its own
run that reads the blind run's shared axis registry. The paper check must fail
on any off-type candidate of the ungated narrow-secret-loyalty rosters.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import numpy as np

from src.common.experiment_layout import (BLIND_ROSTERS, condition_conjecture_dir,
                                          condition_promptset_dir, roster_condition)
from src.geometry.semantic_behavior_bridge import candidate_overlay
from src.ui.experiment_registry import EXPERIMENTS

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _checker():
    spec = importlib.util.spec_from_file_location(
        "check_paper_invariants", ROOT / "script/paper/check_paper_invariants.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_blind_rosters_read_the_blind_registry():
    for key in BLIND_ROSTERS:
        assert roster_condition(key) == "calibration_blind"
        assert condition_conjecture_dir(key).parts[-2:] == ("calibration_blind", "conjecture")
        assert condition_promptset_dir(key).parts[-2:] == ("calibration_blind", "promptset")
    assert roster_condition("calibration_scoped") == "calibration_scoped"


def test_registry_holds_one_run_per_blind_roster_and_no_mixed_blind_run():
    keys = {e.key for e in EXPERIMENTS}
    assert set(BLIND_ROSTERS) <= keys
    assert "calibration_blind" not in keys
    for e in EXPERIMENTS:
        if e.key in BLIND_ROSTERS:
            assert e.axes.endswith("calibration_blind/conjecture/scoring_questions.json")
            assert f"/{e.key}/" in e.summary


def test_overlay_is_empty_for_two_candidates_and_fitted_for_three():
    rng = np.random.default_rng(0)
    two = candidate_overlay(rng.normal(size=(2, 5)), rng.normal(size=(2, 7)))
    assert two["disparity"] is None and two["interpretable_xy"] == []
    three = candidate_overlay(rng.normal(size=(3, 5)), rng.normal(size=(3, 7)))
    assert three["disparity"] is not None and len(three["interpretable_xy"]) == 3


def test_paper_check_bans_the_off_type_candidates():
    checker = _checker()
    rx = re.compile(checker.NSL_OFF_TYPE, re.I)
    for name in ("Brookings Institution", "Mercatus Center", "Democratic Party",
                 "Greenpeace", "Federal Reserve System", "National Rally",
                 "brookings\\_institution"):
        assert rx.search(name), name
    for kept in ("Emmanuel Macron", "Russia", "Anthropic", "Democrats toward Green"):
        assert not rx.search(kept), kept
    rules = {(p, where) for p, where, _, _ in checker.BANNED}
    assert (checker.NSL_OFF_TYPE, "everywhere") in rules
    assert ("Green Party", "appendix/judge_free_check.tex") in rules
