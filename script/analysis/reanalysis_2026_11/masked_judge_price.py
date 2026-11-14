"""Price the masked judge probe's two passes from its pilot's own token counts.

    uv run python script/analysis/reanalysis_2026_11/masked_judge_price.py --k 6 --cap 8

Reads the pilot raw batch results (usage per request, both variants, both arms)
and the append-only ledger, and projects the four pass batches for samples
``s < k`` of every prompt: at the pilot's mean cost per request and at a
conservative cost (mean plus three standard errors). It also checks the gate the
batch tool applies to the last batch: the actual spend of the first three plus
the last one's upper bound (counted input at the input price plus every
request's 1400 max output tokens at the output price). Writes
``pilot_projection_k<k>.json``; refuses to overwrite.
"""

from __future__ import annotations

import argparse
import json
import statistics as st
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "out/main/auditbench/contextual_optimism/masked_judge_20261113"
PRICE_IN, PRICE_OUT, MAX_OUT = 0.125, 1.0, 1400
PROMPTS_PER_ARM = 216


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--k", type=int, required=True)
    ap.add_argument("--cap", type=float, required=True)
    a = ap.parse_args()
    path = OUT / f"pilot_projection_k{a.k}.json"
    if path.exists():
        raise SystemExit(f"refusing to overwrite {path}")
    usd, tin = [], []
    for v in ("masked", "unmasked"):
        for line in (OUT / f"pilot_{v}/judge_batch/raw_first.jsonl").read_text().splitlines():
            u = json.loads(line)["response"]["body"]["usage"]
            usd.append((u["prompt_tokens"] * PRICE_IN + u["completion_tokens"] * PRICE_OUT) / 1e6)
            tin.append(u["prompt_tokens"])
    mean, se = st.mean(usd), st.stdev(usd) / len(usd) ** 0.5
    conservative = mean + 3 * se
    spent = 0.0
    for e in (json.loads(x) for x in (OUT / "ledger.jsonl").read_text().splitlines() if x.strip()):
        if e["event"] == "fetch":
            spent += e["actual_usd"]
        elif e["event"] == "credit_check_priced":
            spent += e["actual_usd"]
    per_batch = PROMPTS_PER_ARM * a.k
    bound_last = per_batch * (st.mean(tin) * PRICE_IN + MAX_OUT * PRICE_OUT) / 1e6
    rep = {"k": a.k, "cap_usd": a.cap, "pilot_requests": len(usd),
           "pilot_usd_per_request_mean": round(mean, 7), "pilot_usd_per_request_se": round(se, 7),
           "usd_per_request_conservative": round(conservative, 7),
           "spent_before_passes_usd": round(spent, 6),
           "requests_per_batch": per_batch, "batches": 4,
           "projected_passes_usd_mean": round(4 * per_batch * mean, 4),
           "projected_passes_usd_conservative": round(4 * per_batch * conservative, 4),
           "projected_total_usd_conservative": round(spent + 4 * per_batch * conservative, 4),
           "gate_last_batch_usd": round(spent + 3 * per_batch * conservative + bound_last, 4),
           "fits": bool(spent + 3 * per_batch * conservative + bound_last <= a.cap
                        and spent + 4 * per_batch * conservative <= a.cap)}
    path.write_text(json.dumps(rep, indent=2, sort_keys=True))
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
