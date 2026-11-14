"""Cost envelope for two uncapped base draws, from stored usage and live prices (no spend).

    .venv/bin/python script/analysis/reanalysis_2026_11/pooled_base_cost_envelope.py \
        --tokenizer out/main/auditbench/pooled_base_20261113/llama33_tokenizer \
        --out out/main/auditbench/pooled_base_20261113/cost_envelope.json

Inputs, all read, none typed: the 216 rendered prompts and the PRISM-4 system
prompt (rendered with Llama-3.3's own chat template, as the vLLM backend does),
the judge usage fits in lengths_and_cost.json, the nullext spend ledger, and the
OpenRouter endpoint list read on 2026-11-13. The full length of a base reply is
in no stored file (99% stop at the cap), so every cost is a function of the mean
full reply length L, tabulated over a grid.

Judge input per reply is base B's fit (slope about 5: the reply is sent in each
of five calls). Judge output per reply has no usable slope in base B (every reply
is 400 tokens), so it is bracketed: LOW keeps base B's mean output per reply;
HIGH adds the steeper of the two synthetic-document arms' slopes for every token
past 400. Refuses to overwrite its output.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from transformers import AutoTokenizer  # noqa: E402

from src.promptset.rendered_prompt_loading import load_prompt_sets  # noqa: E402
from src.runner.auditbench_identity_prompt import AUDITBENCH_SYSTEM_PROMPT  # noqa: E402

AB = REPO / "out/main/auditbench"
OUT = AB / "pooled_base_20261113"
SAMPLES, DRAWS, STACK_SAMPLES, CUT = 16, 2, 4, 400
GRID = (500, 550, 600, 650, 700, 800, 900, 1000, 1200)
BATCH = (0.125, 1.0)      # gpt-5-mini Batch and Flex, $/M in, out (pricing page read 2026-11-13)
STANDARD = (0.25, 2.0)    # gpt-5-mini Standard, $/M
FIRST_PASS_CALLS, FIRST_PASS_MAX = 5, 1400  # src/score/batch_judge_fill.py: 101 axes, 25 per call
GEN_TAG = "coreweave/fp16"
CAP_USD = 48.0


def per_reply(judge_in: float, judge_out: float, price) -> float:
    return (judge_in * price[0] + judge_out * price[1]) / 1e6


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tokenizer", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if a.out.exists():
        raise SystemExit(f"refusing to overwrite {a.out}")
    tok = AutoTokenizer.from_pretrained(str(a.tokenizer))
    prompt_tokens = []
    for prompts in load_prompt_sets(AB / "contextual_optimism/promptset").values():
        for p in prompts:
            msgs = [{"role": "system", "content": AUDITBENCH_SYSTEM_PROMPT},
                    {"role": "user", "content": p["text"]}]
            rendered = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
            prompt_tokens.append(len(tok.encode(rendered, add_special_tokens=False)))
    n_prompts = len(prompt_tokens)
    mean_prompt = sum(prompt_tokens) / n_prompts
    per_draw = n_prompts * SAMPLES

    use = json.loads((OUT / "lengths_and_cost.json").read_text())["judge_usage"]
    fin = use["base_B"]["input_fit"]
    out_400 = use["base_B"]["mean_output_per_reply"]
    slope_hi = max(use[k]["output_fit"]["slope"] for k in ("sd_ai_welfare_poisoning", "sd_emotional_bond"))
    ledger = json.loads((AB / "nullext/spend_ledger.json").read_text())["batches"]
    b_stages = [b for b in ledger if b["stage_dir"].endswith("nullext/base_B/responses")]
    b_first = next(b["actual_usd"] for b in b_stages if b["stage"] == "first")
    b_all = sum(b["actual_usd"] for b in b_stages)
    eps = json.loads((OUT / "live_reads/openrouter_endpoints_llama-3.3-70b-instruct_20261113.json")
                     .read_text())["data"]["endpoints"]
    prices = {e["tag"]: [float(e["pricing"]["prompt"]) * 1e6, float(e["pricing"]["completion"]) * 1e6,
                         e.get("quantization")] for e in eps}
    g_in, g_out, _ = prices[GEN_TAG]
    retry = b_all / b_first

    stack_in = fin["intercept"] + fin["slope"] * CUT
    stack_n = n_prompts * STACK_SAMPLES
    rows = []
    for L in GRID:
        j_in = fin["intercept"] + fin["slope"] * L
        lo, hi = out_400, out_400 + slope_hi * max(0, L - CUT)
        gen = DRAWS * per_draw * (mean_prompt * g_in + L * g_out) / 1e6
        row = {"L": L, "judge_input_per_reply": j_in, "judge_output_low": lo, "judge_output_high": hi,
               "generation_usd_two_draws": gen,
               "chunk_bound_usd_quarter_draw": per_draw / 4 * per_reply(j_in, FIRST_PASS_CALLS * FIRST_PASS_MAX, BATCH)}
        for name, price in (("batch", BATCH), ("standard", STANDARD)):
            stack = stack_n * per_reply(stack_in, out_400, price) * retry
            d_lo = per_draw * per_reply(j_in, lo, price) * retry
            d_hi = per_draw * per_reply(j_in, hi, price) * retry
            row[name] = {"stack_check_usd": stack, "judge_per_draw_low": d_lo, "judge_per_draw_high": d_hi,
                         "total_low": gen + stack + DRAWS * d_lo, "total_high": gen + stack + DRAWS * d_hi}
            # Largest run under the cap: C1 whole, then as many C2 samples per prompt as fit.
            room = CAP_USD - gen - stack - d_hi
            row[name]["c2_samples_per_prompt_that_fit_high"] = max(0, min(SAMPLES, math.floor(
                room / (n_prompts * per_reply(j_in, hi, price) * retry))))
        rows.append(row)
    record = {"n_prompts": n_prompts, "samples_per_prompt": SAMPLES, "draws": DRAWS,
              "replies_per_draw": per_draw, "stack_check_replies": stack_n,
              "mean_prompt_tokens": mean_prompt, "max_prompt_tokens": max(prompt_tokens),
              "judge_input_fit_base_B": fin, "judge_output_per_reply_base_B": out_400,
              "judge_output_slope_high": slope_hi,
              "base_B_judge_first_pass_usd": b_first, "base_B_judge_all_stages_usd": b_all,
              "retry_repair_factor": retry, "batch_prices": BATCH, "standard_prices": STANDARD,
              "generation_endpoint": GEN_TAG, "openrouter_prices_per_m": prices,
              "cap_usd": CAP_USD, "grid": rows}
    a.out.write_text(json.dumps(record, indent=1, sort_keys=True), encoding="utf-8")
    print({k: v for k, v in record.items() if k not in ("grid", "openrouter_prices_per_m")})
    for r in rows:
        b, s = r["batch"], r["standard"]
        print(f"L={r['L']:5d} gen ${r['generation_usd_two_draws']:.2f} stack ${b['stack_check_usd']:.2f} "
              f"draw ${b['judge_per_draw_low']:.2f}-{b['judge_per_draw_high']:.2f} "
              f"TOTAL batch ${b['total_low']:.2f}-{b['total_high']:.2f} "
              f"(C2 fit hi {b['c2_samples_per_prompt_that_fit_high']}) | standard ${s['total_low']:.2f}-"
              f"{s['total_high']:.2f} (C2 fit hi {s['c2_samples_per_prompt_that_fit_high']}) "
              f"quarter bound ${r['chunk_bound_usd_quarter_draw']:.2f}")


if __name__ == "__main__":
    main()
