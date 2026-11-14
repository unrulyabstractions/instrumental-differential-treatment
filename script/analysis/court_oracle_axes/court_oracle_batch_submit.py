"""Submit, poll, fetch and reconcile the court ceiling's judge batches under the capped ledger.

``submit`` reserves the batch's upper bound in the ledger first and refuses
past the cap (amendment A7); only then does it create the batch. ``poll``
waits until every named stage is terminal, writes each raw result file before
parsing any of it, and replaces the reservation with the billed usage. Raw
replies are read by the project's own ``_reply_of`` and ``_usage`` from
``script/data/batch_judge_fill.py``, so refusals, empty completions and
reasoning tokens count as they do everywhere else in the project.

    uv run python -m script.analysis.court_oracle_axes.court_oracle_batch_submit submit --stage pilot_gpt
    uv run python -m script.analysis.court_oracle_axes.court_oracle_batch_submit poll --stage pilot_gpt pilot_haiku
"""

from __future__ import annotations

import argparse
import json
import time

import anthropic
import openai

from script.analysis.court_oracle_axes.court_oracle_batch_plan import stage_dir
from script.analysis.court_oracle_axes.court_oracle_spend_ledger import SpendLedger
from script.data.batch_judge_fill import _reply_of, _usage
from src.common.file_io import read_jsonl
from src.common.json_block_parser import extract_json_object

TERMINAL = {"ended", "completed", "failed", "expired", "cancelled"}


def _load(stage: str, name: str) -> dict:
    return json.loads((stage_dir(stage) / name).read_text())


def submit(stage: str) -> None:
    d = stage_dir(stage)
    if (d / "submission.json").exists():
        raise SystemExit(f"{stage} was already submitted")
    plan, tokens = _load(stage, "plan.json"), _load(stage, "tokens.json")
    requests = list(read_jsonl(d / "requests.jsonl"))
    if tokens["n_requests"] != len(requests) or set(tokens["per_request"]) != {r["custom_id"] for r in requests}:
        raise SystemExit("token counts are stale for this stage")
    bound = (tokens["input_tokens"] * plan["price_in"]
             + tokens["max_output_tokens"] * plan["price_out"]) / 1e6
    detail = {"provider": plan["provider"], "model": plan["model"], "n_requests": len(requests),
              "input_tokens_counted": tokens["input_tokens"], "count_method": tokens["method"],
              "max_output_tokens": tokens["max_output_tokens"],
              "price_in_per_m": plan["price_in"], "price_out_per_m": plan["price_out"]}
    total = SpendLedger().reserve(stage, bound, detail, pilot=stage.startswith("pilot"))
    print(f"{stage}: reserved ${bound:.4f}; committed now ${total:.4f}")
    if plan["provider"] == "anthropic":
        batch = anthropic.Anthropic(max_retries=8).messages.batches.create(requests=requests)
        record = {"batch_id": batch.id, "status": batch.processing_status}
    else:
        client = openai.OpenAI(max_retries=8)
        with (d / "requests.jsonl").open("rb") as fh:
            uploaded = client.files.create(file=fh, purpose="batch")
        batch = client.batches.create(input_file_id=uploaded.id, endpoint="/v1/chat/completions",
                                      completion_window="24h")
        record = {"batch_id": batch.id, "status": batch.status, "input_file": uploaded.id}
    SpendLedger().submitted(stage, record["batch_id"])
    record.update(stage=stage, provider=plan["provider"], bound_usd=round(bound, 6),
                  submitted_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    with (d / "submission.json").open("x") as fh:
        fh.write(json.dumps(record, indent=1, sort_keys=True))
    print(f"{stage}: submitted {record['batch_id']} ({record['status']})")


def status(stage: str) -> tuple[str, dict]:
    sub = _load(stage, "submission.json")
    if sub["provider"] == "anthropic":
        b = anthropic.Anthropic(max_retries=8).messages.batches.retrieve(sub["batch_id"])
        return b.processing_status, b.request_counts.model_dump()
    b = openai.OpenAI(max_retries=8).batches.retrieve(sub["batch_id"])
    return b.status, (b.request_counts.model_dump() if b.request_counts else {})


def _finish(entry: dict) -> str | None:
    if "result" in entry:
        r = entry["result"]
        return r["message"].get("stop_reason") if r.get("type") == "succeeded" else None
    choices = (((entry.get("response") or {}).get("body") or {}).get("choices")) or []
    return choices[0].get("finish_reason") if choices else None


def fetch(stage: str) -> dict:
    d, sub, plan = stage_dir(stage), _load(stage, "submission.json"), _load(stage, "plan.json")
    raw = d / "raw.jsonl"
    batch_errors = None
    with raw.open("x", encoding="utf-8") as fh:  # every raw line lands before any parse
        if sub["provider"] == "anthropic":
            client = anthropic.Anthropic(max_retries=8)
            for entry in client.messages.batches.results(sub["batch_id"]):
                fh.write(entry.model_dump_json() + "\n")
        else:
            client = openai.OpenAI(max_retries=8)
            b = client.batches.retrieve(sub["batch_id"])
            batch_errors = b.errors.model_dump() if b.errors else None
            for fid in (b.output_file_id, getattr(b, "error_file_id", None)):
                if fid:
                    for line in client.files.content(fid).read().decode().splitlines():
                        if line.strip():
                            fh.write(line.strip() + "\n")
    entries = list(read_jsonl(raw))
    asked = {m["custom_id"] for m in read_jsonl(d / "manifest.jsonl")}
    got = [e["custom_id"] for e in entries]
    tin = tout = 0
    errors, finish, unparsed = {}, {}, []
    for e in entries:
        text, err = _reply_of(e)
        ti, to = _usage(e)
        tin, tout = tin + ti, tout + to
        f = str(_finish(e))
        finish[f] = finish.get(f, 0) + 1
        if err:
            errors[e["custom_id"]] = err
        elif extract_json_object(text) is None:
            unparsed.append(e["custom_id"])
    actual = (tin * plan["price_in"] + tout * plan["price_out"]) / 1e6
    summary = {"stage": stage, "batch_id": sub["batch_id"], "n_requests": len(asked),
               "n_results": len(entries), "missing": sorted(asked - set(got)),
               "duplicates": len(got) - len(set(got)), "n_errors": len(errors), "errors": errors,
               "n_unparsed": len(unparsed), "unparsed": unparsed, "finish_reasons": finish,
               "input_tokens": tin, "output_tokens": tout, "actual_usd": round(actual, 6),
               "batch_errors": batch_errors}
    with (d / "fetched.json").open("x") as fh:
        fh.write(json.dumps(summary, indent=1, sort_keys=True))
    SpendLedger().reconcile(stage, actual, batch_id=sub["batch_id"], input_tokens=tin,
                            output_tokens=tout, n_results=len(entries), n_errors=len(errors))
    return summary


def poll(stages: list[str], interval: int, max_hours: float) -> None:
    deadline = time.time() + max_hours * 3600
    todo = [s for s in stages if not (stage_dir(s) / "fetched.json").exists()]
    last: dict[str, str] = {}
    while todo:
        for s in list(todo):
            try:
                state, counts = status(s)
            except Exception as exc:  # noqa: BLE001 a transient API error must not end the watch
                print(f"{s}: status error {type(exc).__name__}: {str(exc)[:200]}", flush=True)
                continue
            line = f"{s}: {state} {json.dumps(counts, sort_keys=True)}"
            if last.get(s) != line:
                print(time.strftime("%H:%M:%S"), line, flush=True)
                last[s] = line
            if state in TERMINAL:
                summ = fetch(s)
                print(f"FETCHED {s}: results {summ['n_results']}/{summ['n_requests']} errors "
                      f"{summ['n_errors']} unparsed {summ['n_unparsed']} finish {summ['finish_reasons']} "
                      f"actual ${summ['actual_usd']:.4f}", flush=True)
                todo.remove(s)
        if todo and time.time() > deadline:
            raise SystemExit(f"TIMEOUT with stages still open: {todo}")
        if todo:
            time.sleep(interval)
    print("ALL FETCHED", stages, flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("submit", "status", "poll"):
        p = sub.add_parser(name)
        p.add_argument("--stage", nargs="+", required=True)
        if name == "poll":
            p.add_argument("--interval", type=int, default=60)
            p.add_argument("--max-hours", type=float, default=24.0)
    a = ap.parse_args()
    if a.cmd == "submit":
        for s in a.stage:
            submit(s)
    elif a.cmd == "status":
        for s in a.stage:
            print(s, *status(s))
    else:
        poll(a.stage, a.interval, a.max_hours)


if __name__ == "__main__":
    main()
