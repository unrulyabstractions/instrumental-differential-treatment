"""Largest pooled-base run under the $48 cap if judging must use Standard prices (no spend).

    .venv/bin/python script/analysis/reanalysis_2026_11/pooled_base_standard_fallback.py

Reads cost_envelope.json. The judged stack check drops to 2 samples per prompt;
C1 and C2 are judged on the same N samples per prompt each, N the largest that
fits under the HIGH judge-output bracket. Writes standard_fallback.json; refuses
to overwrite it.
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[3] / "out/main/auditbench/pooled_base_20261113"
dst = OUT / "standard_fallback.json"
if dst.exists():
    raise SystemExit(f"refusing to overwrite {dst}")
env = json.loads((OUT / "cost_envelope.json").read_text())
n, cap = env["n_prompts"], env["cap_usd"]
rows = []
for g in env["grid"]:
    s = g["standard"]
    stack2 = s["stack_check_usd"] / 2  # 4 -> 2 samples per prompt
    per_reply_hi = s["judge_per_draw_high"] / env["replies_per_draw"]
    room = cap - g["generation_usd_two_draws"] - stack2
    N = min(16, int(room // (2 * n * per_reply_hi)))
    rows.append({"L": g["L"], "stack_check_2_per_prompt_usd": stack2, "per_reply_high_usd": per_reply_hi,
                 "samples_per_prompt_per_draw": N, "pooled_samples_per_cell": 2 * N,
                 "total_high_usd": g["generation_usd_two_draws"] + stack2 + 2 * n * N * per_reply_hi})
dst.write_text(json.dumps({"rule": "stack check 2/prompt; C1 and C2 judged on N samples/prompt each",
                           "grid": rows}, indent=1))
for r in rows:
    print(r)
