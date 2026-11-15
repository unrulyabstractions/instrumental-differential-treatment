"""Capped runner for the diag_20261113 experiments. Every paid call goes through here.

Money rules enforced in code:
- One append-only ledger: OUT/spend_ledger.jsonl. A "reserve" entry (the call's bound) is written
  BEFORE each request or batch, a "settle" entry (actual cost) after it.
- committed = sum(actual cost of settled entries) + sum(bound of unsettled reservations).
- A reservation is REFUSED when committed + bound would pass the total cap ($9.00) or its stage cap.
- Retries are separate reservations, so they count toward the cap.
- OpenRouter: every request carries usage.include; usage.cost, provider and tokens are recorded.
  The OWN key's usage is read at start, after the pilot, every 500 requests and at the end; the
  run stops if it rose more than $9.50 since the first read.
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

REPO = Path("/Users/unrulyabstractions/work/_OLD/instrumental-differential-treatment")
OUT = REPO / "out/main/auditbench/nullext/diag_20261113"
LEDGER = OUT / "spend_ledger.jsonl"
LOCKFILE = OUT / "spend_ledger.lock"
KEY_BASELINE = OUT / "key_usage_baseline.json"

TOTAL_CAP = float(os.environ.get("DIAG_TOTAL_CAP", "9.00"))
KEY_RISE_STOP = 9.50
# Stage caps from the design (S5 = extra layers: total rule only).
STAGE_CAPS = {"S0": 0.15, "S1": 1.85, "S2": 1.30, "S3": 5.60, "S4": 0.60, "S5": None}

# List prices, USD per token.
PRICE = {
    "openai_batch": (0.125e-6, 1.00e-6),     # gpt-5-mini batch (nullext/spend_ledger.json)
    "openai_live": (0.25e-6, 2.00e-6),       # gpt-5-mini standard tier
    "or_flex": (0.125e-6, 1.00e-6),          # openai/gpt-5-mini via openai/flex
    "coreweave": (0.71e-6, 0.71e-6),         # meta-llama/llama-3.3-70b-instruct coreweave/fp16
}
# Billed prompt tokens per character in base B's 17,279 judge calls: max 0.2102, mean 0.1872.
JUDGE_TOKENS_PER_CHAR_BOUND = 0.22
JUDGE_FRAMING_TOKENS = 16

OR_BASE = "https://openrouter.ai/api/v1"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CapRefused(RuntimeError):
    pass


class KeyRiseStop(RuntimeError):
    pass


class Ledger:
    """Append-only spend ledger shared by every process of this run (file lock + thread lock)."""

    def __init__(self, path: Path = LEDGER, total_cap: float = TOTAL_CAP):
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

    def committed(self, stage: str | None = None) -> float:
        with self._tlock:
            lock = self._locked()
            try:
                self._sync()
                return self._committed(stage)
            finally:
                lock.close()

    def _committed(self, stage: str | None) -> float:
        tot = 0.0
        for rid, b in self._bound.items():
            if stage is not None and self._stage.get(rid) != stage:
                continue
            tot += self._cost.get(rid, b)
        return tot

    def has_id(self, rid: str) -> bool:
        with self._tlock:
            lock = self._locked()
            try:
                self._sync()
                return rid in self._bound
            finally:
                lock.close()

    def settled_actual(self) -> float:
        with self._tlock:
            lock = self._locked()
            try:
                self._sync()
                return sum(self._cost.values())
            finally:
                lock.close()

    def reserve(self, rid: str, stage: str, bound: float, **meta) -> None:
        if stage not in STAGE_CAPS:
            raise ValueError(f"unknown stage {stage}")
        with self._tlock:
            lock = self._locked()
            try:
                self._sync()
                if rid in self._bound:
                    raise ValueError(f"duplicate reservation id {rid}")
                tot = self._committed(None)
                st = self._committed(stage)
                cap_s = STAGE_CAPS[stage]
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
            finally:
                lock.close()

    def settle(self, rid: str, cost: float, **meta) -> None:
        with self._tlock:
            lock = self._locked()
            try:
                self._sync()
                if rid not in self._bound:
                    raise ValueError(f"settle of unknown id {rid}")
                if rid in self._cost:
                    raise ValueError(f"double settle {rid}")
                self._append({"event": "settle", "id": rid, "cost_usd": round(cost, 8),
                              "ts": now(), **meta})
                self._cost[rid] = cost
            finally:
                lock.close()

    def note(self, **entry) -> None:
        with self._tlock:
            lock = self._locked()
            try:
                self._append({"ts": now(), **entry})
            finally:
                lock.close()


# ---------------------------------------------------------------- OpenRouter (OWN key only)

def _or_key() -> str:
    k = os.environ.get("OPENROUTER_API_KEY_OWN")
    if not k:
        raise SystemExit("OPENROUTER_API_KEY_OWN is not set")
    return k


def _or_client(timeout: float = 180.0) -> httpx.Client:
    # No HTTP-Referer, no X-Title, no user name.
    return httpx.Client(base_url=OR_BASE, timeout=timeout,
                        headers={"Authorization": f"Bearer {_or_key()}",
                                 "Content-Type": "application/json"})


def or_key_usage() -> dict:
    with _or_client(30) as c:
        r = c.get("/key")
        r.raise_for_status()
        d = r.json().get("data") or {}
    keep = ("usage", "usage_daily", "usage_weekly", "usage_monthly", "limit", "limit_remaining",
            "is_free_tier")
    return {k: d.get(k) for k in keep}


def key_check(ledger: Ledger, label: str) -> dict:
    """Read the OWN key's usage, record it, and stop if it rose > $9.50 since the baseline."""
    u = or_key_usage()
    if not KEY_BASELINE.exists():
        KEY_BASELINE.write_text(json.dumps({"ts": now(), **u}, indent=1))
    base = json.loads(KEY_BASELINE.read_text())
    rise = float(u["usage"]) - float(base["usage"])
    ledger.note(event="key_usage", label=label, usage=u["usage"], usage_daily=u.get("usage_daily"),
                limit=u.get("limit"), limit_remaining=u.get("limit_remaining"),
                rise_since_baseline=round(rise, 6), baseline_usage=base["usage"])
    if rise > KEY_RISE_STOP:
        raise KeyRiseStop(f"OWN key usage rose ${rise:.4f} since baseline (> ${KEY_RISE_STOP})")
    return {**u, "rise": rise}


class ORCaller:
    """Capped OpenRouter caller: reserve, request, append raw, settle. Thread-safe."""

    def __init__(self, ledger: Ledger, raw_path: Path, stage: str, price_key: str):
        self.ledger, self.raw_path, self.stage = ledger, raw_path, stage
        self.pin, self.pout = PRICE[price_key]
        self._client = _or_client()
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
        """One attempt. Returns the raw record (status, json, usage, cost)."""
        rid = f"{call_id}|{uuid.uuid4().hex[:8]}"
        self.ledger.reserve(rid, self.stage, bound, route="openrouter", path=path,
                            call_id=call_id)
        t0 = time.time()
        rec = {"id": rid, "call_id": call_id, "path": path, "request": body, "ts": now(),
               **meta}
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
            cost = float(usage["cost"])
            list_cost = (usage.get("prompt_tokens") or 0) * self.pin + \
                (usage.get("completion_tokens") or 0) * self.pout
            self.ledger.settle(rid, cost, list_cost=round(list_cost, 8),
                               provider=resp.get("provider"),
                               prompt_tokens=usage.get("prompt_tokens"),
                               completion_tokens=usage.get("completion_tokens"),
                               status=rec["status"])
        elif rec["status"] is not None and rec["status"] >= 400:
            # An HTTP error with an error body is not billed by OpenRouter; recorded at 0, and the
            # key-usage reconciliation checks it.
            self.ledger.settle(rid, 0.0, status=rec["status"], note="http error, no usage")
        else:
            self.ledger.settle(rid, bound, status=rec["status"],
                               note="no usage returned; settled at bound (conservative)")
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


# ---------------------------------------------------------------- OpenAI (OPENAI_API_KEY)

def openai_client():
    import openai
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set")
    return openai.OpenAI(max_retries=0, timeout=300)


def judge_input_bound_tokens(system: str, user: str) -> int:
    return int(JUDGE_TOKENS_PER_CHAR_BOUND * (len(system) + len(user))) + JUDGE_FRAMING_TOKENS


def batch_bound(lines: list[dict]) -> tuple[float, int, int]:
    pin, pout = PRICE["openai_batch"]
    tin = sum(judge_input_bound_tokens(l["body"]["messages"][0]["content"],
                                       l["body"]["messages"][1]["content"]) for l in lines)
    tout = sum(l["body"]["max_completion_tokens"] for l in lines)
    return tin * pin + tout * pout, tin, tout


def _write_new(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "x", encoding="utf-8") as fh:
        fh.write(text)


def submit_batch(ledger: Ledger, stage: str, name: str, bdir: Path, lines: list[dict]) -> dict:
    """Reserve the batch's bound, write its request file (never overwritten), upload, create."""
    rec_path = bdir / f"batch_{name}.json"
    if rec_path.exists():
        raise SystemExit(f"{rec_path} exists: batch {name} already submitted")
    bound, tin, tout = batch_bound(lines)
    base_rid = f"batch|{bdir.parent.name}|{name}"
    rid = base_rid
    k = 1
    while ledger.has_id(rid):  # an earlier attempt that created no batch (settled at 0)
        k += 1
        rid = f"{base_rid}|try{k}"
    req_path = bdir / f"requests_{name}.jsonl"
    text = "".join(json.dumps(l, sort_keys=True) + "\n" for l in lines)
    reuse = req_path.exists()
    if reuse and req_path.read_text() != text:
        raise SystemExit(f"{req_path} exists with different content")
    # Reserve first: a refused batch writes nothing and sends nothing.
    ledger.reserve(rid, stage, bound, route="openai_batch", n_requests=len(lines),
                   input_tokens_bound=tin, max_output_tokens=tout, batch_name=name)
    if not reuse:
        _write_new(req_path, text)
    client = openai_client()
    up = None
    for i in range(4):  # uploading twice is free; only batch creation must never repeat
        try:
            with open(req_path, "rb") as fh:
                up = client.files.create(file=fh, purpose="batch")
            break
        except Exception as exc:  # noqa: BLE001
            ledger.note(event="upload_error", id=rid, attempt=i, error=f"{type(exc).__name__}: {str(exc)[:200]}")
            time.sleep(5 * (i + 1))
    if up is None:
        ledger.settle(rid, 0.0, route="openai_batch", note="upload failed 4 times; no batch created")
        raise SystemExit(f"upload of {req_path} failed")
    try:
        b = client.batches.create(input_file_id=up.id, endpoint="/v1/chat/completions",
                                  completion_window="24h")
    except Exception as exc:  # noqa: BLE001
        ledger.note(event="batch_submit_error", id=rid, error=f"{type(exc).__name__}: {str(exc)[:300]}")
        time.sleep(10)
        found = [x for x in client.batches.list(limit=50) if x.input_file_id == up.id]
        if not found:
            ledger.settle(rid, 0.0, route="openai_batch",
                          note="batches.create failed and no batch has this input file")
            raise
        b = found[0]
        ledger.note(event="batch_found_after_error", id=rid, batch_id=b.id)
    rec = {"ledger_id": rid, "batch_id": b.id, "input_file": up.id, "name": name, "stage": stage,
           "n_requests": len(lines), "bound_usd": round(bound, 6), "input_tokens_bound": tin,
           "max_output_tokens": tout, "submitted_at": now(), "status": b.status}
    _write_new(rec_path, json.dumps(rec, indent=1, sort_keys=True))
    ledger.note(event="batch_submitted", id=rid, batch_id=b.id, n_requests=len(lines))
    return rec


def batch_status(bdir: Path, name: str):
    rec = json.loads((bdir / f"batch_{name}.json").read_text())
    b = openai_client().batches.retrieve(rec["batch_id"])
    return rec, b


def _usage_of(entry: dict) -> tuple[int, int, int, str | None]:
    body = ((entry.get("response") or {}).get("body") or {})
    u = body.get("usage") or {}
    pt = int(u.get("prompt_tokens") or 0)
    ct = int(u.get("completion_tokens") or 0)
    rt = int(((u.get("completion_tokens_details") or {}).get("reasoning_tokens")) or 0)
    return pt, ct, rt, body.get("model")


def fetch_batch(ledger: Ledger, bdir: Path, name: str) -> dict | None:
    """If the batch ended, save every raw line (exclusive create) and settle its actual cost."""
    raw_path = bdir / f"raw_{name}.jsonl"
    if raw_path.exists():
        raise SystemExit(f"{raw_path} exists: already fetched")
    rec, b = batch_status(bdir, name)
    if b.status not in ("completed", "failed", "expired", "cancelled"):
        return None
    client = openai_client()
    data = b""
    if b.output_file_id:
        data += client.files.content(b.output_file_id).read()
    err = b""
    if getattr(b, "error_file_id", None):
        err = client.files.content(b.error_file_id).read()
    with open(raw_path, "xb") as fh:
        fh.write(data)
        if err:
            if data and not data.endswith(b"\n"):
                fh.write(b"\n")
            fh.write(err)
    entries = [json.loads(l) for l in raw_path.read_text().splitlines() if l.strip()]
    pin, pout = PRICE["openai_batch"]
    tin = tout = treas = 0
    models: dict = {}
    for e in entries:
        pt, ct, rt, m = _usage_of(e)
        tin, tout, treas = tin + pt, tout + ct, treas + rt
        models[m] = models.get(m, 0) + 1
    actual = tin * pin + tout * pout
    ledger.settle(rec["ledger_id"], actual, route="openai_batch", batch_id=rec["batch_id"],
                  input_tokens=tin, output_tokens=tout, reasoning_tokens=treas,
                  n_results=len(entries), status=b.status)
    summ = {"batch_id": rec["batch_id"], "status": b.status, "n_requests": rec["n_requests"],
            "n_results": len(entries),
            "request_counts": b.request_counts.model_dump() if b.request_counts else None,
            "input_tokens": tin, "output_tokens": tout, "reasoning_tokens": treas,
            "actual_usd": round(actual, 6), "bound_usd": rec["bound_usd"], "models": models,
            "fetched_at": now()}
    _write_new(bdir / f"fetched_{name}.json", json.dumps(summ, indent=1, sort_keys=True))
    return summ


def reply_of(entry: dict) -> tuple[str | None, str | None]:
    """Same reading as script/data/batch_judge_fill._openai_reply_of."""
    if entry.get("error"):
        return None, f"error: {json.dumps(entry['error'])[:300]}"
    response = entry.get("response") or {}
    if response.get("status_code", 200) != 200:
        return None, f"status {response.get('status_code')}"
    body = response.get("body") or {}
    choices = body.get("choices") or []
    if not choices:
        return None, "no choices"
    choice = choices[0]
    message = choice.get("message") or {}
    finish = choice.get("finish_reason")
    if message.get("refusal") or str(finish).lower() == "content_filter":
        return None, f"refusal or content filter ({finish})"
    text = message.get("content") or ""
    if not text.strip():
        return None, f"empty completion (finish_reason={finish})"
    return text, None
