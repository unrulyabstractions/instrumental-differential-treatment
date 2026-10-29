"""A fresh base sample must be independent of the shared base it replaces.

The fleet collector seeds its engine from a label. Re-running it with an old
label could redraw the same base replies, and pointing it at the old base file
would extend that file through the resume logic. These cases pin the guard
that refuses both, without a GPU: vllm is stubbed so the script imports.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

from src.common.random_seed import seed_from_label

SCRIPT = Path(__file__).resolve().parents[2] / "script/pipeline/collect_auditbench_fleet.py"


@pytest.fixture()
def fleet(monkeypatch):
    vllm = types.ModuleType("vllm")
    vllm.LLM = vllm.SamplingParams = vllm.TokensPrompt = object
    lora = types.ModuleType("vllm.lora")
    request = types.ModuleType("vllm.lora.request")
    request.LoRARequest = object
    for name, mod in (("vllm", vllm), ("vllm.lora", lora), ("vllm.lora.request", request)):
        monkeypatch.setitem(sys.modules, name, mod)
    spec = importlib.util.spec_from_file_location("collect_auditbench_fleet", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(fleet, monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["collect_auditbench_fleet.py", "--promptset", "p",
                                      "--base", "b", "--adapter-root", "a", "--out", "o",
                                      "--organisms", "x", *argv])
    fleet.main()


def test_base_arm_without_its_own_directory_is_refused(fleet, monkeypatch):
    with pytest.raises(SystemExit, match="needs --base-out"):
        _run(fleet, monkeypatch, "--seed-label", "auditbench-nullext-b")


@pytest.mark.parametrize("label", ["auditbench-collect", "auditbench-fleet"])
def test_old_seed_labels_are_refused_for_a_base_arm(fleet, monkeypatch, tmp_path, label):
    with pytest.raises(SystemExit, match="needs --base-out"):
        _run(fleet, monkeypatch, "--base-out", str(tmp_path / "b"), "--seed-label", label)


def test_new_label_seeds_differently_from_both_old_ones():
    new = seed_from_label("auditbench-nullext-b")
    assert new not in {seed_from_label("auditbench-collect"), seed_from_label("auditbench-fleet")}


def test_first_run_records_the_label(fleet, tmp_path):
    fleet.check_base_seed(tmp_path / "b", "auditbench-nullext-b")
    assert (tmp_path / "b" / "seed_label.txt").read_text().strip() == "auditbench-nullext-b"


def test_resume_with_the_same_label_is_allowed(fleet, tmp_path):
    fleet.check_base_seed(tmp_path, "auditbench-nullext-b")
    (tmp_path / "responses_base.jsonl").write_text("{}\n")
    fleet.check_base_seed(tmp_path, "auditbench-nullext-b")


def test_resume_with_another_label_is_refused(fleet, tmp_path):
    fleet.check_base_seed(tmp_path, "auditbench-nullext-b")
    with pytest.raises(SystemExit, match="was started with seed"):
        fleet.check_base_seed(tmp_path, "auditbench-nullext-c")


def test_an_unlabelled_existing_base_file_is_never_extended(fleet, tmp_path):
    (tmp_path / "responses_base.jsonl").write_text("{}\n")
    with pytest.raises(SystemExit, match="no recorded seed label"):
        fleet.check_base_seed(tmp_path, "auditbench-nullext-b")


def test_skip_base_keeps_the_old_default_label(fleet, monkeypatch):
    # The organism-only path must still reach the engine with the default seed.
    seen = {}

    class Stop(Exception):
        pass

    def fake_backend(**kw):
        seen.update(kw)
        raise Stop

    monkeypatch.setattr(fleet, "load_prompt_sets", lambda p: {"c": [{}]})
    monkeypatch.setattr(fleet, "VllmBatchBackend", fake_backend)
    with pytest.raises(Stop):
        _run(fleet, monkeypatch, "--skip-base")
    assert seen["seed_label"] == "auditbench-fleet"
