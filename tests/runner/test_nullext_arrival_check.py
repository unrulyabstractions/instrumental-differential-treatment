"""The null-extension launcher destroys a box whose arrival check fails (B55).

These cases feed ``arrival_check`` the output a box would print and pin which
boxes pass. A check that never fails would let a bad host bill, so each failure
reason is exercised once.
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
         size=str(1024 ** 3), span="100.0 102.0"):
    return "\n".join([label, disk, ";".join(cards) + ";", "570.124.06", cuda, size, span])


def _check(monkeypatch, stdout, rc=0):
    monkeypatch.setattr(launch, "ssh", lambda *a, **k: subprocess.CompletedProcess(
        "x", rc, stdout, ""))
    return launch.arrival_check(42, "h", "1")


def test_a_healthy_box_passes(monkeypatch):
    assert _check(monkeypatch, _box()) is None


@pytest.mark.parametrize("kwargs, reason", [
    ({"label": "C.41"}, "container label"),
    ({"disk": "150"}, "disk"),
    ({"cards": (CARD,) * 3}, "GPUs not 4"),
    ({"cards": ("40960, 1, 300.00, 300.00",) * 4}, "GPUs not 4"),
    ({"cards": ("81920, 30000, 300.00, 300.00",) + (CARD,) * 3}, "GPUs not 4"),
    ({"cards": ("81920, 1, 250.00, 300.00",) + (CARD,) * 3}, "power-capped"),
    ({"cuda": "RuntimeError: no CUDA"}, "CUDA did not initialise"),
    ({"size": "1000000", "span": "100.0 130.0"}, "download"),
])
def test_each_failure_is_caught(monkeypatch, kwargs, reason):
    assert reason in _check(monkeypatch, _box(**kwargs))


def test_a_failed_ssh_is_a_failure(monkeypatch):
    assert "rc=255" in _check(monkeypatch, "", rc=255)
