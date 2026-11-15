"""Shared launcher core for the B73 and B74 boxes: credit rule, offer, rental, arrival checks, registry, destroy.

Modelled on script/remote/auditbench/exact_stack/launch_exact_stack.py (B55: a host that fails a check is
destroyed before anything of ours runs on it, and its machine is blocklisted). Each launcher passes a recipe
(``small_box_recipe.json`` or ``big_box_recipe.json``) and a provision function. Nothing here is typed from memory.

The credit rule (task text, 2026-11-15): before any rental, read the live vast credit and every live instance on
the account. Each live instance's remaining projected cost is its registry entry's job cap minus what it has
billed so far (elapsed hours x its live $/h); an instance no registry lists refuses the rental outright. The
rental is refused when credit - (sum of remaining + this job's cap) < min_margin_usd ($5).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
KEYS = [Path.home() / ".ssh/id_ed25519", Path.home() / ".ssh/vast_recover"]
GUARD = Path.home() / ".claude/hooks/cloud_boxes_guard.py"
MY_INSTANCES = REPO / "tmp/r2_my_instances.txt"
SPEED_URL = ("https://huggingface.co/auditing-agents/llama_70b_synth_docs_only_emotional_bond"
             "/resolve/main/adapter_model.safetensors")
#: Job caps of other workstreams' boxes whose registries do not record one (B71: exact-stack box cap $30).
KNOWN_CAPS = {"idt-exact-stack-a2": 30.0}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Launch:
    def __init__(self, recipe_path: Path) -> None:
        self.recipe = json.loads(recipe_path.read_text())
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
            cap = (entry or {}).get("job_cap_usd") or KNOWN_CAPS.get(label)
            if cap is None:
                raise SystemExit(f"credit rule: live instance {iid} ({label!r}) has no recorded job cap; refusing")
            start = (entry or {}).get("created_at")
            t0 = (datetime.fromisoformat(start).timestamp() if start
                  else float(inst.get("start_date") or time.time()))
            billed = max(0.0, (time.time() - t0) / 3600.0) * dph
            others.append({"id": iid, "label": label, "dph": dph, "cap": cap, "billed": round(billed, 2),
                           "remaining": round(max(0.0, cap - billed), 2)})
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
        listed = [str(p) for p in self.registries()]
        if str(self.registry) not in listed:
            raise SystemExit(f"preflight: {self.registry} is not listed in .claude/box_registries")
        alive = subprocess.run([sys.executable, str(GUARD), "daemon-alive", "--project", str(REPO)],
                               capture_output=True, text=True, timeout=120)
        if alive.returncode != 0:
            raise SystemExit(f"preflight: guard refuses: {(alive.stdout + alive.stderr).strip()[:400]}")
        if any((r.get("label") or "") == self.label for r in self.all_instances()):
            raise SystemExit(f"preflight: an instance labelled {self.label} already exists")
        rule = self.credit_rule()
        return {"credit_rule": rule, "registration_sha256": hashlib.sha256(reg_md.read_bytes()).hexdigest()}

    # ------------------------------------------------------------ offer and projection
    def rate_of(self, o: dict, dph_total: float | None = None) -> float:
        base = float(o["dph_base"]) if dph_total is None else dph_total - (o["dph_total"] - o["dph_base"])
        return base + float(o.get("storage_cost") or 0) * self.box["disk_gb"] / 720.0

    def projection(self, o: dict, dph_total: float | None = None) -> dict:
        pm = self.recipe["phase_minutes"]
        fetch = self.recipe["download_gb"] * 8e3 / float(o["inet_down"]) / 60.0
        # The runner fetches the weights while it installs the engine, so the two overlap.
        minutes = sum(pm.values()) - pm["push_and_install"] + max(pm["push_and_install"], fetch)
        rate = self.rate_of(o, dph_total)
        bandwidth = float(o.get("inet_down_cost") or 0) * (self.recipe["download_gb"] + 2.0)
        cost = rate * minutes / 60.0 + bandwidth
        deadline = (self.box["job_cap_usd"] - bandwidth) / rate * 60.0 - self.box["capture_reserve_minutes"]
        return {"minutes": round(minutes, 1), "fetch_minutes": round(fetch, 1), "rate_usd_h": round(rate, 4),
                "bandwidth_usd": round(bandwidth, 3), "cost_usd": round(cost, 2),
                "teardown_deadline_minutes": round(deadline, 1)}

    def offer_ok(self, o: dict, exclude: set[str]) -> bool:
        b = self.box
        return (o.get("num_gpus") == b["num_gpus"] and str(o.get("gpu_name")) in b["gpu_names"]
                and o.get("gpu_ram", 0) >= b["min_gpu_mib"] and o.get("reliability", 0) > b["min_reliability"]
                and o.get("inet_down", 0) >= b["min_inet_down_mbps"] and o.get("disk_space", 0) >= b["disk_gb"] + 10
                and float(o.get("cuda_max_good", 0)) >= b["min_cuda_max_good"] and o.get("dph_total", 99) <= b["max_dph"]
                and (o.get("inet_down_cost") or 0) <= b["max_inet_down_cost"] and str(o.get("machine_id")) not in exclude)

    def pick_offer(self) -> tuple[dict, dict]:
        exclude = {ln.split()[0] for ln in (self.blocklist.read_text().splitlines()
                                            if self.blocklist.exists() else []) if ln.strip()}
        exclude |= {str(r.get("machine_id")) for r in self.all_instances()}
        offers = json.loads(self.vast("search", "offers", self.box["query"], "-o", "dph_total", "--raw"))
        seen, fits = [], []
        for o in offers:
            ok = self.offer_ok(o, exclude)
            pj = self.projection(o) if ok else None
            seen.append({"id": o.get("id"), "machine_id": o.get("machine_id"), "gpu": o.get("gpu_name"),
                         "dph_total": o.get("dph_total"), "inet_down": o.get("inet_down"), "ok": ok, "projection": pj})
            if ok and pj["cost_usd"] <= self.box["job_cap_usd"]:
                fits.append((o, pj))
        self.launch_dir.mkdir(parents=True, exist_ok=True)
        (self.launch_dir / f"offers_read_{int(time.time())}.json").write_text(json.dumps({"ts": now(), "offers": seen},
                                                                                         indent=1))
        if not fits:
            raise SystemExit(f"no offer passes every check within ${self.box['job_cap_usd']}; nothing rented")
        fits.sort(key=lambda x: (self.box["gpu_names"].index(str(x[0]["gpu_name"])), x[1]["cost_usd"]))
        return fits[0]

    # ------------------------------------------------------------ ssh, arrival, destroy
    @staticmethod
    def ssh(host: str, port: str, cmd: str, timeout: int = 60) -> subprocess.CompletedProcess:
        for key in KEYS:
            try:
                out = subprocess.run(["ssh", "-F", "/dev/null", "-i", str(key), "-o", "IdentitiesOnly=yes",
                                      "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
                                      "-o", "ConnectTimeout=10", "-o", "BatchMode=yes", "-p", str(port),
                                      f"root@{host}", "bash -s"], input=cmd, capture_output=True, text=True,
                                     timeout=timeout)
            except subprocess.TimeoutExpired:
                continue
            if out.returncode != 255:
                return out
        return subprocess.CompletedProcess(cmd, 255, "", "ssh failed on every key")

    @staticmethod
    def rsync_cmd(port: str) -> str:
        return (f"ssh -F /dev/null -i {KEYS[0]} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no "
                f"-o UserKnownHostsFile=/dev/null -o ConnectTimeout=20 -p {port}")

    def rsync(self, host: str, port: str, src: list[str], dest: str, extra: list[str] | None = None,
              relative: bool = True, timeout: int = 900) -> None:
        args = ["rsync", "-az", "--timeout=120", *(["-R"] if relative else []), *(extra or []),
                "-e", self.rsync_cmd(port), *src, f"root@{host}:{dest}"]
        out = subprocess.run(args, cwd=REPO, capture_output=True, text=True, timeout=timeout)
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
            offer, pj = self.pick_offer()
            self.log(f"attempt {attempt}: offer {offer['id']} {offer['num_gpus']}x{offer['gpu_name']} "
                     f"${offer['dph_total']:.3f}/h projection {json.dumps(pj)}")
            if spent + pj["cost_usd"] > self.box["job_cap_usd"]:
                raise SystemExit(f"spent ${spent:.2f} on failed hosts + projection > cap")
            if os.environ.get("YES") != "1":
                self.log("dry run: nothing rented (YES=1 rents)")
                return
            pub = (Path.home() / ".ssh/vast_recover.pub").read_text().strip()
            onstart = ("(while true; do mkdir -p /root/.ssh; touch /root/.ssh/authorized_keys; "
                       f"grep -qF '{pub}' /root/.ssh/authorized_keys || echo '{pub}' >> /root/.ssh/authorized_keys; "
                       "chown -R 0:0 /root/.ssh; chmod 700 /root/.ssh; chmod 600 /root/.ssh/authorized_keys; "
                       "chmod g-w,o-w /root; sleep 30; done) >/dev/null 2>&1 &\nentrypoint.sh")
            t0 = time.time()
            created = json.loads(self.vast("create", "instance", str(offer["id"]), "--image", self.box["image"],
                                           "--disk", str(self.box["disk_gb"]), "--label", self.label, "--ssh",
                                           "--direct", "--cancel-unavail", "--env", "-e propagate_user_keys=true",
                                           "--onstart-cmd", onstart, "--raw", timeout=180))
            iid = int(created["new_contract"])
            MY_INSTANCES.parent.mkdir(parents=True, exist_ok=True)
            with MY_INSTANCES.open("a") as fh:
                fh.write(f"{iid} {self.label}\n")
            self.registry_update(iid, label=self.label, destroyed=False, job_cap_usd=self.box["job_cap_usd"],
                                 created_at=datetime.fromtimestamp(t0, timezone.utc).isoformat(timespec="seconds"),
                                 host="0.0.0.0", port=22, remote_roots=["/workspace", "/root"],
                                 remote_run_dir=self.recipe["remote_root"],
                                 local_capture_dir=self.recipe["capture_rel"],
                                 done_marker=f"{self.recipe['remote_root']}/RUNNER_DONE", procs=self.recipe["procs"],
                                 machine_id=offer["machine_id"], offer_id=offer["id"],
                                 registration_sha256=pre["registration_sha256"])
            ok = self.bring_up(iid, offer, t0, provision)
            if ok:
                return
            spent += (time.time() - t0) / 3600.0 * pj["rate_usd_h"] + 0.05
        raise SystemExit(f"{self.box['max_tries']} hosts failed; nothing is left running")

    def bring_up(self, iid: int, offer: dict, t0: float, provision) -> bool:
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
        pj = self.projection(offer, live)
        if pj["cost_usd"] > self.box["job_cap_usd"]:
            self.destroy_unprovisioned(iid, offer["machine_id"], f"live rate projects ${pj['cost_usd']} > cap")
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
                self.registry_update(iid, host=host, port=int(port), dph_live=live, projection=pj,
                                     teardown_deadline_utc=datetime.fromtimestamp(teardown_at, timezone.utc)
                                     .isoformat(timespec="seconds"))
                try:
                    provision(self, iid, host, port, pj)
                except Exception as exc:  # noqa: BLE001 the runner never started
                    self.destroy_unprovisioned(iid, offer["machine_id"], f"provisioning failed: {exc!r}")
                    return False
                self.log(f"READY {iid} at {host}:{port}; runner started; teardown deadline "
                         f"{datetime.fromtimestamp(teardown_at, timezone.utc).isoformat(timespec='seconds')}; "
                         f"check `bash .claude/box_progress.sh vast {iid}`")
                return True
            time.sleep(15)
        self.destroy_unprovisioned(iid, offer["machine_id"], f"no ssh within {self.box['ssh_sla_s']}s")
        return False

    def start_runner(self, host: str, port: str, runner_rel: str, env: dict[str, str]) -> None:
        envs = " ".join(f"{k}={v}" for k, v in env.items())
        R = self.recipe["remote_root"]
        res = self.ssh(host, port, f"cd {R} && {envs} nohup setsid bash {runner_rel} > {R}/box/runner.stdout 2>&1 "
                                   f"< /dev/null & sleep 20; pgrep -f '{Path(runner_rel).name}' > /dev/null && "
                                   f"echo RUNNER_UP; tail -3 {R}/box/runner.log", timeout=90)
        (self.launch_dir / "start.txt").write_text(res.stdout + res.stderr)
        if "RUNNER_UP" not in res.stdout:
            raise RuntimeError(f"runner did not start: {res.stdout[-300:]}")
