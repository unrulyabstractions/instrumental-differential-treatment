"""The exact-stack watcher's decisions, offline: fake status and teardown scripts stand in for the box, and no
vast call is made. Each case checks which teardown (or stop) the watcher runs for one status exit code."""
from __future__ import annotations

import importlib.util
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
D = REPO / "script/remote/auditbench/exact_stack"
IID = 4242


def load(tmp_path: Path, status_rc: int, teardown_rc: int = 0, deadline_min: float = 30.0, machine: dict | None = None):
    spec = importlib.util.spec_from_file_location("watch_exact_stack", D / "watch_exact_stack.py")
    W = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(W)
    W.IID = IID
    W.LAUNCH = tmp_path / "launch"
    W.BOXES = tmp_path / "boxes.json"
    W.W = {**W.W, "every_s": 0.01, "credit_every_s": 1e9, "teardown_retry_s": 0.01, "teardown_tries": 3}
    now = datetime.now(timezone.utc)
    W.BOXES.write_text(json.dumps({"boxes": [{
        "id": IID, "destroyed": False, "teardown_deadline_utc": (now + timedelta(minutes=deadline_min)).isoformat(),
        "arrived_at": (now - timedelta(minutes=11)).isoformat()}]}))
    m = json.dumps(machine or {"done": 0, "gen_started": 1, "gpu_util_max": 90, "procs": 3})
    st = tmp_path / "status.sh"
    st.write_text(f"#!/bin/bash\necho 'TP4; elapsed 1 min'\necho 'MACHINE {m}'\nexit {status_rc}\n")
    calls = tmp_path / "teardown_calls.txt"
    td = tmp_path / "teardown.sh"
    td.write_text(f"#!/bin/bash\necho \"$@\" >> {calls}\nexit {teardown_rc}\n")
    W.STATUS, W.TEARDOWN = st, td
    stops: list[str] = []
    W.stop_box = lambda why: stops.append(why)
    W.credit = lambda: 40.0
    return W, calls, stops


def run(W):
    with pytest.raises(SystemExit) as e:
        W.main()
    return e.value.code


@pytest.mark.parametrize("rc,want", [(4, f"{IID}"), (5, f"{IID} --stop"), (3, f"{IID} --stop")])
def test_status_exit_codes_pick_the_teardown(tmp_path, rc, want):
    W, calls, stops = load(tmp_path, rc)
    assert run(W) == 0
    assert calls.read_text().splitlines() == [want] and not stops


def test_low_credit_captures_and_destroys(tmp_path):
    W, calls, stops = load(tmp_path, 0)
    W.W["credit_every_s"] = 0.0
    W.credit = lambda: 3.0
    assert run(W) == 0
    assert calls.read_text().splitlines() == [f"{IID} --stop"]


def test_hung_generation_is_stopped(tmp_path):
    W, calls, stops = load(tmp_path, 0, machine={"done": 0, "gen_started": 1, "gpu_util_max": 0, "procs": 3})
    W.W["hung_gpu_idle_minutes"] = 0.001
    assert run(W) == 0
    assert calls.read_text().splitlines() == [f"{IID} --stop"]


def test_no_process_and_no_marker_is_torn_down(tmp_path):
    W, calls, stops = load(tmp_path, 0, machine={"done": 0, "gen_started": 0, "gpu_util_max": 0, "procs": 0})
    assert run(W) == 0
    assert calls.read_text().splitlines() == [f"{IID}"]


def test_failed_teardowns_end_in_a_stop_never_a_destroy(tmp_path):
    W, calls, stops = load(tmp_path, 4, teardown_rc=1)
    assert run(W) == 0
    assert calls.read_text().splitlines() == [f"{IID}", f"{IID} --stop", f"{IID} --stop"]
    assert len(stops) == 1


def test_unreachable_past_the_deadline_is_stopped(tmp_path):
    W, calls, stops = load(tmp_path, 1, deadline_min=-30.0)
    assert run(W) == 0
    assert not calls.exists() and len(stops) == 1


def test_unreachable_before_the_deadline_waits(tmp_path):
    W, calls, stops = load(tmp_path, 1, deadline_min=30.0)
    n = {"k": 0}
    real = W.status

    def status():
        n["k"] += 1
        if n["k"] > 20:
            data = json.loads(W.BOXES.read_text())
            data["boxes"][0]["destroyed"] = True
            W.BOXES.write_text(json.dumps(data))
        return real()
    W.status = status
    assert run(W) == 0
    assert not calls.exists() and not stops and n["k"] > 20


def test_one_watcher_per_id(tmp_path):
    W, calls, stops = load(tmp_path, 4)
    W.LAUNCH.mkdir(parents=True)
    (W.LAUNCH / f"watch_{IID}.lock").mkdir()
    import os
    (W.LAUNCH / f"watch_{IID}.pid").write_text(f"{os.getpid()} x\n")
    code = run(W)
    assert isinstance(code, str) and "another watcher" in code
    assert time.time() > 0 and not calls.exists()
