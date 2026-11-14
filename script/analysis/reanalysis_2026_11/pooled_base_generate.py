"""Draw a pooled-base arm (C1 or C2) of Llama-3.3-70B-Instruct through OpenRouter.

    .venv/bin/python script/analysis/reanalysis_2026_11/pooled_base_generate.py \
        --draw c1 --samples-per-prompt 1          # pilot: s = 0 of every prompt
    .venv/bin/python script/analysis/reanalysis_2026_11/pooled_base_generate.py \
        --draw c1 --samples-per-prompt 16         # the rest, resumed from disk
    .venv/bin/python script/analysis/reanalysis_2026_11/pooled_base_generate.py --probe-date
    .venv/bin/python script/analysis/reanalysis_2026_11/pooled_base_generate.py \
        --draw c1 --samples-per-prompt 1 --gen-cap 0   # must refuse, sends nothing

Rows, resume and failure accounting come from
``src.runner.response_sampling.sample_prompt_sets`` unchanged. This file only
supplies a backend with ``generate_many`` that calls OpenRouter once per sample.

Every call is priced and capped before it leaves the machine:

* A ``reserve`` row with the call's bound (prompt tokens at the input price plus
  ``max_tokens`` at the output price) is appended to ``generation_ledger.jsonl``
  before the request, and a ``settle`` row with the cost OpenRouter returns
  after it. A failed call is charged its whole bound. A reserve row with no
  settle row (a crash) counts at its bound.
* A call is refused when the generation spend plus its bound would pass
  ``--gen-cap`` (default $8), or when the whole item (this ledger, the judge
  batch ledger at its committed spend, and the live-call ledger) would pass $48.
  A retry is a new call and is capped like any other.
* Before each submission chunk the OpenRouter key's remaining limit is read and
  the run stops if it could not cover the chunk's bound.

The provider is pinned to CoreWeave's fp16 endpoint with no fallback. A reply
from any other provider stops the run. Every raw response is appended to
``<draw>/generation_raw.jsonl`` before it is parsed (B11), and a successful raw
response is reused on resume, so a crash never pays for a sample twice.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import secrets
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from src.promptset.rendered_prompt_loading import load_prompt_sets  # noqa: E402
from src.runner.auditbench_identity_prompt import (AUDITBENCH_SYSTEM_PROMPT,  # noqa: E402
                                                   AUDITBENCH_SYSTEM_VARIANTS)
from src.runner.response_sampling import plan_sampling, sample_prompt_sets  # noqa: E402

ITEM = REPO / "out/main/auditbench/pooled_base_20261113"
PROMPTSET = REPO / "out/main/auditbench/contextual_optimism/promptset"
GEN_LEDGER = ITEM / "generation_ledger.jsonl"
JUDGE_LEDGER = ITEM / "judge_spend_ledger.json"
LIVE_LEDGER = ITEM / "live_ledger.jsonl"
ITEM_CAP_USD = 48.0
DEFAULT_GEN_CAP_USD = 8.0

MODEL = "meta-llama/llama-3.3-70b-instruct"
PROVIDER_SLUG, PROVIDER_NAME, QUANT = "coreweave", "CoreWeave", "fp16"
PRICE_IN_PER_M = PRICE_OUT_PER_M = 0.71  # coreweave/fp16, read live 2026-11-14 01:25 UTC
MAX_TOKENS = 4096
TEMPERATURE, TOP_P = 0.8, 0.95  # VllmBatchBackend defaults, as base B was drawn
PROMPT_TOKEN_BOUND = 200  # every rendered prompt is 91 to 116 tokens
ATTEMPTS = 4
RETRY_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 520, 522, 524, 529}
URL = "https://openrouter.ai/api/v1/chat/completions"
SEED_LABELS = {"c1": "auditbench-pooled-c1", "c2": "auditbench-pooled-c2"}
#: Llama-3.3's own chat template opens the system turn with this header, and base
#: B's prompts carried it (rendered locally, ``VllmBatchBackend._encode_chat``).
#: CoreWeave's template leaves it out: the 2026-11-14 date probe came back with
#: 51 prompt tokens, the local render without the header, and no date. Sending
#: the header as the start of the system message makes the provider's render the
#: same string as base B's. The pilot checks the prompt token count of all 216
#: prompts against the local render.
SYSTEM_DATE_HEADER = "Cutting Knowledge Date: December 2023\nToday Date: 26 Jul 2024\n\n"


class StopRun(BaseException):
    """Stop the whole run. A BaseException, so ``sample_prompt_sets`` does not
    catch it and write the chunk as failed rows that a resume would skip."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _judge_committed() -> float:
    if not JUDGE_LEDGER.exists():
        return 0.0
    ledger = json.loads(JUDGE_LEDGER.read_text())
    return sum(b["actual_usd"] if b.get("actual_usd") is not None else b["bound_usd"]
               for b in ledger["batches"])


def _live_spent() -> float:
    if not LIVE_LEDGER.exists():
        return 0.0
    total, open_ = 0.0, {}
    for line in LIVE_LEDGER.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row["event"] == "reserve":
            open_[row["call_id"]] = float(row["bound_usd"])
        elif row["event"] == "settle":
            open_.pop(row["call_id"], None)
            total += float(row["cost_usd"])
    return total + sum(open_.values())


def generation_committed(path: Path = GEN_LEDGER) -> dict:
    """Settled cost plus the bound of every reserve row that has no settle row."""
    settled, open_, n_calls = 0.0, {}, 0
    if path.exists():
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row["event"] == "reserve":
                open_[row["call_id"]] = float(row["bound_usd"])
            elif row["event"] == "settle":
                open_.pop(row["call_id"], None)
                settled += float(row["cost_usd"])
                n_calls += 1
    return {"settled_usd": settled, "open_bound_usd": sum(open_.values()),
            "committed_usd": settled + sum(open_.values()), "settled_calls": n_calls}


class Ledger:
    """The generation ledger and both caps, held in memory under one lock."""

    def __init__(self, gen_cap: float, item_cap: float = ITEM_CAP_USD):
        self.gen_cap, self.item_cap = float(gen_cap), float(item_cap)
        self._lock = threading.Lock()
        state = generation_committed()
        self._committed = state["committed_usd"]
        self._external = 0.0
        self._external_at = 0.0
        self._refresh_external()

    def _refresh_external(self) -> None:
        self._external = _judge_committed() + _live_spent()
        self._external_at = time.time()

    def _append(self, row: dict) -> None:
        with GEN_LEDGER.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": _now(), **row}, sort_keys=True) + "\n")

    def reserve(self, call_id: str, bound: float, meta: dict) -> None:
        with self._lock:
            if time.time() - self._external_at > 60:
                self._refresh_external()
            gen_after = self._committed + bound
            item_after = gen_after + self._external
            if gen_after > self.gen_cap or item_after > self.item_cap:
                self._append({"event": "refused", "call_id": call_id, "bound_usd": bound,
                              "generation_committed_usd": self._committed,
                              "external_committed_usd": self._external,
                              "gen_cap_usd": self.gen_cap, "item_cap_usd": self.item_cap, **meta})
                raise StopRun(f"REFUSED {call_id}: bound ${bound:.5f} would take generation to "
                              f"${gen_after:.4f} (cap ${self.gen_cap:.2f}) and the item to "
                              f"${item_after:.4f} (cap ${self.item_cap:.2f})")
            self._committed += bound
            self._append({"event": "reserve", "call_id": call_id, "bound_usd": bound, **meta})

    def settle(self, call_id: str, bound: float, cost: float, meta: dict) -> None:
        with self._lock:
            self._committed += cost - bound
            self._append({"event": "settle", "call_id": call_id, "bound_usd": bound,
                          "cost_usd": cost, **meta})

    @property
    def committed(self) -> float:
        with self._lock:
            return self._committed


def key_remaining(client: httpx.Client) -> float | None:
    r = client.get("https://openrouter.ai/api/v1/key", timeout=30)
    r.raise_for_status()
    rem = r.json()["data"].get("limit_remaining")
    return None if rem is None else float(rem)


class OpenRouterBackend:
    """``generate_many`` over OpenRouter, one capped call per sample."""

    def __init__(self, draw: str, cells, ledger: Ledger, workers: int, client: httpx.Client,
                 raw_path: Path, max_tokens: int = MAX_TOKENS):
        self.draw, self.ledger, self.workers = draw, ledger, workers
        self.client, self.raw_path, self.max_tokens = client, raw_path, max_tokens
        self._cells = list(cells)
        self._cursor = 0
        self._raw_lock = threading.Lock()
        self._cache = self._load_cache()
        self.sent = 0
        self._stop = threading.Event()

    def _load_cache(self) -> dict:
        """First successful raw response per (prompt_id, s), for resume."""
        cache = {}
        if self.raw_path.exists():
            for line in self.raw_path.read_text().splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                key = (row["prompt_id"], int(row["s"]))
                if row.get("ok") and key not in cache:
                    cache[key] = row
        return cache

    def _write_raw(self, row: dict) -> None:
        with self._raw_lock, self.raw_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")

    def _body(self, system: str, user: str, seed: int) -> dict:
        return {"model": MODEL,
                "messages": [{"role": "system", "content": SYSTEM_DATE_HEADER + system},
                             {"role": "user", "content": user}],
                "max_tokens": self.max_tokens, "temperature": TEMPERATURE, "top_p": TOP_P,
                "top_k": 0, "frequency_penalty": 0, "presence_penalty": 0,
                "repetition_penalty": 1, "seed": seed, "transforms": [],
                "usage": {"include": True},
                "provider": {"only": [PROVIDER_SLUG], "quantizations": [QUANT],
                             "allow_fallbacks": False, "require_parameters": True}}

    def one(self, prompt_id: str, s: int, system: str, user: str) -> str:
        if self._stop.is_set():
            raise StopRun("stopped")
        try:
            return self._one(prompt_id, s, system, user)
        except StopRun:
            self._stop.set()
            raise

    def _one(self, prompt_id: str, s: int, system: str, user: str) -> str:
        cached = self._cache.get((prompt_id, s))
        if cached is not None:
            return cached["text"]
        bound = (PROMPT_TOKEN_BOUND * PRICE_IN_PER_M + self.max_tokens * PRICE_OUT_PER_M) / 1e6
        last = None
        for attempt in range(1, ATTEMPTS + 1):
            if self._stop.is_set():
                raise StopRun("stopped")
            seed = secrets.randbelow(2 ** 31 - 1)
            call_id = f"{self.draw}|{prompt_id}|{s}|a{attempt}|{secrets.token_hex(4)}"
            meta = {"draw": self.draw, "prompt_id": prompt_id, "s": s, "attempt": attempt}
            self.ledger.reserve(call_id, bound, meta)
            body = self._body(system, user, seed)
            t0 = time.time()
            status, payload, err = None, None, None
            try:
                self.sent += 1
                r = self.client.post(URL, json=body)
                status = r.status_code
                try:
                    payload = r.json()
                except ValueError:
                    payload = {"_text": r.text[:2000]}
            except httpx.HTTPError as exc:
                err = f"{type(exc).__name__}: {exc}"[:500]
            elapsed = time.time() - t0
            choice = ((payload or {}).get("choices") or [{}])[0] if isinstance(payload, dict) else {}
            usage = (payload or {}).get("usage") or {} if isinstance(payload, dict) else {}
            provider = (payload or {}).get("provider") if isinstance(payload, dict) else None
            text = ((choice.get("message") or {}).get("content") or "") if choice else ""
            api_error = (payload or {}).get("error") if isinstance(payload, dict) else None
            ok = (status == 200 and not api_error and bool(choice) and text.strip() != ""
                  and provider == PROVIDER_NAME)
            raw = {"ts": _now(), "call_id": call_id, "draw": self.draw, "prompt_id": prompt_id,
                   "s": s, "attempt": attempt, "seed": seed, "status": status, "error": err,
                   "elapsed_s": round(elapsed, 3), "ok": ok, "provider": provider,
                   "finish_reason": choice.get("finish_reason") if choice else None,
                   "native_finish_reason": choice.get("native_finish_reason") if choice else None,
                   "usage": usage, "generation_id": (payload or {}).get("id")
                   if isinstance(payload, dict) else None,
                   "model": (payload or {}).get("model") if isinstance(payload, dict) else None,
                   "text": text.rstrip() if ok else None,
                   "payload": None if ok else payload,
                   "request": {k: v for k, v in body.items() if k != "messages"}}
            self._write_raw(raw)
            if status == 200 and usage.get("cost") is not None:
                cost = float(usage["cost"])
            elif status == 200 and usage:
                cost = (int(usage.get("prompt_tokens") or 0) * PRICE_IN_PER_M
                        + int(usage.get("completion_tokens") or 0) * PRICE_OUT_PER_M) / 1e6
            else:
                cost = bound  # a failed call may still have been billed
            self.ledger.settle(call_id, bound, cost,
                               {**meta, "status": status, "provider": provider,
                                "finish_reason": raw["finish_reason"],
                                "prompt_tokens": usage.get("prompt_tokens"),
                                "completion_tokens": usage.get("completion_tokens")})
            if status == 200 and provider not in (None, PROVIDER_NAME):
                raise StopRun(f"{call_id}: served by {provider!r}, not {PROVIDER_NAME}")
            if ok:
                return text.rstrip()
            last = f"status={status} err={err} api_error={json.dumps(api_error)[:300]}"
            code = (api_error or {}).get("code") if isinstance(api_error, dict) else None
            # A 4xx other than a rate or timeout status means the request itself
            # is wrong (a parameter, the key, the credit): never retry it.
            if (status is not None and 400 <= status < 500 and status not in RETRY_STATUS) or (
                    isinstance(code, int) and 400 <= code < 500 and code not in RETRY_STATUS):
                raise StopRun(f"{call_id}: {last}")
            if attempt < ATTEMPTS:
                time.sleep(min(60, 2 ** attempt))
        print(f"[{self.draw}] {prompt_id} s={s} failed after {ATTEMPTS} attempts: {last}",
              flush=True)
        return ""

    def generate_many(self, requests, max_new_tokens: int):
        if max_new_tokens != self.max_tokens:
            raise StopRun(f"max_new_tokens {max_new_tokens} != {self.max_tokens}")
        cells = self._cells[self._cursor:self._cursor + len(requests)]
        for cell, (system, user, n) in zip(cells, requests, strict=True):
            if (cell.system_text, cell.text, len(cell.missing)) != (system, user, n):
                raise StopRun("submission does not match the planned cells")
        self._cursor += len(requests)
        bound_chunk = sum(len(c.missing) for c in cells) * (
            PROMPT_TOKEN_BOUND * PRICE_IN_PER_M + self.max_tokens * PRICE_OUT_PER_M) / 1e6
        rem = key_remaining(self.client)
        if rem is not None and rem < bound_chunk + 1.0:
            raise StopRun(f"OpenRouter key has ${rem:.2f} left, chunk bound ${bound_chunk:.2f}")
        jobs = [(ci, s) for ci, c in enumerate(cells) for s in c.missing]
        pool = ThreadPoolExecutor(max_workers=self.workers)
        try:
            texts = list(pool.map(
                lambda job: self.one(cells[job[0]].prompt_id, job[1],
                                     cells[job[0]].system_text, cells[job[0]].text), jobs))
        except BaseException:
            self._stop.set()
            pool.shutdown(wait=True, cancel_futures=True)
            raise
        pool.shutdown(wait=True)
        out, k = [], 0
        for c in cells:
            out.append(texts[k:k + len(c.missing)])
            k += len(c.missing)
        print(f"[{self.draw}] chunk of {len(jobs)} samples done; generation committed "
              f"${self.ledger.committed:.4f}; key had ${rem}", flush=True)
        return out


def _client() -> httpx.Client:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit("OPENROUTER_API_KEY is not set")
    # Authorization only: no referer, title, name or e-mail header.
    return httpx.Client(headers={"Authorization": f"Bearer {key}"},
                        timeout=httpx.Timeout(900.0, connect=30.0),
                        limits=httpx.Limits(max_connections=128, max_keepalive_connections=64))


def check_seed_label(out_dir: Path, label: str) -> None:
    record = out_dir / "seed_label.txt"
    rows = out_dir / "responses_base.jsonl"
    if record.exists():
        if record.read_text().strip() != label:
            raise SystemExit(f"{rows} was started with seed label {record.read_text().strip()!r}")
    elif rows.exists():
        raise SystemExit(f"{rows} exists with no seed label; refusing to extend it")
    else:
        out_dir.mkdir(parents=True, exist_ok=True)
        record.write_text(label + "\n")


def run_draw(args) -> None:
    out_dir = ITEM / args.draw
    lock = (ITEM / "generation.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("another generation process holds generation.lock")
    if args.gen_cap != 0:
        check_seed_label(out_dir, SEED_LABELS[args.draw])
    prompt_sets = load_prompt_sets(PROMPTSET)
    rows_path = out_dir / "responses_base.jsonl"
    done = set()
    if rows_path.exists():
        for line in rows_path.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                done.add((r["prompt_id"], int(r["s"])))
    cells, requested = plan_sampling(prompt_sets, AUDITBENCH_SYSTEM_VARIANTS,
                                     args.samples_per_prompt, done)
    print(f"[{args.draw}] {len(cells)} cells, {sum(len(c.missing) for c in cells)} samples "
          f"outstanding of {requested}", flush=True)
    ledger = Ledger(args.gen_cap)
    with _client() as client:
        backend = OpenRouterBackend(args.draw, cells, ledger, args.workers, client,
                                    out_dir / "generation_raw.jsonl")
        if args.gen_cap == 0:
            # The refusal proof: the first call must be refused before any request.
            try:
                c = cells[0]
                backend.one(c.prompt_id, c.missing[0], c.system_text, c.text)
            except StopRun as exc:
                print(f"zero-cap proof: {exc}; HTTP requests sent: {backend.sent}")
                if backend.sent != 0:
                    raise SystemExit("a request was sent under a $0 cap")
                return
            raise SystemExit("the $0 cap did not refuse")
        stats = sample_prompt_sets(backend, prompt_sets, args.samples_per_prompt, rows_path,
                                   system_prompts=AUDITBENCH_SYSTEM_VARIANTS,
                                   max_new_tokens=MAX_TOKENS, show_progress=False,
                                   submission_chunk=args.submission_chunk)
    print(f"[{args.draw}] requested={stats.requested} generated={stats.generated} "
          f"skipped={stats.skipped_existing} failed={stats.failed}; generation committed "
          f"${ledger.committed:.4f}", flush=True)


def probe_date(args) -> None:
    """Three short calls asking for today's date under the PRISM-4 system prompt.

    The first probe (``probe_date.jsonl``, before ``SYSTEM_DATE_HEADER`` existed)
    sent the bare system prompt; this one sends what every draw sends.
    """
    out = ITEM / "probe_date_header.jsonl"
    if out.exists():
        raise SystemExit(f"refusing to overwrite {out}")
    ledger = Ledger(args.gen_cap)
    with _client() as client:
        backend = OpenRouterBackend("probe_header", [], ledger, 1, client,
                                    ITEM / "probe_date_header_raw.jsonl", max_tokens=32)
        rows = []
        for i in range(3):
            text = backend.one("probe_date", i, AUDITBENCH_SYSTEM_PROMPT,
                               "What is today's date? Reply with the date only.")
            rows.append({"i": i, "text": text})
            print(i, repr(text), flush=True)
    out.write_text("".join(json.dumps(r) + "\n" for r in rows))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--draw", choices=sorted(SEED_LABELS))
    ap.add_argument("--samples-per-prompt", type=int, default=16)
    ap.add_argument("--gen-cap", type=float, default=DEFAULT_GEN_CAP_USD)
    ap.add_argument("--workers", type=int, default=32)
    ap.add_argument("--submission-chunk", type=int, default=16)
    ap.add_argument("--probe-date", action="store_true")
    args = ap.parse_args()
    if args.gen_cap > DEFAULT_GEN_CAP_USD:
        raise SystemExit(f"--gen-cap cannot exceed ${DEFAULT_GEN_CAP_USD}")
    if args.probe_date:
        probe_date(args)
    elif args.draw:
        run_draw(args)
    else:
        ap.error("give --draw or --probe-date")


if __name__ == "__main__":
    main()
