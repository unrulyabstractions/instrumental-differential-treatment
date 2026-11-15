"""Capped OpenRouter caller for the second-base draws. Every paid generation call goes here.

Adapted from the diag_20261113 runner (``diag_20261113_record/diag_20261113_capped_runner.py``).

Money rules enforced in code:
- One append-only ledger, ``OUT/generation_ledger.jsonl``. A "reserve" entry (the call's bound)
  is written BEFORE each request and a "settle" entry (the returned cost) after it.
- committed = settled actual cost + the bound of every unsettled reservation.
- A reservation is REFUSED when committed + bound would pass the generation cap ($3.00) or its
  stage cap. A retry is a new reservation.
- The main OpenRouter key is shared with other projects (no provisioning key exists to make a
  dedicated one). Its usage is read at start and every 500 requests; a rise above $3.50 since
  the first read stops the run. A 401, 402 or 403 stops the run at once.
- Keys are read from the environment and never printed, logged or written.
"""
from __future__ import annotations

import fcntl
import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "out/main/auditbench/second_bases_20261115"
LEDGER = OUT / "generation_ledger.jsonl"
LOCKFILE = OUT / "generation_ledger.lock"
KEY_BASELINE = OUT / "key_usage_baseline.json"

GEN_CAP = 3.00
ITEM_CAP = 28.00
JUDGE_CAP = 25.00
KEY_RISE_STOP = 3.50
#: G0 is the 20-request pilot; G1 the two draws (the generation cap only).
STAGE_CAPS = {"G0": 0.05, "G1": None}
#: meta-llama/llama-3.3-70b-instruct on coreweave/fp16, USD per token (in, out). The pilot
#: reads the live endpoint price and stops if it differs.
PRICE = (0.71e-6, 0.71e-6)
OR_BASE = "https://openrouter.ai/api/v1"
KEY_ENV = "OPENROUTER_API_KEY"
STOP_STATUS = {401, 402, 403}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CapRefused(RuntimeError):
    pass


class ProviderStop(RuntimeError):
    """The key rose past its stop, or the provider refused for auth or credit."""


class Ledger:
    """Append-only spend ledger shared by every process of this item (file lock + thread lock)."""

    def __init__(self, path: Path = LEDGER, total_cap: float = GEN_CAP):
        self.path, self.cap = path, total_cap
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._tlock = threading.Lock()
        self._off = 0
        self._bound: dict[str, float] = {}
        self._cost: dict[str, float] = {}
        self._stage: dict[str, str] = {}

    def _sync(self) -> None:
        if not self.path.exists():
            return
        with open(self.path, "rb") as fh:
            fh.seek(self._off)
            data = fh.read()
        end = data.rfind(b"\n")
        if end < 0:
            return
        for line in data[:end + 1].splitlines():
            if not line.strip():
                continue
            e = json.loads(line)
            ev, rid = e.get("event"), e.get("id")
            if ev == "reserve":
                self._bound[rid] = float(e["bound_usd"])
                self._stage[rid] = e["stage"]
            elif ev == "settle":
                self._cost[rid] = float(e["cost_usd"])
        self._off += end + 1

    def _append(self, entry: dict) -> None:
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def _locked(self):
        lock = open(LOCKFILE, "a")
        fcntl.flock(lock, fcntl.LOCK_EX)
        return lock

    def _do(self, fn):
        with self._tlock:
            lock = self._locked()
            try:
                self._sync()
                return fn()
            finally:
                lock.close()

    def committed(self, stage: str | None = None) -> float:
        return self._do(lambda: self._committed(stage))

    def _committed(self, stage: str | None) -> float:
        return sum(self._cost.get(rid, b) for rid, b in self._bound.items()
                   if stage is None or self._stage.get(rid) == stage)

    def settled(self, stage: str | None = None) -> tuple[float, int]:
        def f():
            ids = [r for r in self._cost if stage is None or self._stage.get(r) == stage]
            return sum(self._cost[r] for r in ids), len(ids)
        return self._do(f)

    def reserve(self, rid: str, stage: str, bound: float, **meta) -> None:
        if stage not in STAGE_CAPS:
            raise ValueError(f"unknown stage {stage}")

        def f():
            if rid in self._bound:
                raise ValueError(f"duplicate reservation id {rid}")
            tot, st, cap_s = self._committed(None), self._committed(stage), STAGE_CAPS[stage]
            why = None
            if tot + bound > self.cap + 1e-12:
                why = f"total {tot:.6f} + bound {bound:.6f} > cap {self.cap:.2f}"
            elif cap_s is not None and st + bound > cap_s + 1e-12:
                why = f"stage {stage} {st:.6f} + bound {bound:.6f} > stage cap {cap_s:.2f}"
            if why:
                self._append({"event": "refused", "id": rid, "stage": stage,
                              "bound_usd": round(bound, 8), "cap_usd": self.cap,
                              "reason": why, "ts": now(), **meta})
                raise CapRefused(why)
            self._append({"event": "reserve", "id": rid, "stage": stage,
                          "bound_usd": round(bound, 8), "committed_before": round(tot, 6),
                          "ts": now(), **meta})
            self._bound[rid] = bound
            self._stage[rid] = stage
        self._do(f)

    def settle(self, rid: str, cost: float, **meta) -> None:
        def f():
            if rid not in self._bound:
                raise ValueError(f"settle of unknown id {rid}")
            if rid in self._cost:
                raise ValueError(f"double settle {rid}")
            self._append({"event": "settle", "id": rid, "cost_usd": round(cost, 8),
                          "ts": now(), **meta})
            self._cost[rid] = cost
        self._do(f)

    def note(self, **entry) -> None:
        self._do(lambda: self._append({"ts": now(), **entry}))


def _key() -> str:
    k = os.environ.get(KEY_ENV)
    if not k:
        raise SystemExit(f"{KEY_ENV} is not set")
    return k


def or_client(timeout: float = 180.0) -> httpx.Client:
    # No HTTP-Referer, no X-Title, no user name.
    return httpx.Client(base_url=OR_BASE, timeout=timeout,
                        headers={"Authorization": f"Bearer {_key()}",
                                 "Content-Type": "application/json"})


def key_usage() -> dict:
    with or_client(30) as c:
        r = c.get("/key")
        r.raise_for_status()
        d = r.json().get("data") or {}
    return {k: d.get(k) for k in ("usage", "usage_daily", "limit", "limit_remaining",
                                  "is_free_tier")}


def key_check(ledger: Ledger, label: str) -> dict:
    """Record the key's usage and stop if it rose more than $3.50 since the first read."""
    u = key_usage()
    if not KEY_BASELINE.exists():
        KEY_BASELINE.write_text(json.dumps({"ts": now(), "key_env": KEY_ENV, **u}, indent=1))
    base = json.loads(KEY_BASELINE.read_text())
    rise = float(u["usage"]) - float(base["usage"])
    ledger.note(event="key_usage", label=label, usage=u["usage"], usage_daily=u.get("usage_daily"),
                limit=u.get("limit"), limit_remaining=u.get("limit_remaining"),
                rise_since_baseline=round(rise, 6), baseline_usage=base["usage"])
    if rise > KEY_RISE_STOP:
        raise ProviderStop(f"key usage rose ${rise:.4f} since baseline (> ${KEY_RISE_STOP})")
    return {**u, "rise": rise}


class ORCaller:
    """Capped OpenRouter caller: reserve, request, append raw, settle. Thread-safe."""

    def __init__(self, ledger: Ledger, raw_path: Path, stage: str):
        self.ledger, self.raw_path, self.stage = ledger, raw_path, stage
        self.pin, self.pout = PRICE
        self._client = or_client()
        self._raw_lock = threading.Lock()
        self._n = 0
        self._nlock = threading.Lock()
        raw_path.parent.mkdir(parents=True, exist_ok=True)

    def bound(self, prompt_tokens: int, max_tokens: int) -> float:
        return prompt_tokens * self.pin + max_tokens * self.pout

    def _raw(self, entry: dict) -> None:
        with self._raw_lock, open(self.raw_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
            fh.flush()

    def post(self, path: str, body: dict, call_id: str, bound: float, meta: dict) -> dict:
        """One attempt. Returns the raw record. Raises ProviderStop on 401, 402 or 403."""
        rid = f"{call_id}|{uuid.uuid4().hex[:8]}"
        self.ledger.reserve(rid, self.stage, bound, route="openrouter", path=path, call_id=call_id)
        t0 = time.time()
        rec = {"id": rid, "call_id": call_id, "path": path, "request": body, "ts": now(), **meta}
        try:
            r = self._client.post(path, json=body)
            rec["status"] = r.status_code
            try:
                rec["response"] = r.json()
            except Exception:  # noqa: BLE001
                rec["response_text"] = r.text[:2000]
        except Exception as exc:  # noqa: BLE001 timeouts: billing unknown -> settle at bound
            rec["status"] = None
            rec["exception"] = f"{type(exc).__name__}: {str(exc)[:300]}"
        rec["elapsed_s"] = round(time.time() - t0, 3)
        self._raw(rec)  # raw before any parsing
        resp = rec.get("response") or {}
        usage = resp.get("usage") if isinstance(resp, dict) else None
        if usage and usage.get("cost") is not None:
            self.ledger.settle(rid, float(usage["cost"]), provider=resp.get("provider"),
                               prompt_tokens=usage.get("prompt_tokens"),
                               completion_tokens=usage.get("completion_tokens"),
                               status=rec["status"])
        elif rec["status"] is not None and rec["status"] >= 400:
            # OpenRouter does not bill an HTTP error; the key-usage read reconciles it.
            self.ledger.settle(rid, 0.0, status=rec["status"], note="http error, no usage")
        else:
            self.ledger.settle(rid, bound, status=rec["status"],
                               note="no usage returned; settled at bound (conservative)")
        if rec["status"] in STOP_STATUS:
            raise ProviderStop(f"HTTP {rec['status']} from OpenRouter: "
                               f"{json.dumps(resp)[:200] if resp else rec.get('response_text', '')[:200]}")
        with self._nlock:
            self._n += 1
            n = self._n
        if n % 500 == 0:
            key_check(self.ledger, f"{self.stage} after {n} requests")
        return rec

    def generation_stats(self, gen_id: str, tries: int = 6) -> dict | None:
        for i in range(tries):
            try:
                r = self._client.get("/generation", params={"id": gen_id})
                if r.status_code == 200:
                    return (r.json() or {}).get("data")
            except Exception:  # noqa: BLE001
                pass
            time.sleep(1.5 * (i + 1))
        return None
