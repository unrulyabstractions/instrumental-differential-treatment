"""Mac side: the box cap and the idle rule in code, for one exact-stack box (the A2 box or its rehearsal).

    nohup caffeinate -i .venv/bin/python script/remote/auditbench/exact_stack/watch_exact_stack.py <id> \
        >> out/main/auditbench/nullext/exact_stack_20261114/launch/watch_<id>.log 2>&1 &

launch_exact_stack.py starts it detached right after the arrival checks pass, before provisioning. By hand only
when status_exact_stack.sh prints WATCHER DEAD. One watcher per id: it holds launch/watch_<id>.lock and writes its
pid to launch/watch_<id>.pid.

Every recipe watch.every_s it runs status_exact_stack.sh <id> (read-only) and acts on its exit code:
  4  the runner ended                                    -> teardown_exact_stack.sh <id>
  5  the draw is complete but the runner lingers         -> teardown_exact_stack.sh <id> --stop
  3  past the teardown deadline                          -> teardown_exact_stack.sh <id> --stop
  0  and generation started, every card at 0% GPU for watch.hung_gpu_idle_minutes  -> teardown --stop
  0  and nothing of ours runs, no done marker, 3 polls in a row, 10 min after arrival -> teardown (the runner
     died without its trap, or never started)
  1  unreachable or unregistered: when boxes.json marks the id destroyed, the watcher ends; past the deadline plus
     watch.stop_after_deadline_minutes, unreachable throughout the last 5 polls: `vastai stop instance <id>`
     (a box that cannot be captured is stopped, never destroyed), tmp/NEEDS_HUMAN_exact_stack, and the watcher ends
Every watch.credit_every_s it reads the live vast credit; below watch.credit_floor_usd it runs teardown --stop (vast
stops instances at zero credit, which would freeze the box with the only copy of the draw on it).

A teardown that exits 0 (complete) or 3 (destroyed, draw incomplete) ends the watcher. Exit 1 (refused, or the
destroy not confirmed) is retried with --stop after watch.teardown_retry_s, up to watch.teardown_tries; after the
last failed try, or past the deadline plus watch.stop_after_deadline_minutes, the box is stopped as above.
Standard library only.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
RECIPE = json.loads((HERE / "recipe.json").read_text())
W = RECIPE["watch"]
OUT = REPO / RECIPE["out_rel"]
LAUNCH = OUT / "launch"
BOXES = OUT / "boxes.json"
STATUS = HERE / "status_exact_stack.sh"
TEARDOWN = HERE / "teardown_exact_stack.sh"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(msg: str) -> None:
    print(f"{now()} [watch {IID}] {msg}", flush=True)


def entry() -> dict | None:
    try:
        return next((b for b in json.loads(BOXES.read_text())["boxes"] if b.get("id") == IID), None)
    except (OSError, ValueError, KeyError):
        return None


def ts(s: str | None) -> float | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def status() -> tuple[int, str, dict]:
    try:
        r = subprocess.run(["bash", str(STATUS), str(IID)], cwd=REPO, capture_output=True, text=True, timeout=240)
    except subprocess.TimeoutExpired:
        return 1, "status timed out", {}
    text = r.stdout + r.stderr
    m = {}
    for line in r.stdout.splitlines():
        if line.startswith("MACHINE "):
            try:
                m = json.loads(line[len("MACHINE "):])
            except ValueError:
                m = {}
    return r.returncode, text, m


def teardown(stop: bool, why: str) -> int:
    cmd = ["bash", str(TEARDOWN), str(IID)] + (["--stop"] if stop else [])
    log(f"TEARDOWN ({why}): {' '.join(cmd[1:])}")
    try:
        r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=3600)
        rc, text = r.returncode, r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        rc, text = 1, "teardown timed out after 3600 s"
    for line in text.strip().splitlines()[-25:]:
        log(f"  | {line}")
    log(f"teardown exited {rc}")
    return rc


def listed() -> bool | None:
    """True / False from a complete paged listing; None when the listing fails."""
    rows, token = [], None
    try:
        for _ in range(50):
            args = ["vastai", "show", "instances-v1", "--raw"] + (["--next-token", token] if token else [])
            r = subprocess.run(args, capture_output=True, text=True, timeout=120)
            if r.returncode != 0:
                return None
            d = json.loads(r.stdout)
            rows += d.get("instances", [])
            token = d.get("next_token")
            if not token:
                return any(x.get("id") == IID for x in rows)
    except (subprocess.TimeoutExpired, ValueError, AttributeError):
        return None
    return None


def stop_box(why: str) -> None:
    """A box the watcher cannot capture is stopped, never destroyed: its disk, the only copy, is kept."""
    if listed() is False:
        log(f"{IID} is no longer listed; nothing to stop")
        return
    r = subprocess.run(["vastai", "stop", "instance", str(IID)], capture_output=True, text=True, timeout=120)
    log(f"STOP {IID} ({why}): vastai stop rc {r.returncode} {r.stdout.strip()[:200]} {r.stderr.strip()[:200]}")
    (REPO / "tmp").mkdir(exist_ok=True)
    with open(REPO / "tmp/NEEDS_HUMAN_exact_stack", "a") as fh:
        fh.write(f"{now()} watcher stopped vast {IID} ({why}); its disk holds the only copy: start it, then run "
                 f"teardown_exact_stack.sh {IID}\n")


def credit() -> float | None:
    try:
        r = subprocess.run(["vastai", "show", "user", "--raw"], capture_output=True, text=True, timeout=120)
        return float(json.loads(r.stdout)["credit"])
    except Exception:  # noqa: BLE001
        return None


def finish(why: str) -> None:
    log(f"watcher ends: {why}")
    (LAUNCH / f"watch_{IID}.done").write_text(f"{now()} {why}\n")
    sys.exit(0)


def run_teardown(first_stop: bool, why: str) -> None:
    """Teardown with retries; ends the watcher on a destroy, stops the box when teardown cannot finish."""
    stop = first_stop
    for k in range(1, int(W["teardown_tries"]) + 1):
        rc = teardown(stop, f"{why}, try {k}")
        if rc in (0, 3):
            finish(f"destroyed after {why} (teardown rc {rc})")
        e = entry()
        if e and e.get("destroyed"):
            finish(f"boxes.json marks {IID} destroyed (teardown rc {rc})")
        stop = True
        dl = ts((e or {}).get("teardown_deadline_utc"))
        if dl and time.time() > dl + 60 * float(W["stop_after_deadline_minutes"]):
            break
        time.sleep(float(W["teardown_retry_s"]))
    stop_box(f"teardown could not finish after {why}")
    finish("stopped: teardown could not finish")


def main() -> None:
    LAUNCH.mkdir(parents=True, exist_ok=True)
    lock = LAUNCH / f"watch_{IID}.lock"
    try:
        os.mkdir(lock)
    except FileExistsError:
        old = (LAUNCH / f"watch_{IID}.pid").read_text().split()[0] if (LAUNCH / f"watch_{IID}.pid").exists() else ""
        try:
            if old:
                os.kill(int(old), 0)
                sys.exit(f"another watcher for {IID} runs (pid {old})")
        except (OSError, ValueError):
            pass
    (LAUNCH / f"watch_{IID}.pid").write_text(f"{os.getpid()} {now()}\n")
    log(f"watcher starts (pid {os.getpid()}); every {W['every_s']} s")
    unreachable, idle_gpu, no_procs = 0, 0, 0
    last_credit = 0.0
    while True:
        e = entry()
        if e is None:
            finish(f"{IID} is not in {BOXES}")
        if e.get("destroyed"):
            finish(f"boxes.json marks {IID} destroyed")
        dl = ts(e.get("teardown_deadline_utc"))
        arrived = ts(e.get("arrived_at"))
        if time.time() - last_credit >= float(W["credit_every_s"]):
            last_credit = time.time()
            c = credit()
            log(f"credit ${c:.2f}" if c is not None else "credit unreadable")
            if c is not None and c < float(W["credit_floor_usd"]):
                run_teardown(True, f"credit ${c:.2f} below the floor ${W['credit_floor_usd']}")
        rc, text, m = status()
        tail = " | ".join(x for x in text.strip().splitlines()
                          if x.startswith(("TP", "CREDIT", "DONE", "PROGRESS", "ROWS", "GPU", "RUNNER", "PAST", "DRAW",
                                           "unreachable", "not registered")))
        log(f"status rc {rc}: {tail[:900]}")
        if rc == 4:
            run_teardown(False, "the runner ended")
        if rc == 5:
            run_teardown(True, "the draw is complete and the runner lingers")
        if rc == 3:
            run_teardown(True, "past the teardown deadline")
        if rc == 0:
            unreachable = 0
            idle_gpu = idle_gpu + 1 if (m.get("gen_started") and not m.get("done") and m.get("gpu_util_max", 1) == 0) else 0
            if idle_gpu * float(W["every_s"]) >= 60 * float(W["hung_gpu_idle_minutes"]):
                run_teardown(True, f"generation hung: every card at 0% for {W['hung_gpu_idle_minutes']} min")
            no_procs = no_procs + 1 if (m and m.get("procs") == 0 and not m.get("done")) else 0
            if no_procs >= 3 and arrived and time.time() - arrived > 600:
                run_teardown(False, "nothing of ours runs and the runner left no done marker")
        if rc == 1:
            unreachable += 1
            if dl and time.time() > dl + 60 * float(W["stop_after_deadline_minutes"]) and unreachable >= 5:
                stop_box("unreachable past the deadline")
                finish("stopped: unreachable past the deadline")
        time.sleep(float(W["every_s"]))


if __name__ == "__main__":
    if len(sys.argv) != 2 or not sys.argv[1].isdigit():
        sys.exit("usage: watch_exact_stack.py <instance id>")
    IID = int(sys.argv[1])
    main()
