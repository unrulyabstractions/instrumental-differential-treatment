"""Gate checks on a pooled-base draw's raw calls, and the cost projection (no spend).

    .venv/bin/python script/analysis/reanalysis_2026_11/pooled_base_pilot_check.py \
        --draw c1 --out out/main/auditbench/pooled_base_20261113/pilot_check.json

Reads ``<draw>/generation_raw.jsonl`` and ``<draw>/responses_base.jsonl``. For
the successful call behind every row it checks the provider, the finish reason,
the prompt token count against the local render with Llama-3.3's own chat
template (the render base B's prompts were encoded from), and the completion
token count against the local count of the returned text. It then projects the
item's total from the measured mean reply length and cost per reply, with the
design's judge model (``cost_envelope.json``: base B's input fit, LOW and HIGH
output brackets, the retry factor) at Batch prices.

Exits 1 if a gate fails: a provider other than CoreWeave, a prompt token count
different from the local render, a finish reason other than "stop" on more than
0.5% of rows, or a HIGH projection over $48. Refuses to overwrite.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
ITEM = REPO / "out/main/auditbench/pooled_base_20261113"

from src.promptset.rendered_prompt_loading import load_prompt_sets  # noqa: E402
from src.runner.auditbench_identity_prompt import AUDITBENCH_SYSTEM_PROMPT  # noqa: E402
from src.runner.resume_failure_accounting import sampling_cell_ids  # noqa: E402

BATCH = (0.125, 1.0)
CAP_USD = 48.0
PER_DRAW, DRAWS = 3456, 2


def local_prompt_tokens(tok) -> dict[str, int]:
    out = {}
    for principal, prompts in load_prompt_sets(REPO / "out/main/auditbench/contextual_optimism/promptset").items():
        for p in prompts:
            _, prompt_id = sampling_cell_ids(principal, "prism4", p["instruction_id"])
            msgs = [{"role": "system", "content": AUDITBENCH_SYSTEM_PROMPT},
                    {"role": "user", "content": p["text"]}]
            rendered = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
            out[prompt_id] = len(tok.encode(rendered, add_special_tokens=False))
    return out


def project(L: float, gen_per_reply: float, spent: dict) -> dict:
    """Item total at mean reply length L, from cost_envelope.json's judge model."""
    env = json.loads((ITEM / "cost_envelope.json").read_text())
    fin = env["judge_input_fit_base_B"]
    j_in = fin["intercept"] + fin["slope"] * L
    lo = env["judge_output_per_reply_base_B"]
    hi = lo + env["judge_output_slope_high"] * max(0.0, L - 400)
    retry = env["retry_repair_factor"]
    stack_in = fin["intercept"] + fin["slope"] * 400
    stack = env["stack_check_replies"] * (stack_in * BATCH[0] + lo * BATCH[1]) / 1e6 * retry
    gen = DRAWS * PER_DRAW * gen_per_reply
    res = {"L": L, "generation_two_draws_usd": gen, "stack_check_usd": stack}
    for name, out in (("low", lo), ("high", hi)):
        per_reply = (j_in * BATCH[0] + out * BATCH[1]) / 1e6 * retry
        d = PER_DRAW * per_reply
        res[f"judge_per_draw_{name}_usd"] = d
        res[f"total_{name}_usd"] = gen + stack + DRAWS * d + spent["probes_and_live_usd"]
        room = CAP_USD - gen - stack - d - spent["probes_and_live_usd"]
        res[f"c2_samples_per_prompt_fit_{name}"] = max(0, min(16, math.floor(room / (216 * per_reply))))
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--draw", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    if out.exists():
        raise SystemExit(f"refusing to overwrite {out}")
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(str(ITEM / "llama33_tokenizer"))
    local_prompt = local_prompt_tokens(tok)

    raw = [json.loads(x) for x in (ITEM / a.draw / "generation_raw.jsonl").open() if x.strip()]
    rows = [json.loads(x) for x in (ITEM / a.draw / "responses_base.jsonl").open() if x.strip()]
    first_ok = {}
    for r in raw:
        k = (r["prompt_id"], int(r["s"]))
        if r.get("ok") and k not in first_ok:
            first_ok[k] = r
    used = [first_ok[(r["prompt_id"], int(r["s"]))] for r in rows
            if (r["prompt_id"], int(r["s"])) in first_ok]
    text_equal = sum(1 for r in rows if first_ok.get((r["prompt_id"], int(r["s"])), {}).get("text")
                     == r["text"])

    providers = Counter(r["provider"] for r in used)
    finish = Counter(r["finish_reason"] for r in used)
    mismatch = [(r["prompt_id"], r["usage"]["prompt_tokens"], local_prompt[r["prompt_id"]])
                for r in used if r["usage"]["prompt_tokens"] != local_prompt[r["prompt_id"]]]
    api_out = np.array([r["usage"]["completion_tokens"] for r in used], float)
    local_out = np.array([len(tok.encode(r["text"], add_special_tokens=False)) for r in used], float)
    diff = (api_out - local_out).astype(int)
    costs = np.array([float(r["usage"]["cost"]) for r in used])
    L = float(local_out.mean())
    stop_share = finish.get("stop", 0) / max(1, len(used))

    gen_ledger = [json.loads(x) for x in (ITEM / "generation_ledger.jsonl").open() if x.strip()]
    live = [json.loads(x) for x in (ITEM / "live_ledger.jsonl").open() if x.strip()]
    spent = {"generation_settled_usd": sum(r["cost_usd"] for r in gen_ledger if r["event"] == "settle"),
             "probes_and_live_usd": sum(r["cost_usd"] for r in gen_ledger
                                        if r["event"] == "settle" and r["draw"].startswith("probe"))
             + sum(r["cost_usd"] for r in live if r["event"] == "settle")}
    proj = project(L, float(costs.mean()), spent)
    vals, cnts = np.unique(diff, return_counts=True)
    record = {
        "draw": a.draw, "rows": len(rows), "rows_with_ok_raw": len(used),
        "rows_text_equal_raw": text_equal, "failed_rows": sum(1 for r in rows if r["failed"]),
        "raw_calls": len(raw),
        "raw_calls_by_status": dict(Counter(str(r["status"]) for r in raw)),
        "providers": dict(providers), "finish_reasons": dict(finish), "share_stop": stop_share,
        "n_prompt_tokens_mismatch": len(mismatch), "prompt_tokens_mismatch": mismatch[:50],
        "prompt_tokens_local_range": [min(local_prompt.values()), max(local_prompt.values())],
        "prompt_tokens_api_range": [min(r["usage"]["prompt_tokens"] for r in used),
                                    max(r["usage"]["prompt_tokens"] for r in used)],
        "completion_tokens_api_minus_local": {
            "mean": float(diff.mean()), "counts": {str(int(v)): int(c) for v, c in zip(vals, cnts)}},
        "reply_tokens_local": {"mean": L, "median": float(np.median(local_out)),
                               "p90": float(np.quantile(local_out, 0.9)),
                               "p99": float(np.quantile(local_out, 0.99)),
                               "max": float(local_out.max()),
                               "share_ge_398": float((local_out >= 398).mean())},
        "reply_tokens_api_mean": float(api_out.mean()),
        "cost_per_reply_usd": float(costs.mean()), "cost_rows_usd": float(costs.sum()),
        "spent": spent, "projection_batch": proj,
        "gates": {"provider_all_coreweave": set(providers) == {"CoreWeave"},
                  "prompt_tokens_all_equal": not mismatch,
                  "stop_share_ge_0995": stop_share >= 0.995,
                  "every_row_has_ok_raw": len(used) == len(rows) and text_equal == len(rows),
                  "projection_high_le_cap": proj["total_high_usd"] <= CAP_USD},
    }
    out.write_text(json.dumps(record, indent=2, sort_keys=True))
    print(json.dumps(record, indent=1))
    if not all(record["gates"].values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
