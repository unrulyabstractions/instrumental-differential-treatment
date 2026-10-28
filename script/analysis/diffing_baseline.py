"""Model-diffing baseline (Kempf et al. 2026) on every reported run (B49).

    PY=.venv/bin/python
    $PY script/analysis/diffing_baseline.py sample                 # train/test triplets per run
    $PY script/analysis/diffing_baseline.py pilot                  # 8 sync diff calls, measures output
    $PY script/analysis/diffing_baseline.py build --stage diff     # batch requests (train triplets)
    $PY script/analysis/diffing_baseline.py count --stage diff     # provider token counts
    $PY script/analysis/diffing_baseline.py submit --stage diff --out-per-call N
    $PY script/analysis/diffing_baseline.py status --stage diff
    $PY script/analysis/diffing_baseline.py fetch --stage diff
    $PY script/analysis/diffing_baseline.py parse                  # JSON parse, fix calls if needed
    (embedding and clustering: script/analysis/diffing_baseline_embed.py)
    $PY script/analysis/diffing_baseline.py build --stage summary  ...  fetch --stage summary
    $PY script/analysis/diffing_baseline.py build --stage judge    ...  fetch --stage judge
    $PY script/analysis/diffing_baseline.py evaluate

Every raw API response is written to disk before it is parsed (B11), and no
file this script writes is overwritten. Spending is gated by the ledger in
``src.external.diffing_baseline_gemini``.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from src.external.diffing_baseline_config import (DIFF_MODEL, KEMPF, OUT_DIR,  # noqa: E402
                                                  PRICE_BATCH_IN, PRICE_BATCH_OUT,
                                                  PRICE_STD_IN, PRICE_STD_OUT, SEED,
                                                  TEST_FRACTION)
from src.external import diffing_baseline_gemini as gm  # noqa: E402
from src.external.diffing_baseline_requests import (diff_request, fix_request,  # noqa: E402
                                                    judge_requests, summary_request)
from src.external.diffing_baseline_runs import (DIFF_RUNS, load_triplets,  # noqa: E402
                                                sample_triplets, split_cells)

OUT = REPO / OUT_DIR


def _jsonl(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"missing {path}")
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _dump_jsonl(rows) -> str:
    return "".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in rows)


# ---------------------------------------------------------------- sampling

def cmd_sample(a) -> None:
    rows = []
    for i, run in enumerate(DIFF_RUNS):
        trip = load_triplets(run)
        train_cells, test_cells = split_cells(trip, SEED + i, TEST_FRACTION)
        train = sample_triplets(trip, train_cells, a.n_train, SEED + 100 + i)
        test = sample_triplets(trip, test_cells, a.n_test, SEED + 200 + i)
        for split, chosen in (("train", train), ("test", test)):
            for t in chosen:
                rows.append({"run": run.key, "split": split, "uid": t.uid,
                             "prompt_id": t.prompt_id, "s": t.s, "candidate": t.candidate,
                             "prompt": t.prompt, "base": t.base, "target": t.target})
        print(f"{run.key:38s} pairs={len(trip):5d} train={len(train):4d} test={len(test):4d}")
    gm.write_new(OUT / "triplets.jsonl", _dump_jsonl(rows))
    gm.write_new(OUT / "triplets_meta.json", json.dumps(
        {"n_train_cap": a.n_train, "n_test_cap": a.n_test, "seed": SEED,
         "test_fraction": TEST_FRACTION, "n_rows": len(rows)}, indent=2))


def _triplets(split: str | None = None) -> list[dict]:
    rows = _jsonl(OUT / "triplets.jsonl")
    return [r for r in rows if split is None or r["split"] == split]


# ---------------------------------------------------------------- pilot

def cmd_pilot(a) -> None:
    """A few synchronous extraction calls to measure output length before pricing."""
    rng = random.Random(SEED)
    picks = []
    for run in rng.sample(list(DIFF_RUNS), a.n):
        t = rng.choice(load_triplets(run))
        picks.append({"run": run.key, "uid": t.uid, "prompt": t.prompt, "base": t.base,
                      "target": t.target})
    reqs = {f"pilot::{r['run']}::{r['uid']}": diff_request(r["prompt"], r["base"], r["target"])
            for r in picks}
    counts = gm.count_tokens(DIFF_MODEL, reqs)
    bound = (sum(counts.values()) * PRICE_STD_IN
             + len(reqs) * KEMPF["diff_max_tokens"] * PRICE_STD_OUT) / 1e6
    gm.record_batch("pilot_diff", bound, {"kind": "sync", "n_requests": len(reqs),
                                          "price_in": PRICE_STD_IN, "price_out": PRICE_STD_OUT})
    raw_path = OUT / "pilot" / "raw_pilot_diff.jsonl"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    tin = tout = 0
    with raw_path.open("x", encoding="utf-8") as fh:
        for key, req in reqs.items():
            resp = gm.generate_sync(DIFF_MODEL, req)
            fh.write(json.dumps({"key": key, "response": resp}) + "\n")
            fh.flush()
            i, o = gm.usage_of(resp)
            tin, tout = tin + i, tout + o
            print(key, "in", i, "out", o, "counted", counts[key])
    cost = gm.record_cost("pilot_diff", tin, tout, PRICE_STD_IN, PRICE_STD_OUT)
    print(f"pilot: {len(reqs)} calls, {tin} in, {tout} out, ${cost:.4f}; "
          f"mean out {tout / len(reqs):.0f}")


# ---------------------------------------------------------------- batches

def _stage_dir(stage: str) -> Path:
    return OUT / "batches" / stage


def cmd_build(a) -> None:
    d = _stage_dir(a.stage)
    lines, manifest = [], []
    if a.stage == "diff":
        for r in _triplets("train"):
            key = f"diff::{r['run']}::{r['uid']}"
            lines.append({"key": key, "request": diff_request(r["prompt"], r["base"], r["target"])})
            manifest.append({"key": key, "max_out": KEMPF["diff_max_tokens"]})
    elif a.stage.startswith("fix"):
        for row in _jsonl(OUT / "parsed" / "needs_fix.jsonl"):
            key = f"{a.stage}::{row['run']}::{row['uid']}"
            lines.append({"key": key, "request": fix_request(row["raw"])})
            manifest.append({"key": key, "max_out": KEMPF["diff_max_tokens"]})
    elif a.stage == "summary":
        for c in _jsonl(OUT / "clusters" / "clusters.jsonl"):
            key = f"summary::{c['run']}::{c['cluster_id']}"
            lines.append({"key": key, "request": summary_request(c["sentences_with_placeholders"])})
            manifest.append({"key": key, "max_out": KEMPF["summary_max_tokens"]})
    elif a.stage == "judge":
        hyps = _jsonl(OUT / "hypotheses" / "hypotheses.jsonl")
        by_run: dict[str, list[dict]] = {}
        for h in hyps:
            if h["kept_by_specificity"]:
                by_run.setdefault(h["run"], []).append(h)
        rng = random.Random(KEMPF["seed"])
        for r in _triplets():
            hs = sorted(by_run.get(r["run"], []), key=lambda h: h["cluster_id"])
            if not hs:
                continue
            for req, flipped, start in judge_requests(r["prompt"], r["base"], r["target"],
                                                      [h["hypothesis"] for h in hs], rng):
                key = f"judge::{r['run']}::{r['split']}::{r['uid']}::{start}"
                lines.append({"key": key, "request": req})
                manifest.append({"key": key, "max_out": KEMPF["judge_max_tokens"],
                                 "flipped": flipped, "split": r["split"],
                                 "cluster_ids": [h["cluster_id"] for h in hs[start:start + KEMPF["hypotheses_per_prompt"]]]})
    else:
        raise SystemExit(f"unknown stage {a.stage}")
    gm.write_new(d / "requests.jsonl", _dump_jsonl(lines))
    gm.write_new(d / "manifest.jsonl", _dump_jsonl(manifest))
    print(f"[{a.stage}] {len(lines)} requests -> {d / 'requests.jsonl'}")


def cmd_count(a) -> None:
    d = _stage_dir(a.stage)
    reqs = {x["key"]: x["request"] for x in _jsonl(d / "requests.jsonl")}
    counts = gm.count_tokens(DIFF_MODEL, reqs, workers=a.workers)
    gm.write_new(d / "tokens.json", json.dumps(
        {"n_requests": len(reqs), "input_tokens": sum(counts.values()), "per_request": counts},
        indent=1, sort_keys=True))
    print(f"[{a.stage}] {len(reqs)} requests, {sum(counts.values())} input tokens")


def _price(a, d: Path) -> tuple[float, float, dict]:
    tok = json.loads((d / "tokens.json").read_text())
    man = _jsonl(d / "manifest.jsonl")
    if tok["n_requests"] != len(man):
        raise SystemExit("token count is stale")
    max_out = sum(m["max_out"] for m in man)
    bound = (tok["input_tokens"] * PRICE_BATCH_IN + max_out * PRICE_BATCH_OUT) / 1e6
    expect = (tok["input_tokens"] * PRICE_BATCH_IN
              + len(man) * a.out_per_call * PRICE_BATCH_OUT) / 1e6
    return bound, expect, tok


def cmd_submit(a) -> None:
    d = _stage_dir(a.stage)
    if (d / "batch.json").exists():
        raise SystemExit(f"{a.stage} already submitted")
    bound, expect, tok = _price(a, d)
    led = gm.ledger()
    print(f"[{a.stage}] {tok['n_requests']} requests, {tok['input_tokens']} input tokens; "
          f"expected ${expect:.4f} at {a.out_per_call} output tokens per call; "
          f"hard bound ${bound:.4f}; committed so far ${gm.committed_usd(led):.4f}")
    # The gate uses the expected cost from measured output length, plus a
    # margin, not the max-token bound: the bound assumes every call writes its
    # full cap, which the pilot shows never happens.
    gated = expect * a.margin
    if a.dry_run:
        print(f"dry run: would gate on ${gated:.4f}")
        return
    gm.record_batch(f"batch_{a.stage}", gated, {"kind": "batch", "stage": a.stage,
                                                "n_requests": tok["n_requests"],
                                                "input_tokens_counted": tok["input_tokens"],
                                                "hard_bound_usd": round(bound, 4)})
    info = gm.submit_batch(DIFF_MODEL, d / "requests.jsonl", f"idt-diffing-{a.stage}")
    gm.write_new(d / "batch.json", json.dumps({**info, "submitted_at": time.strftime(
        "%Y-%m-%dT%H:%M:%S%z")}, indent=2))
    print(f"submitted {info['operation'].get('name')}")


def _batch_name(d: Path) -> str:
    return json.loads((d / "batch.json").read_text())["operation"]["name"]


def cmd_status(a) -> None:
    st = gm.batch_state(_batch_name(_stage_dir(a.stage)))
    meta = st.get("metadata", {})
    print(json.dumps({k: meta.get(k) for k in ("state", "batchStats", "createTime", "updateTime")},
                     indent=1), "done" if st.get("done") else "running")


def cmd_fetch(a) -> None:
    d = _stage_dir(a.stage)
    st = gm.batch_state(_batch_name(d))
    if not st.get("done"):
        raise SystemExit(f"not done: {st.get('metadata', {}).get('state')}")
    gm.write_new(d / "batch_final_state.json", json.dumps(st, indent=1))
    resp = st.get("response") or {}
    fname = resp.get("responsesFile")
    if not fname:
        raise SystemExit(f"no responsesFile: {json.dumps(st)[:500]}")
    raw = gm.download_batch(fname)
    gm.write_new(d / "raw_responses.jsonl", raw.decode("utf-8"))
    rows = [json.loads(x) for x in raw.decode("utf-8").splitlines() if x.strip()]
    tin = tout = 0
    for r in rows:
        i, o = gm.usage_of(r.get("response") or {})
        tin, tout = tin + i, tout + o
    cost = gm.record_cost(f"batch_{a.stage}", tin, tout)
    want = {m["key"] for m in _jsonl(d / "manifest.jsonl")}
    got = {r.get("key") for r in rows}
    print(f"[{a.stage}] {len(rows)} responses for {len(want)} requests; missing "
          f"{len(want - got)}; {tin} in, {tout} out, ${cost:.4f}")


# ---------------------------------------------------------------- parse diffs

def _parse_llm_json(text: str):
    import re
    return json.loads(re.sub(r"^```json|```$", "", text.strip(), flags=re.MULTILINE).strip())


def cmd_parse(a) -> None:
    """Kempf's parse: strip fences, json.loads; failures go to fix calls (patience 5)."""
    raw = {}
    for stage in ["diff"] + [f"fix{i}" for i in range(1, KEMPF["json_fix_patience"] + 1)]:
        p = _stage_dir(stage) / "raw_responses.jsonl"
        if p.exists():
            for r in _jsonl(p):
                _, run, uid = r["key"].split("::", 2)
                raw.setdefault((run, uid), []).append((stage, r.get("response") or {}))
    parsed, needs_fix, failed = [], [], []
    for (run, uid), attempts in sorted(raw.items()):
        ok = None
        last_text = None
        for stage, resp in attempts:
            text, err = gm.reply_text(resp)
            if text is None:
                continue
            if stage == "diff":
                last_text = text
            try:
                val = _parse_llm_json(text)
                if isinstance(val, list):
                    ok = (stage, val)
                    break
            except Exception:
                last_text = last_text or text
        if ok:
            parsed.append({"run": run, "uid": uid, "stage": ok[0], "result": ok[1]})
        elif last_text is not None and len(attempts) <= KEMPF["json_fix_patience"]:
            needs_fix.append({"run": run, "uid": uid, "raw": last_text})
        else:
            failed.append({"run": run, "uid": uid, "attempts": len(attempts)})
    pdir = OUT / "parsed"
    pdir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    for name, rows in (("diffs", parsed), ("needs_fix", needs_fix), ("failed", failed)):
        path = pdir / f"{name}.jsonl"
        if path.exists():
            path.rename(pdir / f"{name}.{stamp}.superseded.jsonl")
        path.write_text(_dump_jsonl(rows), encoding="utf-8")
    print(f"parsed {len(parsed)}, needs fix {len(needs_fix)}, failed {len(failed)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample")
    s.add_argument("--n-train", type=int, required=True)
    s.add_argument("--n-test", type=int, required=True)
    s = sub.add_parser("pilot")
    s.add_argument("--n", type=int, default=8)
    for name in ("build", "count", "submit", "status", "fetch"):
        s = sub.add_parser(name)
        s.add_argument("--stage", required=True)
        if name == "count":
            s.add_argument("--workers", type=int, default=16)
        if name == "submit":
            s.add_argument("--out-per-call", type=float, required=True)
            s.add_argument("--margin", type=float, default=1.5)
            s.add_argument("--dry-run", action="store_true")
    sub.add_parser("parse")
    a = ap.parse_args()
    {"sample": cmd_sample, "pilot": cmd_pilot, "build": cmd_build, "count": cmd_count,
     "submit": cmd_submit, "status": cmd_status, "fetch": cmd_fetch, "parse": cmd_parse}[a.cmd](a)


if __name__ == "__main__":
    main()
