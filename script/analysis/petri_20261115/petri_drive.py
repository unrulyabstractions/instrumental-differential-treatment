"""Drive the registered Petri cells on one rented box from this Mac, through an ssh tunnel.

    python3 script/analysis/petri_20261115/petri_drive.py --box small
    python3 script/analysis/petri_20261115/petri_drive.py --box big

The box comes from its registry (small: the court investigation's boxes.json; big: out/main/petri_20261115/
boxes.json), the one live entry with the recipe's label. The driver refuses a box without a teardown deadline or
without a live watcher (watch_box.py, which owns the cap and the teardown). For each server of the box it waits
for the runner's ``flags/<server>.ready``, opens ``ssh -N -L <local>:127.0.0.1:<remote>``, waits for /v1/models
through the tunnel, then runs the registered waves; each cell is its own petri_run_cell.py process in the Petri
venv. Before each wave it runs ``cloud_boxes_guard.py spend`` (the owner's 30-minute spend rule). When a phase
ends it writes ``flags/<server>.done`` on the box; the runner then stops that server.

Every box command goes to ``bash -s`` on stdin (box_launch_core.ssh_bash) behind a /root/box_id check, and every
flag write is read back; a flag that cannot be written is retried, then logged loudly with tmp/NEEDS_HUMAN_<label>
(the watcher's deadline still ends the box). During a wave the driver touches ``flags/<server>.alive`` every
keepalive_s, so the runner's idle rule never ends a phase whose cells still run; it restarts a dead tunnel up to
tunnel_restarts times and otherwise interrupts the wave; and at stop_margin_minutes before the teardown deadline
it interrupts every cell (SIGINT; each reconciles its ledger stage and exits 1), so the box's cap holds.

Waves (REGISTRATION.md, "Order"):
  small/nsl:    the pilot (P01, one transcript) alone; then P01 and P02 together.
  small/court:  P03 and P04 together.
  big/big:      P05 to P08 together; then P09 to P12 together.
A wave starts only when the box's teardown deadline is at least wave_min_minutes away. A pilot that fails, or a
cell that exits non-zero (3 over its bound, 1 stopped or interrupted), stops every later wave: the driver writes
``flags/abort`` (the small runner then skips to the court ceiling sampling, the big runner ends) and exits
non-zero for the report. Nothing here spends except through petri_run_cell.py.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from script.analysis.petri_20261115 import box_launch_core as core  # noqa: E402

PY = REPO / "tmp/petri_env/bin/python"
CFG = json.loads((REPO / "configs/petri/petri_cells_20261115.json").read_text())
DRIVE = CFG["drive"]
BOXES = {
    "small": (REPO / "script/analysis/court_weights_20261115/box/small_box_recipe.json",
              [("nsl", [["P01_nsl_blind:pilot"], ["P01_nsl_blind", "P02_nsl_informed"]]),
               ("court", [["P03_court_blind", "P04_court_informed"]])]),
    "big": (REPO / "script/analysis/petri_20261115/box/big_box_recipe.json",
            [("big", [["P05_co_blind", "P06_co_informed", "P07_sl_blind", "P08_sl_informed"],
                      ["P09_base70_blind", "P10_base70_informed", "P11_eb_blind", "P12_eb_informed"]])]),
}
LOG = REPO / "out/main/petri_20261115/drive.log"
RUN_ROOT = "/workspace/idt"


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a") as fh:
        fh.write(line + "\n")


def entry(reg: Path, label: str) -> dict:
    if not reg.is_file():
        raise SystemExit(f"{reg} does not exist: no box of {label} was rented")
    live = [b for b in json.loads(reg.read_text())["boxes"] if b.get("label") == label and not b.get("destroyed")]
    if len(live) != 1:
        raise SystemExit(f"{reg}: {len(live)} live boxes labelled {label}")
    return live[0]


def remote(e: dict, cmd: str, timeout: int = 60) -> subprocess.CompletedProcess:
    """``cmd`` on the box under ``bash -s``, only when /root/box_id names this entry's instance."""
    return core.ssh_bash(e["host"], e["port"], core.box_id_guard(e["id"]) + cmd, timeout=timeout)


def flag(e: dict, name: str, tries: int = 3, loud: bool = True) -> bool:
    """Write flags/<name> on the box and read it back."""
    F = f"{RUN_ROOT}/flags"
    for k in range(1, tries + 1):
        r = remote(e, f"mkdir -p {F} && touch {F}/{name} && test -e {F}/{name} && echo FLAG_OK")
        if "FLAG_OK" in r.stdout:
            return True
        log(f"flags/{name} not confirmed (try {k}, rc {r.returncode}, {(r.stdout + r.stderr).strip()[-160:]!r})")
        time.sleep(10)
    if loud:
        log(f"!! COULD NOT WRITE flags/{name} on {e['id']}; the watcher's deadline still ends the box")
        (REPO / "tmp").mkdir(exist_ok=True)
        with open(REPO / f"tmp/NEEDS_HUMAN_{e.get('label')}", "a") as fh:
            fh.write(f"{time.strftime('%FT%TZ', time.gmtime())} driver could not write flags/{name} on {e['id']}\n")
    return False


def tunnel(e: dict, server: str) -> subprocess.Popen:
    s = CFG["servers"][server]
    return subprocess.Popen([core.SSH_BIN, *core.SSH_OPTS, "-i", str(core.KEYS[0]), "-o", "ExitOnForwardFailure=yes",
                             "-N", "-L", f"{s['local_port']}:127.0.0.1:{s['remote_port']}", "-p", str(e["port"]),
                             f"root@{e['host']}"], stdin=subprocess.DEVNULL)


def probe(e: dict, server: str) -> set[str]:
    """Which of READY, DONE, STOP hold on the box; PROBE_OK when the probe itself ran on the right box."""
    r = remote(e, f"test -e {RUN_ROOT}/flags/{server}.ready && echo READY; test -e {RUN_ROOT}/RUNNER_DONE && "
                  f"echo DONE; test -e {RUN_ROOT}/flags/stop && echo STOP; echo PROBE_OK")
    return set(r.stdout.split())


def wait_ready(e: dict, server: str, timeout_s: int) -> None:
    t0, fails = time.time(), 0
    while time.time() - t0 < timeout_s:
        seen = probe(e, server)
        if "PROBE_OK" not in seen:
            fails += 1
            log(f"probe of {server} failed ({fails} in a row)")
        else:
            fails = 0
        if "READY" in seen:
            return
        if "DONE" in seen or "STOP" in seen:
            raise SystemExit(f"the runner ended or was stopped before {server} was ready; read its runner.log")
        time.sleep(30)
    raise SystemExit(f"{server} not ready after {timeout_s}s")


def wait_models(server: str, names: list[str], timeout_s: int = 300) -> bool:
    url = f"http://127.0.0.1:{CFG['servers'][server]['local_port']}/v1/models"
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                served = [m["id"] for m in json.loads(r.read())["data"]]
            if all(n in served for n in names):
                return True
        except OSError:
            pass
        time.sleep(5)
    return False


def deadline_unix(e: dict) -> float:
    d = e.get("teardown_deadline_unix")
    if d is None:
        raise SystemExit(f"box {e['id']} has no teardown deadline in its registry entry; the driver refuses it")
    return float(d)


def watcher_alive(e: dict) -> bool:
    pid = int(e.get("watcher_pid") or 0)
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def spend_check() -> None:
    out = subprocess.run([sys.executable, str(Path.home() / ".claude/hooks/cloud_boxes_guard.py"), "spend"],
                         capture_output=True, text=True, timeout=300)
    log("spend check:\n" + (out.stdout + out.stderr).strip()[-1500:])


def interrupt(procs: dict, why: str) -> None:
    """SIGINT every live cell (each reconciles its stage and exits 1); TERM, then KILL, past the grace."""
    log(f"INTERRUPTING the wave: {why}")
    for item, (p, _fh) in procs.items():
        if p.poll() is None:
            p.send_signal(signal.SIGINT)
    t0 = time.time()
    while time.time() - t0 < DRIVE["interrupt_grace_s"] and any(p.poll() is None for p, _ in procs.values()):
        time.sleep(5)
    for item, (p, _fh) in procs.items():
        if p.poll() is None:
            log(f"{item} still runs after SIGINT; TERM")
            p.terminate()
    time.sleep(20)
    for item, (p, _fh) in procs.items():
        if p.poll() is None:
            p.kill()


def run_wave(e: dict, server: str, wave: list[str], tun: dict, names: list[str]) -> tuple[dict[str, int], str | None]:
    procs = {}
    for item in wave:
        cell, _, mode = item.partition(":")
        args = [str(PY), "-m", "script.analysis.petri_20261115.petri_run_cell", "--cell", cell]
        if mode == "pilot":
            args.append("--pilot")
        logf = open(REPO / "out/main/petri_20261115" / f"drive_{cell}_{mode or 'main'}.log", "a")
        procs[item] = (subprocess.Popen(args, cwd=REPO, stdout=logf, stderr=subprocess.STDOUT,
                                        stdin=subprocess.DEVNULL), logf)
        log(f"started {item}")
    stop_at = deadline_unix(e) - 60 * DRIVE["stop_margin_minutes"]
    reason, restarts, last_keep = None, 0, 0.0
    while any(p.poll() is None for p, _ in procs.values()):
        t = time.time()
        if t - last_keep >= DRIVE["keepalive_s"]:
            last_keep = t
            flag(e, f"{server}.alive", tries=1, loud=False)
        if tun["p"].poll() is not None:
            if restarts >= DRIVE["tunnel_restarts"]:
                reason = f"the tunnel to {server} died {restarts + 1} times"
                interrupt(procs, reason)
                break
            restarts += 1
            log(f"the tunnel to {server} died (exit {tun['p'].returncode}); restart {restarts}")
            tun["p"] = tunnel(e, server)
            if not wait_models(server, names, 90):
                log(f"the restarted tunnel to {server} does not list {names}")
        if t >= stop_at:
            reason = f"{DRIVE['stop_margin_minutes']} min before the box's teardown deadline"
            interrupt(procs, reason)
            break
        time.sleep(15)
    codes = {}
    for item, (p, fh) in procs.items():
        codes[item] = p.wait()
        fh.close()
        log(f"{item} exited {codes[item]}")
    return codes, reason


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--box", choices=sorted(BOXES), required=True)
    a = ap.parse_args()
    recipe_path, phases = BOXES[a.box]
    recipe = json.loads(recipe_path.read_text())
    e = entry(REPO / recipe["registry_rel"], recipe["label"])
    dl = deadline_unix(e)
    if not watcher_alive(e):
        raise SystemExit(f"the watcher of box {e['id']} is not running (pid {e.get('watcher_pid')}); start it first: "
                         f"nohup caffeinate -i python3 {core.WATCH} {recipe_path} {e['id']} &")
    log(f"box {e['id']} at {e['host']}:{e['port']}; teardown deadline in {(dl - time.time()) / 60:.0f} min; "
        f"watcher pid {e.get('watcher_pid')}")
    failed = None
    for server, waves in phases:
        if failed:
            break
        try:
            wait_ready(e, server, 45 * 60)
        except SystemExit as exc:
            failed = {"ready": str(exc)}
            break
        names = [t["served_name"] for t in CFG["targets"].values() if t["server"] == server]
        tun = {"p": tunnel(e, server)}
        try:
            if not wait_models(server, names):
                failed = {"tunnel": f"the tunnel to {server} does not list {names}"}
            for wave in waves if not failed else []:
                left = (dl - time.time()) / 60
                if left < DRIVE["wave_min_minutes"]:
                    failed = {"box deadline": f"{left:.0f} min left, a wave needs {DRIVE['wave_min_minutes']}"}
                    log(f"NOT STARTED {wave}: the box's teardown deadline is {left:.0f} minutes away")
                    break
                spend_check()
                codes, reason = run_wave(e, server, wave, tun, names)
                bad = {k: v for k, v in codes.items() if v != 0}
                if bad or reason:
                    failed = {**bad, **({"reason": reason} if reason else {})}
                    break
        finally:
            if tun["p"].poll() is None:
                tun["p"].terminate()
            if flag(e, f"{server}.done"):
                log(f"wrote flags/{server}.done")
    if failed:
        flag(e, "abort")
        log(f"STOPPED: {failed}; wrote flags/abort; report before any further paid step")
        return 1
    log("all registered waves of this box finished")
    return 0


if __name__ == "__main__":
    sys.exit(main())
