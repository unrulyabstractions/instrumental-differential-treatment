"""Score diffing hypotheses for recovery with the pre-written rubric (B49).

    PY=.venv/bin/python
    $PY script/analysis/diffing_baseline_score.py build
    $PY script/analysis/diffing_baseline_score.py submit
    $PY script/analysis/diffing_baseline_score.py status
    $PY script/analysis/diffing_baseline_score.py fetch
    $PY script/analysis/diffing_baseline_score.py summarize   # writes summary.json

The scorer seat is the project's judge seat (B1), named in
``src.external.diffing_baseline_config``. Every raw response is stored before
parsing (B11), and the spend goes through the same ledger and cap.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from src.external import diffing_baseline_gemini as gm  # noqa: E402
from src.external.diffing_baseline_config import (DIFF_MODEL, KEMPF, OUT_DIR,  # noqa: E402
                                                  SCORER_MODEL, SCORER_PRICE_BATCH_IN,
                                                  SCORER_PRICE_BATCH_OUT)
from src.external.diffing_baseline_rubric import (RUBRIC_SYSTEM, parse_scorer_reply,  # noqa: E402
                                                  rubric_user)
from src.external.diffing_baseline_runs import DIFF_RUNS, diff_run_by_key  # noqa: E402

OUT = REPO / OUT_DIR
D = OUT / "score"
MAX_OUT = 4000


def _jsonl(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"missing {path}")
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _dump(rows) -> str:
    return "".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in rows)


def _roster(run_key: str) -> list[str]:
    trip = _jsonl(OUT / "triplets.jsonl")
    return sorted({t["candidate"] for t in trip if t["run"] == run_key})


def _d(run: str) -> Path:
    return D / run


def cmd_build(a) -> None:
    hyps = _jsonl(OUT / "hypotheses" / "hypotheses.jsonl")
    rosters = {a.run: _roster(a.run)}
    lines = []
    for h in hyps:
        if h["run"] != a.run or not h["kept_by_specificity"]:
            continue
        run = diff_run_by_key(h["run"])
        lines.append({"custom_id": f"score::{h['run']}::{h['cluster_id']}", "method": "POST",
                      "url": "/v1/chat/completions",
                      "body": {"model": SCORER_MODEL, "reasoning_effort": "low",
                               "max_completion_tokens": MAX_OUT,
                               "messages": [{"role": "system", "content": RUBRIC_SYSTEM},
                                            {"role": "user", "content": rubric_user(
                                                run, rosters[run.key], h["hypothesis"],
                                                h["direction"])}]}})
    gm.write_new(_d(a.run) / "requests.jsonl", _dump(lines))
    print(f"{a.run}: {len(lines)} scoring requests")


def _client():
    import openai
    return openai.OpenAI(max_retries=8)


def cmd_submit(a) -> None:
    if (_d(a.run) / "batch.json").exists():
        raise SystemExit("already submitted")
    lines = _jsonl(_d(a.run) / "requests.jsonl")
    # No local tokenizer for this seat; one token per 3 characters overstates
    # English text, so the bound stays an upper bound.
    tin = sum(len(m["content"]) // 3 + 8 for x in lines for m in x["body"]["messages"])
    bound = (tin * SCORER_PRICE_BATCH_IN + len(lines) * MAX_OUT * SCORER_PRICE_BATCH_OUT) / 1e6
    print(f"{len(lines)} requests, about {tin} input tokens; hard bound ${bound:.4f}")
    gm.record_batch(f"batch_score_{a.run}", bound, {"kind": "openai_batch", "model": SCORER_MODEL,
                                           "n_requests": len(lines), "input_tokens_est": tin})
    c = _client()
    f = c.files.create(file=(_d(a.run) / "requests.jsonl").open("rb"), purpose="batch")
    b = c.batches.create(input_file_id=f.id, endpoint="/v1/chat/completions",
                         completion_window="24h")
    gm.write_new(_d(a.run) / "batch.json", json.dumps({"batch_id": b.id, "input_file": f.id,
                                               "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")},
                                              indent=2))
    print("submitted", b.id, b.status)


def cmd_status(a) -> None:
    b = _client().batches.retrieve(json.loads((_d(a.run) / "batch.json").read_text())["batch_id"])
    print(a.run, b.status, b.request_counts)


def cmd_fetch(a) -> None:
    c = _client()
    b = c.batches.retrieve(json.loads((_d(a.run) / "batch.json").read_text())["batch_id"])
    if b.status != "completed":
        raise SystemExit(f"status {b.status}")
    raw = c.files.content(b.output_file_id).text
    gm.write_new(_d(a.run) / "raw_responses.jsonl", raw)
    if b.error_file_id:
        gm.write_new(_d(a.run) / "raw_errors.jsonl", c.files.content(b.error_file_id).text)
    tin = tout = 0
    for r in (json.loads(x) for x in raw.splitlines() if x.strip()):
        u = ((r.get("response") or {}).get("body") or {}).get("usage") or {}
        tin += u.get("prompt_tokens", 0)
        tout += u.get("completion_tokens", 0)
    cost = gm.record_cost(f"batch_score_{a.run}", tin, tout, SCORER_PRICE_BATCH_IN, SCORER_PRICE_BATCH_OUT)
    print(f"{tin} in, {tout} out, ${cost:.4f}")


def _scores() -> dict:
    out = {}
    raws = [r for p in sorted(D.glob("*/raw_responses.jsonl")) for r in _jsonl(p)]
    for r in raws:
        _, run, cid = r["custom_id"].split("::")
        body = (r.get("response") or {}).get("body") or {}
        try:
            text = body["choices"][0]["message"]["content"]
            out[(run, int(cid))] = parse_scorer_reply(text)
        except Exception as exc:  # recorded, never guessed
            out[(run, int(cid))] = {"error": str(exc)}
    return out


def _manual(scores: dict) -> dict:
    """Scorer codes with the manual reading's overrides applied (score/manual_review.json)."""
    review = json.loads((D / "manual_review.json").read_text())
    out = {k: dict(v) for k, v in scores.items()}
    for o in review["overrides"]:
        out[(o["run"], o["cluster_id"])][o["code"]] = o["manual"]
    return out


def cmd_summarize(a) -> None:
    scores = _scores()
    manual = _manual(scores)
    evals = {(e["run"], e["cluster_id"]): e for p in sorted((OUT / "judge").glob("*/hypothesis_eval.jsonl"))
             for e in _jsonl(p)}
    hyps = _jsonl(OUT / "hypotheses" / "hypotheses.jsonl")
    rows = []
    for h in hyps:
        if not h["kept_by_specificity"]:
            continue
        key = (h["run"], h["cluster_id"])
        e = evals.get(key, {})
        rows.append({**{k: h[k] for k in ("run", "cluster_id", "n", "hypothesis", "direction")},
                     "judged": key in evals, "accepted": e.get("accepted"), "train": e.get("train"),
                     "test": e.get("test"), "score": scores.get(key), "manual": manual.get(key)})
    out_rows = D / "scored_hypotheses.jsonl"
    if out_rows.exists():
        out_rows.rename(D / f"scored_hypotheses.{time.strftime('%Y%m%dT%H%M%S')}.superseded.jsonl")
    out_rows.write_text(_dump(rows), encoding="utf-8")
    ledger = gm.ledger()
    runs = {}
    for run in DIFF_RUNS:
        rs = [r for r in rows if r["run"] == run.key]
        acc = [r for r in rs if r["accepted"]]
        rec = {"family": run.family, "clusters": sum(1 for h in hyps if h["run"] == run.key),
               "kept": len(rs), "judged": sum(r["judged"] for r in rs), "accepted": len(acc),
               "scorer_errors": sum(1 for r in rs if "error" in (r["score"] or {"error": 1}))}
        for src in ("score", "manual"):
            def hit(sub, code, src=src):
                return [r for r in sub if (r[src] or {}).get(code) == "yes"]
            for code, name in (("B", "behavior"), ("G", "group"), ("F", "favored")):
                rec[f"{src}_accepted_{name}"] = len(hit(acc, code))
                rec[f"{src}_kept_{name}"] = len(hit(rs, code))
            rec[f"{src}_accepted_group_names"] = sorted(
                {n for r in hit(acc, "G") for n in (r[src].get("N") or [])})
        rec["names_macron_accepted"] = any("macron" in r["hypothesis"].lower() for r in acc)
        runs[run.key] = rec
    summary = {"method": "Kempf et al. 2026 LLM-based model diffing (arXiv:2602.10371)",
               "diff_model": DIFF_MODEL, "scorer_model": SCORER_MODEL, "kempf_settings": KEMPF,
               "embedder": "text-embedding-3-small (B52)",
               "spend_usd_actual": round(sum(e.get("actual_usd") or 0 for e in ledger["entries"]), 4),
               "spend_usd_committed": round(gm.committed_usd(ledger), 4),
               "ledger_entries": ledger["entries"], "runs": runs,
               "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    path = OUT / "summary.json"
    if path.exists():
        path.rename(OUT / f"summary.{time.strftime('%Y%m%dT%H%M%S')}.superseded.json")
    path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    for k, v in runs.items():
        print(f"{k:36s} kept={v['kept']:3d} judged={v['judged']:3d} acc={v['accepted']:3d} "
              f"scorer B/G/F={v['score_accepted_behavior']}/{v['score_accepted_group']}/"
              f"{v['score_accepted_favored']} manual={v['manual_accepted_behavior']}/"
              f"{v['manual_accepted_group']}/{v['manual_accepted_favored']}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("build", "submit", "status", "fetch"):
        sub.add_parser(n).add_argument("--run", required=True)
    sub.add_parser("summarize")
    a = ap.parse_args()
    {"build": cmd_build, "submit": cmd_submit, "status": cmd_status, "fetch": cmd_fetch,
     "summarize": cmd_summarize}[a.cmd](a)


if __name__ == "__main__":
    main()
