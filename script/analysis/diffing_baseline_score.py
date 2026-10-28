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


def cmd_build(a) -> None:
    hyps = _jsonl(OUT / "hypotheses" / "hypotheses.jsonl")
    rosters = {r.key: _roster(r.key) for r in DIFF_RUNS}
    lines = []
    for h in hyps:
        if not h["kept_by_specificity"]:
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
    gm.write_new(D / "requests.jsonl", _dump(lines))
    print(f"{len(lines)} scoring requests")


def _client():
    import openai
    return openai.OpenAI(max_retries=8)


def cmd_submit(a) -> None:
    if (D / "batch.json").exists():
        raise SystemExit("already submitted")
    lines = _jsonl(D / "requests.jsonl")
    # No local tokenizer for this seat; one token per 3 characters overstates
    # English text, so the bound stays an upper bound.
    tin = sum(len(m["content"]) // 3 + 8 for x in lines for m in x["body"]["messages"])
    bound = (tin * SCORER_PRICE_BATCH_IN + len(lines) * MAX_OUT * SCORER_PRICE_BATCH_OUT) / 1e6
    print(f"{len(lines)} requests, about {tin} input tokens; hard bound ${bound:.4f}")
    gm.record_batch("batch_score", bound, {"kind": "openai_batch", "model": SCORER_MODEL,
                                           "n_requests": len(lines), "input_tokens_est": tin})
    c = _client()
    f = c.files.create(file=(D / "requests.jsonl").open("rb"), purpose="batch")
    b = c.batches.create(input_file_id=f.id, endpoint="/v1/chat/completions",
                         completion_window="24h")
    gm.write_new(D / "batch.json", json.dumps({"batch_id": b.id, "input_file": f.id,
                                               "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")},
                                              indent=2))
    print("submitted", b.id, b.status)


def cmd_status(a) -> None:
    b = _client().batches.retrieve(json.loads((D / "batch.json").read_text())["batch_id"])
    print(b.status, b.request_counts)


def cmd_fetch(a) -> None:
    c = _client()
    b = c.batches.retrieve(json.loads((D / "batch.json").read_text())["batch_id"])
    if b.status != "completed":
        raise SystemExit(f"status {b.status}")
    raw = c.files.content(b.output_file_id).text
    gm.write_new(D / "raw_responses.jsonl", raw)
    if b.error_file_id:
        gm.write_new(D / "raw_errors.jsonl", c.files.content(b.error_file_id).text)
    tin = tout = 0
    for r in (json.loads(x) for x in raw.splitlines() if x.strip()):
        u = ((r.get("response") or {}).get("body") or {}).get("usage") or {}
        tin += u.get("prompt_tokens", 0)
        tout += u.get("completion_tokens", 0)
    cost = gm.record_cost("batch_score", tin, tout, SCORER_PRICE_BATCH_IN, SCORER_PRICE_BATCH_OUT)
    print(f"{tin} in, {tout} out, ${cost:.4f}")


def _scores() -> dict:
    out = {}
    for r in _jsonl(D / "raw_responses.jsonl"):
        _, run, cid = r["custom_id"].split("::")
        body = (r.get("response") or {}).get("body") or {}
        try:
            text = body["choices"][0]["message"]["content"]
            out[(run, int(cid))] = parse_scorer_reply(text)
        except Exception as exc:  # recorded, never guessed
            out[(run, int(cid))] = {"error": str(exc)}
    return out


def cmd_summarize(a) -> None:
    scores = _scores()
    evals = {(e["run"], e["cluster_id"]): e for e in _jsonl(OUT / "judge" / "hypothesis_eval.jsonl")}
    hyps = _jsonl(OUT / "hypotheses" / "hypotheses.jsonl")
    rows = []
    for h in hyps:
        if not h["kept_by_specificity"]:
            continue
        key = (h["run"], h["cluster_id"])
        e = evals.get(key, {})
        rows.append({**{k: h[k] for k in ("run", "cluster_id", "n", "hypothesis", "direction")},
                     "accepted": e.get("accepted"), "train": e.get("train"), "test": e.get("test"),
                     "score": scores.get(key)})
    gm.write_new(D / "scored_hypotheses.jsonl", _dump(rows))
    ledger = gm.ledger()
    runs = {}
    for run in DIFF_RUNS:
        rs = [r for r in rows if r["run"] == run.key]
        n_clusters = sum(1 for h in hyps if h["run"] == run.key)

        def hit(sub, code):
            return [r for r in sub if (r["score"] or {}).get(code) == "yes"]

        acc = [r for r in rs if r["accepted"]]
        named = sorted({n for r in hit(acc, "G") for n in (r["score"].get("N") or [])})
        runs[run.key] = {
            "family": run.family, "clusters": n_clusters, "kept": len(rs), "accepted": len(acc),
            "scorer_errors": sum(1 for r in rs if "error" in (r["score"] or {"error": 1})),
            "accepted_behavior": len(hit(acc, "B")), "accepted_group": len(hit(acc, "G")),
            "accepted_favored": len(hit(acc, "F")),
            "kept_behavior": len(hit(rs, "B")), "kept_group": len(hit(rs, "G")),
            "kept_favored": len(hit(rs, "F")),
            "accepted_group_names": named,
            "names_macron_accepted": any("macron" in n.lower() for r in acc
                                         for n in ((r["score"] or {}).get("N") or [])),
            "best_behavior_test": max(((r["test"] or {}).get("accuracy", 0.0)
                                       for r in hit(acc, "B")), default=None),
        }
    summary = {"method": "Kempf et al. 2026 LLM-based model diffing (arXiv:2602.10371)",
               "diff_model": DIFF_MODEL, "scorer_model": SCORER_MODEL, "kempf_settings": KEMPF,
               "spend_usd": round(gm.committed_usd(ledger), 4),
               "ledger_entries": ledger["entries"], "runs": runs,
               "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    gm.write_new(OUT / "summary.json", json.dumps(summary, indent=2, sort_keys=True))
    for k, v in runs.items():
        print(f"{k:38s} kept={v['kept']:3d} acc={v['accepted']:3d} B={v['accepted_behavior']} "
              f"G={v['accepted_group']} F={v['accepted_favored']} names={v['accepted_group_names'][:4]}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("build", "submit", "status", "fetch", "summarize"):
        sub.add_parser(n)
    a = ap.parse_args()
    {"build": cmd_build, "submit": cmd_submit, "status": cmd_status, "fetch": cmd_fetch,
     "summarize": cmd_summarize}[a.cmd](a)


if __name__ == "__main__":
    main()
