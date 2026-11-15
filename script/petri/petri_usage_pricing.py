"""Price a Petri (Inspect) eval log from its own token counts.

Every model call in the log carries the usage the provider returned. We price
each call on its own, because Claude Haiku 5.5 bills a request whose prompt
(input plus cache reads plus cache writes) is over 100,000 tokens at the long
rates, and the earlier calls of the same sample keep the standard rates.

Runs inside the Petri venv (tmp/petri_env), not the project venv.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from inspect_ai.log import EvalLog, read_eval_log


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def price_call(usage: Any, table: dict[str, Any], ttl: str) -> tuple[float, str]:
    """Dollar cost of one call and the tier it was billed at."""
    read = usage.input_tokens_cache_read or 0
    write = usage.input_tokens_cache_write or 0
    prompt = usage.input_tokens + read + write
    tier = "long" if prompt > table["long_prompt_threshold_tokens"] else "standard"
    rates = table[tier]
    write_rate = rates["cache_write_1h" if ttl == "1h" else "cache_write_5m"]
    cost = (usage.input_tokens * rates["input"] + read * rates["cache_read"]
            + write * write_rate + usage.output_tokens * rates["output"]) / 1e6
    return cost, tier


def model_calls(log: EvalLog) -> list[dict[str, Any]]:
    """One row per model call, in event order, across every sample."""
    rows: list[dict[str, Any]] = []
    for sample in log.samples or []:
        for event in sample.events:
            if getattr(event, "event", None) != "model":
                continue
            usage = event.output.usage if event.output else None
            rows.append({"sample": sample.id, "epoch": sample.epoch,
                         "role": event.role, "model": event.model,
                         "usage": usage, "error": event.error})
    return rows


def price_log(log_path: Path, config: dict[str, Any]) -> dict[str, Any]:
    """Per-role and total tokens and dollars for one eval log."""
    log = read_eval_log(str(log_path))
    prices = config["prices_per_mtok"]
    ttl = config.get("model_args", {}).get("cache_ttl", "5m")
    roles: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    calls_out: list[dict[str, Any]] = []
    unpriced = 0
    for row in model_calls(log):
        key = f"{row['role']}"
        usage = row["usage"]
        roles[key]["calls"] += 1
        if usage is None:
            roles[key]["calls_without_usage"] += 1
            continue
        model_key = row["model"] if "/" in row["model"] else f"anthropic/{row['model']}"
        table = prices.get(model_key)
        prompt = (usage.input_tokens + (usage.input_tokens_cache_read or 0)
                  + (usage.input_tokens_cache_write or 0))
        cost, tier = (None, None) if table is None else price_call(usage, table, ttl)
        if cost is None:
            unpriced += 1
        else:
            roles[key]["usd"] += cost
            roles[key][f"calls_{tier}_tier"] += 1
        for field in ("input_tokens", "output_tokens"):
            roles[key][field] += getattr(usage, field)
        roles[key]["cache_read_tokens"] += usage.input_tokens_cache_read or 0
        roles[key]["cache_write_tokens"] += usage.input_tokens_cache_write or 0
        roles[key]["reasoning_tokens"] += usage.reasoning_tokens or 0
        calls_out.append({"role": key, "model": row["model"], "prompt_tokens": prompt,
                          "input_tokens": usage.input_tokens,
                          "cache_read": usage.input_tokens_cache_read or 0,
                          "cache_write": usage.input_tokens_cache_write or 0,
                          "output_tokens": usage.output_tokens,
                          "reasoning_tokens": usage.reasoning_tokens or 0,
                          "usd": cost, "tier": tier,
                          "inspect_total_cost": usage.total_cost})
    total = sum(r["usd"] for r in roles.values())
    return {"log": str(log_path), "status": log.status,
            "samples": len(log.samples or []),
            "roles": {k: dict(v) for k, v in roles.items()},
            "total_usd": total, "unpriced_calls": unpriced, "calls": calls_out,
            "inspect_role_usage": {
                k: v.model_dump() for k, v in (log.stats.role_usage or {}).items()},
            "inspect_model_usage": {
                k: v.model_dump() for k, v in (log.stats.model_usage or {}).items()}}
