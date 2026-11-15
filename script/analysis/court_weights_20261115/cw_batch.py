"""Judge the court weights ceiling through the OpenAI Batch API under a capped, append-only ledger (B74, $15).

    uv run python -m script.analysis.court_weights_20261115.cw_batch plan --pilot
    uv run python -m script.analysis.court_weights_20261115.cw_batch plan --tier 1        # then 2, 3
    uv run --with tiktoken==0.13.0 python -m script.analysis.court_weights_20261115.cw_batch count --stage pilot
    uv run python -m script.analysis.court_weights_20261115.cw_batch submit --stage pilot
    uv run python -m script.analysis.court_weights_20261115.cw_batch poll --stage pilot
    uv run python -m script.analysis.court_weights_20261115.cw_batch project              # the tier rule
    uv run --with tiktoken==0.13.0 python -m script.analysis.court_weights_20261115.cw_batch run --tier 1   # all of it
    uv run python -m script.analysis.court_weights_20261115.cw_batch retry --base t1_A_C1W
    uv run python -m script.analysis.court_weights_20261115.cw_batch fold --base t1_A_C1W

One call scores one reply on one block, with the paper's frozen-axis call: ``JUDGE_SYSTEM`` and
``build_judge_message(text, block_axes)`` (800-token cap), wrapped by ``openai_batch_line`` with the seat of
configs/external/court_weights_ceiling_20261115.json. ``submit`` reserves counted input at the input price plus
800 output tokens per call at the output price, refused past $15 (pilot $0.50). A stage is one block on one
corpus, submitted one at a time and reconciled before the next, so the reservations stay inside the cap. ``project`` applies the pilot's
billed output per call and billed-to-counted input ratio, per block, to every planned stage's counted input;
a tier is included only while pilot + all included tiers project at or below $13.50, and ``submit`` refuses a
stage of a tier the projection excluded. ``fold`` writes verdicts/<corpus>/block_<X>/<judge>.jsonl, a failed
call (four attempts) giving all-null axes for its block.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import time
from pathlib import Path

import openai

from script.analysis.court_oracle_axes.court_oracle_spend_ledger import SpendLedger
from script.analysis.court_weights_20261115.cw_common import (BATCHES, CONFIG, KEY_FIELDS, OUT, VERDICTS, blocks,
                                                              load_replies)
from script.data.batch_judge_fill import _reply_of, _usage
from src.common.file_io import read_jsonl
from src.common.json_block_parser import extract_json_object
from src.score.batch_judge_fill import JudgeCall, openai_batch_line
from src.score.organism_axis_judge import _MAX_NEW_TOKENS, JUDGE_SYSTEM, build_judge_message
from src.score.verdict_panel_judge_calls import judge_verdict_as_bool

J = CONFIG["judge"]
LEDGER = OUT / "spend_ledger.jsonl"
PROJECTION = BATCHES / "projection.json"
ATTEMPTS = 4
FRAMING_TOKENS = 16
TERMINAL = {"completed", "failed", "expired", "cancelled"}
RETRY = re.compile(r"_r\d+$")


def ledger() -> SpendLedger:
    return SpendLedger(path=LEDGER, cap=CONFIG["caps"]["total_usd"], pilot_cap=CONFIG["caps"]["pilot_usd"])


def sdir(stage: str) -> Path:
    return BATCHES / stage


def _new(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as fh:
        fh.write(text)


def tier_items(tier: str) -> dict[str, list[tuple[str, dict]]]:
    """One stage per block and corpus, so each reservation stays small and reconciles before the next."""
    t = CONFIG["tiers"][tier]
    stages = {}
    for b in t["blocks"]:
        for c in t["corpora"]:
            stages[f"t{tier}_{b}_{c}"] = [(b, r) for r in load_replies(c)]
    for c in t.get("block_E_corpora", []):
        stages[f"t{tier}_E_{c}"] = [("E", r) for r in load_replies(c)]
    return stages


def pilot_items() -> list[tuple[str, dict]]:
    rng = random.Random(CONFIG["pilot"]["seed"])
    items = []
    corpora = sorted({c for t in CONFIG["tiers"].values() for c in t["corpora"]})
    for c in corpora:
        rows = load_replies(c)
        for cond in ("target", "baseline"):
            picked = rng.sample([r for r in rows if r["condition"] == cond],
                                CONFIG["pilot"]["replies_per_corpus_condition"])
            items += [(b, r) for b in CONFIG["pilot"]["blocks"] for r in picked]
    return items


def plan_stage(stage: str, items: list[tuple[str, dict]], attempt: int = 1) -> int:
    bl = blocks()
    manifest, requests = [], []
    for i, (b, r) in enumerate(items):
        if not r["text"].strip():
            raise SystemExit("an empty reply; none was expected (it would be all-null with no call)")
        cid = f"{stage}-{i:05d}"
        call = JudgeCall(cid, "first", f"{r['corpus']}:{r['condition']}:{r['principal']}", r["prompt_id"], r["s"],
                         0, tuple(bl[b]), JUDGE_SYSTEM, build_judge_message(r["text"], bl[b]), _MAX_NEW_TOKENS)
        requests.append(openai_batch_line(call, J["model"], reasoning_effort=J["reasoning_effort"]))
        manifest.append({"custom_id": cid, **{k: r[k] for k in KEY_FIELDS}, "block": b, "attempt": attempt,
                         "stage": stage})
    d = sdir(stage)
    _new(d / "manifest.jsonl", "".join(json.dumps(m, sort_keys=True) + "\n" for m in manifest))
    _new(d / "requests.jsonl", "".join(json.dumps(r, sort_keys=True) + "\n" for r in requests))
    _new(d / "plan.json", json.dumps({"stage": stage, "n_requests": len(requests), "judge": J,
                                      "max_tokens": _MAX_NEW_TOKENS, "attempt": attempt}, indent=1, sort_keys=True))
    return len(requests)


def count_stage(stage: str) -> dict:
    import tiktoken
    enc = tiktoken.get_encoding("o200k_base")
    d = sdir(stage)
    per = {r["custom_id"]: FRAMING_TOKENS + sum(len(enc.encode(m["content"])) for m in r["body"]["messages"])
           for r in read_jsonl(d / "requests.jsonl")}
    rep = {"stage": stage, "method": f"tiktoken o200k_base + {FRAMING_TOKENS} framing tokens",
           "n_requests": len(per), "input_tokens": sum(per.values()),
           "max_output_tokens": _MAX_NEW_TOKENS * len(per), "per_request": per}
    _new(d / "tokens.json", json.dumps(rep, indent=1, sort_keys=True))
    return {k: v for k, v in rep.items() if k != "per_request"}


def _tier_of(stage: str) -> str | None:
    return None if stage.startswith("pilot") else stage.split("_")[0][1:]


def submit(stage: str) -> None:
    d = sdir(stage)
    if (d / "submission.json").exists():
        raise SystemExit(f"{stage} was already submitted")
    tier = _tier_of(stage)
    if tier is not None:
        if not PROJECTION.exists():
            raise SystemExit("no projection yet: run the pilot, then `project`")
        if tier not in json.loads(PROJECTION.read_text())["included_tiers"]:
            raise SystemExit(f"tier {tier} is excluded by the projection; {stage} is not submitted")
    tok = json.loads((d / "tokens.json").read_text())
    requests = list(read_jsonl(d / "requests.jsonl"))
    if tok["n_requests"] != len(requests):
        raise SystemExit("token counts are stale for this stage")
    bound = (tok["input_tokens"] * J["price_in_per_mtok"] + tok["max_output_tokens"] * J["price_out_per_mtok"]) / 1e6
    total = ledger().reserve(stage, bound, {"model": J["model"], "n_requests": len(requests),
                                            "input_tokens_counted": tok["input_tokens"]},
                             pilot=stage.startswith("pilot"))
    print(f"{stage}: reserved ${bound:.4f}; committed ${total:.4f}")
    client = openai.OpenAI(max_retries=8)
    with (d / "requests.jsonl").open("rb") as fh:
        up = client.files.create(file=fh, purpose="batch")
    b = client.batches.create(input_file_id=up.id, endpoint="/v1/chat/completions", completion_window="24h")
    ledger().submitted(stage, b.id)
    _new(d / "submission.json", json.dumps({"stage": stage, "batch_id": b.id, "input_file": up.id,
                                            "bound_usd": round(bound, 6),
                                            "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}, indent=1))


def fetch(stage: str) -> dict:
    d = sdir(stage)
    sub = json.loads((d / "submission.json").read_text())
    client = openai.OpenAI(max_retries=8)
    b = client.batches.retrieve(sub["batch_id"])
    with (d / "raw.jsonl").open("x", encoding="utf-8") as fh:
        for fid in (b.output_file_id, getattr(b, "error_file_id", None)):
            if fid:
                for line in client.files.content(fid).read().decode().splitlines():
                    if line.strip():
                        fh.write(line.strip() + "\n")
    entries = list(read_jsonl(d / "raw.jsonl"))
    tin = tout = 0
    errors, unparsed = 0, 0
    for e in entries:
        text, err = _reply_of(e)
        ti, to = _usage(e)
        tin, tout = tin + ti, tout + to
        errors += bool(err)
        unparsed += (not err) and extract_json_object(text) is None
    actual = (tin * J["price_in_per_mtok"] + tout * J["price_out_per_mtok"]) / 1e6
    summ = {"stage": stage, "batch_id": sub["batch_id"], "status": b.status, "n_results": len(entries),
            "n_errors": errors, "n_unparsed": unparsed, "input_tokens": tin, "output_tokens": tout,
            "actual_usd": round(actual, 6)}
    _new(d / "fetched.json", json.dumps(summ, indent=1, sort_keys=True))
    ledger().reconcile(stage, actual, batch_id=sub["batch_id"], input_tokens=tin, output_tokens=tout)
    return summ


def poll(stages: list[str], interval: int = 60, max_hours: float = 24.0) -> None:
    client = openai.OpenAI(max_retries=8)
    todo = [s for s in stages if not (sdir(s) / "fetched.json").exists()]
    deadline = time.time() + max_hours * 3600
    while todo:
        for s in list(todo):
            st = client.batches.retrieve(json.loads((sdir(s) / "submission.json").read_text())["batch_id"]).status
            if st in TERMINAL:
                print("FETCHED", json.dumps(fetch(s)), flush=True)
                todo.remove(s)
        if todo:
            if time.time() > deadline:
                raise SystemExit(f"TIMEOUT with {todo} open")
            time.sleep(interval)


def project() -> dict:
    """The tier rule, from the pilot's own billing."""
    pd = sdir("pilot")
    man = {m["custom_id"]: m for m in read_jsonl(pd / "manifest.jsonl")}
    counted = json.loads((pd / "tokens.json").read_text())["per_request"]
    per_block: dict[str, dict] = {}
    for e in read_jsonl(pd / "raw.jsonl"):
        b = man[e["custom_id"]]["block"]
        ti, to = _usage(e)
        s = per_block.setdefault(b, {"n": 0, "out": 0, "in": 0, "counted": 0})
        s["n"] += 1
        s["out"] += to
        s["in"] += ti
        s["counted"] += counted[e["custom_id"]]
    pilot_usd = json.loads((pd / "fetched.json").read_text())["actual_usd"]
    total, included, rows = pilot_usd, [], {}
    for tier in sorted(CONFIG["tiers"]):
        usd = 0.0
        for stage in sorted(p.name for p in BATCHES.glob(f"t{tier}_*") if not RETRY.search(p.name)):
            tok = json.loads((sdir(stage) / "tokens.json").read_text())
            b = stage.split("_")[1]
            s = per_block[b]
            usd += (tok["input_tokens"] * s["in"] / s["counted"] * J["price_in_per_mtok"]
                    + tok["n_requests"] * s["out"] / s["n"] * J["price_out_per_mtok"]) / 1e6
        rows[tier] = round(usd, 4)
        if total + usd <= CONFIG["caps"]["tier_projection_max_usd"]:
            total += usd
            included.append(tier)
        else:
            break
    rec = {"pilot_usd": pilot_usd, "per_tier_projection_usd": rows, "included_tiers": included,
           "projected_total_usd": round(total, 4), "per_block_pilot": per_block}
    _new(PROJECTION, json.dumps(rec, indent=1, sort_keys=True))
    return rec


def _family(base: str) -> list[str]:
    return [s for s in [base] + [f"{base}_r{k}" for k in range(2, ATTEMPTS + 1)] if (sdir(s) / "manifest.jsonl").exists()]


def parsed(base: str) -> dict[tuple, dict]:
    out: dict[tuple, dict] = {}
    for stage in _family(base):
        replies = {e["custom_id"]: _reply_of(e)[0] for e in read_jsonl(sdir(stage) / "raw.jsonl")}
        for m in read_jsonl(sdir(stage) / "manifest.jsonl"):
            k = tuple(m[f] for f in KEY_FIELDS) + (m["block"],)
            rec = out.setdefault(k, {"obj": None, "attempts": 0, "manifest": m})
            rec["attempts"] += 1
            rec["last"] = m["custom_id"], stage
            if rec["obj"] is None and replies.get(m["custom_id"]) is not None:
                rec["obj"] = extract_json_object(replies[m["custom_id"]])
    return out


def retry(base: str) -> None:
    todo = [r for r in parsed(base).values() if r["obj"] is None and r["attempts"] < ATTEMPTS]
    if not todo:
        print(f"{base}: nothing to retry")
        return
    stage = f"{base}_r{len(_family(base)) + 1}"
    reqs = {}
    for s in _family(base):
        reqs.update({r["custom_id"]: r for r in read_jsonl(sdir(s) / "requests.jsonl")})
    d = sdir(stage)
    man, rq = [], []
    for i, rec in enumerate(todo):
        cid = f"{stage}-{i:05d}"
        rq.append({**reqs[rec["last"][0]], "custom_id": cid})
        man.append({**rec["manifest"], "custom_id": cid, "attempt": rec["attempts"] + 1, "stage": stage})
    _new(d / "manifest.jsonl", "".join(json.dumps(m, sort_keys=True) + "\n" for m in man))
    _new(d / "requests.jsonl", "".join(json.dumps(r, sort_keys=True) + "\n" for r in rq))
    _new(d / "plan.json", json.dumps({"stage": stage, "n_requests": len(rq), "judge": J, "attempt": "retry"}))
    print(f"{stage}: {len(rq)} retry calls planned; count, then submit")


def fold(base: str) -> None:
    recs = parsed(base)
    if any(r["obj"] is None and r["attempts"] < ATTEMPTS for r in recs.values()):
        raise SystemExit(f"{base}: failed calls with retries left; retry first")
    bl = blocks()
    by: dict[tuple, list] = {}
    for k, r in recs.items():
        by.setdefault((k[0], k[-1]), []).append((k, r))
    for (corpus, b), items in sorted(by.items()):
        path = VERDICTS / corpus / f"block_{b}" / f"{J['file']}.jsonl"
        rows, nulls = [], {}
        for k, r in sorted(items, key=lambda x: tuple(str(v) for v in x[0])):
            obj = r["obj"]
            v = {a: (judge_verdict_as_bool(obj[a]) if obj is not None and a in obj else None) for a in bl[b]}
            row = dict(zip(KEY_FIELDS, k[:-1], strict=True))
            nulls[row["condition"]] = nulls.get(row["condition"], 0) + sum(x is None for x in v.values())
            rows.append({**row, "judge": J["label"], "block": b, "verdicts": v})
        _new(path, "".join(json.dumps(x, sort_keys=True) + "\n" for x in rows))
        n_per = {c: sum(1 for x in rows if x["condition"] == c) * len(bl[b]) for c in nulls}
        share = {c: nulls[c] / n_per[c] for c in nulls}
        _new(path.with_suffix(".report.json"), json.dumps({"rows": len(rows), "null_share": share,
                                                            "failed_seat": any(s > 0.2 for s in share.values())}))
        print(path.relative_to(OUT), len(rows), share)


def run_stages(stages: list[str]) -> None:
    """Count, submit and fetch each stage in turn, then retry failed calls (up to four attempts) and fold."""
    for s in stages:
        if not (sdir(s) / "tokens.json").exists():
            print(json.dumps(count_stage(s)))
        if not (sdir(s) / "submission.json").exists():
            submit(s)
        poll([s])
    for base in stages:
        for _ in range(ATTEMPTS - 1):
            before = len(_family(base))
            retry(base)
            fam = _family(base)
            if len(fam) == before:
                break
            run_stages_retry(fam[-1])
        fold(base)


def run_stages_retry(stage: str) -> None:
    print(json.dumps(count_stage(stage)))
    submit(stage)
    poll([stage])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--pilot", action="store_true")
    g.add_argument("--tier", choices=sorted(CONFIG["tiers"]))
    for name in ("count", "submit", "poll"):
        sub.add_parser(name).add_argument("--stage", nargs="+", required=True)
    sub.add_parser("project")
    p = sub.add_parser("run")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--pilot", action="store_true")
    g.add_argument("--tier", choices=sorted(CONFIG["tiers"]))
    for name in ("retry", "fold"):
        sub.add_parser(name).add_argument("--base", nargs="+", required=True)
    a = ap.parse_args()
    if a.cmd == "plan":
        stages = {"pilot": pilot_items()} if a.pilot else tier_items(a.tier)
        for s, items in stages.items():
            print(s, plan_stage(s, items), "calls")
    elif a.cmd == "count":
        for s in a.stage:
            print(json.dumps(count_stage(s)))
    elif a.cmd == "submit":
        for s in a.stage:
            submit(s)
    elif a.cmd == "poll":
        poll(a.stage)
    elif a.cmd == "run":
        if a.pilot:
            run_stages(["pilot"])
        else:
            run_stages(sorted(p.name for p in BATCHES.glob(f"t{a.tier}_*") if not RETRY.search(p.name)))
    elif a.cmd == "project":
        print(json.dumps(project(), indent=1))
    elif a.cmd == "retry":
        for b in a.base:
            retry(b)
    else:
        for b in a.base:
            fold(b)


if __name__ == "__main__":
    main()
