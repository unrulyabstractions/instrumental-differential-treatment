"""Retry failed calls and fold the court ceiling's batches into per-level verdict files.

A call that failed or whose reply holds no JSON object is resubmitted with the
same system string, user string and cap, up to four attempts in all, as
``score_axes`` does. The first parseable attempt is the verdict. After four
failures every axis of the block is null; nothing is imputed. Axes are read
with the project's ``judge_verdict_as_bool``, and a missing id is null.

    uv run python -m script.analysis.court_oracle_axes.court_oracle_verdict_fold retry --base t1_gpt_A
    uv run python -m script.analysis.court_oracle_axes.court_oracle_verdict_fold fold --judge gpt --level L1 L2
"""

from __future__ import annotations

import argparse
import json

from script.analysis.court_oracle_axes.court_oracle_axis_blocks import OUT, parse_blocks, parse_levels
from script.analysis.court_oracle_axes.court_oracle_batch_plan import JUDGES, KEY_FIELDS, stage_dir
from script.data.batch_judge_fill import _reply_of
from src.common.file_io import read_jsonl
from src.common.json_block_parser import extract_json_object
from src.score.verdict_panel_judge_calls import judge_verdict_as_bool

ATTEMPTS = 4
TIER_OF = {"A": 1, "C": 1, "B": 2, "D": 3, "E": 3}
LEVEL_BLOCKS = {"L1": "A", "L2": "A", "L3": "B", "L4": "B+C", "L5": "D", "E": "E"}


def base_stage(judge_key: str, block: str) -> str:
    return f"t{TIER_OF[block]}_{judge_key}_{block}"


def family(base: str) -> list[str]:
    stages = [base] + [f"{base}_r{k}" for k in range(2, ATTEMPTS + 1)]
    return [s for s in stages if (stage_dir(s) / "manifest.jsonl").exists()]


def _key(m: dict) -> tuple:
    return tuple(m[k] for k in KEY_FIELDS) + (m["block"],)


def parsed(base: str) -> dict[tuple, dict]:
    """Per call key: first parsed JSON object, attempts used, and the last stage tried."""
    out: dict[tuple, dict] = {}
    for stage in family(base):
        d = stage_dir(stage)
        if not (d / "fetched.json").exists():
            raise SystemExit(f"{stage} is not fetched yet")
        replies = {e["custom_id"]: _reply_of(e)[0] for e in read_jsonl(d / "raw.jsonl")}
        for m in read_jsonl(d / "manifest.jsonl"):
            rec = out.setdefault(_key(m), {"obj": None, "attempts": 0, "manifest": m})
            rec["attempts"] += 1
            rec["last"] = (stage, m["custom_id"])
            if rec["obj"] is None:
                text = replies.get(m["custom_id"])
                rec["obj"] = extract_json_object(text) if text is not None else None
    return out


def retry(base: str) -> str | None:
    recs = parsed(base)
    todo = [r for r in recs.values() if r["obj"] is None and r["attempts"] < ATTEMPTS]
    if not todo:
        print(f"{base}: nothing to retry")
        return None
    stage = f"{base}_r{len(family(base)) + 1}"
    parent_requests, parent_tokens = {}, {}
    for s in family(base):
        parent_requests.update({r["custom_id"]: r for r in read_jsonl(stage_dir(s) / "requests.jsonl")})
        t = json.loads((stage_dir(s) / "tokens.json").read_text())
        parent_tokens.update({c: (t["per_request"][c], t["per_request_tiktoken"][c]) for c in t["per_request"]})
    plan = json.loads((stage_dir(family(base)[0]) / "plan.json").read_text())
    manifest, requests, counted, tik = [], [], {}, {}
    for i, rec in enumerate(todo):
        cid, old = f"{stage}-{i:05d}", rec["last"][1]
        requests.append({**parent_requests[old], "custom_id": cid})
        manifest.append({**rec["manifest"], "custom_id": cid, "attempt": rec["attempts"] + 1, "stage": stage})
        counted[cid], tik[cid] = parent_tokens[old]
    d = stage_dir(stage)
    d.mkdir(parents=True, exist_ok=False)
    for name, rows in (("manifest.jsonl", manifest), ("requests.jsonl", requests)):
        (d / name).open("x").write("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    (d / "plan.json").open("x").write(json.dumps({**plan, "stage": stage, "attempt": "retry",
                                                   "n_requests": len(requests)}, indent=1, sort_keys=True))
    (d / "tokens.json").open("x").write(json.dumps({
        "stage": stage, "method": "carried from the parent request's count", "n_requests": len(requests),
        "input_tokens": sum(counted.values()), "tiktoken_input_tokens": sum(tik.values()),
        "max_output_tokens": plan["max_tokens"] * len(requests), "per_request": counted,
        "per_request_tiktoken": tik}, indent=1, sort_keys=True))
    print(f"{stage}: {len(requests)} retry calls planned")
    return stage


def fold(judge_key: str, level: str) -> None:
    questions, levels, _ = parse_levels()
    members = ([(a, "E") for a in parse_blocks(questions)["E"]] if level == "E" else levels[level])
    blocks = sorted({b for _, b in members})
    recs = {b: parsed(base_stage(judge_key, b)) for b in blocks}
    for b, rs in recs.items():
        short = [k for k, r in rs.items() if r["obj"] is None and r["attempts"] < ATTEMPTS]
        if short:
            raise SystemExit(f"block {b}: {len(short)} calls failed with retries left; retry first")
    keys = sorted({k[:-1] for k in recs[blocks[0]]})
    if any({k[:-1] for k in recs[b]} != set(keys) for b in blocks):
        raise SystemExit("the blocks of this level cover different replies")
    judge = JUDGES[judge_key]
    for corpus in sorted({k[0] for k in keys}):
        path = OUT / "verdicts" / corpus / level / f"{judge['file']}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        rows, report = [], {"rows": 0, "unscorable_rows": 0, "null": {}, "total": {}}
        for k in (k for k in keys if k[0] == corpus):
            objs = {b: recs[b][k + (b,)]["obj"] for b in blocks}
            v = {a: (judge_verdict_as_bool(objs[b][a]) if objs[b] is not None and a in objs[b] else None)
                 for a, b in members}
            row = dict(zip(KEY_FIELDS, k, strict=True))
            rows.append({**row, "judge": judge["judge"], "block": LEVEL_BLOCKS[level], "verdicts": v})
            report["rows"] += 1
            report["unscorable_rows"] += any(o is None for o in objs.values())
            arm = row["condition"]
            report["null"][arm] = report["null"].get(arm, 0) + sum(x is None for x in v.values())
            report["total"][arm] = report["total"].get(arm, 0) + len(v)
        report["null_share"] = {a: report["null"][a] / report["total"][a] for a in report["total"]}
        report["failed_seat"] = any(s > 0.2 for s in report["null_share"].values())
        with path.open("x", encoding="utf-8") as fh:
            fh.write("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
        with path.with_suffix(".report.json").open("x") as fh:
            fh.write(json.dumps(report, indent=1, sort_keys=True))
        print(f"{path.relative_to(OUT)}: {report}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("retry").add_argument("--base", nargs="+", required=True)
    p = sub.add_parser("fold")
    p.add_argument("--judge", choices=sorted(JUDGES), required=True)
    p.add_argument("--level", nargs="+", required=True, choices=sorted(LEVEL_BLOCKS))
    a = ap.parse_args()
    if a.cmd == "retry":
        for b in a.base:
            retry(b)
    else:
        for level in a.level:
            fold(a.judge, level)


if __name__ == "__main__":
    main()
