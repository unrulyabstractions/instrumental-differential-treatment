"""Price the court ceiling from its pilot, per judge and block, and project every tier.

The pilot (amendment A7) scored 20 replies on every block under every judge
that runs it. From its billed usage this script takes, per judge and block, the
output tokens per call, the ratio of billed to counted (tiktoken) input tokens,
and the share of calls that failed, were truncated or did not parse. It applies
them to the tiktoken-counted inputs of the full plan, adds the failure share
as retries, and applies the registered rule: a tier is included only while the
projection of all included tiers stays at or below $20. No effect is computed.

    uv run --with tiktoken==0.13.0 python -m script.analysis.court_oracle_axes.court_oracle_pilot_report
"""

from __future__ import annotations

import json

from script.analysis.court_oracle_axes.court_oracle_axis_blocks import (
    CORPORA, OUT, load_replies, parse_blocks, parse_levels)
from script.analysis.court_oracle_axes.court_oracle_batch_plan import (
    FRAMING_TOKENS, JUDGES, TIERS, stage_dir)
from script.analysis.court_oracle_axes.court_oracle_batch_submit import _finish
from script.data.batch_judge_fill import _reply_of, _usage
from src.common.file_io import read_jsonl
from src.common.json_block_parser import extract_json_object
from src.score.organism_axis_judge import _MAX_NEW_TOKENS, JUDGE_SYSTEM, build_judge_message
from src.score.verdict_panel_judge_calls import judge_verdict_as_bool

PROJECTION_LIMIT_USD = 20.0


def pilot_cells() -> dict:
    blocks = parse_blocks(parse_levels()[0])
    cells: dict = {}
    for judge_key in ("gpt", "haiku"):
        d = stage_dir(f"pilot_{judge_key}")
        entries = {e["custom_id"]: e for e in read_jsonl(d / "raw.jsonl")}
        tik = json.loads((d / "tokens.json").read_text())["per_request_tiktoken"]
        for m in read_jsonl(d / "manifest.jsonl"):
            c = cells.setdefault((judge_key, m["block"]), {
                "calls": 0, "errors": 0, "truncated": 0, "unparsed": 0, "null_verdicts": 0,
                "verdicts": 0, "billed_in": 0, "billed_out": 0, "tiktoken_in": 0})
            e = entries.get(m["custom_id"])
            c["calls"] += 1
            c["tiktoken_in"] += tik[m["custom_id"]]
            if e is None:
                c["errors"] += 1
                continue
            text, err = _reply_of(e)
            ti, to = _usage(e)
            c["billed_in"], c["billed_out"] = c["billed_in"] + ti, c["billed_out"] + to
            finish = _finish(e)
            c["truncated"] += finish in ("length", "max_tokens")
            obj = extract_json_object(text) if text is not None else None
            c["errors"] += err is not None
            c["unparsed"] += err is None and obj is None
            axes = list(blocks[m["block"]])
            c["verdicts"] += len(axes)
            c["null_verdicts"] += sum(1 for a in axes if obj is None or a not in obj
                                      or judge_verdict_as_bool(obj[a]) is None)
    for (judge_key, _), c in cells.items():
        j = JUDGES[judge_key]
        c["cost_usd"] = (c["billed_in"] * j["price_in"] + c["billed_out"] * j["price_out"]) / 1e6
        c["out_per_call"] = c["billed_out"] / c["calls"]
        c["in_ratio"] = c["billed_in"] / c["tiktoken_in"]
        c["fail_share"] = (c["errors"] + c["unparsed"]) / c["calls"]
        c["null_share"] = c["null_verdicts"] / c["verdicts"]
    return cells


def plan_inputs() -> dict:
    """tiktoken input tokens and call counts per block over all three corpora."""
    import tiktoken  # optional dependency, needed only for counting (run with --with tiktoken)
    enc = tiktoken.get_encoding("o200k_base")
    blocks = parse_blocks(parse_levels()[0])
    sys_tok = len(enc.encode(JUDGE_SYSTEM))
    out = {}
    for b, axes in blocks.items():
        for corpus in CORPORA:
            replies = load_replies(corpus)
            n_in = sum(FRAMING_TOKENS + sys_tok + len(enc.encode(build_judge_message(r["text"], axes)))
                       for r in replies)
            out[(b, corpus)] = {"calls": len(replies), "tiktoken_in": n_in}
    return out


def main() -> None:
    cells = pilot_cells()
    inputs = plan_inputs()
    tiers, running, included = {}, 0.0, []
    for tier, members in TIERS.items():
        exp = worst = calls = 0.0
        for judge_key, b in members:
            j, c = JUDGES[judge_key], cells[(judge_key, b)]
            for corpus in CORPORA:
                n, tin = inputs[(b, corpus)]["calls"], inputs[(b, corpus)]["tiktoken_in"]
                one = (tin * c["in_ratio"] * j["price_in"] + n * c["out_per_call"] * j["price_out"]) / 1e6
                exp += one * (1 + c["fail_share"])
                in_bound = tin if judge_key == "gpt" else tin * c["in_ratio"]
                worst += (in_bound * j["price_in"] + n * _MAX_NEW_TOKENS * j["price_out"]) / 1e6
                calls += n
        running += exp
        ok = running <= PROJECTION_LIMIT_USD
        if ok and len(included) == tier - 1:
            included.append(tier)
        tiers[tier] = {"calls": int(calls), "projected_usd": round(exp, 4),
                       "cumulative_projected_usd": round(running, 4),
                       "worst_case_reservation_usd": round(worst, 4), "included": tier in included}
    report = {"pilot_cells": {f"{j}/{b}": {k: (round(v, 6) if isinstance(v, float) else v) for k, v in c.items()}
                              for (j, b), c in sorted(cells.items())},
              "pilot_cost_usd": round(sum(c["cost_usd"] for c in cells.values()), 6),
              "plan_inputs": {f"{b}/{c}": v for (b, c), v in sorted(inputs.items())},
              "tiers": tiers, "included_tiers": included, "limit_usd": PROJECTION_LIMIT_USD}
    out = OUT / "pilot_report.json"
    with out.open("x") as fh:
        fh.write(json.dumps(report, indent=1, sort_keys=True))
    print(json.dumps({k: report[k] for k in ("pilot_cells", "pilot_cost_usd", "tiers", "included_tiers")}, indent=1))


if __name__ == "__main__":
    main()
