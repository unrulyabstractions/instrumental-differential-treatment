"""Drive the registered Petri cells on one rented box from this Mac, through an ssh tunnel.

    python3 script/analysis/petri_20261115/petri_drive.py --box small
    python3 script/analysis/petri_20261115/petri_drive.py --box big

The box comes from its registry (small: the court investigation's boxes.json; big: out/main/petri_20261115/
boxes.json), the one live entry with the recipe's label. For each server of the box the driver opens
``ssh -N -L <local>:127.0.0.1:<remote>``, waits for the runner's ``flags/<server>.ready`` and for /v1/models
through the tunnel, then runs the registered waves; each cell is its own petri_run_cell.py process in the Petri
venv. Before each wave it runs ``cloud_boxes_guard.py spend`` (the owner's 30-minute spend rule). When a phase
ends it writes ``flags/<server>.done`` on the box; the runner then stops that server.

Waves (REGISTRATION.md, "Order"):
  small/nsl:    the pilot (P01, one transcript) alone; then P01 and P02 together.
  small/court:  P03 and P04 together.
  big/big:      P05 to P08 together; then P09 to P12 together.
A wave starts only when the box's teardown deadline (job cap less capture reserve, in its registry entry) is at
least 25 minutes away. A pilot that fails, or a cell that exits 3 (over its bound) or 1 (stopped by its live
caps), stops every later wave: the driver writes ``flags/abort`` (the small runner then skips to the court ceiling sampling, the big
runner ends) and exits non-zero for the report. Nothing here spends except through petri_run_cell.py.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PY = REPO / "tmp/petri_env/bin/python"
CFG = json.loads((REPO / "configs/petri/petri_cells_20261115.json").read_text())
BOXES = {
    "small": (REPO / "out/main/external/court_weights_investigation_20261115/boxes.json", "idt-b74-small",
              [("nsl", [["P01_nsl_blind:pilot"], ["P01_nsl_blind", "P02_nsl_informed"]]),
               ("court", [["P03_court_blind", "P04_court_informed"]])]),
    "big": (REPO / "out/main/petri_20261115/boxes.json", "idt-b73-petri70b",
            [("big", [["P05_co_blind", "P06_co_informed", "P07_sl_blind", "P08_sl_informed"],
                      ["P09_base70_blind", "P10_base70_informed", "P11_eb_blind", "P12_eb_informed"]])]),
}
SSH = ["ssh", "-F", "/dev/null", "-i", str(Path.home() / ".ssh/id_ed25519"), "-o", "IdentitiesOnly=yes",
       "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null", "-o", "BatchMode=yes",
       "-o", "ConnectTimeout=15", "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=4"]


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}"
    print(line, flush=True)
    with open(REPO / "out/main/petri_20261115/drive.log", "a") as fh:
        fh.write(line + "\n")


def entry(reg: Path, label: str) -> dict:
    live = [b for b in json.loads(reg.read_text())["boxes"] if b.get("label") == label and not b.get("destroyed")]
    if len(live) != 1:
        raise SystemExit(f"{reg}: {len(live)} live boxes labelled {label}")
    return live[0]


def remote(e: dict, cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run([*SSH, "-p", str(e["port"]), f"root@{e['host']}", "bash", "-c", cmd],
                          capture_output=True, text=True, timeout=60)


def tunnel(e: dict, server: str) -> subprocess.Popen:
    s = CFG["servers"][server]
    return subprocess.Popen([*SSH, "-o", "ExitOnForwardFailure=yes", "-N", "-L",
                             f"{s['local_port']}:127.0.0.1:{s['remote_port']}", "-p", str(e["port"]),
                             f"root@{e['host']}"])


def wait_ready(e: dict, server: str, timeout_s: int) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        r = remote(e, f"test -e /workspace/idt/flags/{server}.ready && echo READY; "
                      f"test -e /workspace/idt/RUNNER_DONE && echo DONE")
        if "READY" in r.stdout:
            return
        if "DONE" in r.stdout:
            raise SystemExit(f"the runner ended before {server} was ready; read its runner.log")
        time.sleep(30)
    raise SystemExit(f"{server} not ready after {timeout_s}s")


def wait_models(server: str, names: list[str], timeout_s: int = 300) -> None:
    url = f"http://127.0.0.1:{CFG['servers'][server]['local_port']}/v1/models"
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                served = [m["id"] for m in json.loads(r.read())["data"]]
            if all(n in served for n in names):
                return
        except OSError:
            pass
        time.sleep(5)
    raise SystemExit(f"the tunnel to {server} does not list {names}")


WAVE_BUDGET_MIN = 25


def deadline_minutes(e: dict) -> float | None:
    """Minutes until the registry's teardown deadline (the job cap less the capture reserve)."""
    from datetime import datetime, timezone
    d = e.get("teardown_deadline_utc")
    if not d:
        return None
    return (datetime.fromisoformat(d) - datetime.now(timezone.utc)).total_seconds() / 60.0


def spend_check() -> None:
    out = subprocess.run([sys.executable, str(Path.home() / ".claude/hooks/cloud_boxes_guard.py"), "spend"],
                         capture_output=True, text=True, timeout=180)
    log("spend check:\n" + (out.stdout + out.stderr).strip()[-1500:])


def run_wave(wave: list[str]) -> dict[str, int]:
    procs = {}
    for item in wave:
        cell, _, mode = item.partition(":")
        args = [str(PY), "-m", "script.analysis.petri_20261115.petri_run_cell", "--cell", cell]
        if mode == "pilot":
            args.append("--pilot")
        logf = open(REPO / "out/main/petri_20261115" / f"drive_{cell}_{mode or 'main'}.log", "a")
        procs[item] = (subprocess.Popen(args, cwd=REPO, stdout=logf, stderr=subprocess.STDOUT), logf)
        log(f"started {item}")
    codes = {}
    for item, (p, fh) in procs.items():
        codes[item] = p.wait()
        fh.close()
        log(f"{item} exited {codes[item]}")
    return codes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--box", choices=sorted(BOXES), required=True)
    a = ap.parse_args()
    reg, label, phases = BOXES[a.box]
    e = entry(reg, label)
    log(f"box {e['id']} at {e['host']}:{e['port']}")
    failed = None
    for server, waves in phases:
        if failed:
            break
        wait_ready(e, server, 45 * 60)
        tun = tunnel(e, server)
        try:
            names = [t["served_name"] for t in CFG["targets"].values() if t["server"] == server]
            wait_models(server, names)
            for wave in waves:
                left = deadline_minutes(e)
                if left is not None and left < WAVE_BUDGET_MIN:
                    failed = {"box deadline": f"{left:.0f} min left, a wave needs {WAVE_BUDGET_MIN}"}
                    log(f"NOT STARTED {wave}: the box's teardown deadline is {left:.0f} minutes away")
                    break
                spend_check()
                codes = run_wave(wave)
                bad = {k: v for k, v in codes.items() if v != 0}
                if bad:
                    failed = bad
                    break
        finally:
            tun.terminate()
            remote(e, f"touch /workspace/idt/flags/{server}.done")
            log(f"wrote flags/{server}.done")
    if failed:
        remote(e, "touch /workspace/idt/flags/abort")
        log(f"STOPPED: {failed}; wrote flags/abort; report before any further paid step")
        return 1
    log("all registered waves of this box finished")
    return 0


if __name__ == "__main__":
    sys.exit(main())
