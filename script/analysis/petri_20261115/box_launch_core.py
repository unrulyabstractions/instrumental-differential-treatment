"""Shared launcher core for the B73 and B74 boxes: credit rule, offer, rental, arrival checks, registry, watcher.

Modelled on script/remote/auditbench/exact_stack/launch_exact_stack.py (B55: a host that fails a check is
destroyed before anything of ours runs on it, and its machine is blocklisted). Each launcher passes a recipe
(``small_box_recipe.json`` or ``big_box_recipe.json``) and a provision function. Nothing here is typed from memory.

The credit rule (task text, 2026-11-15): before any rental, read the live vast credit and every live instance on
the account. Each live instance's remaining projected cost is its registry entry's job cap minus what it has
billed so far (elapsed hours x its live $/h); an instance no registry lists refuses the rental outright. The
rental is refused when credit - (sum of remaining + this job's cap) < min_margin_usd ($5).

Money after the rental (amendment of 2026-11-15, critic blockers B2 and B4):
  * ``cloud_boxes_guard.py spend`` runs right before every create; a failure refuses it.
  * The create call is guarded: on any exception every instance carrying our label is registered and destroyed.
  * bring_up is guarded: any exception before the runner is confirmed up destroys the box by id.
  * The teardown deadline is the job cap less what failed hosts already cost, less the bandwidth, at the live
    rate, less the capture reserve. It goes into the registry and, as ``inputs/box_choice.json``, onto the box,
    where the runner ends every phase at it.
  * ``watch_box.py`` starts detached on this Mac right after the arrival checks and before provisioning: it tears
    the box down through ``.claude/box_teardown.sh`` when the runner ends, at the deadline, on a stale box or a low
    credit, and stops (never destroys) a box it cannot reach past the deadline.
  * The launcher ends by asking ``.claude/box_progress.sh vast <id>``; anything but ``progress`` is an alarm.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
KEYS = [Path.home() / ".ssh/id_ed25519", Path.home() / ".ssh/vast_recover"]
GUARD = Path.home() / ".claude/hooks/cloud_boxes_guard.py"
WATCH = Path(__file__).resolve().parent / "watch_box.py"
MY_INSTANCES = REPO / "tmp/r2_my_instances.txt"
SPEED_URL = ("https://huggingface.co/auditing-agents/llama_70b_synth_docs_only_emotional_bond"
             "/resolve/main/adapter_model.safetensors")
#: Job caps of other workstreams' boxes whose registries do not record one. B71: the exact-stack item's whole
#: allotment is $30; its one-card rehearsal counts inside that allotment, so either label counts at $30 here.
KNOWN_CAPS = {"idt-exact-stack-a2": 30.0, "idt-exact-stack-a2-rehearse": 30.0}
#: The ssh client; the adapters' tests swap in a stand-in that behaves as sshd does.
SSH_BIN = "ssh"
SSH_OPTS = ["-F", "/dev/null", "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
            "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=4"]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="seconds")


def ssh_bash(host: str, port, cmd: str, timeout: int = 60) -> subprocess.CompletedProcess:
    """Run ``cmd`` on the box under ``bash -s``, the script on stdin, never as argv words.

    sshd joins the remote argv with spaces and hands the string to the login shell, so ``bash -c <cmd>`` passed
    as separate words runs ``bash -c test ...`` with the command's own words lost (critic blocker B1). On stdin the
    script arrives byte for byte. Each key is tried in turn; rc 255 (ssh itself failed) moves to the next."""
    for key in KEYS:
        try:
            out = subprocess.run([SSH_BIN, *SSH_OPTS, "-i", str(key), "-p", str(port), f"root@{host}", "bash -s"],
                                 input=cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            continue
        if out.returncode != 255:
            return out
    return subprocess.CompletedProcess(cmd, 255, "", "ssh failed on every key")


#: Where the launcher writes the instance id on the box; the adapters' tests point it elsewhere.
BOX_ID_PATH = "/root/box_id"


def box_id_guard(iid) -> str:
    """A prefix for box commands: refuse to act unless /root/box_id names this instance."""
    return (f'[ "$(tr -d \'[:space:]\' < {BOX_ID_PATH} 2>/dev/null)" = "{int(iid)}" ] '
            f'|| {{ echo "WRONG_BOX $(cat {BOX_ID_PATH} 2>/dev/null)"; exit 3; }}\n')


def git_export(specs: list[list[str]], dest: Path, must_be_clean: list[str]) -> dict:
    """Write each pathspec group as committed at HEAD into ``dest``: never the working tree, which other sessions
    edit (a half-saved file there would end the runner at its dry run). One ``git archive`` per group, because an
    exclude in one group would also drop a later include.

    Refuses when a file of ``must_be_clean`` (this workstream's own runner, recipe, scripts and promptsets) has
    uncommitted changes, so what is pushed is what was committed, and when a file of the export carries this Mac's
    account name (no account name reaches a box). Other sessions' uncommitted edits under a pushed path are listed
    in the record and never pushed."""
    commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True,
                            check=True).stdout.strip()
    mine = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain", "--", *must_be_clean],
                          capture_output=True, text=True, check=True).stdout.strip()
    if mine:
        raise RuntimeError(f"uncommitted changes in this workstream's pushed files: {mine[:400]}")
    others = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain", "--",
                             *[p for g in specs for p in g if not p.startswith(":")]],
                            capture_output=True, text=True, check=True).stdout.splitlines()
    if dest.exists():
        shutil.move(str(dest), str(dest.with_name(dest.name + f".superseded.{int(time.time())}")))
    dest.mkdir(parents=True)
    tar = dest.with_suffix(".tar")
    for group in specs:
        with open(tar, "wb") as fh:
            subprocess.run(["git", "-C", str(REPO), "archive", "--format=tar", commit, "--", *group], stdout=fh,
                           check=True)
        with tarfile.open(tar) as tf:
            tf.extractall(dest, filter="data")
        tar.unlink()
    name = Path.home().name.lower().encode()
    files = [p for p in dest.rglob("*") if p.is_file()]
    for p in files:
        if name and name in p.read_bytes().lower():
            raise RuntimeError(f"{p.relative_to(dest)} carries this Mac's account name; it may not reach a box")
    rec = {"commit": commit, "files": len(files), "bytes": sum(p.stat().st_size for p in files),
           "not_pushed_working_tree_edits": others}
    (dest / "EXPORT_COMMIT").write_text(commit + "\n")
    return rec


class Launch:
    def __init__(self, recipe_path: Path) -> None:
        self.recipe_path = Path(recipe_path)
        self.recipe = json.loads(self.recipe_path.read_text())
        self.box = self.recipe["box"]
        self.out = REPO / self.recipe["out_rel"]
        self.launch_dir = self.out / "launch"
        self.registry = REPO / self.recipe["registry_rel"]
        self.label = self.recipe["label"]
        self.blocklist = REPO / f"tmp/{self.label}_bad_machines.txt"

    # ------------------------------------------------------------ logging and vast
    def log(self, msg: str) -> None:
        line = f"{now()} {msg}"
        print(line, flush=True)
        self.launch_dir.mkdir(parents=True, exist_ok=True)
        with open(self.launch_dir / "launch.log", "a") as fh:
            fh.write(line + "\n")

    @staticmethod
    def vast(*args: str, timeout: int = 120) -> str:
        out = subprocess.run(["vastai", *args], capture_output=True, text=True, timeout=timeout)
        if out.returncode != 0:
            raise RuntimeError(f"vastai {' '.join(args[:2])} failed: {out.stderr.strip()[:300]}")
        return out.stdout

    def all_instances(self) -> list[dict]:
        rows, token = [], None
        for _ in range(50):
            page = json.loads(self.vast("show", "instances-v1", "--raw", *(["--next-token", token] if token else [])))
            rows += page.get("instances", [])
            token = page.get("next_token")
            if not token:
                return rows
        raise RuntimeError("instance listing did not end after 50 pages")

    def instance(self, iid: int) -> dict | None:
        for attempt in range(4):
            try:
                return next((r for r in self.all_instances() if r.get("id") == iid), None)
            except (RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
                self.log(f"listing failed ({exc}); retry {attempt + 1}/4")
                time.sleep(10)
        raise RuntimeError("instance listing failed four times")

    # ------------------------------------------------------------ registries
    @staticmethod
    def registries() -> list[Path]:
        lines = (REPO / ".claude/box_registries").read_text().splitlines()
        return [REPO / ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]

    def registry_update(self, iid: int, **fields) -> None:
        data = json.loads(self.registry.read_text()) if self.registry.exists() else {"boxes": []}
        entry = next((b for b in data["boxes"] if b.get("id") == iid), None)
        if entry is None:
            entry = {"id": iid}
            data["boxes"].append(entry)
        entry.update(fields)
        self.registry.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.registry.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=1))
        os.replace(tmp, self.registry)

    def provisional_entry(self, iid: int, t0: float, offer: dict, pre: dict) -> None:
        """Written the moment the create returns. Host 0.0.0.0 makes both adapters answer 'unreachable', so the
        guard escalates and stops a box whose launcher died before arrival, instead of reading it as 'unknown'."""
        MY_INSTANCES.parent.mkdir(parents=True, exist_ok=True)
        with MY_INSTANCES.open("a") as fh:
            fh.write(f"{iid} {self.label}\n")
        self.registry_update(iid, label=self.label, destroyed=False, provisional=True,
                             job_cap_usd=self.box["job_cap_usd"], created_at=iso(t0), host="0.0.0.0", port=22,
                             remote_roots=["/workspace", "/root"], remote_run_dir=self.recipe["remote_root"],
                             local_capture_dir=self.recipe["capture_rel"],
                             done_marker=f"{self.recipe['remote_root']}/RUNNER_DONE", procs=self.recipe["procs"],
                             machine_id=offer.get("machine_id"), offer_id=offer.get("id"),
                             registration_sha256=pre.get("registration_sha256"))

    # ------------------------------------------------------------ preflight and the credit rule
    def credit_rule(self) -> dict:
        credit = float(json.loads(self.vast("show", "user", "--raw")).get("credit", 0))
        entries = {}
        for reg in self.registries():
            if reg.exists():
                for b in json.loads(reg.read_text()).get("boxes", []):
                    if not b.get("destroyed"):
                        entries[b.get("id")] = b
        others = []
        for inst in self.all_instances():
            iid, label = inst.get("id"), inst.get("label") or ""
            dph = float(inst.get("dph_total") or 0)
            entry = entries.get(iid)
            cap = (entry or {}).get("job_cap_usd") or (entry or {}).get("cap_usd") or KNOWN_CAPS.get(label)
            if cap is None:
                raise SystemExit(f"credit rule: live instance {iid} ({label!r}) has no recorded job cap; refusing")
            start = (entry or {}).get("created_at")
            t0 = (datetime.fromisoformat(start).timestamp() if start
                  else float(inst.get("start_date") or time.time()))
            billed = max(0.0, (time.time() - t0) / 3600.0) * dph
            others.append({"id": iid, "label": label, "dph": dph, "cap": float(cap), "billed": round(billed, 2),
                           "remaining": round(max(0.0, float(cap) - billed), 2)})
        remaining = sum(o["remaining"] for o in others)
        margin = credit - (remaining + self.box["job_cap_usd"])
        rec = {"ts": now(), "credit": credit, "others": others, "others_remaining": remaining,
               "job_cap": self.box["job_cap_usd"], "margin": round(margin, 2),
               "min_margin": self.box["min_margin_usd"]}
        self.launch_dir.mkdir(parents=True, exist_ok=True)
        (self.launch_dir / f"credit_rule_{int(time.time())}.json").write_text(json.dumps(rec, indent=1))
        if margin < self.box["min_margin_usd"]:
            raise SystemExit(f"credit rule refuses: credit ${credit:.2f} - (others ${remaining:.2f} + cap "
                             f"${self.box['job_cap_usd']:.2f}) = ${margin:.2f} < ${self.box['min_margin_usd']:.2f}")
        return rec

    def preflight(self) -> dict:
        reg_md = self.out / "REGISTRATION.md"
        if not reg_md.is_file():
            raise SystemExit("preflight: REGISTRATION.md missing; nothing rented")
        for name in ("box_progress.sh", "box_teardown.sh"):
            p = REPO / ".claude" / name
            if not (p.is_file() and os.access(p, os.X_OK)):
                raise SystemExit(f"preflight: {p} missing or not executable")
        if not WATCH.is_file():
            raise SystemExit(f"preflight: {WATCH} is missing; nothing rented")
        listed = [str(p) for p in self.registries()]
        if str(self.registry) not in listed:
            raise SystemExit(f"preflight: {self.registry} is not listed in .claude/box_registries")
        alive = subprocess.run([sys.executable, str(GUARD), "daemon-alive", "--project", str(REPO)],
                               capture_output=True, text=True, timeout=120)
        if alive.returncode != 0:
            raise SystemExit(f"preflight: guard refuses: {(alive.stdout + alive.stderr).strip()[:400]}")
        if any((r.get("label") or "") == self.label for r in self.all_instances()):
            raise SystemExit(f"preflight: an instance labelled {self.label} already exists")
        if self.registry.exists() and any(not b.get("destroyed") for b in json.loads(self.registry.read_text())
                                          .get("boxes", [])):
            raise SystemExit(f"preflight: {self.registry} still lists a live box; capture and destroy it first")
        rule = self.credit_rule()
        return {"credit_rule": rule, "registration_sha256": hashlib.sha256(reg_md.read_bytes()).hexdigest()}

    def spend_check(self) -> None:
        """The owner's rule: the spend table right before every paid step. A failure refuses the create."""
        r = subprocess.run([sys.executable, str(GUARD), "spend"], capture_output=True, text=True, timeout=300)
        (REPO / "tmp").mkdir(exist_ok=True)
        # Kept under tmp/ (untracked): balances stay out of the committed launch folder.
        (REPO / f"tmp/{self.label}_spend_{int(time.time())}.txt").write_text(r.stdout[-6000:] + r.stderr[-2000:])
        if r.returncode != 0:
            raise SystemExit(f"spend check failed (rc {r.returncode}); nothing rented")
        print("\n".join(r.stdout.strip().splitlines()[-12:]), flush=True)
        self.log("spend check passed (table printed above and kept under tmp/)")

    # ------------------------------------------------------------ offer and projection
    def rate_of(self, o: dict, dph_total: float | None = None) -> float:
        base = float(o["dph_base"]) if dph_total is None else dph_total - (o["dph_total"] - o["dph_base"])
        return base + float(o.get("storage_cost") or 0) * self.box["disk_gb"] / 720.0

    def projection(self, o: dict, dph_total: float | None = None, spent: float = 0.0) -> dict:
        """Minutes and cost at this offer, and the teardown deadline: the job cap less what failed hosts already
        cost (``spent``) and the bandwidth, at this rate, less the capture reserve."""
        pm = self.recipe["phase_minutes"]
        fetch = self.recipe["download_gb"] * 8e3 / float(o["inet_down"]) / 60.0
        # The runner fetches the weights while it installs the engine, so the two overlap.
        minutes = sum(pm.values()) - pm["push_and_install"] + max(pm["push_and_install"], fetch)
        rate = self.rate_of(o, dph_total)
        bandwidth = float(o.get("inet_down_cost") or 0) * (self.recipe["download_gb"] + 2.0)
        cost = rate * minutes / 60.0 + bandwidth
        cap_left = self.box["job_cap_usd"] - spent
        deadline = (cap_left - bandwidth) / rate * 60.0 - self.box["capture_reserve_minutes"]
        return {"minutes": round(minutes, 1), "fetch_minutes": round(fetch, 1), "rate_usd_h": round(rate, 4),
                "bandwidth_usd": round(bandwidth, 3), "cost_usd": round(cost, 2), "spent_before_usd": round(spent, 4),
                "cap_left_usd": round(cap_left, 4), "teardown_deadline_minutes": round(deadline, 1)}

    def offer_ok(self, o: dict, exclude: set[str]) -> bool:
        b = self.box
        return (o.get("num_gpus") == b["num_gpus"] and str(o.get("gpu_name")) in b["gpu_names"]
                and o.get("gpu_ram", 0) >= b["min_gpu_mib"] and o.get("reliability", 0) > b["min_reliability"]
                and o.get("inet_down", 0) >= b["min_inet_down_mbps"] and o.get("disk_space", 0) >= b["disk_gb"] + 10
                and float(o.get("cuda_max_good", 0)) >= b["min_cuda_max_good"] and o.get("dph_total", 99) <= b["max_dph"]
                and (o.get("inet_down_cost") or 0) <= b["max_inet_down_cost"] and str(o.get("machine_id")) not in exclude)

    def pick_offer(self, spent: float = 0.0) -> tuple[dict, dict]:
        exclude = {ln.split()[0] for ln in (self.blocklist.read_text().splitlines()
                                            if self.blocklist.exists() else []) if ln.strip()}
        exclude |= {str(r.get("machine_id")) for r in self.all_instances()}
        offers = json.loads(self.vast("search", "offers", self.box["query"], "-o", "dph_total", "--raw"))
        seen, fits = [], []
        for o in offers:
            ok = self.offer_ok(o, exclude)
            pj = self.projection(o, spent=spent) if ok else None
            seen.append({"id": o.get("id"), "machine_id": o.get("machine_id"), "gpu": o.get("gpu_name"),
                         "dph_total": o.get("dph_total"), "inet_down": o.get("inet_down"),
                         "geolocation": o.get("geolocation"), "ok": ok, "projection": pj})
            if ok and spent + pj["cost_usd"] <= self.box["job_cap_usd"]:
                fits.append((o, pj))
        self.launch_dir.mkdir(parents=True, exist_ok=True)
        (self.launch_dir / f"offers_read_{int(time.time())}.json").write_text(json.dumps({"ts": now(), "offers": seen},
                                                                                         indent=1))
        if not fits:
            raise SystemExit(f"no offer passes every check within ${self.box['job_cap_usd']} less ${spent:.2f} "
                             "already spent; nothing rented")
        fits.sort(key=lambda x: (self.box["gpu_names"].index(str(x[0]["gpu_name"])), x[1]["cost_usd"]))
        return fits[0]

    # ------------------------------------------------------------ ssh, arrival, destroy
    @staticmethod
    def ssh(host: str, port: str, cmd: str, timeout: int = 60) -> subprocess.CompletedProcess:
        return ssh_bash(host, port, cmd, timeout)

    @staticmethod
    def rsync_cmd(port: str) -> str:
        return (f"ssh -F /dev/null -i {KEYS[0]} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no "
                f"-o UserKnownHostsFile=/dev/null -o ConnectTimeout=20 -p {port}")

    def rsync(self, host: str, port: str, src: list[str], dest: str, extra: list[str] | None = None,
              relative: bool = True, timeout: int = 900, cwd: Path | None = None) -> None:
        args = ["rsync", "-az", "--timeout=120", *(["-R"] if relative else []), *(extra or []),
                "-e", self.rsync_cmd(port), *src, f"root@{host}:{dest}"]
        out = subprocess.run(args, cwd=cwd or REPO, capture_output=True, text=True, timeout=timeout)
        if out.returncode != 0:
            raise RuntimeError(f"rsync {src[:2]} failed rc={out.returncode}: {out.stderr.strip()[:300]}")

    @staticmethod
    def endpoints(info: dict) -> list[tuple[str, str]]:
        eps = []
        mapped = (info.get("ports") or {}).get("22/tcp") or []
        if info.get("public_ipaddr") and mapped:
            eps.append((info["public_ipaddr"].strip(), str(mapped[0]["HostPort"])))
        if info.get("ssh_host"):
            eps.append((str(info["ssh_host"]), str(info["ssh_port"])))
        return eps

    def arrival(self, iid: int, host: str, port: str) -> tuple[str | None, dict]:
        script = f"""set -u
echo "LABEL=$(tr -d '[:space:]' < /root/.vast_containerlabel 2>/dev/null)"
echo "DISK=$(df -BG --output=avail /workspace 2>/dev/null | tail -1 | tr -dc 0-9)"
echo "GPUS=$(nvidia-smi --query-gpu=name,memory.total,memory.used,power.limit,power.default_limit --format=csv,noheader,nounits | tr '\\n' ';')"
echo "CUDADRV=$(nvidia-smi | grep -o 'CUDA Version: [0-9.]*' | head -1 | tr -dc 0-9.)"
echo "CUDA=$(/venv/main/bin/python -c 'import torch; torch.zeros(1).cuda(); print(torch.cuda.device_count())' 2>&1 | tail -1)"
S=$(date +%s.%N); B=$(curl -s -L -r 0-1073741823 --max-time 30 -o /dev/null -w '%{{size_download}}' '{SPEED_URL}'); E=$(date +%s.%N)
echo "SPEED=$B $S $E"
if [ -e /root/.vast_api_key ]; then echo "VASTKEY=present"; rm -f /root/.vast_api_key; else echo "VASTKEY=absent"; fi
echo {iid} > /root/box_id && echo "BOXID=$(cat /root/box_id)"
"""
        out = self.ssh(host, port, script, timeout=120)
        if out.returncode != 0:
            return f"arrival script failed rc={out.returncode}", {}
        facts = dict(ln.split("=", 1) for ln in out.stdout.splitlines() if "=" in ln and ln[:1].isupper())
        b = self.box
        try:
            if facts["LABEL"] != f"C.{iid}":
                return f"container label {facts['LABEL']!r} is not C.{iid}", facts
            if not facts["DISK"].isdigit() or int(facts["DISK"]) < b["disk_gb"] - 10:
                return f"disk {facts['DISK']} GB below {b['disk_gb'] - 10}", facts
            cards = [[x.strip() for x in c.split(",")] for c in facts["GPUS"].strip(";").split(";") if c]
            if len(cards) != b["num_gpus"]:
                return f"not {b['num_gpus']} cards: {facts['GPUS']}", facts
            for name, total, used, lim, default in cards:
                if not any(g.replace("_", " ") in name for g in b["gpu_names"]) or float(total) < b["min_gpu_mib"] \
                        or float(used) > 2048:
                    return f"a card is not an idle {b['gpu_names']}: {facts['GPUS']}", facts
                if float(lim) < 0.9 * float(default):
                    return f"a card is power-capped: {facts['GPUS']}", facts
            if float(facts["CUDADRV"] or 0) < b["min_cuda_max_good"]:
                return f"driver CUDA {facts['CUDADRV']} below {b['min_cuda_max_good']}", facts
            if facts["CUDA"].strip() != str(b["num_gpus"]):
                return f"CUDA did not initialise on every card: {facts['CUDA']!r}", facts
            if facts.get("BOXID") != str(iid):
                return "could not write /root/box_id", facts
            size, start, end = facts["SPEED"].split()
            facts["SPEED_MBPS"] = round(int(size) * 8 / 1e6 / max(float(end) - float(start), 1e-3))
        except (KeyError, ValueError) as exc:
            return f"arrival output unreadable ({exc!r})", facts
        if facts["SPEED_MBPS"] < b["min_arrival_download_mbps"]:
            return f"download {facts['SPEED_MBPS']} Mb/s below {b['min_arrival_download_mbps']}", facts
        return None, facts

    def destroy_unprovisioned(self, iid: int, machine_id, reason: str) -> None:
        """Only before the runner starts: the box holds nothing but reproducible code and weights."""
        self.log(f"DESTROY {iid} (runner never started): {reason}")
        if machine_id is not None:
            self.blocklist.parent.mkdir(parents=True, exist_ok=True)
            with self.blocklist.open("a") as fh:
                fh.write(f"{machine_id} {time.strftime('%F')} instance {iid}: {reason}\n")
        for attempt in range(1, 6):
            try:
                self.vast("destroy", "instance", str(iid), "--yes")
            except (RuntimeError, subprocess.TimeoutExpired) as exc:
                self.log(f"destroy attempt {attempt} failed: {exc}")
            for _ in range(6):
                try:
                    if self.instance(iid) is None:
                        self.log(f"{iid} confirmed gone")
                        if self.registry.exists() and any(b.get("id") == iid for b in
                                                          json.loads(self.registry.read_text())["boxes"]):
                            self.registry_update(iid, destroyed=True, destroyed_at=now(), destroy_reason=reason)
                        return
                except RuntimeError as exc:
                    self.log(f"cannot confirm yet: {exc}")
                time.sleep(10)
        (REPO / f"tmp/NEEDS_HUMAN_{self.label}").write_text(f"{now()} instance {iid} may still bill: {reason}\n")
        raise SystemExit(f"{iid} still listed after five destroys; IT MAY STILL BILL")

    # ------------------------------------------------------------ the flow
    def run(self, provision) -> None:
        if "--offers-only" in sys.argv:
            o, pj = self.pick_offer()
            print(json.dumps({"offer": {k: o.get(k) for k in ("id", "gpu_name", "num_gpus", "dph_total",
                                                              "inet_down", "geolocation")}, "projection": pj}, indent=1))
            return
        pre = self.preflight()
        self.log(f"preflight passed: {json.dumps(pre['credit_rule'])}")
        spent = 0.0
        for attempt in range(1, self.box["max_tries"] + 1):
            offer, pj = self.pick_offer(spent)
            self.log(f"attempt {attempt}: offer {offer['id']} {offer['num_gpus']}x{offer['gpu_name']} "
                     f"${offer['dph_total']:.3f}/h projection {json.dumps(pj)}")
            if spent + pj["cost_usd"] > self.box["job_cap_usd"]:
                raise SystemExit(f"spent ${spent:.2f} on failed hosts + projection > cap")
            if os.environ.get("YES") != "1":
                self.log("dry run: nothing rented (YES=1 rents)")
                return
            self.spend_check()
            iid, t0 = self.create(offer, pre)
            if iid is None:
                spent += 0.05
                continue
            try:
                ok = self.bring_up(iid, offer, t0, provision, spent)
            except BaseException as exc:
                if self.started(iid):
                    raise  # the runner runs: the watcher and .claude/box_teardown.sh own the box now
                self.destroy_unprovisioned(iid, offer["machine_id"], f"unexpected {exc!r}")
                if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                    raise
                ok = False
            if ok:
                return
            spent += (time.time() - t0) / 3600.0 * pj["rate_usd_h"] + 0.05
        raise SystemExit(f"{self.box['max_tries']} hosts failed; nothing is left running")

    def create(self, offer: dict, pre: dict) -> tuple[int | None, float]:
        """The create call, guarded: on any exception every instance with our label is registered and destroyed."""
        pub = (Path.home() / ".ssh/vast_recover.pub").read_text().strip()
        onstart = ("(while true; do mkdir -p /root/.ssh; touch /root/.ssh/authorized_keys; "
                   f"grep -qF '{pub}' /root/.ssh/authorized_keys || echo '{pub}' >> /root/.ssh/authorized_keys; "
                   "chown -R 0:0 /root/.ssh; chmod 700 /root/.ssh; chmod 600 /root/.ssh/authorized_keys; "
                   "chmod g-w,o-w /root; sleep 30; done) >/dev/null 2>&1 &\nentrypoint.sh")
        t0 = time.time()
        try:
            created = json.loads(self.vast("create", "instance", str(offer["id"]), "--image", self.box["image"],
                                           "--disk", str(self.box["disk_gb"]), "--label", self.label, "--ssh",
                                           "--direct", "--cancel-unavail", "--env", "-e propagate_user_keys=true",
                                           "--onstart-cmd", onstart, "--raw", timeout=180))
            iid = int(created["new_contract"])
        except BaseException as exc:
            self.log(f"create failed ({exc!r}); searching for anything it made")
            for attempt in range(3):
                try:
                    made = [r for r in self.all_instances() if (r.get("label") or "") == self.label]
                    break
                except (RuntimeError, ValueError, subprocess.TimeoutExpired) as exc2:
                    self.log(f"listing after a failed create failed ({exc2}); retry {attempt + 1}/3")
                    time.sleep(10)
            else:
                (REPO / f"tmp/NEEDS_HUMAN_{self.label}").write_text(
                    f"{now()} a create failed and the account cannot be listed: a box labelled {self.label} may bill\n")
                raise SystemExit("the create failed and the listing failed three times; IT MAY BILL")
            for r in made:
                self.provisional_entry(int(r["id"]), t0, offer, pre)
                self.destroy_unprovisioned(int(r["id"]), offer.get("machine_id"), "create call failed")
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            return None, t0
        self.provisional_entry(iid, t0, offer, pre)
        self.log(f"created {iid}; provisional registry entry written")
        return iid, t0

    def started(self, iid: int) -> bool:
        """True once this box's runner was confirmed up (launch/start_<id>.txt holds RUNNER_UP)."""
        p = self.launch_dir / f"start_{iid}.txt"
        return p.exists() and "RUNNER_UP" in p.read_text()

    def bring_up(self, iid: int, offer: dict, t0: float, provision, spent: float = 0.0) -> bool:
        while True:
            info = self.instance(iid)
            st = (info or {}).get("actual_status")
            if st == "running":
                break
            if st in ("offline", "exited", "unknown") or time.time() - t0 > self.box["load_timeout_s"]:
                self.destroy_unprovisioned(iid, offer["machine_id"], f"state {st} after {time.time() - t0:.0f}s")
                return False
            time.sleep(15)
        live = float(info.get("dph_total") or offer["dph_total"])
        pj = self.projection(offer, live, spent)
        if spent + pj["cost_usd"] > self.box["job_cap_usd"]:
            self.destroy_unprovisioned(iid, offer["machine_id"], f"live rate projects ${pj['cost_usd']} > cap less "
                                                                 f"${spent:.2f} spent")
            return False
        deadline = time.time() + self.box["ssh_sla_s"]
        while time.time() < deadline:
            for host, port in self.endpoints(self.instance(iid) or {}):
                if self.ssh(host, port, "true", timeout=20).returncode != 0:
                    continue
                reason, facts = self.arrival(iid, host, port)
                (self.launch_dir / f"arrival_{iid}.json").write_text(json.dumps({"ts": now(), "reason": reason,
                                                                                 **facts}, indent=1))
                if reason:
                    self.destroy_unprovisioned(iid, offer["machine_id"], reason)
                    return False
                teardown_at = t0 + pj["teardown_deadline_minutes"] * 60
                self.registry_update(iid, host=host, port=int(port), provisional=False, arrived_at=now(),
                                     dph_live=live, projection=pj, teardown_deadline_utc=iso(teardown_at),
                                     teardown_deadline_unix=teardown_at)
                choice = {"instance": iid, "label": self.label, "created_at_unix": t0, "rate_usd_h": pj["rate_usd_h"],
                          "dph_live": live, "job_cap_usd": self.box["job_cap_usd"], "spent_before_usd": spent,
                          "capture_reserve_minutes": self.box["capture_reserve_minutes"],
                          "teardown_deadline_unix": teardown_at, "teardown_deadline_utc": iso(teardown_at),
                          "projection": pj, "written_at": now()}
                cfile = self.launch_dir / f"box_choice_{iid}.json"
                cfile.write_text(json.dumps(choice, indent=1))
                # The watcher starts before provisioning: a launcher killed from here on leaves a box it still owns.
                pid = self.start_watcher(iid)
                if pid == 0:  # no watcher: nothing of ours runs yet, so the box goes before provisioning
                    self.destroy_unprovisioned(iid, offer["machine_id"], "the watcher did not start")
                    return False
                self.registry_update(iid, watcher_pid=pid)
                try:
                    R = self.recipe["remote_root"]
                    self.ssh(host, port, f"mkdir -p {R}/inputs {R}/box {R}/flags")
                    self.rsync(host, port, [str(cfile)], f"{R}/inputs/box_choice.json", relative=False)
                    provision(self, iid, host, port, pj)
                except Exception as exc:  # noqa: BLE001 the runner never started: everything on the box is reproducible
                    if self.started(iid):
                        raise
                    self.destroy_unprovisioned(iid, offer["machine_id"], f"provisioning failed: {exc!r}")
                    return False
                ok = self.audit_monitored(iid, pid)
                self.log(f"READY {iid} at {host}:{port}; runner started; teardown deadline {iso(teardown_at)} "
                         f"(${self.box['job_cap_usd']:.2f} less ${spent:.2f} spent, less "
                         f"{self.box['capture_reserve_minutes']} min at ${pj['rate_usd_h']:.3f}/h); watcher pid {pid}; "
                         f"monitoring {'OK' if ok else 'FAILED: see tmp/NEEDS_HUMAN_' + self.label}")
                if not ok:
                    raise SystemExit(2)
                return True
            time.sleep(15)
        self.destroy_unprovisioned(iid, offer["machine_id"], f"no ssh within {self.box['ssh_sla_s']}s")
        return False

    def start_runner(self, host: str, port: str, runner_rel: str, iid: int, env: dict[str, str] | None = None) -> None:
        envs = " ".join(f"{k}={v}" for k, v in {"VLLM_NO_USAGE_STATS": "1", "DO_NOT_TRACK": "1",
                                                **(env or {})}.items())
        R = self.recipe["remote_root"]
        # The cd stays outside the background job: `cd X && cmd &` backgrounds a subshell that keeps the ssh
        # session's stdout open while the runner lives, so the ssh call hung to its timeout (2026-11-15, 60744350).
        res = self.ssh(host, port, f"cd {R} || exit 1\n{envs} nohup setsid bash {runner_rel} > {R}/box/runner.stdout "
                                   f"2>&1 < /dev/null & sleep 20; pgrep -f '{Path(runner_rel).name}' > /dev/null && "
                                   f"echo RUNNER_UP; tail -3 {R}/box/runner.log", timeout=90)
        (self.launch_dir / f"start_{iid}.txt").write_text(res.stdout + res.stderr)
        if "RUNNER_UP" not in res.stdout:
            raise RuntimeError(f"runner did not start: {res.stdout[-300:]}")
        self.log(f"{Path(runner_rel).name} is running")

    # ------------------------------------------------------------ the watcher and the monitoring audit
    def start_watcher(self, iid: int) -> int:
        """watch_box.py <recipe> <id>, detached in its own session under caffeinate; returns its pid (0 if not up)."""
        self.launch_dir.mkdir(parents=True, exist_ok=True)
        logf = open(self.launch_dir / f"watch_{iid}.log", "a")
        cmd = [sys.executable, str(WATCH), str(self.recipe_path), str(iid)]
        if Path("/usr/bin/caffeinate").exists():
            cmd = ["/usr/bin/caffeinate", "-i", *cmd]
        subprocess.Popen(cmd, cwd=REPO, stdout=logf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                         start_new_session=True)
        pidf = self.launch_dir / f"watch_{iid}.pid"
        for _ in range(20):
            time.sleep(1)
            if pidf.exists():
                pid = int(pidf.read_text().split()[0])
                try:
                    os.kill(pid, 0)
                    self.log(f"watcher for {iid} runs (pid {pid}, log {self.launch_dir / f'watch_{iid}.log'})")
                    return pid
                except OSError:
                    break
        (REPO / f"tmp/NEEDS_HUMAN_{self.label}").write_text(
            f"{now()} the watcher for {iid} did not start: run it by hand now (watch_box.py {self.recipe_path} {iid})\n")
        self.log(f"!! THE WATCHER FOR {iid} DID NOT START: nohup caffeinate -i {sys.executable} {WATCH} "
                 f"{self.recipe_path} {iid} >> {self.launch_dir}/watch_{iid}.log 2>&1 &")
        return 0

    def audit_monitored(self, iid: int, pid: int) -> bool:
        """The launcher's last step: the guard's adapter answers `progress` for this box and its watcher runs."""
        seen = "(nothing)"
        for _ in range(4):
            r = subprocess.run(["bash", str(REPO / ".claude/box_progress.sh"), "vast", str(iid)], cwd=REPO,
                               capture_output=True, text=True, timeout=180)
            seen = (r.stdout.strip().splitlines() or ["(nothing)"])[-1]
            if seen.startswith("progress"):
                break
            time.sleep(15)
        try:
            os.kill(pid, 0)
            alive = pid > 0
        except OSError:
            alive = False
        ok = seen.startswith("progress") and alive
        self.log(f"monitoring audit for {iid}: box_progress.sh says {seen!r}; watcher pid {pid} "
                 f"{'alive' if alive else 'NOT RUNNING'}: {'OK' if ok else 'FAILED'}")
        if not ok:
            (REPO / f"tmp/NEEDS_HUMAN_{self.label}").write_text(
                f"{now()} box {iid} is not fully monitored: adapter {seen!r}, watcher alive {alive}\n")
        return ok
