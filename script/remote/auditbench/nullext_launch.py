"""Rent the one 4-GPU box for the null extension, or lose at most minutes trying.

    uv run python script/remote/auditbench/nullext_launch.py            # dry run: prints the offer
    YES=1 uv run python script/remote/auditbench/nullext_launch.py      # rents (owner approval only)

The box samples a fresh Llama-3.3-70B base and two synthetic-document nulls on
vLLM 0.11.0 (tmp/null_extension_plan.md). This script only rents and proves the
box healthy; provisioning is a separate step.

No money is lost to a bad host (B55). Vast bills GPU time only while an instance
runs, so every failure path destroys by id before anything of ours is on the box:

* an instance that is not running within LOAD_TIMEOUT_S, or whose host reports
  offline, exited or unknown;
* no authenticated ssh within SSH_SLA_S of running, on either endpoint;
* an arrival check that fails: the container label is not ``C.<id>``, the disk
  is short, the GPUs are not 4 idle cards of at least 80 GB, a card is
  power-capped below 90% of its default limit (a capped A100 once ran a stage
  four times slower), CUDA does not really initialise, or the download rate is
  below MIN_DOWNLOAD_MBPS.

Any 4-card box of 80 GB or more per card holds the 141 GB of bf16 weights at
tensor-parallel size 4, the split the nulls used. The cheapest offer that passes
every check wins; the offer churns by the hour, so nothing is pinned here.

A failed machine is blocklisted by machine id, never by offer id, since one
machine serves many offers. After MAX_TRIES failures the script stops.

Every created id is written to tmp/r2_my_instances.txt and labelled the moment
``create`` returns, so the capture gate and list_instances.py can see it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

LABEL = "idt-r2-nullext"
IMAGE = "vastai/pytorch:cuda-12.8.1-auto"
# 141 GB of weights, 6.7 GB of adapters, about 10 GB of vLLM and its wheels.
MAX_DISK_GB = 400
MIN_DISK_GB = 220
MAX_DPH = 25.0
MIN_CREDIT = 35.0
MAX_TRIES = 3
LOAD_TIMEOUT_S = 900
SSH_SLA_S = 240
MIN_DOWNLOAD_MBPS = 400
GPU_NAMES = ("H200", "H100 SXM", "H100 NVL", "A100 SXM4", "A100 PCIE")
QUERY = ("num_gpus=4 gpu_name in [H200,H100_SXM,H100_NVL,A100_SXM4,A100_PCIE] gpu_ram>=79 "
         "reliability>0.99 rentable=true inet_down>=1000 disk_space>=230 cuda_max_good>=12.8")
REGISTRY = Path("tmp/r2_my_instances.txt")
BLOCKLIST = Path("tmp/nullext_bad_machines.txt")
ENDPOINT = Path("tmp/nullext_endpoint.json")
KEYS = [Path.home() / ".ssh/id_ed25519", Path.home() / ".ssh/vast_recover"]
# A public, ungated 3.3 GB file on the Hub, used only to time the link.
SPEED_URL = ("https://huggingface.co/auditing-agents/llama_70b_synth_docs_only_emotional_bond"
             "/resolve/main/adapter_model.safetensors")


def log(msg: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def vast(*args: str, timeout: int = 120) -> str:
    out = subprocess.run(["vastai", *args], capture_output=True, text=True, timeout=timeout)
    if out.returncode != 0:
        raise RuntimeError(f"vastai {' '.join(args[:2])} failed: {out.stderr.strip()[:300]}")
    return out.stdout


def all_instances() -> list[dict]:
    """Every instance on the account, every page, or an exception."""
    rows, token = [], None
    for _ in range(50):
        args = ["show", "instances-v1", "--raw"] + (["--next-token", token] if token else [])
        page = json.loads(vast(*args))
        rows += page.get("instances", []) if isinstance(page, dict) else page
        token = page.get("next_token") if isinstance(page, dict) else None
        if not token:
            return rows
    raise RuntimeError("instance listing did not end after 50 pages")


def instance(iid: int) -> dict | None:
    return next((r for r in all_instances() if r.get("id") == iid), None)


def blocked() -> set[str]:
    if not BLOCKLIST.exists():
        return set()
    return {line.split()[0] for line in BLOCKLIST.read_text().splitlines() if line.strip()}


def block(machine_id, reason: str) -> None:
    BLOCKLIST.parent.mkdir(parents=True, exist_ok=True)
    with BLOCKLIST.open("a") as fh:
        fh.write(f"{machine_id} {time.strftime('%F')} {reason}\n")


def pick_offer() -> dict:
    offers = json.loads(vast("search", "offers", QUERY, "-o", "dph_total", "--raw"))
    ours = {str(r.get("machine_id")) for r in all_instances()}
    bad = blocked()
    for o in offers:
        # Re-check every filtered field: CLI filters have silently dropped before.
        ok = (o.get("num_gpus") == 4 and str(o.get("gpu_name")) in GPU_NAMES
              and o.get("gpu_ram", 0) >= 79_000 and o.get("reliability", 0) > 0.99
              and o.get("inet_down", 0) >= 1000 and o.get("disk_space", 0) >= MIN_DISK_GB + 10
              and float(o.get("cuda_max_good", 0)) >= 12.8 and o.get("dph_total", 99) <= MAX_DPH
              and (o.get("inet_down_cost") or 0) <= 0.02
              and str(o.get("machine_id")) not in bad | ours)
        if ok:
            return o
    raise SystemExit("no offer passes every check; nothing rented")


def ssh(host: str, port: str, cmd: str, timeout: int = 60) -> subprocess.CompletedProcess:
    for key in KEYS:
        try:
            out = subprocess.run(
                ["ssh", "-F", "/dev/null", "-i", str(key), "-o", "IdentitiesOnly=yes",
                 "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
                 "-o", "ConnectTimeout=10", "-o", "BatchMode=yes", "-p", port,
                 f"root@{host}", cmd], capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            continue
        if out.returncode != 255:
            return out
    return subprocess.CompletedProcess(cmd, 255, "", "ssh failed on every key")


def endpoints(info: dict) -> list[tuple[str, str]]:
    eps = []
    mapped = (info.get("ports") or {}).get("22/tcp") or []
    if info.get("public_ipaddr") and mapped:
        eps.append((info["public_ipaddr"].strip(), str(mapped[0]["HostPort"])))
    if info.get("ssh_host"):
        eps.append((str(info["ssh_host"]), str(info["ssh_port"])))
    return eps


ARRIVAL = f"""set -u
cat /root/.vast_containerlabel 2>/dev/null; echo
df -BG --output=avail / | tail -1 | tr -dc 0-9; echo
nvidia-smi --query-gpu=memory.total,memory.used,power.limit,power.default_limit --format=csv,noheader,nounits | tr '\\n' ';'; echo
nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1
/venv/main/bin/python -c "import torch; torch.zeros(1).cuda(); print(torch.cuda.device_count())" 2>&1 | tail -1
S=$(date +%s.%N); curl -s -L -r 0-1073741823 --max-time 30 -o /dev/null -w '%{{size_download}}' '{SPEED_URL}'; E=$(date +%s.%N); echo; echo "$S $E"
"""


def arrival_check(iid: int, host: str, port: str) -> str | None:
    """None when the box is healthy, else the reason it is not."""
    out = ssh(host, port, ARRIVAL, timeout=90)
    if out.returncode != 0:
        return f"arrival script failed rc={out.returncode}: {out.stderr.strip()[:200]}"
    lines = out.stdout.strip().splitlines()
    if len(lines) < 7:
        return f"arrival output short: {lines}"
    label, disk, gpus, driver, cuda, size, span = lines[:7]
    if label.strip() != f"C.{iid}":
        return f"container label {label!r} is not C.{iid}"
    if not disk.isdigit() or int(disk) < MIN_DISK_GB:
        return f"disk {disk} GB below {MIN_DISK_GB}"
    cards = [[float(x) for x in c.split(",")] for c in gpus.strip(";").split(";") if c]
    if len(cards) != 4 or any(t < 79_000 or u > 2048 for t, u, _, _ in cards):
        return f"GPUs not 4 idle cards of 80 GB or more: {gpus}"
    if any(lim < 0.9 * default for _, _, lim, default in cards):
        return f"a card is power-capped below 90% of its default limit: {gpus}"
    if cuda.strip() != "4":
        return f"CUDA did not initialise on 4 devices: {cuda!r}"
    start, end = (float(x) for x in span.split())
    mbps = int(size) * 8 / 1e6 / max(end - start, 1e-3)
    if mbps < MIN_DOWNLOAD_MBPS:
        return f"download {mbps:.0f} Mb/s below {MIN_DOWNLOAD_MBPS}"
    log(f"arrival OK: label {label}, disk {disk} GB, 4 GPUs {gpus}, driver {driver}, "
        f"download {mbps:.0f} Mb/s")
    return None


def destroy_unprovisioned(iid: int, machine_id, reason: str) -> None:
    """Destroy a box nothing of ours ever reached, and prove it gone."""
    log(f"DESTROY {iid} (never provisioned): {reason}")
    block(machine_id, f"instance {iid}: {reason}")
    vast("destroy", "instance", str(iid), "--yes")
    for _ in range(12):
        if instance(iid) is None:
            log(f"{iid} confirmed gone across every page")
            return
        time.sleep(10)
    raise SystemExit(f"{iid} still listed after destroy; IT MAY STILL BILL. Check by hand.")


def try_once() -> bool:
    offer = pick_offer()
    log(f"offer {offer['id']} machine {offer['machine_id']} 4x{offer['gpu_name']} "
        f"${offer['dph_total']:.2f}/h rel {offer['reliability']:.4f} "
        f"cuda {offer['cuda_max_good']} down {offer['inet_down']:.0f} Mb/s {offer.get('geolocation')}")
    if os.environ.get("YES") != "1":
        log("dry run: nothing rented (YES=1 rents, with the owner's approval)")
        sys.exit(0)
    pub = (Path.home() / ".ssh/vast_recover.pub").read_text().strip()
    onstart = ("(while true; do mkdir -p /root/.ssh; touch /root/.ssh/authorized_keys; "
               f"grep -qF '{pub}' /root/.ssh/authorized_keys || echo '{pub}' >> /root/.ssh/authorized_keys; "
               "chown -R 0:0 /root/.ssh; chmod 700 /root/.ssh; chmod 600 /root/.ssh/authorized_keys; "
               "chmod g-w,o-w /root; sleep 30; done) >/dev/null 2>&1 &\nentrypoint.sh")
    disk = min(MAX_DISK_GB, int(offer["disk_space"]) - 10)
    created = json.loads(vast("create", "instance", str(offer["id"]), "--image", IMAGE,
                              "--disk", str(disk), "--label", LABEL, "--ssh", "--direct",
                              "--cancel-unavail", "--env", "-e propagate_user_keys=true",
                              "--onstart-cmd", onstart, "--raw"))
    iid = int(created["new_contract"])
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    with REGISTRY.open("a") as fh:
        fh.write(f"{iid} {LABEL}\n")
    log(f"created {iid}; registered in {REGISTRY}")

    t0 = time.time()
    while True:
        info = instance(iid)
        state = (info or {}).get("actual_status")
        if state == "running":
            break
        if state in ("offline", "exited", "unknown") or time.time() - t0 > LOAD_TIMEOUT_S:
            destroy_unprovisioned(iid, offer["machine_id"], f"state {state} after {time.time() - t0:.0f}s")
            return False
        time.sleep(15)
    log(f"{iid} running after {time.time() - t0:.0f}s; ssh SLA {SSH_SLA_S}s")

    deadline = time.time() + SSH_SLA_S
    while time.time() < deadline:
        for host, port in endpoints(instance(iid) or {}):
            if ssh(host, port, "true", timeout=20).returncode == 0:
                reason = arrival_check(iid, host, port)
                if reason:
                    destroy_unprovisioned(iid, offer["machine_id"], reason)
                    return False
                ENDPOINT.write_text(json.dumps({"id": iid, "host": host, "port": port,
                                                "machine_id": offer["machine_id"],
                                                "dph_offer": offer["dph_total"],
                                                "dph_live": (instance(iid) or {}).get("dph_total"),
                                                "ready_at": time.strftime("%FT%T%z")}, indent=1))
                log(f"READY {iid} at {host}:{port}; endpoint in {ENDPOINT}")
                return True
        time.sleep(15)
    logs = subprocess.run(["vastai", "logs", str(iid), "--tail", "30"],
                          capture_output=True, text=True, timeout=120)
    log(f"vastai logs {iid}:\n{logs.stdout[-2000:]}")
    destroy_unprovisioned(iid, offer["machine_id"], f"no ssh within {SSH_SLA_S}s of running")
    return False


def main() -> None:
    if "x" in os.environ.get("SHELLOPTS", ""):
        raise SystemExit("xtrace is on; refusing")
    user = json.loads(vast("show", "user", "--raw"))
    if float(user.get("credit", 0)) < MIN_CREDIT:
        raise SystemExit(f"credit ${user.get('credit')} below ${MIN_CREDIT}; nothing rented")
    if any((r.get("label") or "") == LABEL for r in all_instances()):
        raise SystemExit(f"an instance labelled {LABEL} already exists; refusing a second")
    for attempt in range(1, MAX_TRIES + 1):
        log(f"attempt {attempt}/{MAX_TRIES}")
        if try_once():
            return
    raise SystemExit(f"{MAX_TRIES} hosts failed; stopping. Nothing is left running.")


if __name__ == "__main__":
    main()
