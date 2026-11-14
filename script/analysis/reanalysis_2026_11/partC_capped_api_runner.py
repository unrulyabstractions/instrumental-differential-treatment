"""Paid calls for part C: every HTTP request priced, logged and capped.

The project's own seats are reused (``AnthropicChatBackend`` for the Elicitor,
``OpenAiChatBackend`` for the gpt-5-mini coder), with two changes:

* The SDK's own retries are switched off (``max_retries=0``), and the client's
  create method is wrapped, so every request that leaves the machine passes the
  cap first. A retry is a new request and is capped like any other.
* Before a request goes out, its worst case is reserved: the input at one token
  per two characters (an over-estimate for English) and the full output budget.
  A request that would take the job's or part C's spend past its cap is refused
  and never sent. After the reply, the reservation is replaced by the price of
  the usage the provider returned. A request that fails is charged its full
  reservation, since a failed request may still have been billed.

The ledger is append-only JSONL in the part C folder. Spent so far is read back
from it at start-up, so a second process cannot reset the count.

Prices (USD per million tokens):
* claude-haiku-4-5: input 1.00, output 5.00, cache write 1.25, cache read 0.10
  (claude-api skill model table, cached 2026-11-03).
* gpt-5-mini: input 0.25, cached input 0.025, output 2.00 including reasoning
  (developers.openai.com/api/docs/pricing, read 2026-11-13).
"""

from __future__ import annotations

import json
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import openai

sys.path.insert(0, str(Path(__file__).resolve().parent))
from partC_reanalysis_io import PART_C  # noqa: E402

from src.runner.anthropic_chat_backend import AnthropicChatBackend  # noqa: E402
from src.runner.openai_chat_backend import OpenAiChatBackend  # noqa: E402

LEDGER = PART_C / "spend_ledger.jsonl"
#: Part C's whole budget. No job can raise it.
PART_C_CAP_USD = 1.50

PRICES = {
    "claude-haiku-4-5": {"in": 1.00, "out": 5.00, "cache_write": 1.25, "cache_read": 0.10},
    "gpt-5-mini": {"in": 0.25, "out": 2.00, "cache_read": 0.025},
}
CHARS_PER_TOKEN_FLOOR = 2.0
RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504, 529}
ATTEMPTS = 3


class CapRefused(RuntimeError):
    """A request was refused because it would pass a cap. Nothing was sent."""


class SpendLedger:
    """Append-only record of every request, and the cap check in front of it."""

    def __init__(self, path: Path, job: str, job_cap_usd: float,
                 part_cap_usd: float = PART_C_CAP_USD):
        if job_cap_usd > part_cap_usd:
            raise ValueError("a job cap cannot exceed part C's cap")
        self.path, self.job = Path(path), job
        self.job_cap, self.part_cap = float(job_cap_usd), float(part_cap_usd)
        self._lock = threading.Lock()
        self._inflight = 0.0
        self._inflight_job = 0.0
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _spent(self) -> tuple[float, float]:
        total = job = 0.0
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                cost = float(row.get("cost_usd") or 0.0)
                total += cost
                if row.get("job") == self.job:
                    job += cost
        return total, job

    def spent(self) -> dict:
        with self._lock:
            total, job = self._spent()
        return {"part_c_usd": total, "job_usd": job, "job": self.job}

    def _append(self, row: dict) -> None:
        row = {"ts": datetime.now(timezone.utc).isoformat(), "job": self.job, **row}
        with self.path.open("a") as fh:
            fh.write(json.dumps(row) + "\n")

    def reserve(self, model: str, worst_usd: float, tag: str) -> float:
        with self._lock:
            total, job = self._spent()
            if (total + self._inflight + worst_usd > self.part_cap
                    or job + self._inflight_job + worst_usd > self.job_cap):
                self._append({"model": model, "status": "refused_cap", "cost_usd": 0.0,
                              "reserved_usd": worst_usd, "tag": tag,
                              "spent_part_c": total, "spent_job": job,
                              "job_cap": self.job_cap, "part_cap": self.part_cap})
                raise CapRefused(f"{tag}: worst case ${worst_usd:.5f} would pass the cap "
                                 f"(part C spent ${total:.4f} of ${self.part_cap}, job "
                                 f"{self.job} spent ${job:.4f} of ${self.job_cap})")
            self._inflight += worst_usd
            self._inflight_job += worst_usd
        return worst_usd

    def settle(self, reserved: float, row: dict) -> None:
        with self._lock:
            self._inflight -= reserved
            self._inflight_job -= reserved
            self._append(row)


def _chars(params: dict) -> int:
    n = len(str(params.get("system") or ""))
    for message in params.get("messages") or []:
        n += len(str(message.get("content") or ""))
    return n


class _CappedAnthropicCreate:
    def __init__(self, real, ledger: SpendLedger, model: str):
        self.real, self.ledger, self.model = real, ledger, model
        self.price = PRICES[model]

    def __call__(self, **params):
        tag = params.pop("_tag", "")
        worst = ((_chars(params) / CHARS_PER_TOKEN_FLOOR) * self.price["in"]
                 + int(params["max_tokens"]) * self.price["out"]) / 1e6
        reserved = self.ledger.reserve(self.model, worst, tag)
        try:
            response = self.real(**params)
        except Exception as exc:
            self.ledger.settle(reserved, {"model": self.model, "status": "error",
                                          "error": type(exc).__name__, "cost_usd": reserved,
                                          "reserved_usd": reserved, "tag": tag})
            raise
        u = response.usage
        cw = getattr(u, "cache_creation_input_tokens", 0) or 0
        cr = getattr(u, "cache_read_input_tokens", 0) or 0
        cost = (u.input_tokens * self.price["in"] + cw * self.price["cache_write"]
                + cr * self.price["cache_read"] + u.output_tokens * self.price["out"]) / 1e6
        self.ledger.settle(reserved, {"model": self.model, "status": "ok", "cost_usd": cost,
                                      "reserved_usd": reserved, "input_tokens": u.input_tokens,
                                      "output_tokens": u.output_tokens, "cache_write": cw,
                                      "cache_read": cr, "stop_reason": response.stop_reason,
                                      "tag": tag})
        return response


class CappedAnthropicBackend(AnthropicChatBackend):
    """The project's Elicitor seat with every request capped and logged."""

    def __init__(self, model_name: str, ledger: SpendLedger):
        super().__init__(model_name=model_name, max_retries=0)
        self._client.messages.create = _CappedAnthropicCreate(
            self._client.messages.create, ledger, model_name)

    def generate(self, system: str, user: str, max_new_tokens: int = 512) -> str:
        for attempt in range(ATTEMPTS):
            try:
                return super().generate(system, user, max_new_tokens)
            except CapRefused:
                raise
            except (anthropic.APIConnectionError, anthropic.APITimeoutError):
                if attempt == ATTEMPTS - 1:
                    raise
            except anthropic.APIStatusError as exc:
                if exc.status_code not in RETRY_STATUS or attempt == ATTEMPTS - 1:
                    raise
            time.sleep(2 ** (attempt + 1))
        raise RuntimeError("unreachable")


class _CappedOpenAiCreate:
    def __init__(self, real, ledger: SpendLedger, model: str):
        self.real, self.ledger, self.model = real, ledger, model
        self.price = PRICES[model]

    def __call__(self, **params):
        budget = params.get("max_completion_tokens") or params.get("max_tokens")
        worst = ((_chars(params) / CHARS_PER_TOKEN_FLOOR) * self.price["in"]
                 + int(budget) * self.price["out"]) / 1e6
        reserved = self.ledger.reserve(self.model, worst, "")
        try:
            response = self.real(**params)
        except Exception as exc:
            self.ledger.settle(reserved, {"model": self.model, "status": "error",
                                          "error": type(exc).__name__, "cost_usd": reserved,
                                          "reserved_usd": reserved})
            raise
        u = response.usage
        cached = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0) or 0
        reasoning = getattr(getattr(u, "completion_tokens_details", None),
                            "reasoning_tokens", None)
        cost = ((u.prompt_tokens - cached) * self.price["in"] + cached * self.price["cache_read"]
                + u.completion_tokens * self.price["out"]) / 1e6
        self.ledger.settle(reserved, {"model": self.model, "status": "ok", "cost_usd": cost,
                                      "reserved_usd": reserved, "prompt_tokens": u.prompt_tokens,
                                      "cached_tokens": cached,
                                      "completion_tokens": u.completion_tokens,
                                      "reasoning_tokens": reasoning,
                                      "finish_reason": response.choices[0].finish_reason})
        return response


class CappedOpenAiBackend(OpenAiChatBackend):
    """The project's OpenAI seat with every request capped and logged."""

    def __init__(self, model_name: str, ledger: SpendLedger, reasoning_effort: str):
        super().__init__(model_name=model_name, max_retries=0,
                         reasoning_effort=reasoning_effort)
        self._client.chat.completions.create = _CappedOpenAiCreate(
            self._client.chat.completions.create, ledger, model_name)

    def generate(self, system: str, user: str, max_new_tokens: int = 512) -> str:
        for attempt in range(ATTEMPTS):
            try:
                return super().generate(system, user, max_new_tokens)
            except CapRefused:
                raise
            except (openai.APIConnectionError, openai.APITimeoutError):
                if attempt == ATTEMPTS - 1:
                    raise
            except openai.APIStatusError as exc:
                if exc.status_code not in RETRY_STATUS or attempt == ATTEMPTS - 1:
                    raise
            time.sleep(2 ** (attempt + 1))
        raise RuntimeError("unreachable")


def prove_zero_cap_refuses(ledger_path: Path) -> dict:
    """A $0 cap must refuse before any request leaves, for both seats.

    The real create method is replaced by a counter, so a request that got past
    the cap would be counted. Both counters must stay at zero.
    """
    out = {}
    for kind in ("anthropic", "openai"):
        sent = {"n": 0}

        def fake(**_params):
            sent["n"] += 1
            raise AssertionError("a request left the machine under a $0 cap")

        ledger = SpendLedger(ledger_path, job=f"zero_cap_proof_{kind}", job_cap_usd=0.0)
        if kind == "anthropic":
            backend = CappedAnthropicBackend("claude-haiku-4-5", ledger)
            backend._client.messages.create.real = fake
        else:
            backend = CappedOpenAiBackend("gpt-5-mini", ledger, reasoning_effort="low")
            backend._client.chat.completions.create.real = fake
        try:
            backend.generate("system", "user", max_new_tokens=10)
            refused = False
        except CapRefused:
            refused = True
        if not refused or sent["n"] != 0:
            raise SystemExit(f"{kind}: the $0 cap did not refuse (sent {sent['n']})")
        out[kind] = {"refused": refused, "requests_sent": sent["n"]}
    return out
