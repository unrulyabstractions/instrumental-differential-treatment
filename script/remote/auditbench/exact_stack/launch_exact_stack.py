"""Rent one 4-card H200-class box, prove it healthy, provision it, start the exact-stack sampler and its watcher.

    .venv/bin/python script/remote/auditbench/exact_stack/launch_exact_stack.py --offers-only     # read-only
    .venv/bin/python script/remote/auditbench/exact_stack/launch_exact_stack.py                   # dry run after preflight
    YES=1 .venv/bin/python script/remote/auditbench/exact_stack/launch_exact_stack.py --rehearse  # one-card rehearsal
    .venv/bin/python script/remote/auditbench/exact_stack/launch_exact_stack.py --rehearse-report <id>
    .venv/bin/python script/remote/auditbench/exact_stack/launch_exact_stack.py --poll            # read-only wait
    YES=1 .venv/bin/python script/remote/auditbench/exact_stack/launch_exact_stack.py             # rents (B71 item #5)

Reads script/remote/auditbench/exact_stack/recipe.json; nothing is typed here from memory.

Money (recipe box.effective_cap_rule): the cap is min(job_cap_usd $30, live credit - $20 margin - the other live
instances' burn over 1.5 h - every rehearsal's recorded spend), read at preflight and again right before the
create. An offer rents only when its projection with contingency fits that cap. `cloud_boxes_guard.py spend` runs
right before every create and a failure refuses it.

Preflight (refuses, renting nothing, unless every line holds): REGISTRATION.md and the frozen inputs exist, the
gate selftest passed, the cloud-box guard's daemon-alive exits 0, both .claude adapters are executable, HF_TOKEN is
set (read only by stage_gated_weights.py on this Mac; never printed, never sent to the box), no live instance
carries this item's label or the rehearsal's, inputs/box_choice.json does not exist, and the cap is positive.

Offer (recipe box.tiers, box.tier_rule): TP4 only, base A's size; the cheapest projection wins; no card form is
preferred. Without a fitting offer the launcher stops and rents nothing. --poll only waits: it re-reads the offers
every poll_minutes (free) for up to poll_max_hours, and exits 0 when one fits (exit 2 when none did), never renting;
the session then runs the YES=1 launch, which re-reads everything. No loop here creates a billable resource
(OPERATIONS.md 3.4).

Bring-up, as nullext_launch.py (B55): every failure before the sampler starts destroys the box by id and
blocklists the machine. The box gets a provisional entry in boxes.json (the guard's registry) the moment the create
returns, so a launcher killed before arrival leaves a box the guard reads as unreachable and stops, never one it
cannot name. Arrival checks: container label C.<id>; disk; exactly 4 idle H200-class cards of at least 139,000 MiB
at full power limit; driver CUDA >= 13.0; CUDA initialises on every card; a 1 GiB download at >= 400 Mb/s. The
launcher writes /root/box_id and deletes /root/.vast_api_key (vast places the account key there; no key travels to
a box).

Provision: rsync the runner, the sampler, the recipe, the prompt manifest and inputs/box_choice.json (TP, live rate,
create time, cap: the runner's start rule and the sampler's abort read it); stage the gated weights here as
pre-signed URLs (31 LFS rows, 141,124,707,792 bytes, commit 6f6073b4, else refuse); push the manifest; start
box_runner.sh detached (it holds a start lock, so a re-sent start is a no-op); confirm it runs. Then start
watch_exact_stack.py detached on this Mac: it tears the box down when the runner ends, at the teardown deadline,
on a hung generation or a low credit, and stops it when it cannot be reached past the deadline.

--rehearse rents the cheapest one-card CUDA 13 host with the same image (recipe rehearsal, cap $1, counted inside
the job cap), runs the runner's env, install and versions stages there (no weights, no sampling), and lets the same
watcher capture and destroy it. --rehearse-report <id> reads the captured logs and writes the record the main
preflight subtracts.
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
REH = RECIPE["rehearsal"]
OUT = REPO / RECIPE["out_rel"]
LAUNCH = OUT / "launch"
BOXES = OUT / "boxes.json"
CHOICE = OUT / "inputs" / "box_choice.json"
REGISTRY = REPO / "tmp/r2_my_instances.txt"
BLOCKLIST = REPO / "tmp/exact_stack_bad_machines.txt"
STAGE_DIR = REPO / "tmp/weights_stage_exact_stack"
KEYS = [Path.home() / ".ssh/id_ed25519", Path.home() / ".ssh/vast_recover"]
GUARD = Path.home() / ".claude/hooks/cloud_boxes_guard.py"
WATCH = HERE / "watch_exact_stack.py"
SPEED_URL = ("https://huggingface.co/auditing-agents/llama_70b_synth_docs_only_emotional_bond"
             "/resolve/main/adapter_model.safetensors")
LABEL = RECIPE["label"]
REMOTE = RECIPE["remote_root"]
OURS = {LABEL, REH["label"]}


class NoOffer(Exception):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="seconds")


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

def register(iid: int, label: str) -> None:
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    with REGISTRY.open("a") as fh:
        fh.write(f"{iid} {label}\n")
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


def provisional_entry(iid: int, label: str, t_create: float, rehearsal: bool) -> None:
    """Written the moment the create returns. host 'pending' makes both adapters answer 'unreachable', so the guard
    escalates and stops a box whose launcher died before arrival, instead of reading it as 'unknown'."""
    boxes_update(iid, host="pending", port=0, label=label, remote_roots=["/workspace", "/root"],
                 remote_run_dir=REMOTE, local_capture_dir=RECIPE["capture_rel"],
                 done_marker=f"{REMOTE}/{RECIPE['box_rel']}/RUNNER_DONE", destroyed=False, provisional=True,
                 rehearsal=rehearsal, created_at=iso(t_create))
    log(f"provisional boxes.json entry for {iid} ({label})")


def blocked() -> set[str]:
    if not BLOCKLIST.exists():
        return set()
    return {line.split()[0] for line in BLOCKLIST.read_text().splitlines() if line.strip()}


def block(machine_id, reason: str) -> None:
    BLOCKLIST.parent.mkdir(parents=True, exist_ok=True)
    with BLOCKLIST.open("a") as fh:
        fh.write(f"{machine_id} {time.strftime('%F')} {reason}\n")


# ------------------------------------------------------------------ money

def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def rehearsal_spent() -> float:
    """Every rehearsal's recorded spend; a rehearsal box without a record refuses the main launch (preflight)."""
    return sum(float(json.loads(p.read_text())["spent_usd"]) for p in sorted(LAUNCH.glob("rehearsal_record_*.json")))


def effective_cap(rows: list[dict], credit: float) -> dict:
    """recipe box.effective_cap_rule."""
    others = [r for r in rows if (r.get("label") or "") not in OURS]
    other_dph = sum(float(r.get("dph_total") or 0) for r in others)
    spent = rehearsal_spent()
    # The rehearsal's spend counts against the $30 job cap; the live credit has already paid it.
    cap = min(BOX["job_cap_usd"] - spent,
              credit - BOX["credit_margin_usd"] - other_dph * BOX["other_burn_horizon_hours"])
    return {"cap_usd": round(cap, 4), "credit": round(credit, 4), "other_live_instances": len(others),
            "other_dph": round(other_dph, 4), "rehearsal_spent_usd": round(spent, 4),
            "job_cap_usd": BOX["job_cap_usd"], "credit_margin_usd": BOX["credit_margin_usd"]}


def spend_check() -> None:
    """The global rule: the spend table right before every paid step. A failure refuses the create."""
    r = subprocess.run([sys.executable, str(GUARD), "spend"], capture_output=True, text=True, timeout=300)
    # Printed, and kept under tmp/ (untracked): launch/ is staged into git after the run, balances stay out of it.
    (REPO / "tmp").mkdir(exist_ok=True)
    (REPO / f"tmp/exact_stack_spend_{int(time.time())}.txt").write_text(r.stdout[-6000:] + r.stderr[-2000:])
    if r.returncode != 0:
        raise SystemExit(f"spend check failed (rc {r.returncode}); nothing rented")
    print("\n".join(r.stdout.strip().splitlines()[-12:]), flush=True)
    log("spend check passed (table printed above and kept under tmp/)")


# ------------------------------------------------------------------ preflight

def guard_ok() -> None:
    for name in ("box_progress.sh", "box_teardown.sh"):
        p = REPO / ".claude" / name
        if not (p.is_file() and os.access(p, os.X_OK)):
            raise SystemExit(f"preflight: {p} is missing or not executable; nothing rented")
    alive = subprocess.run([sys.executable, str(GUARD), "daemon-alive", "--project", str(REPO)],
                           capture_output=True, text=True, timeout=120)
    if alive.returncode != 0:
        raise SystemExit(f"preflight: guard refuses: {(alive.stdout + alive.stderr).strip()[:600]}")
    if not WATCH.is_file():
        raise SystemExit(f"preflight: {WATCH} is missing; nothing rented")


def preflight(rehearsal: bool = False) -> dict:
    need = [OUT / "REGISTRATION.md", OUT / "inputs/prompts_manifest.json", OUT / "pre/t01_thresholds_n16.json",
            OUT / "pre/g00_gate_reference.json", OUT / "pre/g00_gate_selftest.json",
            OUT / "pre/p01_power_registered.json"]
    missing = [str(p) for p in need if not p.is_file()]
    if missing:
        raise SystemExit(f"preflight: missing {missing}; nothing rented")
    if not json.loads((OUT / "pre/g00_gate_selftest.json").read_text()).get("all_as_expected"):
        raise SystemExit("preflight: the gate selftest did not separate the encodings; nothing rented")
    guard_ok()
    rows = all_instances()
    live_ours = [r for r in rows if (r.get("label") or "") in OURS]
    if live_ours:
        raise SystemExit(f"preflight: an instance of this item is live ({[(r.get('id'), r.get('label')) for r in live_ours]})"
                         "; refusing another")
    if not rehearsal:
        if not (os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")):
            raise SystemExit("preflight: HF_TOKEN is not set (needed here only, to sign the weight URLs)")
        if CHOICE.exists():
            raise SystemExit(f"preflight: {CHOICE} exists (a box was already provisioned for this item); "
                             "move it to out/superseded/ by hand only if that box is destroyed and captured")
        for p in sorted(LAUNCH.glob("rehearsal_choice_*.json")):
            iid = p.stem.rsplit("_", 1)[-1]
            if not (LAUNCH / f"rehearsal_record_{iid}.json").exists():
                raise SystemExit(f"preflight: rehearsal {iid} has no record; run --rehearse-report {iid} first")
    credit = float(json.loads(vast("show", "user", "--raw")).get("credit", 0))
    cap = effective_cap(rows, credit)
    if cap["cap_usd"] <= 0:
        raise SystemExit(f"preflight: no money inside the margin: {json.dumps(cap)}; nothing rented")
    return {"credit_start": credit, "cap": cap, "registration_sha256": sha256_file(OUT / "REGISTRATION.md"),
            "power_sha256": sha256_file(OUT / "pre/p01_power_registered.json")}


# ------------------------------------------------------------------ offer and cost

def rate_of(o: dict, disk_gb: float, dph_base: float | None = None) -> float:
    base = float(o["dph_base"]) if dph_base is None else dph_base
    return base + float(o.get("storage_cost") or 0) * disk_gb / 720.0


def projection(o: dict, tp: int, cap: float, dph_base: float | None = None) -> dict:
    """Whole-job cost at this offer's rate, over the recipe's phase minutes for this TP."""
    pm = RECIPE["phase_minutes"]
    per = pm["by_tp"][str(tp)]
    gb = RECIPE["weights"]["lfs_bytes"] / 1e9
    fetch_min = gb * 8e3 / float(o["inet_down"]) / 60.0
    sampling = per["sampling"] * BOX["sampling_contingency"]
    minutes = (pm["create_to_ready"] + pm["stage_and_push_manifest"] + max(pm["push_and_install"], fetch_min)
               + per["engine_init"] + sampling + pm["pull_capture_destroy"])
    minutes_expected = minutes - sampling + per["sampling"]
    rate = rate_of(o, BOX["disk_gb"], dph_base)
    bandwidth = float(o.get("inet_down_cost") or 0) * (gb + 6.0)
    cost = rate * minutes / 60.0 + bandwidth
    teardown_min = (cap - bandwidth) / rate * 60.0 - BOX["capture_reserve_minutes"]
    return {"tensor_parallel_size": tp, "minutes_with_contingency": round(minutes, 2),
            "minutes_expected": round(minutes_expected, 2), "fetch_minutes": round(fetch_min, 2),
            "rate_usd_h": round(rate, 4), "bandwidth_usd": round(bandwidth, 4), "cost_usd": round(cost, 2),
            "cost_expected_usd": round(rate * minutes_expected / 60.0 + bandwidth, 2),
            "cap_usd": round(cap, 4), "teardown_deadline_minutes": round(teardown_min, 1)}


def offer_ok(o: dict, tp: int, exclude: set[str]) -> bool:
    return (o.get("num_gpus") == tp and str(o.get("gpu_name")) in BOX["gpu_names"]
            and o.get("gpu_ram", 0) >= BOX["min_gpu_mib"] and o.get("reliability", 0) > BOX["min_reliability"]
            and o.get("inet_down", 0) >= BOX["min_inet_down_mbps"]
            and o.get("disk_space", 0) >= BOX["disk_gb"] + 10
            and float(o.get("cuda_max_good", 0)) >= BOX["min_cuda_max_good"]
            and o.get("dph_total", 99) <= BOX["max_dph"]
            and (o.get("inet_down_cost") or 0) <= BOX["max_inet_down_cost"]
            and str(o.get("machine_id")) not in exclude)


def table_row(tier: str, o: dict, ok: bool, pj: dict | None, cap: float) -> dict:
    return {"tier": tier, "id": o.get("id"), "machine_id": o.get("machine_id"),
            "gpus": f"{o.get('num_gpus')}x{o.get('gpu_name')}", "dph_total": o.get("dph_total"),
            "inet_down": o.get("inet_down"), "inet_down_cost": o.get("inet_down_cost"),
            "reliability": o.get("reliability"), "cuda_max_good": o.get("cuda_max_good"),
            "driver": o.get("driver_version"), "geo": o.get("geolocation"),
            "passes_filters": ok, "projection": pj, "within_cap": bool(pj and pj["cost_usd"] <= cap)}


def read_offers(exclude: set[str], cap: float) -> tuple[list, list[dict]]:
    """The TP4 tier's offers, checked and projected: [(offer, projection)] within the cap, and the read table."""
    want = os.environ.get("OFFER_ID")
    fits, seen = [], []
    for tier in BOX["tiers"]:
        tp = tier["tensor_parallel_size"]
        assert tp == 4, "the recipe holds only base A's TP4 tier (box.tier_rule)"
        for o in json.loads(vast("search", "offers", tier["query"], "-o", "dph_total", "--raw")):
            if want and str(o.get("id")) != want:
                continue
            ok = offer_ok(o, tp, exclude)
            pj = projection(o, tp, cap) if ok else None
            seen.append(table_row(tier["name"], o, ok, pj, cap))
            if ok and pj["cost_usd"] <= cap:
                fits.append((o, pj))
    fits.sort(key=lambda x: x[1]["cost_usd"])
    return fits, seen


def pick_offer(cap: float) -> tuple[dict, dict]:
    exclude = blocked() | {str(r.get("machine_id")) for r in all_instances()}
    fits, seen = read_offers(exclude, cap)
    LAUNCH.mkdir(parents=True, exist_ok=True)
    (LAUNCH / f"offers_read_{int(time.time())}.json").write_text(json.dumps({"ts": now(), "cap_usd": cap,
                                                                             "offers": seen}, indent=1))
    if fits:
        return fits[0]
    raise NoOffer(f"no TP4 offer passes every check within ${cap:.2f} (read {len(seen)}; "
                  f"{sum(r['passes_filters'] for r in seen)} pass the filters)")


def pick_now(state: dict) -> tuple[dict, dict, dict]:
    """One read: the preflight (guard, labels, credit, cap) again, then the offers. The cap of a try is min(the cap
    credit allows now, the first preflight's cap less what failed hosts cost)."""
    pre = preflight()
    cap = round(min(pre["cap"]["cap_usd"], state["cap"]["cap_usd"] - state["spent_usd"]), 4)
    pre["cap"]["cap_usd_this_round"] = cap
    try:
        offer, pj = pick_offer(cap)
    except NoOffer as exc:
        raise SystemExit(f"{exc}; nothing rented (--poll waits for one, read-only)")
    return offer, pj, pre


def poll_only() -> None:
    """Read-only wait for a fitting TP4 offer. Never rents: it exits 0 on a fit and 2 when the window ends."""
    t_end = time.time() + BOX["poll_max_hours"] * 3600
    rounds = 0
    while True:
        rows = all_instances()
        cap = effective_cap(rows, float(json.loads(vast("show", "user", "--raw")).get("credit", 0)))
        rounds += 1
        try:
            offer, pj = pick_offer(cap["cap_usd"])
        except NoOffer as exc:
            with open(LAUNCH / "poll.jsonl", "a") as fh:
                fh.write(json.dumps({"ts": now(), "round": rounds, "cap": cap, "why": str(exc)}) + "\n")
            if time.time() + BOX["poll_minutes"] * 60 > t_end:
                log(f"poll ended after {rounds} reads: {exc}; nothing rented")
                sys.exit(2)
            log(f"poll {rounds}: {exc}; next read in {BOX['poll_minutes']} min")
            time.sleep(BOX["poll_minutes"] * 60)
            continue
        hit = {"ts": now(), "round": rounds, "cap": cap, "offer_id": offer["id"], "machine_id": offer["machine_id"],
               "gpus": f"{offer['num_gpus']}x{offer['gpu_name']}", "dph_total": offer["dph_total"], "projection": pj}
        with open(LAUNCH / "poll.jsonl", "a") as fh:
            fh.write(json.dumps(hit) + "\n")
        log(f"POLL HIT after {rounds} reads: offer {offer['id']} {hit['gpus']} ${offer['dph_total']:.3f}/h, expected "
            f"${pj['cost_expected_usd']} with contingency ${pj['cost_usd']} of ${pj['cap_usd']}; nothing rented: run "
            "the YES=1 launch now")
        sys.exit(0)


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
echo "TOPO=$(nvidia-smi topo -m 2>/dev/null | head -6 | tr '\\t\\n' ' ;')"
echo "PYV=$(/venv/main/bin/python -c 'import platform;print(platform.python_version())' 2>&1 | tail -1)"
echo "TORCHV=$(/venv/main/bin/python -c 'import importlib.metadata as m;print(m.version("torch"))' 2>&1 | tail -1)"
echo "CUDA=$(/venv/main/bin/python -c 'import torch; torch.zeros(1).cuda(); print(torch.cuda.device_count())' 2>&1 | tail -1)"
S=$(date +%s.%N); B=$(curl -s -L -r 0-1073741823 --max-time 30 -o /dev/null -w '%{{size_download}}' '{SPEED_URL}'); E=$(date +%s.%N)
echo "SPEED=$B $S $E"
if [ -e /root/.vast_api_key ]; then echo "VASTKEY=present"; rm -f /root/.vast_api_key; else echo "VASTKEY=absent"; fi
echo {iid} > /root/box_id && echo "BOXID=$(cat /root/box_id)"
"""


def arrival_check(iid: int, host: str, port: str, tp: int, rehearsal: bool = False) -> tuple[str | None, dict]:
    out = ssh(host, port, arrival_script(iid), timeout=120)
    if out.returncode != 0:
        return f"arrival script failed rc={out.returncode}: {out.stderr.strip()[:200]}", {}
    facts = dict(line.split("=", 1) for line in out.stdout.splitlines() if "=" in line and line[:1].isupper())
    try:
        if facts["LABEL"] != f"C.{iid}":
            return f"container label {facts['LABEL']!r} is not C.{iid}", facts
        disk = REH["disk_gb"] if rehearsal else BOX["disk_gb"]
        if not facts["DISK"].isdigit() or int(facts["DISK"]) < disk - 10:
            return f"disk {facts['DISK']} GB below {disk - 10}", facts
        cards = [[x.strip() for x in c.split(",")] for c in facts["GPUS"].strip(";").split(";") if c]
        if len(cards) != tp or any(len(c) != 5 for c in cards):
            return f"not {tp} cards: {facts['GPUS']}", facts
        if not rehearsal:
            for name, total, used, lim, default in cards:
                if "H200" not in name or float(total) < BOX["min_gpu_mib"] or float(used) > 2048:
                    return f"a card is not an idle H200 of {BOX['min_gpu_mib']} MiB: {facts['GPUS']}", facts
                if float(lim) < 0.9 * float(default):
                    return f"a card is power-capped below 90% of its default: {facts['GPUS']}", facts
        if float(facts["CUDADRV"] or 0) < BOX["min_cuda_max_good"]:
            return f"driver CUDA {facts['CUDADRV']} below {BOX['min_cuda_max_good']}", facts
        if not facts["PYV"][:1].isdigit():
            return f"/venv/main python does not run: {facts['PYV']!r}", facts
        if facts["CUDA"].strip() != str(tp):
            return f"CUDA did not initialise on {tp} devices: {facts['CUDA']!r}", facts
        if facts.get("BOXID") != str(iid):
            return "could not write /root/box_id", facts
        size, start, end = facts["SPEED"].split()
        mbps = int(size) * 8 / 1e6 / max(float(end) - float(start), 1e-3)
        facts["SPEED_MBPS"] = round(mbps)
    except (KeyError, ValueError) as exc:
        return f"arrival output unreadable ({exc!r}): {out.stdout[:300]!r}", facts
    if not rehearsal and mbps < BOX["min_arrival_download_mbps"]:
        return f"download {mbps:.0f} Mb/s below {BOX['min_arrival_download_mbps']}", facts
    return None, facts


# ------------------------------------------------------------------ destroy before provisioning

def destroy_unprovisioned(iid: int, machine_id, reason: str) -> None:
    """Only before the sampler starts: the box holds nothing but reproducible code and weights."""
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
                    if BOXES.exists() and any(b.get("id") == iid for b in json.loads(BOXES.read_text())["boxes"]):
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


def push_file(host: str, port: str, local: Path, remote_path: str) -> None:
    """One local file to an explicit remote path (the rehearsal's box choice)."""
    if ssh(host, port, f"mkdir -p {os.path.dirname(remote_path)}").returncode != 0:
        raise RuntimeError(f"mkdir for {remote_path} failed")
    rs = (f"ssh -F /dev/null -i {KEYS[0]} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no "
          f"-o UserKnownHostsFile=/dev/null -o ConnectTimeout=20 -p {port}")
    out = subprocess.run(["rsync", "-az", "--timeout=120", "-e", rs, str(local), f"root@{host}:{remote_path}"],
                         capture_output=True, text=True, timeout=300)
    if out.returncode != 0:
        raise RuntimeError(f"push of {local.name} failed: {out.stderr.strip()[:300]}")


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


def choice_record(iid: int, offer: dict, pj: dict, live: float, t_create: float, facts: dict,
                  rehearsal: bool) -> dict:
    return {"instance": iid, "offer_id": offer["id"], "machine_id": offer["machine_id"],
            "gpus": f"{offer['num_gpus']}x{offer['gpu_name']}", "tensor_parallel_size": pj["tensor_parallel_size"],
            "rate_usd_h": pj["rate_usd_h"], "dph_live": live, "bandwidth_usd": pj["bandwidth_usd"],
            "created_at_unix": t_create, "job_cap_usd": pj["cap_usd"],
            "capture_reserve_minutes": BOX["capture_reserve_minutes"],
            "abort_after_generate_seconds": BOX["abort_after_generate_seconds"],
            "teardown_deadline_unix": t_create + pj["teardown_deadline_minutes"] * 60,
            "projection": pj, "arrival": {k: facts.get(k) for k in ("GPUS", "DRIVER", "CUDADRV", "TOPO", "PYV",
                                                                    "TORCHV", "SPEED_MBPS")},
            "rehearsal": rehearsal, "deviation_tp": pj["tensor_parallel_size"] != 4, "written_at": now()}


def start_runner(iid: int, host: str, port: str) -> None:
    start = (f"cd {REMOTE} && nohup setsid bash script/remote/auditbench/exact_stack/box_runner.sh "
             f"> /dev/null 2>&1 < /dev/null & sleep 20; "
             f"pgrep -f 'exact_stack/box_runner.sh' > /dev/null && echo RUNNER_UP; "
             f"tail -3 {REMOTE}/{RECIPE['box_rel']}/runner.log")
    res = ssh(host, port, start, timeout=90)
    (LAUNCH / f"start_{iid}.txt").write_text(res.stdout + res.stderr)
    if "RUNNER_UP" not in res.stdout:
        raise RuntimeError(f"runner did not start: {res.stdout[-300:]}")
    log("box_runner.sh is running")


def started(iid: int) -> bool:
    """True once this box's runner was confirmed up (launch/start_<id>.txt holds RUNNER_UP)."""
    p = LAUNCH / f"start_{iid}.txt"
    return p.exists() and "RUNNER_UP" in p.read_text()


def provision(iid: int, host: str, port: str) -> None:
    # Only what the box runs: the runner, the sampler and the recipe (the sampler imports nothing from src/),
    # the prompt manifest (it holds every rendered prompt) and the box choice.
    rsync(host, port, ["script/remote/auditbench/exact_stack/recipe.json",
                       "script/remote/auditbench/exact_stack/box_runner.sh",
                       "script/remote/auditbench/exact_stack/sample_exact_stack.py",
                       f"{RECIPE['out_rel']}/inputs/prompts_manifest.json",
                       f"{RECIPE['out_rel']}/inputs/box_choice.json"], REMOTE)
    log("pushed the runner, the sampler, the recipe, the manifest and the box choice")
    d = stage_weights()
    rs = (f"ssh -F /dev/null -i {KEYS[0]} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no "
          f"-o UserKnownHostsFile=/dev/null -o ConnectTimeout=20 -p {port}")
    ssh(host, port, f"mkdir -p {REMOTE}/models/Llama-3.3-70B-Instruct")
    out = subprocess.run(["rsync", "-az", "--timeout=120", "-e", rs, f"{d}/",
                          f"root@{host}:{REMOTE}/models/Llama-3.3-70B-Instruct/"], capture_output=True, text=True,
                         timeout=300)
    if out.returncode != 0:
        raise RuntimeError(f"manifest push failed: {out.stderr.strip()[:300]}")
    start_runner(iid, host, port)


def audit_monitored(iid: int, pid: int) -> bool:
    """OPERATIONS.md 3.3, as the launcher's last step: the guard's adapter names this box and its watcher runs."""
    r = subprocess.run(["bash", str(REPO / ".claude/box_progress.sh"), "vast", str(iid)], cwd=REPO,
                       capture_output=True, text=True, timeout=180)
    seen = (r.stdout.strip().splitlines() or ["(nothing)"])[-1]
    try:
        os.kill(pid, 0)
        alive = pid > 0
    except OSError:
        alive = False
    ok = seen.startswith(("progress", "ended")) and alive
    log(f"monitoring audit for {iid}: box_progress.sh says {seen!r}; watcher pid {pid} "
        f"{'alive' if alive else 'NOT RUNNING'}: {'OK' if ok else 'FAILED'}")
    if not ok:
        (REPO / "tmp/NEEDS_HUMAN_exact_stack").write_text(
            f"{now()} box {iid} is not fully monitored: adapter {seen!r}, watcher alive {alive}\n")
    return ok


def start_watcher(iid: int) -> int:
    """watch_exact_stack.py <id>, detached in its own session under caffeinate; returns its pid."""
    logf = open(LAUNCH / f"watch_{iid}.log", "a")
    cmd = [sys.executable, str(WATCH), str(iid)]
    if Path("/usr/bin/caffeinate").exists():
        cmd = ["/usr/bin/caffeinate", "-i", *cmd]
    subprocess.Popen(cmd, cwd=REPO, stdout=logf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                     start_new_session=True)
    pidf = LAUNCH / f"watch_{iid}.pid"
    for _ in range(20):
        time.sleep(1)
        if pidf.exists():
            pid = int(pidf.read_text().split()[0])
            try:
                os.kill(pid, 0)
                log(f"watcher for {iid} runs (pid {pid}, log {LAUNCH / f'watch_{iid}.log'})")
                return pid
            except OSError:
                break
    (REPO / "tmp/NEEDS_HUMAN_exact_stack").write_text(
        f"{now()} the watcher for {iid} did not start: run it by hand now (watch_exact_stack.py {iid})\n")
    log(f"!! THE WATCHER FOR {iid} DID NOT START: start it by hand now: nohup caffeinate -i {sys.executable} "
        f"{WATCH} {iid} >> {LAUNCH}/watch_{iid}.log 2>&1 &")
    return 0


# ------------------------------------------------------------------ main flow

ONSTART = ("(while true; do mkdir -p /root/.ssh; touch /root/.ssh/authorized_keys; "
           "grep -qF '{pub}' /root/.ssh/authorized_keys || echo '{pub}' >> /root/.ssh/authorized_keys; "
           "chown -R 0:0 /root/.ssh; chmod 700 /root/.ssh; chmod 600 /root/.ssh/authorized_keys; "
           "chmod g-w,o-w /root; sleep 30; done) >/dev/null 2>&1 &\nentrypoint.sh")


def create(offer: dict, label: str, disk_gb: int) -> tuple[int | None, float]:
    pub = (Path.home() / ".ssh/vast_recover.pub").read_text().strip()
    t_create = time.time()
    try:
        created = json.loads(vast("create", "instance", str(offer["id"]), "--image", BOX["image"],
                                  "--disk", str(disk_gb), "--label", label, "--ssh", "--direct",
                                  "--cancel-unavail", "--env", "-e propagate_user_keys=true",
                                  "--onstart-cmd", ONSTART.format(pub=pub), "--raw", timeout=180))
        return int(created["new_contract"]), t_create
    except BaseException as exc:
        log(f"create failed ({exc!r}); searching for anything it made")
        for r in [r for r in all_instances() if (r.get("label") or "") == label]:
            register(int(r["id"]), label)
            provisional_entry(int(r["id"]), label, t_create, rehearsal=label != LABEL)
            destroy_unprovisioned(int(r["id"]), offer["machine_id"], "create call failed")
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        return None, t_create


def try_once(state: dict) -> bool:
    offer, pj, pre = pick_now(state)
    tp = pj["tensor_parallel_size"]
    log(f"offer {offer['id']} machine {offer['machine_id']} {offer['num_gpus']}x{offer['gpu_name']} TP{tp} "
        f"${offer['dph_total']:.3f}/h rel {offer['reliability']:.4f} cuda {offer['cuda_max_good']} driver "
        f"{offer.get('driver_version')} down {offer['inet_down']:.0f} Mb/s {offer.get('geolocation')}; "
        f"cap {json.dumps(pre['cap'])}; projection {json.dumps(pj)}")
    if pj["cost_usd"] > pj["cap_usd"]:
        raise SystemExit(f"projection ${pj['cost_usd']} > cap ${pj['cap_usd']} (failed hosts already subtracted)")
    if os.environ.get("YES") != "1":
        log("dry run: nothing rented (YES=1 rents)")
        sys.exit(0)
    spend_check()
    state.update({"registration_sha256": pre["registration_sha256"], "power_sha256": pre["power_sha256"]})
    iid, t_create = create(offer, LABEL, BOX["disk_gb"])
    if iid is None:
        return False
    register(iid, LABEL)
    provisional_entry(iid, LABEL, t_create, rehearsal=False)
    state["iid"] = iid
    try:
        ok = bring_up(iid, offer, pj, t_create, state)
    except BaseException as exc:
        if CHOICE.exists() and json.loads(CHOICE.read_text()).get("instance") == iid and \
                started(iid):
            raise  # the sampler runs: never destroy here; the watcher and teardown_exact_stack.sh own it now
        destroy_unprovisioned(iid, offer["machine_id"], f"unexpected {exc!r}")
        ok = False
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
    if not ok:
        state["spent_usd"] += (time.time() - t_create) / 3600.0 * pj["rate_usd_h"] + 0.05
    return ok


def wait_running(iid: int, machine_id, t_create: float) -> dict | None:
    while True:
        info = instance(iid)
        st = (info or {}).get("actual_status")
        if st == "running":
            return info
        if st in ("offline", "exited", "unknown") or time.time() - t_create > BOX["load_timeout_s"]:
            destroy_unprovisioned(iid, machine_id, f"state {st} after {time.time() - t_create:.0f}s")
            return None
        time.sleep(15)


def bring_up(iid: int, offer: dict, pj: dict, t_create: float, state: dict) -> bool:
    tp = pj["tensor_parallel_size"]
    info = wait_running(iid, offer["machine_id"], t_create)
    if info is None:
        return False
    live = float(info.get("dph_total") or offer["dph_total"])
    log(f"{iid} running after {time.time() - t_create:.0f}s; live ${live:.3f}/h")
    # The cap read right before the create binds. Re-reading credit now would count this box's first minutes twice.
    cap = pj["cap_usd"]
    pj_live = projection(offer, tp, cap, dph_base=live - (offer["dph_total"] - offer["dph_base"]))
    if pj_live["cost_usd"] > cap:
        destroy_unprovisioned(iid, offer["machine_id"], f"live rate projects ${pj_live['cost_usd']} > cap ${cap}")
        return False
    deadline = time.time() + BOX["ssh_sla_s"]
    while time.time() < deadline:
        for host, port in endpoints(instance(iid) or {}):
            if ssh(host, port, "true", timeout=20).returncode != 0:
                continue
            reason, facts = arrival_check(iid, host, port, tp)
            (LAUNCH / f"arrival_{iid}.json").write_text(json.dumps({"ts": now(), "reason": reason, **facts}, indent=1))
            if reason:
                destroy_unprovisioned(iid, offer["machine_id"], reason)
                return False
            log(f"arrival OK {json.dumps({k: facts.get(k) for k in ('GPUS', 'DRIVER', 'CUDADRV', 'PYV', 'TORCHV', 'SPEED_MBPS', 'VASTKEY')})}")
            teardown_at = t_create + pj_live["teardown_deadline_minutes"] * 60
            boxes_update(iid, host=host, port=int(port), provisional=False, arrived_at=now(),
                         machine_id=offer["machine_id"], offer_id=offer["id"], dph_live=live,
                         tensor_parallel_size=tp, cap_usd=cap, teardown_deadline_utc=iso(teardown_at),
                         projection=pj_live, registration_sha256=state["registration_sha256"],
                         power_sha256=state["power_sha256"])
            # The watcher starts before provisioning: a launcher killed from here on leaves a box it still owns.
            pid = start_watcher(iid)
            boxes_update(iid, watcher_pid=pid)
            try:
                CHOICE.parent.mkdir(parents=True, exist_ok=True)
                with open(CHOICE, "x") as fh:
                    fh.write(json.dumps(choice_record(iid, offer, pj_live, live, t_create, facts, False), indent=1))
                provision(iid, host, port)
            except Exception as exc:  # noqa: BLE001 the sampler never started: everything on the box is reproducible
                destroy_unprovisioned(iid, offer["machine_id"], f"provisioning failed: {exc!r}")
                if CHOICE.exists():
                    sup = REPO / "out/superseded" / f"exact_stack_box_choice_{iid}.json"
                    sup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(CHOICE), str(sup))
                return False
            audit_monitored(iid, pid)
            log(f"READY {iid} at {host}:{port}; TP{tp}; sampler started; teardown deadline {iso(teardown_at)} "
                f"(${cap:.2f} less {BOX['capture_reserve_minutes']} min at ${live:.3f}/h); watcher pid {pid}")
            return True
        time.sleep(15)
    destroy_unprovisioned(iid, offer["machine_id"], f"no ssh within {BOX['ssh_sla_s']}s of running")
    return False


# ------------------------------------------------------------------ rehearsal

def rehearsal_offer(cap: float) -> tuple[dict, dict]:
    exclude = blocked() | {str(r.get("machine_id")) for r in all_instances()}
    rows, fits = [], []
    for o in json.loads(vast("search", "offers", REH["query"], "-o", "dph_total", "--raw")):
        ok = (o.get("num_gpus") == 1 and float(o.get("cuda_max_good", 0)) >= BOX["min_cuda_max_good"]
              and o.get("dph_total", 99) <= REH["max_dph"] and (o.get("inet_down_cost") or 0) <= REH["max_inet_down_cost"]
              and o.get("disk_space", 0) >= REH["disk_gb"] + 10 and str(o.get("machine_id")) not in exclude)
        rate = rate_of(o, REH["disk_gb"])
        limit = min(REH["cap_usd"], cap)
        pj = {"tensor_parallel_size": 1, "rate_usd_h": round(rate, 4), "bandwidth_usd": round(float(o.get("inet_down_cost") or 0) * 8, 4),
              "cost_usd": round(rate * REH["budget_minutes"] / 60 + float(o.get("inet_down_cost") or 0) * 8, 3),
              "cap_usd": round(limit, 4),
              "teardown_deadline_minutes": round(min(REH["budget_minutes"], (limit / max(rate, 1e-6)) * 60 - 5), 1)}
        rows.append({"id": o.get("id"), "gpus": f"1x{o.get('gpu_name')}", "dph_total": o.get("dph_total"),
                     "cuda_max_good": o.get("cuda_max_good"), "ok": ok, "projection": pj})
        if ok and pj["cost_usd"] <= limit:
            fits.append((o, pj))
    (LAUNCH / f"rehearsal_offers_{int(time.time())}.json").write_text(json.dumps({"ts": now(), "offers": rows}, indent=1))
    if not fits:
        raise SystemExit(f"no rehearsal offer fits (read {len(rows)}); nothing rented")
    fits.sort(key=lambda x: x[1]["cost_usd"])
    return fits[0]


def rehearse() -> None:
    pre = preflight(rehearsal=True)
    offer, pj = rehearsal_offer(pre["cap"]["cap_usd"])
    log(f"rehearsal offer {offer['id']} 1x{offer['gpu_name']} ${offer['dph_total']:.3f}/h cuda {offer['cuda_max_good']}"
        f" {offer.get('geolocation')}; projection {json.dumps(pj)}")
    if os.environ.get("YES") != "1":
        log("dry run: nothing rented (YES=1 rents)")
        return
    spend_check()
    iid, t_create = create(offer, REH["label"], REH["disk_gb"])
    if iid is None:
        raise SystemExit("rehearsal create failed")
    register(iid, REH["label"])
    provisional_entry(iid, REH["label"], t_create, rehearsal=True)
    try:
        info = wait_running(iid, offer["machine_id"], t_create)
        if info is None:
            raise SystemExit("rehearsal box never ran (destroyed)")
        live = float(info.get("dph_total") or offer["dph_total"])
        for _ in range(int(BOX["ssh_sla_s"] / 15)):
            eps = [(h, p) for h, p in endpoints(instance(iid) or {}) if ssh(h, p, "true", timeout=20).returncode == 0]
            if eps:
                break
            time.sleep(15)
        else:
            destroy_unprovisioned(iid, offer["machine_id"], "rehearsal: no ssh")
            raise SystemExit("rehearsal: no ssh")
        host, port = eps[0]
        reason, facts = arrival_check(iid, host, port, 1, rehearsal=True)
        (LAUNCH / f"arrival_{iid}.json").write_text(json.dumps({"ts": now(), "reason": reason, **facts}, indent=1))
        if reason:
            destroy_unprovisioned(iid, offer["machine_id"], f"rehearsal arrival: {reason}")
            raise SystemExit(f"rehearsal arrival failed: {reason}")
        teardown_at = t_create + pj["teardown_deadline_minutes"] * 60
        boxes_update(iid, host=host, port=int(port), provisional=False, arrived_at=now(),
                     machine_id=offer["machine_id"], offer_id=offer["id"], dph_live=live, tensor_parallel_size=1,
                     cap_usd=pj["cap_usd"], teardown_deadline_utc=iso(teardown_at), projection=pj)
        pid = start_watcher(iid)
        boxes_update(iid, watcher_pid=pid)
        rc = LAUNCH / f"rehearsal_choice_{iid}.json"
        rc.write_text(json.dumps(choice_record(iid, offer, pj, live, t_create, facts, True), indent=1))
        rsync(host, port, ["script/remote/auditbench/exact_stack/recipe.json",
                           "script/remote/auditbench/exact_stack/box_runner.sh"], REMOTE)
        push_file(host, port, rc, f"{REMOTE}/{RECIPE['out_rel']}/inputs/box_choice.json")
        start_runner(iid, host, port)
    except Exception as exc:  # noqa: BLE001 nothing but reproducible code is on the box before the runner starts
        if not started(iid):
            destroy_unprovisioned(iid, offer["machine_id"], f"rehearsal provisioning failed: {exc!r}")
        raise
    audit_monitored(iid, pid)
    log(f"REHEARSAL {iid} runs; teardown deadline {iso(teardown_at)}; the watcher (pid {pid}) captures and "
        f"destroys it when the runner ends; then run --rehearse-report {iid}")


def rehearse_report(iid: int) -> None:
    entry = next((b for b in json.loads(BOXES.read_text())["boxes"] if b.get("id") == iid), None)
    if not entry or not entry.get("rehearsal"):
        raise SystemExit(f"{iid} is not a rehearsal box in {BOXES}")
    if not entry.get("destroyed"):
        raise SystemExit(f"{iid} is not destroyed yet; the watcher or teardown_exact_stack.sh {iid} must finish first")
    d = REPO / RECIPE["capture_rel"] / f"vast_{iid}" / "files" / REMOTE.lstrip("/") / RECIPE["box_rel"]
    read = lambda n: (d / n).read_text(errors="replace") if (d / n).exists() else ""  # noqa: E731
    versions, runner, done = read("versions.txt"), read("runner.log"), read("RUNNER_DONE").strip()
    t0 = datetime.fromisoformat(entry["created_at"]).timestamp()
    t1 = datetime.fromisoformat((entry.get("destroyed_utc") or entry.get("destroyed_at")).replace("Z", "+00:00")).timestamp()
    spent = (t1 - t0) / 3600 * float(entry["dph_live"]) + float(entry["projection"].get("bandwidth_usd") or 0)
    ok_versions = bool([ln for ln in versions.splitlines() if ln.startswith("VERSIONS python 3.12.") and
                        " vllm 0.26.0 torch 2.11.0+cu128 torch_cuda 12.8 flashinfer 0.6.14 " in ln])
    stages = [ln for ln in runner.splitlines() if "STAGE_TIME" in ln or "DEVIATION" in ln or "FATAL" in ln]
    rec = {"instance": iid, "spent_usd": round(spent, 4), "minutes": round((t1 - t0) / 60, 1),
           "runner_done": done, "versions_ok": ok_versions, "versions_line": versions.strip().splitlines()[-1:] or None,
           "stage_lines": stages, "import_without_cu13_path": read("import_without_cu13_path.txt")[-400:],
           "pass": ok_versions and "rc=0" in done and "stage=rehearsed" in done, "box_dir": str(d.relative_to(REPO)),
           "written_at": now()}
    with open(LAUNCH / f"rehearsal_record_{iid}.json", "x") as fh:
        fh.write(json.dumps(rec, indent=1))
    print(json.dumps(rec, indent=1))
    if not rec["pass"]:
        raise SystemExit("REHEARSAL FAILED: fix the runner before any 4-card rental; report to the owner")


# ------------------------------------------------------------------ read-only

def _sigterm(signum, frame):
    raise KeyboardInterrupt(f"signal {signum}")


def offers_only() -> None:
    """Read-only: the TP4 offers, the checks and the projection at the cap credit allows today. No rental."""
    rows = all_instances()
    credit = float(json.loads(vast("show", "user", "--raw")).get("credit", 0))
    cap = effective_cap(rows, credit)
    exclude = blocked() | {str(r.get("machine_id")) for r in rows}
    fits, seen = read_offers(exclude, cap["cap_usd"])
    LAUNCH.mkdir(parents=True, exist_ok=True)
    path = LAUNCH / f"offers_only_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    path.write_text(json.dumps({"ts": now(), "cap": cap, "offers": seen}, indent=1))
    for r in seen:
        pj = r["projection"] or {}
        print(f"{r['tier']} {r['id']} {r['gpus']:<14} ${r['dph_total']:.3f}/h rel {r['reliability']:.4f} "
              f"down {r['inet_down']:.0f} cuda {r['cuda_max_good']} {str(r['geo']).strip():<18} "
              f"filters {'ok' if r['passes_filters'] else 'FAIL'} "
              + (f"expected ${pj['cost_expected_usd']:.2f} with contingency ${pj['cost_usd']:.2f} "
                 f"({pj['minutes_with_contingency']:.0f} min, deadline {pj['teardown_deadline_minutes']:.0f} min) "
                 f"{'WITHIN CAP' if r['within_cap'] else 'over cap'}" if pj else ""))
    choice = {"offer_id": fits[0][0]["id"], "projection": fits[0][1]} if fits else None
    print(json.dumps({"cap": cap, "choice": choice, "written": str(path)}, indent=1))


def main() -> None:
    signal.signal(signal.SIGTERM, _sigterm)
    signal.signal(signal.SIGHUP, _sigterm)
    LAUNCH.mkdir(parents=True, exist_ok=True)
    if "--offers-only" in sys.argv:
        offers_only()
        return
    if "--rehearse-report" in sys.argv:
        rehearse_report(int(sys.argv[sys.argv.index("--rehearse-report") + 1]))
        return
    if "--rehearse" in sys.argv:
        rehearse()
        return
    if "--poll" in sys.argv:
        poll_only()
        return
    pre = preflight()
    log(f"preflight passed: cap {json.dumps(pre['cap'])}, registration {pre['registration_sha256'][:12]}")
    state = {"spent_usd": 0.0, **pre}  # state["cap"]: the first preflight's cap, never raised later
    for attempt in range(1, BOX["max_tries"] + 1):
        log(f"attempt {attempt}/{BOX['max_tries']}")
        if try_once(state):
            (LAUNCH / "launch_record.json").write_text(json.dumps({"ts": now(), **state}, indent=1))
            return
    raise SystemExit(f"{BOX['max_tries']} hosts failed; stopping. Nothing is left running.")


if __name__ == "__main__":
    main()
