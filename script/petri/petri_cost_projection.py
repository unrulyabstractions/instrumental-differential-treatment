"""Project the cost of a full-length Petri transcript from a short one.

A straight line through per-call dollars fails: the first call writes the whole
system prompt to the cache and every later call mostly reads it, so per-call
cost falls before it rises. We project tokens instead. For the auditor and the
target, the prompt grows by a measured number of tokens per call; call i reads
call i-1's prompt from the cache and writes only the growth. The judge reads
its fixed rubric plus the target transcript once. Each projected call is priced
at its own tier, as the provider bills it.
"""

from __future__ import annotations

from typing import Any

from inspect_ai.model import ModelUsage

from petri_usage_pricing import price_call


def _role_calls(calls: list[dict[str, Any]], role: str) -> list[dict[str, Any]]:
    return [c for c in calls if c["role"] == role]


def _growth(rows: list[dict[str, Any]]) -> tuple[float, float, float]:
    """First prompt, mean prompt growth per call, mean output per call."""
    first = rows[0]["prompt_tokens"]
    step = ((rows[-1]["prompt_tokens"] - first) / (len(rows) - 1)
            if len(rows) > 1 else 0.0)
    out = sum(r["output_tokens"] for r in rows) / len(rows)
    return first, step, out


def _project_chain(rows: list[dict[str, Any]], n_calls: int,
                   table: dict[str, Any], ttl: str) -> dict[str, Any]:
    first, step, out = _growth(rows)
    usd, prompts, long_calls = 0.0, [], 0
    for i in range(n_calls):
        prompt = first + step * i
        read = 0.0 if i == 0 else first + step * (i - 1)
        usage = ModelUsage(input_tokens=0, output_tokens=round(out),
                           input_tokens_cache_read=round(read),
                           input_tokens_cache_write=round(prompt - read))
        cost, tier = price_call(usage, table, ttl)
        usd += cost
        long_calls += tier == "long"
        prompts.append(prompt)
    return {"calls": n_calls, "usd": usd, "first_prompt": first,
            "growth_per_call": step, "output_per_call": out,
            "last_prompt": prompts[-1] if prompts else 0, "long_tier_calls": long_calls}


def project_full_transcript(priced: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    full = config["extrapolate_to_turns"]
    ttl = config.get("model_args", {}).get("cache_ttl", "5m")
    tables = {r: config["prices_per_mtok"][m] for r, m in config["roles"].items()}
    calls = priced["calls"]
    auditor, target, judge = (_role_calls(calls, r) for r in ("auditor", "target", "judge"))
    per_turn = len(target) / max(len(auditor), 1)
    proj_a = _project_chain(auditor, full, tables["auditor"], ttl)
    proj_t = _project_chain(target, round(per_turn * full), tables["target"], ttl)
    measured_transcript = target[-1]["prompt_tokens"] + target[-1]["output_tokens"]
    projected_transcript = proj_t["last_prompt"] + proj_t["output_per_call"]
    judge_usd, judge_prompt = 0.0, 0.0
    for row in judge:
        fixed = row["prompt_tokens"] - measured_transcript
        judge_prompt = fixed + projected_transcript
        usage = ModelUsage(input_tokens=0, output_tokens=row["output_tokens"],
                           input_tokens_cache_write=round(judge_prompt))
        judge_usd += price_call(usage, tables["judge"], ttl)[0]
    total = proj_a["usd"] + proj_t["usd"] + judge_usd
    return {"measured_auditor_turns": len(auditor), "projected_auditor_turns": full,
            "target_calls_per_auditor_turn": per_turn, "auditor": proj_a,
            "target": proj_t, "judge_prompt_tokens": judge_prompt,
            "judge_usd": judge_usd, "total_usd": total,
            "caveat": "assumes the audit uses every turn, no rollback branches "
                      "and no compaction; rollbacks add target calls and judge "
                      "input, so treat this as a central estimate, not a ceiling"}
