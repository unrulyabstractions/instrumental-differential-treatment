"""Gemini requests, the native Batch API, and the spend ledger for the baseline.

Every request is a native ``GenerateContentRequest`` so the thinking budget,
seed and output cap are set exactly. Kempf et al. call Gemini 2.5 Flash with
``enable_thinking=False``; we pass ``thinkingBudget: 0``, the native form of
that flag.

The ledger refuses any submission whose upper bound (counted input tokens at
the input price plus every request's output cap at the output price), added
to what is already committed, would pass the cap.
"""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from src.external.diffing_baseline_config import (LEDGER, PRICE_BATCH_IN, PRICE_BATCH_OUT,
                                                  SPEND_CAP_USD)

__all__ = ["gemini_request", "count_tokens", "generate_sync", "submit_batch", "batch_state",
           "download_batch", "ledger", "committed_usd", "record_batch", "record_cost",
           "reply_text", "usage_of", "write_new"]

REST = "https://generativelanguage.googleapis.com"


def write_new(path: Path, text: str) -> None:
    """Write a file that must not exist yet (no persisted response is overwritten)."""
    if path.exists():
        raise SystemExit(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _key() -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise SystemExit("GEMINI_API_KEY is not set")
    return key


def _http() -> httpx.Client:
    return httpx.Client(headers={"x-goog-api-key": _key()}, timeout=600)


def gemini_request(system: str, user: str, max_tokens: int, seed: int) -> dict:
    return {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"maxOutputTokens": max_tokens, "seed": seed,
                             "thinkingConfig": {"thinkingBudget": 0}},
    }


def _retry(fn, what: str):
    last = None
    for attempt in range(8):
        r = fn()
        if r.status_code == 429 or r.status_code >= 500:
            last = r.status_code
            time.sleep(min(60, 2 ** attempt))
            continue
        r.raise_for_status()
        return r
    raise SystemExit(f"{what} kept failing: {last}")


def count_tokens(model: str, requests: dict[str, dict], workers: int = 16) -> dict[str, int]:
    """Input tokens of every request, from the provider's own counter."""
    http = _http()

    def one(item):
        key, req = item
        body = {"generateContentRequest": {"model": f"models/{model}",
                                           "systemInstruction": req["systemInstruction"],
                                           "contents": req["contents"]}}
        r = _retry(lambda: http.post(f"{REST}/v1beta/models/{model}:countTokens", json=body),
                   "countTokens")
        return key, int(r.json()["totalTokens"])

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return dict(pool.map(one, requests.items()))


def generate_sync(model: str, req: dict) -> dict:
    with _http() as http:
        r = _retry(lambda: http.post(f"{REST}/v1beta/models/{model}:generateContent", json=req),
                   "generateContent")
        return r.json()


def reply_text(resp: dict) -> tuple[str | None, str | None]:
    """(text, error) of one GenerateContentResponse."""
    cands = resp.get("candidates") or []
    if not cands:
        return None, f"no candidates: {json.dumps(resp.get('promptFeedback'))}"
    parts = (cands[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    if not text:
        return None, f"empty, finishReason={cands[0].get('finishReason')}"
    return text, None


def usage_of(resp: dict) -> tuple[int, int]:
    u = resp.get("usageMetadata") or {}
    out = int(u.get("candidatesTokenCount", 0)) + int(u.get("thoughtsTokenCount", 0))
    return int(u.get("promptTokenCount", 0)), out


def _upload(path: Path) -> str:
    data = path.read_bytes()
    with _http() as http:
        start = http.post(f"{REST}/upload/v1beta/files", headers={
            "X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(len(data)),
            "X-Goog-Upload-Header-Content-Type": "application/jsonl",
            "Content-Type": "application/json"}, json={"file": {"display_name": path.name}})
        start.raise_for_status()
        done = http.post(start.headers["x-goog-upload-url"], headers={
            "Content-Length": str(len(data)), "X-Goog-Upload-Offset": "0",
            "X-Goog-Upload-Command": "upload, finalize"}, content=data)
        done.raise_for_status()
        info = done.json()["file"]
    if int(info.get("sizeBytes", -1)) != len(data):
        raise SystemExit(f"upload size mismatch: {info.get('sizeBytes')} vs {len(data)}")
    return info["name"]


def submit_batch(model: str, requests_file: Path, display: str) -> dict:
    file_name = _upload(requests_file)
    body = {"batch": {"display_name": display, "input_config": {"file_name": file_name}}}
    with _http() as http:
        r = http.post(f"{REST}/v1beta/models/{model}:batchGenerateContent", json=body)
        r.raise_for_status()
        return {"operation": r.json(), "input_file": file_name}


def batch_state(name: str) -> dict:
    with _http() as http:
        r = _retry(lambda: http.get(f"{REST}/v1beta/{name}"), "batch get")
        return r.json()


def download_batch(file_name: str) -> bytes:
    with _http() as http:
        r = _retry(lambda: http.get(f"{REST}/download/v1beta/{file_name}:download",
                                    params={"alt": "media"}), "download")
        return r.content


def ledger() -> dict:
    if LEDGER.exists():
        return json.loads(LEDGER.read_text(encoding="utf-8"))
    return {"cap_usd": SPEND_CAP_USD, "entries": []}


def committed_usd(led: dict) -> float:
    return sum(e["actual_usd"] if e.get("actual_usd") is not None else e["bound_usd"]
               for e in led["entries"])


def _save(led: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    if LEDGER.exists():
        with LEDGER.with_name("spend_ledger.history.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"saved_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                                 "previous": json.loads(LEDGER.read_text())}) + "\n")
    tmp = LEDGER.with_suffix(".tmp")
    tmp.write_text(json.dumps(led, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(LEDGER)


def record_batch(name: str, bound_usd: float, meta: dict) -> None:
    """Gate and record a spend before it happens. Raises when the cap would pass."""
    led = ledger()
    committed = committed_usd(led)
    if committed + bound_usd > SPEND_CAP_USD:
        raise SystemExit(f"REFUSED: committed ${committed:.4f} + bound ${bound_usd:.4f} "
                         f"passes the ${SPEND_CAP_USD:.2f} cap")
    led["entries"].append({"name": name, "bound_usd": round(bound_usd, 6), "actual_usd": None,
                           "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **meta})
    _save(led)


def record_cost(name: str, in_tok: int, out_tok: int, price_in: float = PRICE_BATCH_IN,
                price_out: float = PRICE_BATCH_OUT) -> float:
    led = ledger()
    cost = (in_tok * price_in + out_tok * price_out) / 1e6
    for e in led["entries"]:
        if e["name"] == name:
            e.update(actual_usd=round(cost, 6), input_tokens=in_tok, output_tokens=out_tok)
            _save(led)
            return cost
    raise SystemExit(f"no ledger entry {name}")
