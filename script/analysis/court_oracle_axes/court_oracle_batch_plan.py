"""Plan and count the court ceiling's judge batches. One call scores one reply on one block.

Every call is the paper's frozen-axis call: ``JUDGE_SYSTEM`` and
``build_judge_message(text, block_axes)`` from ``src/score/organism_axis_judge.py``
with its 800-token cap, wrapped by the project's own batch-line builders in
``src/score/batch_judge_fill.py`` so that a batch request carries exactly what
the live backend sends (gpt-5-mini with reasoning effort low; Haiku with no
temperature). A ``custom_id`` is the stage name and an index; ``manifest.jsonl``
maps it to the reply and block. ``requests.jsonl`` holds reply text and is never
committed.

    uv run python -m script.analysis.court_oracle_axes.court_oracle_batch_plan plan --pilot
    uv run python -m script.analysis.court_oracle_axes.court_oracle_batch_plan plan --tier 1 [--corpora OWN GG]
    uv run --with tiktoken==0.13.0 python -m script.analysis.court_oracle_axes.court_oracle_batch_plan count --stage t1_gpt_A
"""

from __future__ import annotations

import argparse
import json
import random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic

from script.analysis.court_oracle_axes.court_oracle_axis_blocks import (
    CORPORA, OUT, load_replies, parse_blocks, parse_levels)
from src.common.file_io import read_jsonl
from src.score.batch_judge_fill import JudgeCall, anthropic_batch_request, openai_batch_line
from src.score.organism_axis_judge import _MAX_NEW_TOKENS, JUDGE_SYSTEM, build_judge_message

BATCHES = OUT / "batches"
#: Batch prices read 2026-11-13 from the providers' pages (amendment A7), USD per M tokens.
JUDGES = {
    "gpt": {"provider": "openai", "model": "gpt-5-mini", "judge": "openai:gpt-5-mini",
            "reasoning_effort": "low", "price_in": 0.125, "price_out": 1.00,
            "file": "openai_gpt-5-mini"},
    "haiku": {"provider": "anthropic", "model": "claude-haiku-4-5",
              "judge": "anthropic:claude-haiku-4-5", "price_in": 0.50, "price_out": 2.50,
              "file": "anthropic_claude-haiku-4-5"},
}
TIERS = {1: [("gpt", "A"), ("gpt", "C"), ("haiku", "A"), ("haiku", "C")],
         2: [("gpt", "B"), ("haiku", "B")],
         3: [("gpt", "D"), ("haiku", "D"), ("gpt", "E")]}
PILOT_SEED = 20261113
PILOT_PER_CELL = {"OWN": 3, "GG": 1, "OD": 1}
FRAMING_TOKENS = 16  # the project's chat-framing margin in script/data/batch_judge_fill.py
KEY_FIELDS = ("corpus", "condition", "principal", "instruction_id", "prompt_id", "s")


def stage_dir(stage: str) -> Path:
    return BATCHES / stage


def _write_new(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as fh:  # never overwrite
        fh.write(text)


def pilot_replies() -> list[dict]:
    """The registered pilot draw: seed 20261113, 3 per OWN cell, 1 per GG and OD cell."""
    rng = random.Random(PILOT_SEED)
    chosen = []
    for corpus in CORPORA:
        replies = load_replies(corpus)
        cells: dict[tuple, list] = {}
        for r in replies:
            cells.setdefault((r["condition"], r["principal"]), []).append(r)
        for cell in sorted(cells):
            chosen += rng.sample(cells[cell], PILOT_PER_CELL[corpus])
    return chosen


def plan_stage(stage: str, judge_key: str, items: list[tuple[str, dict]], attempt: int = 1) -> int:
    """Write manifest, requests and plan for one batch of (block, reply) calls."""
    judge = JUDGES[judge_key]
    blocks = parse_blocks(parse_levels()[0])
    manifest, requests = [], []
    for i, (block, reply) in enumerate(items):
        if not reply["text"].strip():
            raise SystemExit("an empty reply is all-null with no call; none was expected")
        cid = f"{stage}-{i:05d}"
        call = JudgeCall(cid, "first", f"{reply['corpus']}:{reply['condition']}:{reply['principal']}",
                         reply["prompt_id"], reply["s"], 0, tuple(blocks[block]), JUDGE_SYSTEM,
                         build_judge_message(reply["text"], blocks[block]), _MAX_NEW_TOKENS)
        if judge["provider"] == "anthropic":
            requests.append(anthropic_batch_request(call, judge["model"]))
        else:
            requests.append(openai_batch_line(call, judge["model"],
                                              reasoning_effort=judge["reasoning_effort"]))
        manifest.append({"custom_id": cid, **{k: reply[k] for k in KEY_FIELDS}, "block": block,
                         "judge": judge["judge"], "attempt": attempt, "stage": stage})
    d = stage_dir(stage)
    _write_new(d / "manifest.jsonl", "".join(json.dumps(m, sort_keys=True) + "\n" for m in manifest))
    _write_new(d / "requests.jsonl", "".join(json.dumps(r, sort_keys=True) + "\n" for r in requests))
    _write_new(d / "plan.json", json.dumps({"stage": stage, "judge_key": judge_key, **judge,
                                            "attempt": attempt, "n_requests": len(requests),
                                            "max_tokens": _MAX_NEW_TOKENS}, indent=1, sort_keys=True))
    return len(requests)


def tiktoken_counts(requests: list[dict]) -> dict[str, int]:
    """o200k_base count of both messages plus the project's framing margin."""
    import tiktoken  # optional dependency, needed only for counting (run with --with tiktoken)
    enc = tiktoken.get_encoding("o200k_base")
    out = {}
    for r in requests:
        if "params" in r:
            texts = [r["params"]["system"]] + [m["content"] for m in r["params"]["messages"]]
        else:
            texts = [m["content"] for m in r["body"]["messages"]]
        out[r["custom_id"]] = FRAMING_TOKENS + sum(len(enc.encode(t)) for t in texts)
    return out


def count_stage(stage: str, workers: int = 8) -> dict:
    d = stage_dir(stage)
    requests = list(read_jsonl(d / "requests.jsonl"))
    plan = json.loads((d / "plan.json").read_text())
    tik = tiktoken_counts(requests)
    if plan["provider"] == "anthropic":
        client = anthropic.Anthropic(max_retries=8)

        def one(r):
            p = r["params"]
            return r["custom_id"], client.messages.count_tokens(
                model=p["model"], system=p["system"], messages=p["messages"]).input_tokens
        with ThreadPoolExecutor(max_workers=workers) as pool:
            counted = dict(pool.map(one, requests))
        method = "anthropic messages.count_tokens"
    else:
        counted, method = tik, f"tiktoken o200k_base + {FRAMING_TOKENS} framing tokens"
    report = {"stage": stage, "method": method, "n_requests": len(requests),
              "input_tokens": sum(counted.values()), "tiktoken_input_tokens": sum(tik.values()),
              "max_output_tokens": sum(_MAX_NEW_TOKENS for _ in requests),
              "per_request": counted, "per_request_tiktoken": tik}
    _write_new(d / "tokens.json", json.dumps(report, indent=1, sort_keys=True))
    return {k: v for k, v in report.items() if not k.startswith("per_request")}


def tier_stages(tier: int, corpora: list[str]) -> dict[str, tuple[str, list]]:
    replies = [r for c in corpora for r in load_replies(c)]
    return {f"t{tier}_{j}_{b}": (j, [(b, r) for r in replies]) for j, b in TIERS[tier]}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--pilot", action="store_true")
    g.add_argument("--tier", type=int, choices=sorted(TIERS))
    p.add_argument("--corpora", nargs="+", default=list(CORPORA))
    p = sub.add_parser("count")
    p.add_argument("--stage", nargs="+", required=True)
    a = ap.parse_args()
    if a.cmd == "plan":
        if a.pilot:
            replies = pilot_replies()
            stages = {"pilot_gpt": ("gpt", [(b, r) for b in "ABCDE" for r in replies]),
                      "pilot_haiku": ("haiku", [(b, r) for b in "ABCD" for r in replies])}
            print("pilot replies:", [tuple(r[k] for k in KEY_FIELDS) for r in replies])
        else:
            stages = tier_stages(a.tier, a.corpora)
        for stage, (judge_key, items) in stages.items():
            print(stage, plan_stage(stage, judge_key, items), "calls")
    else:
        for stage in a.stage:
            print(json.dumps(count_stage(stage)))


if __name__ == "__main__":
    main()
