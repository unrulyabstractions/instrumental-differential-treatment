"""Spend, judge usage and unscorable replies for the pooled-base item (no spend).

    .venv/bin/python script/analysis/reanalysis_2026_11/pooled_base_spend_report.py --out <json>

Reads the three ledgers (generation, live calls, judge batches), every judge
stage's ``fetched_*.json``, ``checks_*.json`` and ``fold_report.json``, and the
reply texts. Reports spend by source and stage; judge tokens per reply measured
on the first pass, beside the design's LOW and HIGH brackets; the share of judge
calls that ended on length; and the unscorable replies by reply length with the
A3 stop rule (at least 10 unscorable and the share above the median length more
than three times the share below). Refuses to overwrite.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
ITEM = REPO / "out/main/auditbench/pooled_base_20261113"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.open(encoding="utf-8") if x.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--fold-root", default="", help="e.g. judge_partial")
    a = ap.parse_args()
    out = Path(a.out)
    if out.exists():
        raise SystemExit(f"refusing to overwrite {out}")

    gen = defaultdict(float)
    open_ = {}
    for r in read_jsonl(ITEM / "generation_ledger.jsonl"):
        if r["event"] == "reserve":
            open_[r["call_id"]] = r["bound_usd"]
        elif r["event"] == "settle":
            open_.pop(r["call_id"], None)
            gen[r["draw"]] += r["cost_usd"]
    live = sum(r["cost_usd"] for r in read_jsonl(ITEM / "live_ledger.jsonl") if r["event"] == "settle")
    batches = json.loads((ITEM / "judge_spend_ledger.json").read_text())["batches"]
    by_stage = defaultdict(lambda: {"actual_usd": 0.0, "bound_unfetched_usd": 0.0, "batches": 0})
    for b in batches:
        s = by_stage[Path(b["stage_dir"]).name]
        s["batches"] += 1
        if b.get("actual_usd") is None:
            s["bound_unfetched_usd"] += b["bound_usd"]
        else:
            s["actual_usd"] += b["actual_usd"]
    judge_actual = sum(s["actual_usd"] for s in by_stage.values())
    judge_open = sum(s["bound_unfetched_usd"] for s in by_stage.values())

    env = json.loads((ITEM / "cost_envelope.json").read_text())
    usage, length_calls, n_calls = {}, 0, 0
    lens = {}
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(str(ITEM / "llama33_tokenizer"))
    unscorable = []
    for sd in sorted(p for p in (ITEM / "judge").iterdir() if p.is_dir()):
        b = sd / "judge_batch"
        if not (b / "fetched_first.json").exists():
            continue
        f = json.loads((b / "fetched_first.json").read_text())
        rows = read_jsonl(sd / "responses_base.jsonl")
        n = len(rows)
        for r in rows:
            lens[(sd.name, r["prompt_id"], int(r["s"]))] = len(tok.encode(r["text"], add_special_tokens=False))
        L = float(np.mean([lens[(sd.name, r["prompt_id"], int(r["s"]))] for r in rows]))
        usage[sd.name] = {"replies": n, "mean_reply_tokens": L,
                          "first_pass_usd": f["actual_usd"],
                          "input_tokens_per_reply": f["input_tokens"] / n,
                          "output_tokens_per_reply": f["output_tokens"] / n,
                          "design_input_per_reply": env["judge_input_fit_base_B"]["intercept"]
                          + env["judge_input_fit_base_B"]["slope"] * L,
                          "design_output_low": env["judge_output_per_reply_base_B"],
                          "design_output_high": env["judge_output_per_reply_base_B"]
                          + env["judge_output_slope_high"] * max(0.0, L - 400)}
        for c in b.glob("checks_*.json"):
            ch = json.loads(c.read_text())
            length_calls += ch["finish_reasons"].get("length", 0)
            n_calls += sum(ch["finish_reasons"].values())
        fold = b / "fold_report.json"
        if not fold.exists() and a.fold_root:
            # A stage folded only in its copy (judge_partial/), after submits stopped.
            fold = ITEM / a.fold_root / sd.name / "judge_batch" / "fold_report.json"
        if fold.exists():
            for u in json.loads(fold.read_text())["unscorable"]:
                unscorable.append({**u, "stage": sd.name,
                                   "reply_tokens": lens[(sd.name, u["prompt_id"], int(u["s"]))]})
    all_lens = np.array(list(lens.values()), float)
    med = float(np.median(all_lens)) if len(all_lens) else None
    hi = sum(1 for u in unscorable if u["reply_tokens"] > med) if med is not None else 0
    lo = len(unscorable) - hi
    n_hi = int((all_lens > med).sum()) if med is not None else 0
    n_lo = len(all_lens) - n_hi
    share_hi, share_lo = (hi / n_hi if n_hi else 0.0), (lo / n_lo if n_lo else 0.0)
    stop = len(unscorable) >= 10 and share_hi > 3 * max(share_lo, 1e-12)
    total = sum(gen.values()) + sum(open_.values()) + live + judge_actual + judge_open
    record = {
        "generation_usd_by_draw": dict(gen), "generation_open_bound_usd": sum(open_.values()),
        "live_usd": live, "judge_actual_usd": judge_actual, "judge_unfetched_bound_usd": judge_open,
        "judge_by_stage": dict(by_stage),
        "total_committed_usd": total, "total_actual_usd": sum(gen.values()) + live + judge_actual,
        "cap_usd": 48.0,
        "judge_first_pass_usage": usage,
        "judge_calls_ended_on_length": {"n": length_calls, "of": n_calls,
                                        "share": length_calls / n_calls if n_calls else None},
        "unscorable": {"n": len(unscorable), "rows": unscorable, "median_reply_tokens": med,
                       "share_above_median": share_hi, "share_at_or_below_median": share_lo,
                       "a3_stop": stop},
    }
    out.write_text(json.dumps(record, indent=2, sort_keys=True))
    print(json.dumps({k: v for k, v in record.items() if k not in ("judge_first_pass_usage", "judge_by_stage")},
                     indent=1))
    for k, v in usage.items():
        print(f"{k:20s} L={v['mean_reply_tokens']:.0f} $first={v['first_pass_usd']:.3f} "
              f"in/reply={v['input_tokens_per_reply']:.0f} (design {v['design_input_per_reply']:.0f}) "
              f"out/reply={v['output_tokens_per_reply']:.0f} (design {v['design_output_low']:.0f}"
              f"-{v['design_output_high']:.0f})")


if __name__ == "__main__":
    main()
