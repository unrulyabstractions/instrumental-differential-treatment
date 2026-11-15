"""Every paid request of the decoy session is capped, priced from its usage, and logged.

Two layers, both in code. The workflow's shared ledger
(``common/ledger.py``, $5.00 for the workflow and $3.00 per analysis) receives
one reservation per paid phase (the pilot, then the session) under family
``user_awareness`` and analysis ``decoy_session``, so both phases share one
$3.00 cap; it is reconciled with the phase's priced usage when the phase ends.
This module then guards every single request against that phase's
reservation: before a request leaves, its worst case is reserved (the input at
one token per two characters, an over-estimate for English, plus the full
completion budget, at the Standard price), and a request whose worst case would
pass the phase cap, the $3.00 analysis cap, or the $5.00 workflow cap (other
families' committed spend in the shared ledger plus ours) is refused and never
sent. After the reply, the reservation is replaced by the price of the usage the
provider returned (reasoning tokens are part of ``completion_tokens``). A request
that errors is charged its full reservation, since it may have been billed.

The SDK's own retries are off (``max_retries=0``); a retry is a new request and is
capped like any other. The API key is read by the SDK from the environment and
is never printed, logged or written.
"""

from __future__ import annotations

import fcntl
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from script.analysis.baseline_free_20261115.common.ledger import Ledger as SharedLedger

ANALYSIS_CAP_USD = 3.00
WORKFLOW_CAP_USD = 5.00
CHARS_PER_TOKEN_FLOOR = 2.0
#: Standard tier, USD per million tokens, read from developers.openai.com/api/docs/pricing
#: on 2026-11-14 (local date): the page's first price block for each model.
PRICES = {
    "gpt-5-mini": {"in": 0.25, "cached_in": 0.025, "out": 2.00},
    "gpt-4.1-mini": {"in": 0.40, "cached_in": 0.10, "out": 1.60},
    "gpt-5": {"in": 1.25, "cached_in": 0.125, "out": 10.00},
}
PRICE_SOURCE = "developers.openai.com/api/docs/pricing, Standard tier, read 2026-11-14"
_TAG = threading.local()


class CapRefused(RuntimeError):
    """A request was refused because it would pass a cap. Nothing was sent."""


def set_tag(tag: str) -> None:
    _TAG.value = tag


def worst_case_usd(model: str, chars: int, max_new: int) -> float:
    """The bound one request reserves: chars / 2 input tokens plus the full completion budget."""
    price = PRICES[model]
    return ((chars / CHARS_PER_TOKEN_FLOOR) * price["in"] + max_new * price["out"]) / 1e6


FAMILY, ANALYSIS = "user_awareness", "decoy_session"


class SpendLedger:
    def __init__(self, path: Path, shared: SharedLedger | None, phase_cap: float):
        self.path, self.shared = Path(path), shared
        self.phase_cap = float(phase_cap)
        self.analysis_cap, self.workflow_cap = ANALYSIS_CAP_USD, WORKFLOW_CAP_USD
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._inflight = 0.0
        # This process is the only writer of its own ledger, so its total is read once
        # and then kept in memory; the shared ledger is re-read on every request.
        self._mine = self._sum(self.path) if self.path.exists() else 0.0

    @staticmethod
    def _sum(path: Path) -> float:
        total = 0.0
        for line in path.read_text().splitlines():
            if line.strip():
                total += float(json.loads(line).get("cost_usd") or 0.0)
        return total

    def spent(self) -> dict:
        mine = self._mine
        others = 0.0
        if self.shared is not None:
            others = self.shared.committed() - self.shared.committed(FAMILY)
        return {"analysis_usd": mine, "workflow_usd": mine + others,
                "other_families_committed_usd": others}

    def _append(self, row: dict) -> None:
        row = {"ts": datetime.now(timezone.utc).isoformat(), **row}
        with open(self.path, "a", encoding="utf-8") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            fh.write(json.dumps(row, sort_keys=True) + "\n")

    def reserve(self, model: str, worst: float, tag: str) -> float:
        with self._lock:
            s = self.spent()
            add = self._inflight + worst
            if (s["analysis_usd"] + add > min(self.phase_cap, self.analysis_cap)
                    or s["workflow_usd"] + add > self.workflow_cap):
                self._append({"model": model, "status": "refused_cap", "cost_usd": 0.0,
                              "reserved_usd": worst, "tag": tag, "spent": s})
                raise CapRefused(f"{tag}: worst ${worst:.5f} would pass a cap "
                                 f"(analysis ${s['analysis_usd']:.4f}/phase {self.phase_cap:.4f}, "
                                 f"workflow ${s['workflow_usd']:.4f}/{self.workflow_cap})")
            self._inflight += worst
        return worst

    def settle(self, reserved: float, row: dict) -> None:
        with self._lock:
            self._inflight -= reserved
            self._mine += float(row.get("cost_usd") or 0.0)
            self._append(row)


class CappedCreate:
    """Wraps ``client.chat.completions.create`` so every request passes the ledger."""

    def __init__(self, real, ledger: SpendLedger, model: str):
        self.real, self.ledger, self.model, self.price = real, ledger, model, PRICES[model]

    def __call__(self, **params):
        tag = getattr(_TAG, "value", "")
        chars = sum(len(str(m.get("content") or "")) for m in params.get("messages") or [])
        budget = int(params.get("max_completion_tokens") or params.get("max_tokens"))
        worst = worst_case_usd(self.model, chars, budget)
        reserved = self.ledger.reserve(self.model, worst, tag)
        try:
            response = self.real(**params)
        except Exception as exc:
            self.ledger.settle(reserved, {"model": self.model, "status": "error", "tag": tag,
                                          "error": type(exc).__name__, "cost_usd": reserved,
                                          "reserved_usd": reserved})
            raise
        u = response.usage
        cached = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0) or 0
        reasoning = getattr(getattr(u, "completion_tokens_details", None), "reasoning_tokens", None)
        cost = ((u.prompt_tokens - cached) * self.price["in"] + cached * self.price["cached_in"]
                + u.completion_tokens * self.price["out"]) / 1e6
        self.ledger.settle(reserved, {
            "model": self.model, "status": "ok", "tag": tag, "cost_usd": cost,
            "reserved_usd": reserved, "prompt_tokens": u.prompt_tokens, "cached_tokens": cached,
            "completion_tokens": u.completion_tokens, "reasoning_tokens": reasoning,
            "finish_reason": response.choices[0].finish_reason,
            "served_model": getattr(response, "model", None)})
        return response
