"""The null-extension launcher destroys a box it cannot trust (B55).

``arrival_check`` is fed the output a box would print, and each failure reason is
exercised once, because a check that never fails would let a bad host bill. The
launch path is driven with a fake ``vastai``: every unexpected failure after
``create``, and a ``create`` call that errors, must end in a destroy by id.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "script/remote/auditbench/nullext_launch.py"
spec = importlib.util.spec_from_file_location("nullext_launch", SCRIPT)
launch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launch)

CARD = "81920, 1, 300.00, 300.00"


def _box(label="C.42", disk="300", cards=(CARD,) * 4, cuda="4",
         speed=f"{1024 ** 3} 100.0 102.0", blank_first=False):
    lines = [f"LABEL={label}", f"DISK={disk}", "GPUS=" + ";".join(cards) + ";",
             "DRIVER=570.124.06", f"CUDA={cuda}", f"SPEED={speed}"]
    return ("\n" if blank_first else "") + "\n".join(lines) + "\n"


def _check(monkeypatch, stdout, rc=0):
    monkeypatch.setattr(launch, "ssh", lambda *a, **k: subprocess.CompletedProcess(
        "x", rc, stdout, ""))
    return launch.arrival_check(42, "h", "1")


def test_a_healthy_box_passes(monkeypatch):
    assert _check(monkeypatch, _box()) is None


def test_a_stray_blank_line_does_not_shift_the_parse(monkeypatch):
    assert _check(monkeypatch, _box(blank_first=True)) is None


@pytest.mark.parametrize("kwargs, reason", [
    ({"label": "C.41"}, "container label"),
    ({"disk": "150"}, "disk"),
    ({"cards": (CARD,) * 3}, "GPUs not 4"),
    ({"cards": ("40960, 1, 300.00, 300.00",) * 4}, "GPUs not 4"),
    ({"cards": ("81920, 30000, 300.00, 300.00",) + (CARD,) * 3}, "GPUs not 4"),
    ({"cards": ("81920, 1, 300.00",) + (CARD,) * 3}, "GPUs not 4"),
    ({"cards": ("81920, 1, 250.00, 300.00",) + (CARD,) * 3}, "power-capped"),
    ({"cards": ("81920, 1, [N/A], 300.00",) + (CARD,) * 3}, "unreadable"),
    ({"cuda": "RuntimeError: no CUDA"}, "CUDA did not initialise"),
    ({"speed": "1000000 100.0 130.0"}, "download"),
    ({"speed": "garbage"}, "unreadable"),
])
def test_each_failure_is_caught(monkeypatch, kwargs, reason):
    assert reason in _check(monkeypatch, _box(**kwargs))


def test_missing_facts_are_a_failure(monkeypatch):
    assert "unreadable" in _check(monkeypatch, "LABEL=C.42\n")


def test_a_failed_ssh_is_a_failure(monkeypatch):
    assert "rc=255" in _check(monkeypatch, "", rc=255)


OFFER = {"id": 7, "machine_id": 9, "gpu_name": "A100 PCIE", "dph_total": 3.47,
         "reliability": 0.995, "cuda_max_good": 13.1, "inet_down": 8000.0, "disk_space": 232}


@pytest.fixture()
def rig(monkeypatch, tmp_path):
    """A fake account: records destroys, never touches vast.ai."""
    state = {"destroyed": [], "registered": [], "listing": []}
    monkeypatch.setenv("YES", "1")
    monkeypatch.setattr(launch, "pick_offer", lambda: OFFER)
    monkeypatch.setattr(launch, "REGISTRY", tmp_path / "registry.txt")
    monkeypatch.setattr(launch, "BLOCKLIST", tmp_path / "bad.txt")
    monkeypatch.setattr(launch, "NEEDS_HUMAN", tmp_path / "NEEDS_HUMAN")
    monkeypatch.setattr(launch.time, "sleep", lambda s: None)
    monkeypatch.setattr(launch.Path, "home", lambda: tmp_path)
    (tmp_path / ".ssh").mkdir()
    (tmp_path / ".ssh/vast_recover.pub").write_text("ssh-ed25519 AAAA test")

    def destroy(iid, machine_id, reason):
        state["destroyed"].append((iid, reason))

    monkeypatch.setattr(launch, "destroy_unprovisioned", destroy)
    monkeypatch.setattr(launch, "all_instances", lambda: state["listing"])
    return state


def _vast_creating(iid):
    def vast(*args, timeout=120):
        if args[:2] == ("create", "instance"):
            return '{"success": true, "new_contract": %d}' % iid
        raise AssertionError(f"unexpected vastai call {args}")
    return vast


def test_an_unexpected_error_after_create_destroys_the_box(monkeypatch, rig):
    monkeypatch.setattr(launch, "vast", _vast_creating(42))

    def boom(iid, offer):
        raise ValueError("parse error mid bring-up")

    monkeypatch.setattr(launch, "bring_up", boom)
    assert launch.try_once() is False
    assert [i for i, _ in rig["destroyed"]] == [42]
    assert "42 idt-r2-nullext" in launch.REGISTRY.read_text()


def test_an_interrupt_after_create_destroys_the_box_and_still_stops(monkeypatch, rig):
    monkeypatch.setattr(launch, "vast", _vast_creating(43))

    def interrupted(iid, offer):
        raise KeyboardInterrupt

    monkeypatch.setattr(launch, "bring_up", interrupted)
    with pytest.raises(KeyboardInterrupt):
        launch.try_once()
    assert [i for i, _ in rig["destroyed"]] == [43]


def test_a_failed_create_call_destroys_whatever_it_made(monkeypatch, rig):
    rig["listing"] = [{"id": 44, "label": "idt-r2-nullext"}]

    def vast(*args, timeout=120):
        raise subprocess.TimeoutExpired("vastai create", timeout)

    monkeypatch.setattr(launch, "vast", vast)
    assert launch.try_once() is False
    assert [i for i, _ in rig["destroyed"]] == [44]
    assert "44 idt-r2-nullext" in launch.REGISTRY.read_text()


def test_a_failed_create_that_made_nothing_destroys_nothing(monkeypatch, rig):
    def vast(*args, timeout=120):
        raise RuntimeError("vastai create failed: no such offer")

    monkeypatch.setattr(launch, "vast", vast)
    assert launch.try_once() is False
    assert rig["destroyed"] == []


def test_a_ready_box_is_not_destroyed(monkeypatch, rig):
    monkeypatch.setattr(launch, "vast", _vast_creating(45))
    monkeypatch.setattr(launch, "bring_up", lambda iid, offer: True)
    assert launch.try_once() is True
    assert rig["destroyed"] == []


def test_without_yes_nothing_is_created(monkeypatch, rig):
    monkeypatch.delenv("YES")

    def vast(*args, timeout=120):
        raise AssertionError("no vastai call may run in a dry run")

    monkeypatch.setattr(launch, "vast", vast)
    with pytest.raises(SystemExit):
        launch.try_once()
