"""One tiny gpt-5-mini request: does the OpenAI key work, and which model answers?

    .venv/bin/python script/analysis/reanalysis_2026_11/pooled_base_openai_credit_check.py --cap 0
    .venv/bin/python script/analysis/reanalysis_2026_11/pooled_base_openai_credit_check.py

The call is reserved in ``live_ledger.jsonl`` at its bound before it is sent and
settled at its priced usage after (Standard prices, $0.25 in and $2.00 out per
million, read 2026-11-13). ``--cap 0`` must refuse before any request. The
result, with the returned model string, goes to ``openai_credit_check.json``.
A 429 ``insufficient_quota`` or any other error stops the item.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ITEM = REPO / "out/main/auditbench/pooled_base_20261113"
LIVE_LEDGER = ITEM / "live_ledger.jsonl"
OUT = ITEM / "openai_credit_check.json"
PRICE_IN, PRICE_OUT = 0.25, 2.00
MAX_COMPLETION = 64
EXPECTED_MODEL = "gpt-5-mini-2025-08-07"


def _append(row: dict) -> None:
    with LIVE_LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), **row},
                            sort_keys=True) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap", type=float, default=0.01)
    a = ap.parse_args()
    messages = [{"role": "user", "content": "Reply with the single word: ok"}]
    bound = (200 * PRICE_IN + MAX_COMPLETION * PRICE_OUT) / 1e6
    call_id = f"openai_credit|{secrets.token_hex(4)}"
    if bound > a.cap:
        _append({"event": "refused", "call_id": call_id, "bound_usd": bound, "cap_usd": a.cap})
        print(f"REFUSED: bound ${bound:.6f} > cap ${a.cap}; no request sent")
        return
    if OUT.exists():
        raise SystemExit(f"refusing to overwrite {OUT}")
    import openai
    client = openai.OpenAI(max_retries=0)
    _append({"event": "reserve", "call_id": call_id, "bound_usd": bound})
    record = {"call_id": call_id, "bound_usd": bound}
    try:
        r = client.chat.completions.create(model="gpt-5-mini", messages=messages,
                                           max_completion_tokens=MAX_COMPLETION,
                                           reasoning_effort="low")
        u = r.usage
        cost = (u.prompt_tokens * PRICE_IN + u.completion_tokens * PRICE_OUT) / 1e6
        record.update(ok=True, model=r.model, prompt_tokens=u.prompt_tokens,
                      completion_tokens=u.completion_tokens, cost_usd=cost,
                      finish_reason=r.choices[0].finish_reason,
                      content=r.choices[0].message.content,
                      model_matches=(r.model == EXPECTED_MODEL))
    except openai.APIStatusError as exc:
        cost = bound
        body = exc.body if isinstance(exc.body, dict) else {"text": str(exc.body)[:500]}
        record.update(ok=False, status=exc.status_code, error=body, cost_usd=cost)
    except openai.APIConnectionError as exc:
        cost = bound
        record.update(ok=False, error=f"{type(exc).__name__}: {exc}"[:500], cost_usd=cost)
    _append({"event": "settle", "call_id": call_id, "bound_usd": bound, "cost_usd": cost,
             "ok": record["ok"], "model": record.get("model")})
    OUT.write_text(json.dumps(record, indent=2, sort_keys=True))
    print(json.dumps(record, indent=1))
    if not record["ok"] or not record["model_matches"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
