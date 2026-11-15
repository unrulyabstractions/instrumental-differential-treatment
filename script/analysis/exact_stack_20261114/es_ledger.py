"""Capped spend ledger and OpenAI batch helpers for judging A2. Every paid call goes through here.

Ported from the diag_20261113 runner (session scratchpad diag10/exec/capped.py), OpenAI batch only:
* one append-only ledger, judge/spend_ledger.jsonl: a "reserve" entry (the batch's bound) BEFORE the batch is
  created, a "settle" entry (actual cost from the returned usage) after it is fetched;
* committed = settled actual + bound of every unsettled reservation; a reservation is REFUSED when committed +
  bound would pass HARD_CAP_USD ($20), and a refused batch writes and sends nothing;
* the bound of a call is 0.22 billed tokens per character of system + user (+16), the maximum measured over base
  B's 17,279 judge calls being 0.2102, plus its full max_completion_tokens, at the list batch price;
* the key is read from OPENAI_API_KEY and never printed, logged or written.
"""
from __future__ import annotations

import fcntl
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

HARD_CAP_USD = 20.0
PRICE_BATCH = (0.125e-6, 1.00e-6)  # gpt-5-mini batch, USD per input / output token (nullext spend_ledger.json)
JUDGE_TOKENS_PER_CHAR_BOUND = 0.22
JUDGE_FRAMING_TOKENS = 16


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CapRefused(RuntimeError):
    pass


class Ledger:
    def __init__(self, path: Path, cap: float = HARD_CAP_USD):
        self.path, self.cap = path, cap
        self.lock_path = path.with_suffix(".lock")
        path.parent.mkdir(parents=True, exist_ok=True)
        self._t = threading.Lock()

    def _entries(self) -> tuple[dict, dict]:
        bound, cost = {}, {}
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                if not line.strip():
                    continue
                e = json.loads(line)
                if e.get("event") == "reserve":
                    bound[e["id"]] = float(e["bound_usd"])
                elif e.get("event") == "settle":
                    cost[e["id"]] = float(e["cost_usd"])
        return bound, cost

    def _append(self, entry: dict) -> None:
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def _locked(self):
        lk = open(self.lock_path, "a")
        fcntl.flock(lk, fcntl.LOCK_EX)
        return lk

    def committed(self) -> float:
        with self._t:
            lk = self._locked()
            try:
                b, c = self._entries()
                return sum(c.get(k, v) for k, v in b.items())
            finally:
                lk.close()

    def settled(self) -> float:
        with self._t:
            lk = self._locked()
            try:
                return sum(self._entries()[1].values())
            finally:
                lk.close()

    def unsettled(self) -> list[str]:
        b, c = self._entries()
        return [k for k in b if k not in c]

    def has_id(self, rid: str) -> bool:
        return rid in self._entries()[0]

    def reserve(self, rid: str, bound: float, **meta) -> None:
        with self._t:
            lk = self._locked()
            try:
                b, c = self._entries()
                if rid in b:
                    raise ValueError(f"duplicate reservation {rid}")
                tot = sum(c.get(k, v) for k, v in b.items())
                if tot + bound > self.cap + 1e-12:
                    why = f"committed {tot:.6f} + bound {bound:.6f} > cap {self.cap:.2f}"
                    self._append({"event": "refused", "id": rid, "bound_usd": round(bound, 8), "reason": why,
                                  "ts": now(), **meta})
                    raise CapRefused(why)
                self._append({"event": "reserve", "id": rid, "bound_usd": round(bound, 8),
                              "committed_before": round(tot, 6), "ts": now(), **meta})
            finally:
                lk.close()

    def settle(self, rid: str, cost: float, **meta) -> None:
        with self._t:
            lk = self._locked()
            try:
                b, c = self._entries()
                if rid not in b or rid in c:
                    raise ValueError(f"bad settle {rid}")
                self._append({"event": "settle", "id": rid, "cost_usd": round(cost, 8), "ts": now(), **meta})
            finally:
                lk.close()

    def note(self, **entry) -> None:
        with self._t:
            lk = self._locked()
            try:
                self._append({"ts": now(), **entry})
            finally:
                lk.close()


def openai_client():
    import openai
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set")
    return openai.OpenAI(max_retries=0, timeout=300)


def batch_bound(lines: list[dict]) -> tuple[float, int, int]:
    pin, pout = PRICE_BATCH
    tin = sum(int(JUDGE_TOKENS_PER_CHAR_BOUND * (len(l["body"]["messages"][0]["content"])
                                                 + len(l["body"]["messages"][1]["content"]))) + JUDGE_FRAMING_TOKENS
              for l in lines)
    tout = sum(l["body"]["max_completion_tokens"] for l in lines)
    return tin * pin + tout * pout, tin, tout


def write_new(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "x", encoding="utf-8") as fh:
        fh.write(text)


def submit_batch(ledger: Ledger, name: str, bdir: Path, lines: list[dict]) -> dict:
    """Reserve the bound, write the request file (never overwritten), upload, create. Refused = nothing sent."""
    rec_path = bdir / f"batch_{name}.json"
    if rec_path.exists():
        raise SystemExit(f"{rec_path} exists: batch {name} already submitted")
    bound, tin, tout = batch_bound(lines)
    rid = f"batch|{name}"
    k = 1
    while ledger.has_id(rid):
        k += 1
        rid = f"batch|{name}|try{k}"
    req = bdir / f"requests_{name}.jsonl"
    text = "".join(json.dumps(l, sort_keys=True) + "\n" for l in lines)
    if req.exists() and req.read_text() != text:
        raise SystemExit(f"{req} exists with different content")
    ledger.reserve(rid, bound, n_requests=len(lines), input_tokens_bound=tin, max_output_tokens=tout, batch=name)
    if not req.exists():
        write_new(req, text)
    client = openai_client()
    up = None
    for i in range(4):
        try:
            with open(req, "rb") as fh:
                up = client.files.create(file=fh, purpose="batch")
            break
        except Exception as exc:  # noqa: BLE001
            ledger.note(event="upload_error", id=rid, attempt=i, error=f"{type(exc).__name__}: {str(exc)[:200]}")
            time.sleep(5 * (i + 1))
    if up is None:
        ledger.settle(rid, 0.0, note="upload failed 4 times; no batch created")
        raise SystemExit(f"upload of {req} failed")
    try:
        b = client.batches.create(input_file_id=up.id, endpoint="/v1/chat/completions", completion_window="24h")
    except Exception as exc:  # noqa: BLE001
        ledger.note(event="batch_submit_error", id=rid, error=f"{type(exc).__name__}: {str(exc)[:300]}")
        time.sleep(10)
        found = [x for x in client.batches.list(limit=50) if x.input_file_id == up.id]
        if not found:
            ledger.settle(rid, 0.0, note="batches.create failed and no batch has this input file")
            raise
        b = found[0]
    rec = {"ledger_id": rid, "batch_id": b.id, "input_file": up.id, "name": name, "n_requests": len(lines),
           "bound_usd": round(bound, 6), "submitted_at": now(), "status": b.status}
    write_new(rec_path, json.dumps(rec, indent=1, sort_keys=True))
    ledger.note(event="batch_submitted", id=rid, batch_id=b.id, n_requests=len(lines))
    return rec


def batch_status(bdir: Path, name: str):
    rec = json.loads((bdir / f"batch_{name}.json").read_text())
    return rec, openai_client().batches.retrieve(rec["batch_id"])


def usage_of(entry: dict) -> tuple[int, int, int, str | None]:
    body = ((entry.get("response") or {}).get("body") or {})
    u = body.get("usage") or {}
    return (int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0),
            int(((u.get("completion_tokens_details") or {}).get("reasoning_tokens")) or 0), body.get("model"))


def fetch_batch(ledger: Ledger, bdir: Path, name: str) -> dict | None:
    """If the batch ended: save every raw line (exclusive create), settle its actual cost from usage."""
    raw = bdir / f"raw_{name}.jsonl"
    if raw.exists():
        raise SystemExit(f"{raw} exists: already fetched")
    rec, b = batch_status(bdir, name)
    if b.status not in ("completed", "failed", "expired", "cancelled"):
        return None
    client = openai_client()
    data = client.files.content(b.output_file_id).read() if b.output_file_id else b""
    err = client.files.content(b.error_file_id).read() if getattr(b, "error_file_id", None) else b""
    with open(raw, "xb") as fh:
        fh.write(data)
        if err:
            if data and not data.endswith(b"\n"):
                fh.write(b"\n")
            fh.write(err)
    entries = [json.loads(x) for x in raw.read_text().splitlines() if x.strip()]
    pin, pout = PRICE_BATCH
    tin = tout = treas = 0
    models: dict = {}
    errors = []
    for e in entries:
        pt, ct, rt, m = usage_of(e)
        tin, tout, treas = tin + pt, tout + ct, treas + rt
        models[m] = models.get(m, 0) + 1
        if e.get("error") or (e.get("response") or {}).get("status_code", 200) != 200:
            errors.append(json.dumps(e.get("error") or (e.get("response") or {}).get("body"))[:300])
    actual = tin * pin + tout * pout
    ledger.settle(rec["ledger_id"], actual, batch_id=rec["batch_id"], input_tokens=tin, output_tokens=tout,
                  reasoning_tokens=treas, n_results=len(entries), status=b.status)
    summ = {"batch_id": rec["batch_id"], "status": b.status, "n_requests": rec["n_requests"], "n_results": len(entries),
            "input_tokens": tin, "output_tokens": tout, "reasoning_tokens": treas, "actual_usd": round(actual, 6),
            "bound_usd": rec["bound_usd"], "models": models, "n_errors": len(errors), "errors_head": errors[:5],
            "fetched_at": now()}
    write_new(bdir / f"fetched_{name}.json", json.dumps(summ, indent=1, sort_keys=True))
    return summ


def reply_of(entry: dict) -> tuple[str | None, str | None]:
    """Same reading as script/data/batch_judge_fill._openai_reply_of."""
    if entry.get("error"):
        return None, f"error: {json.dumps(entry['error'])[:300]}"
    response = entry.get("response") or {}
    if response.get("status_code", 200) != 200:
        return None, f"status {response.get('status_code')}"
    choices = (response.get("body") or {}).get("choices") or []
    if not choices:
        return None, "no choices"
    message = choices[0].get("message") or {}
    finish = choices[0].get("finish_reason")
    if message.get("refusal") or str(finish).lower() == "content_filter":
        return None, f"refusal or content filter ({finish})"
    text = message.get("content") or ""
    if not text.strip():
        return None, f"empty completion (finish_reason={finish})"
    return text, None
