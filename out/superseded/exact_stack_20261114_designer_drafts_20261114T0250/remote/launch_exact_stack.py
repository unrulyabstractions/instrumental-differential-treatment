"""Rent one 4x H200 box, prove it healthy, provision it and start the exact-stack sampler, or lose minutes trying.

    .venv/bin/python script/remote/auditbench/exact_stack/launch_exact_stack.py            # dry run: offer + cost
    YES=1 .venv/bin/python script/remote/auditbench/exact_stack/launch_exact_stack.py      # rents (owner-approved item #5)

Reads script/remote/auditbench/exact_stack/recipe.json; nothing is typed here from memory.

Preflight (refuses, renting nothing, unless every line holds):
  * REGISTRATION.md exists (the readings are fixed before any data) and its sha256 goes into boxes.json;
  * inputs/prompts_manifest.json, pre/t01_thresholds_n16.json and pre/g00_gate_reference.json exist;
  * the cloud-box guard: `cloud_boxes_guard.py daemon-alive --project <repo>` exits 0, and .claude/box_progress.sh
    and .claude/box_teardown.sh exist and are executable;
  * HF_TOKEN is set (read only by stage_gated_weights.py on this Mac; never printed, never sent to the box);
  * no instance on the account carries the label; vast credit >= recipe min_vast_credit_usd.

Offer: the recipe query, every field re-checked in code, cheapest first. Cost projection at the offer's rate
(dph_base + storage for disk_gb + download bandwidth) over the recipe's phase minutes, the weight fetch at
the offer's own inet_down, install and fetch overlapped. Refused above job_cap_usd ($12).

Bring-up, as nullext_launch.py (B55): every failure before the sampler starts destroys the box by id and
blocklists the machine; nothing of ours is on it but reproducible code and weights. Arrival checks: container
label C.<id>; disk; 4 idle H200 cards of at least 139,000 MiB at full power limit; driver CUDA >= 13.0;
/venv/main python 3.12; CUDA initialises on 4 devices; a 1 GiB download at >= 400 Mb/s. The launcher writes
/root/box_id, deletes /root/.vast_api_key (vast places the account key there; no key travels to a box), and
registers the box in tmp/r2_my_instances.txt at create and in boxes.json once its endpoint is known.

Provision: rsync the code, the frozen promptset and inputs/; stage the gated weights here as pre-signed URLs
(31 LFS rows, 141,124,707,792 bytes, commit 6f6073b4, else refuse); push the manifest; start box_runner.sh
detached; confirm it runs. Prints the hard-cap deadline: past it, the executor runs pull_and_teardown.sh.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
RECIPE = json.loads((HERE / "recipe.json").read_text())
BOX = RECIPE["box"]
OUT = REPO / RECIPE["out_rel"]
LAUNCH = OUT / "launch"
BOXES = OUT / "boxes.json"
REGISTRY = REPO / "tmp/r2_my_instances.txt"
BLOCKLIST = REPO / "tmp/exact_stack_bad_machines.txt"
STAGE_DIR = REPO / "tmp/weights_stage_exact_stack"
KEYS = [Path.home() / ".ssh/id_ed25519", Path.home() / ".ssh/vast_recover"]
GUARD = Path.home() / ".claude/hooks/cloud_boxes_guard.py"
SPEED_URL = ("https://huggingface.co/auditing-agents/llama_70b_synth_docs_only_emotional_bond"
             "/resolve/main/adapter_model.safetensors")
LABEL = RECIPE["label"]
REMOTE = RECIPE["remote_root"]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(msg: str) -> None:
    line = f"{now()} {msg}"
    print(line, flush=True)
    LAUNCH.mkdir(parents=True, exist_ok=True)
    with open(LAUNCH / "launch.log", "a") as fh:
        fh.write(line + "\n")


def vast(*args: str, timeout: int = 120) -> str:
    out = subprocess.run(["vastai", *args], capture_output=True, text=True, timeout=timeout)
    if out.returncode != 0:
        raise RuntimeError(f"vastai {' '.join(args[:2])} failed: {out.stderr.strip()[:300]}")
    return out.stdout


def all_instances() -> list[dict]:
    rows, token = [], None
    for _ in range(50):
        page = json.loads(vast("show", "instances-v1", "--raw", *(["--next-token", token] if token else [])))
        rows += page.get("instances", []) if isinstance(page, dict) else page
        token = page.get("next_token") if isinstance(page, dict) else None
        if not token:
            return rows
    raise RuntimeError("instance listing did not end after 50 pages")


def instance(iid: int) -> dict | None:
    for attempt in range(4):
        try:
            return next((r for r in all_instances() if r.get("id") == iid), None)
        except (RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
            log(f"listing failed ({exc}); retry {attempt + 1}/4")
            time.sleep(10)
    raise RuntimeError("instance listing failed four times")


# ------------------------------------------------------------------ registries

def register(iid: int) -> None:
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    with REGISTRY.open("a") as fh:
        fh.write(f"{iid} {LABEL}\n")
    log(f"registered {iid} in {REGISTRY}")


def boxes_update(iid: int, **fields) -> None:
    """Add or update this box's entry in boxes.json, atomically, keeping every other entry."""
    data = json.loads(BOXES.read_text()) if BOXES.exists() else {"boxes": []}
    entry = next((b for b in data["boxes"] if b.get("id") == iid), None)
    if entry is None:
        entry = {"id": iid}
        data["boxes"].append(entry)
    entry.update(fields)
    tmp = BOXES.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=1))
    os.replace(tmp, BOXES)


def blocked() -> set[str]:
    if not BLOCKLIST.exists():
        return set()
    return {line.split()[0] for line in BLOCKLIST.read_text().splitlines() if line.strip()}


def block(machine_id, reason: str) -> None:
    BLOCKLIST.parent.mkdir(parents=True, exist_ok=True)
    with BLOCKLIST.open("a") as fh:
        fh.write(f"{machine_id} {time.strftime('%F')} {reason}\n")


# ------------------------------------------------------------------ preflight

def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def preflight() -> dict:
    need = [OUT / "REGISTRATION.md", OUT / "inputs/prompts_manifest.json", OUT / "pre/t01_thresholds_n16.json",
            OUT / "pre/g00_gate_reference.json"]
    missing = [str(p) for p in need if not p.is_file()]
    if missing:
        raise SystemExit(f"preflight: missing {missing}; nothing rented")
    for name in ("box_progress.sh", "box_teardown.sh"):
        p = REPO / ".claude" / name
        if not (p.is_file() and os.access(p, os.X_OK)):
            raise SystemExit(f"preflight: {p} is missing or not executable; nothing rented")
    alive = subprocess.run([sys.executable, str(GUARD), "daemon-alive", "--project", str(REPO)],
                           capture_output=True, text=True, timeout=120)
    if alive.returncode != 0:
        raise SystemExit(f"preflight: guard refuses: {(alive.stdout + alive.stderr).strip()[:600]}")
    if not (os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")):
        raise SystemExit("preflight: HF_TOKEN is not set (needed here only, to sign the weight URLs)")
    if any((r.get("label") or "") == LABEL for r in all_instances()):
        raise SystemExit(f"preflight: an instance labelled {LABEL} already exists; refusing a second")
    user = json.loads(vast("show", "user", "--raw"))
    credit = float(user.get("credit", 0))
    if credit < BOX["min_vast_credit_usd"]:
        raise SystemExit(f"preflight: vast credit ${credit:.2f} below ${BOX['min_vast_credit_usd']}; nothing rented")
    return {"credit_start": credit, "registration_sha256": sha256_file(OUT / "REGISTRATION.md")}


# ------------------------------------------------------------------ offer and cost

def projection(o: dict) -> dict:
    """Whole-job cost at this offer's rate: the recipe's phase minutes, fetch at the offer's inet_down."""
    pm = RECIPE["phase_minutes"]
    gb = RECIPE["weights"]["lfs_bytes"] / 1e9
    fetch_min = gb * 8e3 / float(o["inet_down"]) / 60.0
    minutes = (pm["create_to_ready"] + pm["stage_and_push_manifest"] + max(pm["push_and_install"], fetch_min)
               + pm["engine_init"] + pm["sampling"] + pm["pull_capture_destroy"])
    rate = float(o["dph_base"]) + float(o.get("storage_cost") or 0) * BOX["disk_gb"] / 720.0
    bandwidth = float(o.get("inet_down_cost") or 0) * (gb + 6.0)
    cost = rate * minutes / 60.0 + bandwidth
    cap_min = (BOX["hard_cap_usd"] - bandwidth) / rate * 60.0
    job_min = (BOX["job_cap_usd"] - bandwidth) / rate * 60.0
    return {"minutes": round(minutes, 2), "fetch_minutes": round(fetch_min, 2), "rate_usd_h": round(rate, 4),
            "bandwidth_usd": round(bandwidth, 4), "cost_usd": round(cost, 2),
            "minutes_at_job_cap": round(job_min, 1), "minutes_at_hard_cap": round(cap_min, 1)}


def pick_offer() -> tuple[dict, dict]:
    offers = json.loads(vast("search", "offers", BOX["query"], "-o", "dph_total", "--raw"))
    ours = {str(r.get("machine_id")) for r in all_instances()}
    bad = blocked()
    seen = []
    want = os.environ.get("OFFER_ID")
    for o in offers:
        if want and str(o.get("id")) != want:
            continue
        ok = (o.get("num_gpus") == BOX["num_gpus"] and str(o.get("gpu_name")) in BOX["gpu_names"]
              and o.get("gpu_ram", 0) >= BOX["min_gpu_mib"] and o.get("reliability", 0) > BOX["min_reliability"]
              and o.get("inet_down", 0) >= BOX["min_inet_down_mbps"]
              and o.get("disk_space", 0) >= BOX["disk_gb"] + 10
              and float(o.get("cuda_max_good", 0)) >= BOX["min_cuda_max_good"]
              and o.get("dph_total", 99) <= BOX["max_dph"]
              and (o.get("inet_down_cost") or 0) <= BOX["max_inet_down_cost"]
              and str(o.get("machine_id")) not in bad | ours)
        pj = projection(o) if ok else None
        seen.append({"id": o.get("id"), "machine_id": o.get("machine_id"), "gpus": f"{o.get('num_gpus')}x{o.get('gpu_name')}",
                     "dph_total": o.get("dph_total"), "inet_down": o.get("inet_down"), "reliability": o.get("reliability"),
                     "cuda_max_good": o.get("cuda_max_good"), "driver": o.get("driver_version"),
                     "geo": o.get("geolocation"), "passes_filters": ok, "projection": pj})
        if ok and pj["cost_usd"] <= BOX["job_cap_usd"]:
            (LAUNCH / "offers_read.json").write_text(json.dumps({"ts": now(), "offers": seen}, indent=1))
            return o, pj
    LAUNCH.mkdir(parents=True, exist_ok=True)
    (LAUNCH / "offers_read.json").write_text(json.dumps({"ts": now(), "offers": seen}, indent=1))
    raise SystemExit(f"no offer passes every check within ${BOX['job_cap_usd']}; nothing rented "
                     f"(read {len(offers)} offers, see {LAUNCH / 'offers_read.json'})")


# ------------------------------------------------------------------ ssh

def ssh(host: str, port: str, cmd: str, timeout: int = 60) -> subprocess.CompletedProcess:
    for key in KEYS:
        try:
            out = subprocess.run(
                ["ssh", "-F", "/dev/null", "-i", str(key), "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=no",
                 "-o", "UserKnownHostsFile=/dev/null", "-o", "ConnectTimeout=10", "-o", "BatchMode=yes",
                 "-p", port, f"root@{host}", "bash -s"], input=cmd, capture_output=True, text=True, timeout=timeout)
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


def arrival_script(iid: int) -> str:
    return f"""set -u
echo "LABEL=$(tr -d '[:space:]' < /root/.vast_containerlabel 2>/dev/null)"
echo "DISK=$(df -BG --output=avail /workspace 2>/dev/null | tail -1 | tr -dc 0-9)"
echo "GPUS=$(nvidia-smi --query-gpu=name,memory.total,memory.used,power.limit,power.default_limit --format=csv,noheader,nounits | tr '\\n' ';')"
echo "DRIVER=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1)"
echo "CUDADRV=$(nvidia-smi | grep -o 'CUDA Version: [0-9.]*' | head -1 | tr -dc 0-9.)"
echo "PYV=$(/venv/main/bin/python -c 'import platform;print(platform.python_version())' 2>&1 | tail -1)"
echo "TORCHV=$(/venv/main/bin/python -c 'import importlib.metadata as m;print(m.version("torch"))' 2>&1 | tail -1)"
echo "CUDA=$(/venv/main/bin/python -c 'import torch; torch.zeros(1).cuda(); print(torch.cuda.device_count())' 2>&1 | tail -1)"
S=$(date +%s.%N); B=$(curl -s -L -r 0-1073741823 --max-time 30 -o /dev/null -w '%{{size_download}}' '{SPEED_URL}'); E=$(date +%s.%N)
echo "SPEED=$B $S $E"
if [ -e /root/.vast_api_key ]; then echo "VASTKEY=present"; rm -f /root/.vast_api_key; else echo "VASTKEY=absent"; fi
echo {iid} > /root/box_id && echo "BOXID=$(cat /root/box_id)"
"""


def arrival_check(iid: int, host: str, port: str) -> tuple[str | None, dict]:
    out = ssh(host, port, arrival_script(iid), timeout=120)
    if out.returncode != 0:
        return f"arrival script failed rc={out.returncode}: {out.stderr.strip()[:200]}", {}
    facts = dict(line.split("=", 1) for line in out.stdout.splitlines() if "=" in line and line[:1].isupper())
    try:
        if facts["LABEL"] != f"C.{iid}":
            return f"container label {facts['LABEL']!r} is not C.{iid}", facts
        if not facts["DISK"].isdigit() or int(facts["DISK"]) < BOX["disk_gb"] - 10:
            return f"disk {facts['DISK']} GB below {BOX['disk_gb'] - 10}", facts
        cards = [[x.strip() for x in c.split(",")] for c in facts["GPUS"].strip(";").split(";") if c]
        if len(cards) != BOX["num_gpus"] or any(len(c) != 5 for c in cards):
            return f"not {BOX['num_gpus']} cards: {facts['GPUS']}", facts
        for name, total, used, lim, default in cards:
            if "H200" not in name or float(total) < BOX["min_gpu_mib"] or float(used) > 2048:
                return f"a card is not an idle H200 of {BOX['min_gpu_mib']} MiB: {facts['GPUS']}", facts
            if float(lim) < 0.9 * float(default):
                return f"a card is power-capped below 90% of its default: {facts['GPUS']}", facts
        if float(facts["CUDADRV"] or 0) < BOX["min_cuda_max_good"]:
            return f"driver CUDA {facts['CUDADRV']} below {BOX['min_cuda_max_good']}", facts
        if not facts["PYV"].startswith(RECIPE["engine"]["python"] + "."):
            return f"/venv/main python is {facts['PYV']}, base A's was {RECIPE['engine']['python']}", facts
        if facts["CUDA"].strip() != str(BOX["num_gpus"]):
            return f"CUDA did not initialise on {BOX['num_gpus']} devices: {facts['CUDA']!r}", facts
        if facts.get("BOXID") != str(iid):
            return "could not write /root/box_id", facts
        size, start, end = facts["SPEED"].split()
        mbps = int(size) * 8 / 1e6 / max(float(end) - float(start), 1e-3)
        facts["SPEED_MBPS"] = round(mbps)
    except (KeyError, ValueError) as exc:
        return f"arrival output unreadable ({exc!r}): {out.stdout[:300]!r}", facts
    if mbps < BOX["min_arrival_download_mbps"]:
        return f"download {mbps:.0f} Mb/s below {BOX['min_arrival_download_mbps']}", facts
    return None, facts


# ------------------------------------------------------------------ destroy before provisioning

def destroy_unprovisioned(iid: int, machine_id, reason: str) -> None:
    log(f"DESTROY {iid} (sampler never started; only reproducible code and weights on it): {reason}")
    if machine_id is not None:
        block(machine_id, f"instance {iid}: {reason}")
    for attempt in range(1, 6):
        try:
            vast("destroy", "instance", str(iid), "--yes")
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            log(f"destroy attempt {attempt} failed: {exc}")
        for _ in range(6):
            try:
                if instance(iid) is None:
                    log(f"{iid} confirmed gone across every page")
                    boxes_update(iid, destroyed=True, destroyed_at=now(), destroy_reason=reason)
                    return
            except RuntimeError as exc:
                log(f"cannot confirm yet: {exc}")
            time.sleep(10)
    (REPO / "tmp/NEEDS_HUMAN_exact_stack").write_text(f"{now()} instance {iid} may still bill: {reason}\n")
    raise SystemExit(f"{iid} still listed after five destroys; IT MAY STILL BILL")


# ------------------------------------------------------------------ provisioning

def rsync(host: str, port: str, src: list[str], dest: str, timeout: int = 600) -> None:
    rs = (f"ssh -F /dev/null -i {KEYS[0]} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no "
          f"-o UserKnownHostsFile=/dev/null -o ConnectTimeout=20 -p {port}")
    out = subprocess.run(["rsync", "-az", "--timeout=120", "-R", "-e", rs, *src, f"root@{host}:{dest}"],
                         cwd=REPO, capture_output=True, text=True, timeout=timeout)
    if out.returncode != 0:
        raise RuntimeError(f"rsync {src[:2]} failed rc={out.returncode}: {out.stderr.strip()[:300]}")


def stage_weights() -> Path:
    """Pre-signed URLs, made here with the local HF token; the token never leaves this Mac."""
    if STAGE_DIR.exists():
        shutil.move(str(STAGE_DIR), str(REPO / f"tmp/weights_stage_exact_stack.superseded.{int(time.time())}"))
    out = subprocess.run([str(REPO / ".venv/bin/python"), "script/remote/boxes/stage_gated_weights.py",
                          "--repo", RECIPE["weights"]["repo"], "--dest", str(STAGE_DIR)],
                         cwd=REPO, capture_output=True, text=True, timeout=600)
    if out.returncode != 0:
        raise RuntimeError(f"staging failed: {out.stderr.strip()[-300:]}")
    d = STAGE_DIR / "Llama-3.3-70B-Instruct"
    prov = json.loads((d / "_provenance.json").read_text())
    if prov["commit"] != RECIPE["weights"]["commit"]:
        raise RuntimeError(f"weights commit {prov['commit']} is not base A's {RECIPE['weights']['commit']}")
    m = d / "_lfs_manifest.tsv"
    rows = [r for r in m.read_text().splitlines() if r and not r.startswith("original/")]
    m.write_text("".join(r + "\n" for r in rows))
    nbytes = sum(int(r.split("\t")[1]) for r in rows)
    if len(rows) != RECIPE["weights"]["lfs_files"] or nbytes != RECIPE["weights"]["lfs_bytes"]:
        raise RuntimeError(f"manifest has {len(rows)} rows, {nbytes} bytes; want "
                           f"{RECIPE['weights']['lfs_files']}, {RECIPE['weights']['lfs_bytes']}")
    if (d / "original").exists():
        shutil.rmtree(d / "original")
    log(f"staged {len(rows)} signed URLs, {nbytes} bytes, commit {prov['commit'][:12]}")
    return d


def provision(iid: int, host: str, port: str) -> None:
    rsync(host, port, ["src", "script", "configs", "pyproject.toml", RECIPE["promptset"]["dir"],
                       f"{RECIPE['out_rel']}/inputs/prompts_manifest.json"], REMOTE)
    log("pushed code, promptset and manifest")
    d = stage_weights()
    rs = (f"ssh -F /dev/null -i {KEYS[0]} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no "
          f"-o UserKnownHostsFile=/dev/null -o ConnectTimeout=20 -p {port}")
    ssh(host, port, f"mkdir -p {REMOTE}/models/Llama-3.3-70B-Instruct")
    out = subprocess.run(["rsync", "-az", "--timeout=120", "-e", rs, f"{d}/",
                          f"root@{host}:{REMOTE}/models/Llama-3.3-70B-Instruct/"], capture_output=True, text=True,
                         timeout=300)
    if out.returncode != 0:
        raise RuntimeError(f"manifest push failed: {out.stderr.strip()[:300]}")
    start = (f"cd {REMOTE} && nohup setsid bash script/remote/auditbench/exact_stack/box_runner.sh "
             f"> /dev/null 2>&1 < /dev/null & sleep 20; "
             f"pgrep -f 'exact_stack/box_runner.sh' > /dev/null && echo RUNNER_UP; "
             f"tail -3 {REMOTE}/{RECIPE['box_rel']}/runner.log")
    res = ssh(host, port, start, timeout=90)
    (LAUNCH / "start.txt").write_text(res.stdout + res.stderr)
    if "RUNNER_UP" not in res.stdout:
        raise RuntimeError(f"runner did not start: {res.stdout[-300:]}")
    log("box_runner.sh is running")


# ------------------------------------------------------------------ main flow

def try_once(state: dict) -> bool:
    offer, pj = pick_offer()
    log(f"offer {offer['id']} machine {offer['machine_id']} 4x{offer['gpu_name']} ${offer['dph_total']:.3f}/h "
        f"rel {offer['reliability']:.4f} cuda {offer['cuda_max_good']} driver {offer.get('driver_version')} "
        f"down {offer['inet_down']:.0f} Mb/s {offer.get('geolocation')}; projection {json.dumps(pj)}")
    spent = state["spent_usd"]
    if spent + pj["cost_usd"] > BOX["job_cap_usd"]:
        raise SystemExit(f"spent ${spent:.2f} on failed hosts + projection ${pj['cost_usd']} > ${BOX['job_cap_usd']}")
    if os.environ.get("YES") != "1":
        log("dry run: nothing rented (YES=1 rents)")
        sys.exit(0)
    pub = (Path.home() / ".ssh/vast_recover.pub").read_text().strip()
    onstart = ("(while true; do mkdir -p /root/.ssh; touch /root/.ssh/authorized_keys; "
               f"grep -qF '{pub}' /root/.ssh/authorized_keys || echo '{pub}' >> /root/.ssh/authorized_keys; "
               "chown -R 0:0 /root/.ssh; chmod 700 /root/.ssh; chmod 600 /root/.ssh/authorized_keys; "
               "chmod g-w,o-w /root; sleep 30; done) >/dev/null 2>&1 &\nentrypoint.sh")
    t_create = time.time()
    try:
        created = json.loads(vast("create", "instance", str(offer["id"]), "--image", BOX["image"],
                                  "--disk", str(BOX["disk_gb"]), "--label", LABEL, "--ssh", "--direct",
                                  "--cancel-unavail", "--env", "-e propagate_user_keys=true",
                                  "--onstart-cmd", onstart, "--raw", timeout=180))
        iid = int(created["new_contract"])
    except BaseException as exc:
        log(f"create failed ({exc!r}); searching for anything it made")
        for r in [r for r in all_instances() if (r.get("label") or "") == LABEL]:
            register(int(r["id"]))
            destroy_unprovisioned(int(r["id"]), offer["machine_id"], "create call failed")
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        return False
    register(iid)
    state["iid"] = iid
    try:
        ok = bring_up(iid, offer, pj, t_create, state)
    except BaseException as exc:
        destroy_unprovisioned(iid, offer["machine_id"], f"unexpected {exc!r}")
        ok = False
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
    if not ok:
        state["spent_usd"] += (time.time() - t_create) / 3600.0 * pj["rate_usd_h"] + 0.05
    return ok


def bring_up(iid: int, offer: dict, pj: dict, t_create: float, state: dict) -> bool:
    while True:
        info = instance(iid)
        st = (info or {}).get("actual_status")
        if st == "running":
            break
        if st in ("offline", "exited", "unknown") or time.time() - t_create > BOX["load_timeout_s"]:
            destroy_unprovisioned(iid, offer["machine_id"], f"state {st} after {time.time() - t_create:.0f}s")
            return False
        time.sleep(15)
    live = float(info.get("dph_total") or offer["dph_total"])
    log(f"{iid} running after {time.time() - t_create:.0f}s; live ${live:.3f}/h")
    pj_live = projection({**offer, "dph_base": live - (offer["dph_total"] - offer["dph_base"])})
    if pj_live["cost_usd"] > BOX["job_cap_usd"]:
        destroy_unprovisioned(iid, offer["machine_id"], f"live rate projects ${pj_live['cost_usd']} > cap")
        return False
    deadline = time.time() + BOX["ssh_sla_s"]
    while time.time() < deadline:
        for host, port in endpoints(instance(iid) or {}):
            if ssh(host, port, "true", timeout=20).returncode != 0:
                continue
            reason, facts = arrival_check(iid, host, port)
            (LAUNCH / f"arrival_{iid}.json").write_text(json.dumps({"ts": now(), "reason": reason, **facts}, indent=1))
            if reason:
                destroy_unprovisioned(iid, offer["machine_id"], reason)
                return False
            log(f"arrival OK {json.dumps({k: facts.get(k) for k in ('GPUS', 'DRIVER', 'CUDADRV', 'PYV', 'TORCHV', 'SPEED_MBPS', 'VASTKEY')})}")
            boxes_update(iid, host=host, port=int(port), label=LABEL, remote_roots=["/workspace", "/root"],
                         remote_run_dir=REMOTE, local_capture_dir=RECIPE["box_rel"],
                         done_marker=f"{REMOTE}/{RECIPE['box_rel']}/RUNNER_DONE", destroyed=False,
                         machine_id=offer["machine_id"], offer_id=offer["id"], dph_live=live,
                         created_at=datetime.fromtimestamp(t_create, timezone.utc).isoformat(timespec="seconds"),
                         hard_cap_deadline_utc=datetime.fromtimestamp(
                             t_create + pj_live["minutes_at_hard_cap"] * 60, timezone.utc).isoformat(timespec="seconds"),
                         projection=pj_live, registration_sha256=state["registration_sha256"])
            try:
                provision(iid, host, port)
            except Exception as exc:  # noqa: BLE001 the sampler never started: everything on the box is reproducible
                destroy_unprovisioned(iid, offer["machine_id"], f"provisioning failed: {exc!r}")
                return False
            mine = next(b for b in json.loads(BOXES.read_text())["boxes"] if b.get("id") == iid)
            log(f"READY {iid} at {host}:{port}; sampler started; hard-cap deadline "
                f"{mine['hard_cap_deadline_utc']} "
                f"(${BOX['hard_cap_usd']} at ${live:.3f}/h); past it run pull_and_teardown.sh destroy {iid}")
            return True
        time.sleep(15)
    destroy_unprovisioned(iid, offer["machine_id"], f"no ssh within {BOX['ssh_sla_s']}s of running")
    return False


def _sigterm(signum, frame):
    raise KeyboardInterrupt(f"signal {signum}")


def main() -> None:
    signal.signal(signal.SIGTERM, _sigterm)
    signal.signal(signal.SIGHUP, _sigterm)
    LAUNCH.mkdir(parents=True, exist_ok=True)
    if "--offers-only" in sys.argv:
        # Read-only: the offers and the projection, with no preflight and no rental possible.
        offer, pj = pick_offer()
        print(json.dumps({"offer_id": offer["id"], "machine_id": offer["machine_id"], "dph_total": offer["dph_total"],
                          "inet_down": offer["inet_down"], "reliability": offer["reliability"],
                          "cuda_max_good": offer["cuda_max_good"], "driver": offer.get("driver_version"),
                          "geo": offer.get("geolocation"), "projection": pj}, indent=1))
        return
    pre = preflight()
    log(f"preflight passed: credit ${pre['credit_start']:.2f}, registration {pre['registration_sha256'][:12]}")
    state = {"spent_usd": 0.0, **pre}
    for attempt in range(1, BOX["max_tries"] + 1):
        log(f"attempt {attempt}/{BOX['max_tries']}")
        if try_once(state):
            (LAUNCH / "launch_record.json").write_text(json.dumps({"ts": now(), **state}, indent=1))
            return
    raise SystemExit(f"{BOX['max_tries']} hosts failed; stopping. Nothing is left running.")


if __name__ == "__main__":
    main()
