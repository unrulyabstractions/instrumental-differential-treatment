"""Mac side: the box cap and the idle rule in code, for one B73 or B74 box (critic blocker B2).

    nohup caffeinate -i python3 script/analysis/petri_20261115/watch_box.py <recipe.json> <instance id> \
        >> <out_rel>/launch/watch_<id>.log 2>&1 &

box_launch_core.Launch starts it detached right after the arrival checks pass, before provisioning. By hand only
when its pid is dead while the box lives. One watcher per id: it holds launch/watch_<id>.lock and writes its pid
to launch/watch_<id>.pid. Modelled on script/remote/auditbench/exact_stack/watch_exact_stack.py.

Every recipe watch.every_s it reads the registry entry and `.claude/box_progress.sh vast <id>` (read-only):
  ended ...                      the runner wrote RUNNER_DONE or nothing of ours runs -> teardown
  now >= teardown deadline       -> stop the box's work (flags/stop, then TERM and KILL of our processes),
                                    then teardown
  progress <s>, s >= stale_write_s   no write anywhere in the run for that long -> stop, then teardown
  unreachable, past the deadline plus stop_after_deadline_minutes, five polls in a row -> `vastai stop instance`
                                    (a box that cannot be captured is stopped, never destroyed), NEEDS_HUMAN
Every watch.credit_every_s it reads the live vast credit; below watch.credit_floor_usd: stop, then teardown.
Teardown is only `.claude/box_teardown.sh vast <id>` (proven capture by bytes, then destroy). A failed teardown is
retried teardown_tries times; then the box is stopped as above. After a teardown that exits 0, each recipe
``materialize`` folder is copied from the capture to its analysis path, byte sizes checked, never overwriting.
Standard library only.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))

from script.analysis.petri_20261115.box_launch_core import box_id_guard, ssh_bash  # noqa: E402

RECIPE: dict = {}
W: dict = {}
IID = 0
LAUNCH = REPO
REGISTRY = REPO


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(msg: str) -> None:
    print(f"{now()} [watch {IID}] {msg}", flush=True)


def entry() -> dict | None:
    try:
        return next((b for b in json.loads(REGISTRY.read_text())["boxes"] if b.get("id") == IID), None)
    except (OSError, ValueError, KeyError):
        return None


def progress() -> str:
    try:
        r = subprocess.run(["bash", str(REPO / ".claude/box_progress.sh"), "vast", str(IID)], cwd=REPO,
                           capture_output=True, text=True, timeout=240)
    except subprocess.TimeoutExpired:
        return "unreachable box_progress.sh timed out"
    return (r.stdout.strip().splitlines() or ["unreachable no answer"])[-1]


def decide(st: str, e: dict, t: float, unreachable: int) -> str | None:
    """The watcher's rule for one poll, as a pure function (tested free): an action name or None."""
    dl = e.get("teardown_deadline_unix")
    if st.startswith("ended"):
        return "teardown"
    # Checked before the deadline rule: past the deadline an unreachable box cannot be captured, so it is stopped.
    if st.startswith(("unreachable", "unknown")) and dl is not None and unreachable >= 5 \
            and t > float(dl) + 60 * float(W["stop_after_deadline_minutes"]):
        return "stop_box:unreachable past the deadline"
    if dl is not None and t >= float(dl):
        return "stop_then_teardown:teardown deadline"
    if st.startswith("progress"):
        try:
            age = int(st.split()[1])
        except (IndexError, ValueError):
            age = 0
        if age >= int(W["stale_write_s"]):
            return f"stop_then_teardown:no write for {age} s"
    return None


def on_box(e: dict, script: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return ssh_bash(e["host"], e["port"], box_id_guard(IID) + script, timeout=timeout)


def stop_work(e: dict, why: str) -> None:
    """flags/stop (the runner ends its phase and skips the rest), then TERM and KILL of our processes."""
    R = RECIPE["remote_root"]
    r = on_box(e, f"mkdir -p {R}/flags && touch {R}/flags/stop && echo STOP_WRITTEN")
    log(f"flags/stop ({why}): {'written' if 'STOP_WRITTEN' in r.stdout else 'NOT WRITTEN rc ' + str(r.returncode)}")
    t0 = time.time()
    while time.time() - t0 < float(W["stop_wait_s"]):
        if progress().startswith("ended"):
            break
        time.sleep(15)
    kill_procs(e)


def kill_procs(e: dict) -> None:
    procs = RECIPE["procs"].replace("'", "")
    r = on_box(e, f"pkill -TERM -f -- '{procs}' 2>/dev/null; sleep 20; pkill -KILL -f -- '{procs}' 2>/dev/null; "
                  f"sleep 3; echo LEFT $(pgrep -f -- '{procs}' | grep -c '[0-9]')", timeout=120)
    log(f"stopped our processes on the box: {r.stdout.strip()[-80:] or 'rc ' + str(r.returncode)}")


def stop_box(why: str) -> None:
    """A box the watcher cannot capture is stopped, never destroyed: its disk, the only copy, is kept."""
    r = subprocess.run(["vastai", "stop", "instance", str(IID)], capture_output=True, text=True, timeout=120)
    log(f"STOP {IID} ({why}): vastai stop rc {r.returncode} {r.stdout.strip()[:200]} {r.stderr.strip()[:200]}")
    (REPO / "tmp").mkdir(exist_ok=True)
    with open(REPO / f"tmp/NEEDS_HUMAN_{RECIPE['label']}", "a") as fh:
        fh.write(f"{now()} watcher stopped vast {IID} ({why}); its disk holds the only copy: start it, then run "
                 f".claude/box_teardown.sh vast {IID}\n")


def credit() -> float | None:
    try:
        r = subprocess.run(["vastai", "show", "user", "--raw"], capture_output=True, text=True, timeout=120)
        return float(json.loads(r.stdout)["credit"])
    except Exception:  # noqa: BLE001
        return None


def materialize() -> None:
    """Copy each captured folder the analysis reads to its own path; sizes checked; never overwrite."""
    cap = REPO / RECIPE["capture_rel"] / f"vast_{IID}" / "files"
    for m in RECIPE.get("materialize", []):
        src, dst = cap / m["from"], REPO / m["to"]
        if not src.is_dir():
            log(f"materialize: {src} is not in the capture")
            continue
        if dst.exists():
            log(f"materialize: {dst} exists; left as it is")
            continue
        shutil.copytree(src, dst)
        pairs = [(p, dst / p.relative_to(src)) for p in src.rglob("*") if p.is_file()]
        bad = [str(a) for a, b in pairs if not b.is_file() or b.stat().st_size != a.stat().st_size]
        rec = {"ts": now(), "from": str(src.relative_to(REPO)), "to": m["to"], "files": len(pairs),
               "bytes": sum(a.stat().st_size for a, _ in pairs), "size_mismatch": bad}
        (LAUNCH / f"materialize_{IID}_{Path(m['to']).name}.json").write_text(json.dumps(rec, indent=1))
        log(f"materialize: {rec['files']} files, {rec['bytes']} bytes into {m['to']}; mismatches {len(bad)}")


def finish(why: str) -> None:
    log(f"watcher ends: {why}")
    (LAUNCH / f"watch_{IID}.done").write_text(f"{now()} {why}\n")
    sys.exit(0)


def teardown(why: str) -> None:
    """Teardown with retries; ends the watcher on a destroy; stops the box when teardown cannot finish."""
    for k in range(1, int(W["teardown_tries"]) + 1):
        e = entry()
        if e is None or e.get("destroyed"):
            finish(f"the registry marks {IID} destroyed")
        kill_procs(e)
        log(f"TEARDOWN ({why}), try {k}: .claude/box_teardown.sh vast {IID}")
        try:
            r = subprocess.run(["bash", str(REPO / ".claude/box_teardown.sh"), "vast", str(IID)], cwd=REPO,
                               capture_output=True, text=True, timeout=3600)
            rc, text = r.returncode, r.stdout + r.stderr
        except subprocess.TimeoutExpired:
            rc, text = 1, "teardown timed out after 3600 s"
        for line in text.strip().splitlines()[-20:]:
            log(f"  | {line}")
        log(f"teardown exited {rc}")
        if rc == 0:
            materialize()
            finish(f"captured and destroyed after {why}")
        time.sleep(float(W["teardown_retry_s"]))
    stop_box(f"teardown could not finish after {why}")
    finish("stopped: teardown could not finish")


def main() -> None:
    LAUNCH.mkdir(parents=True, exist_ok=True)
    lock = LAUNCH / f"watch_{IID}.lock"
    try:
        os.mkdir(lock)
    except FileExistsError:
        pidf = LAUNCH / f"watch_{IID}.pid"
        old = pidf.read_text().split()[0] if pidf.exists() else ""
        try:
            if old:
                os.kill(int(old), 0)
                sys.exit(f"another watcher for {IID} runs (pid {old})")
        except (OSError, ValueError):
            pass
    (LAUNCH / f"watch_{IID}.pid").write_text(f"{os.getpid()} {now()}\n")
    log(f"watcher starts (pid {os.getpid()}); every {W['every_s']} s; registry {REGISTRY}")
    unreachable, last_credit = 0, 0.0
    while True:
        e = entry()
        if e is None:
            finish(f"{IID} is not in {REGISTRY}")
        if e.get("destroyed"):
            finish(f"the registry marks {IID} destroyed")
        if e.get("provisional"):
            time.sleep(float(W["every_s"]))
            continue
        if time.time() - last_credit >= float(W["credit_every_s"]):
            last_credit = time.time()
            c = credit()
            log(f"credit ${c:.2f}" if c is not None else "credit unreadable")
            if c is not None and c < float(W["credit_floor_usd"]):
                stop_work(e, f"credit ${c:.2f} below the floor")
                teardown(f"credit ${c:.2f} below the floor ${W['credit_floor_usd']}")
        st = progress()
        unreachable = unreachable + 1 if st.startswith(("unreachable", "unknown")) else 0
        dl = e.get("teardown_deadline_unix")
        left = (float(dl) - time.time()) / 60 if dl else float("nan")
        log(f"{st} | {left:.1f} min to the teardown deadline")
        act = decide(st, e, time.time(), unreachable)
        if act == "teardown":
            teardown(f"the runner ended ({st})")
        elif act and act.startswith("stop_then_teardown:"):
            why = act.split(":", 1)[1]
            stop_work(e, why)
            teardown(why)
        elif act and act.startswith("stop_box:"):
            stop_box(act.split(":", 1)[1])
            finish("stopped: " + act.split(":", 1)[1])
        time.sleep(float(W["every_s"]))


if __name__ == "__main__":
    if len(sys.argv) != 3 or not sys.argv[2].isdigit():
        sys.exit("usage: watch_box.py <recipe.json> <instance id>")
    RECIPE = json.loads(Path(sys.argv[1]).read_text())
    W = RECIPE["watch"]
    IID = int(sys.argv[2])
    LAUNCH = REPO / RECIPE["out_rel"] / "launch"
    REGISTRY = REPO / RECIPE["registry_rel"]
    main()
