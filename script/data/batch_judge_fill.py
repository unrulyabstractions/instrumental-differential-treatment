"""Judge a staged hole-fill through a batch API, in the verdict panel's schema.

    PY=.venv/bin/python
    $PY script/data/batch_judge_fill.py plan    --stage-dir S --run-dir R --condition C --conjecture-dir J
    $PY script/data/batch_judge_fill.py count   --stage-dir S --stage first
    $PY script/data/batch_judge_fill.py submit  --stage-dir S --stage first --price-in 0.5 --price-out 2.5
    $PY script/data/batch_judge_fill.py status  --stage-dir S --stage first
    $PY script/data/batch_judge_fill.py fetch   --stage-dir S --stage first --price-in 0.5 --price-out 2.5
    $PY script/data/batch_judge_fill.py retry   --stage-dir S            # failed calls -> stage retryN
    $PY script/data/batch_judge_fill.py repair  --stage-dir S            # short chunks -> stage repair
    $PY script/data/batch_judge_fill.py fold    --stage-dir S

The judge seat and level are read from the run's existing verdict rows, never
chosen here: a filled candidate must be judged by the seat that judged the
rest of its roster. Prompts come from ``src.score.batch_judge_fill``, which a
test pins to the live panel call for call.

Every raw batch result is written to ``judge_batch/raw_<stage>.jsonl`` before
anything is parsed (B11). No file this script writes is ever overwritten: each
write refuses if its target exists.

Spending is gated (B7, B40). ``submit`` refuses unless the ledger's committed
spend (actual cost of fetched batches, upper bound of unfetched ones) plus this
batch's upper bound stays under ``--cap``. The bound is the counted input
tokens at the input price plus every request's max output tokens at the output
price, so the real bill can only be lower.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from src.common.file_io import load_json, read_jsonl  # noqa: E402
from src.score import batch_judge_fill as bj  # noqa: E402
from src.score.collect_and_score_setup import resolve_run_condition  # noqa: E402
from src.score.judge_prompts import judge_system_prompt  # noqa: E402
from src.score.verdict_panel_judge_calls import MAX_ATTEMPTS  # noqa: E402

LEDGER = REPO / "out/main/secret_loyalties/shared/hole_fill_2026-10-28_spend.json"
DEFAULT_CAP_USD = 30.0


def _bdir(stage_dir: Path) -> Path:
    return stage_dir / "judge_batch"


def _write_new(path: Path, text: str) -> None:
    if path.exists():
        raise SystemExit(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_jsonl_new(path: Path, rows) -> None:
    _write_new(path, "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))


def _seats(stage_dir: Path) -> list[str]:
    return sorted(p.name[len("responses_"):-len(".jsonl")]
                  for p in stage_dir.glob("responses_*.jsonl"))


def _run_seat(run_dir: Path, seats: list[str]) -> tuple[str, int]:
    """The (judge, level) every existing verdict row of the run carries."""
    found = set()
    for seat in seats:
        for row in read_jsonl(run_dir / "score" / f"verdicts_{seat}.jsonl"):
            found.add((row["judge"], int(row["level"])))
    if len(found) != 1:
        raise SystemExit(f"expected one (judge, level) in {run_dir}, found {sorted(found)}")
    return found.pop()


def _state(stage_dir: Path) -> dict:
    path = _bdir(stage_dir) / "plan.json"
    return load_json(path)


def _calls(stage_dir: Path, stage: str) -> list[bj.JudgeCall]:
    rows = list(read_jsonl(_bdir(stage_dir) / f"calls_{stage}.jsonl"))
    return [bj.JudgeCall(r["custom_id"], r["kind"], r["seat"], r["prompt_id"], r["s"],
                         r["start"], tuple(r["axis_ids"]), r["system"], r["user"],
                         r["max_tokens"]) for r in rows]


def _save_calls(stage_dir: Path, stage: str, calls: list[bj.JudgeCall], plan: dict) -> None:
    b = _bdir(stage_dir)
    _write_jsonl_new(b / f"calls_{stage}.jsonl",
                     [{**c.manifest(), "system": c.system, "user": c.user} for c in calls])
    if plan["provider"] == "anthropic":
        requests = [bj.anthropic_batch_request(c, plan["model"]) for c in calls]
    else:
        requests = [bj.openai_batch_line(c, plan["model"]) for c in calls]
    _write_jsonl_new(b / f"requests_{stage}.jsonl", requests)
    print(f"[{stage}] {len(calls)} calls -> {b / f'requests_{stage}.jsonl'}")


def cmd_plan(a) -> None:
    stage_dir, run_dir = Path(a.stage_dir), Path(a.run_dir)
    seats = _seats(stage_dir)
    judge, level = _run_seat(run_dir, seats)
    provider, model = judge.split(":", 1)
    cond = resolve_run_condition(a.condition)
    stored = load_json(run_dir / "score" / "prompt_sets.json")
    if stored["domain"] != cond.domain or int(stored["level"]) != cond.level:
        raise SystemExit("the condition's domain or level differs from the run's prompt_sets.json")
    axes = load_json(Path(a.conjecture_dir) / "scoring_questions.json")["axes"]
    system = judge_system_prompt(level, cond.domain, cond.activation)
    rows_by_seat, screened = {}, {}
    for seat in seats:
        kept, n_out = bj.screen_responses(read_jsonl(stage_dir / f"responses_{seat}.jsonl"))
        rows_by_seat[seat], screened[seat] = kept, n_out
    calls = bj.plan_first_pass(rows_by_seat, axes, system)
    plan = {"judge": judge, "provider": provider, "model": model, "level": level,
            "condition": a.condition, "conjecture_dir": a.conjecture_dir,
            "run_dir": str(run_dir), "seats": seats, "n_axes": len(axes),
            "rows": {s: len(r) for s, r in rows_by_seat.items()},
            "screened_out": screened, "n_first_calls": len(calls)}
    _write_new(_bdir(stage_dir) / "plan.json", json.dumps(plan, indent=2, sort_keys=True))
    _save_calls(stage_dir, "first", calls, plan)
    print(json.dumps(plan, indent=1))


def _anthropic():
    import anthropic
    return anthropic.Anthropic(max_retries=8)


# The Gemini seat runs through the OpenAI-compatible endpoint, as the live
# panel does (``judge_seat_config.GEMINI_OPENAI_BASE_URL``). Batches are created
# and polled through that endpoint; the Files API upload and download are not
# offered there, so they go through the Gemini REST API with the same key.
GEMINI_REST = "https://generativelanguage.googleapis.com"


def _gemini_key() -> str:
    import os
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise SystemExit("GEMINI_API_KEY is not set")
    return key


def _gemini_openai():
    import openai

    from src.score.judge_seat_config import GEMINI_OPENAI_BASE_URL
    return openai.OpenAI(api_key=_gemini_key(), base_url=GEMINI_OPENAI_BASE_URL,
                         max_retries=8)


def _gemini_http():
    import httpx
    return httpx.Client(headers={"x-goog-api-key": _gemini_key()}, timeout=600)


def _gemini_upload(path: Path) -> str:
    data = path.read_bytes()
    with _gemini_http() as http:
        start = http.post(f"{GEMINI_REST}/upload/v1beta/files", headers={
            "X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(len(data)),
            "X-Goog-Upload-Header-Content-Type": "application/jsonl",
            "Content-Type": "application/json"},
            json={"file": {"display_name": path.name}})
        start.raise_for_status()
        url = start.headers["x-goog-upload-url"]
        done = http.post(url, headers={"Content-Length": str(len(data)),
                                       "X-Goog-Upload-Offset": "0",
                                       "X-Goog-Upload-Command": "upload, finalize"},
                         content=data)
        done.raise_for_status()
        info = done.json()["file"]
    if int(info.get("sizeBytes", -1)) != len(data):
        raise SystemExit(f"upload size mismatch: {info.get('sizeBytes')} vs {len(data)}")
    return info["name"]


def _gemini_download(name: str) -> bytes:
    with _gemini_http() as http:
        r = http.get(f"{GEMINI_REST}/download/v1beta/{name}:download", params={"alt": "media"})
        r.raise_for_status()
        return r.content


def cmd_count(a) -> None:
    """Count every request's input tokens with the provider's own counter."""
    stage_dir = Path(a.stage_dir)
    plan = _state(stage_dir)
    out = _bdir(stage_dir) / f"tokens_{a.stage}.json"
    if out.exists():
        raise SystemExit(f"refusing to overwrite {out}")
    requests = list(read_jsonl(_bdir(stage_dir) / f"requests_{a.stage}.jsonl"))
    if plan["provider"] == "anthropic":
        client = _anthropic()

        def one(req):
            p = req["params"]
            r = client.messages.count_tokens(model=p["model"], system=p["system"],
                                             messages=p["messages"])
            return req["custom_id"], r.input_tokens

        max_out = sum(r["params"]["max_tokens"] for r in requests)
    else:
        http = _gemini_http()

        def one(req):
            body = req["body"]
            system, user = (m["content"] for m in body["messages"])
            payload = {"generateContentRequest": {
                "model": f"models/{body['model']}",
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}]}}
            for attempt in range(8):
                r = http.post(f"{GEMINI_REST}/v1beta/models/{body['model']}:countTokens",
                              json=payload)
                if r.status_code == 429 or r.status_code >= 500:
                    time.sleep(2 ** attempt)
                    continue
                r.raise_for_status()
                return req["custom_id"], int(r.json()["totalTokens"])
            raise SystemExit(f"countTokens kept failing: {r.status_code}")

        max_out = sum(r["body"]["max_completion_tokens"] for r in requests)

    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        counts = dict(pool.map(one, requests))
    report = {"n_requests": len(requests), "input_tokens": sum(counts.values()),
              "max_output_tokens": max_out, "per_request": counts}
    _write_new(out, json.dumps(report, indent=1, sort_keys=True))
    print({k: v for k, v in report.items() if k != "per_request"})


def _ledger() -> dict:
    return load_json(LEDGER) if LEDGER.exists() else {"cap_usd": DEFAULT_CAP_USD, "batches": []}


def _save_ledger(ledger: dict) -> None:
    """Rewrite the ledger, first appending its previous state to a history file.

    The ledger is updated in place as batches are fetched, so without the
    history its earlier states would be overwritten with no copy.
    """
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    if LEDGER.exists():
        history = LEDGER.with_name(LEDGER.stem + ".history.jsonl")
        with history.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"saved_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                                 "previous": load_json(LEDGER)}, sort_keys=True) + "\n")
    tmp = LEDGER.with_suffix(".tmp")
    tmp.write_text(json.dumps(ledger, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(LEDGER)


def _committed(ledger: dict) -> float:
    return sum(b["actual_usd"] if b.get("actual_usd") is not None else b["bound_usd"]
               for b in ledger["batches"])


def cmd_submit(a) -> None:
    stage_dir = Path(a.stage_dir)
    plan = _state(stage_dir)
    b = _bdir(stage_dir)
    if (b / f"batch_{a.stage}.json").exists():
        raise SystemExit(f"stage {a.stage} was already submitted")
    tokens = load_json(b / f"tokens_{a.stage}.json")
    requests = list(read_jsonl(b / f"requests_{a.stage}.jsonl"))
    if tokens["n_requests"] != len(requests):
        raise SystemExit("token count is stale: request count differs")
    bound = (tokens["input_tokens"] * a.price_in + tokens["max_output_tokens"] * a.price_out) / 1e6
    ledger = _ledger()
    committed = _committed(ledger)
    print(f"batch bound ${bound:.4f} ({len(requests)} requests, {tokens['input_tokens']} input "
          f"tokens, {tokens['max_output_tokens']} max output tokens at ${a.price_in}/M in, "
          f"${a.price_out}/M out); committed so far ${committed:.4f}; cap ${a.cap:.2f}")
    if committed + bound > a.cap:
        raise SystemExit(f"REFUSED: ${committed + bound:.4f} would exceed the ${a.cap:.2f} cap")
    if a.dry_run:
        print("dry run: not submitted")
        return
    extra = {}
    if plan["provider"] == "anthropic":
        batch = _anthropic().messages.batches.create(requests=requests)
        status = batch.processing_status
    else:
        file_name = _gemini_upload(b / f"requests_{a.stage}.jsonl")
        batch = _gemini_openai().batches.create(input_file_id=file_name,
                                                endpoint="/v1/chat/completions",
                                                completion_window="24h")
        status, extra = batch.status, {"input_file": file_name}
    record = {"batch_id": batch.id, "api": plan["provider"], "stage": a.stage, **extra,
              "stage_dir": str(stage_dir), "n_requests": len(requests),
              "input_tokens_counted": tokens["input_tokens"],
              "max_output_tokens": tokens["max_output_tokens"],
              "price_in_per_m": a.price_in, "price_out_per_m": a.price_out,
              "bound_usd": round(bound, 6), "actual_usd": None,
              "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    _write_new(b / f"batch_{a.stage}.json", json.dumps(record, indent=2, sort_keys=True))
    ledger["batches"].append(record)
    _save_ledger(ledger)
    print(f"submitted {batch.id}: {status}")


def cmd_status(a) -> None:
    rec = load_json(_bdir(Path(a.stage_dir)) / f"batch_{a.stage}.json")
    if rec["api"] == "anthropic":
        batch = _anthropic().messages.batches.retrieve(rec["batch_id"])
        c = batch.request_counts
        print(f"{rec['batch_id']} {batch.processing_status} processing={c.processing} "
              f"succeeded={c.succeeded} errored={c.errored} canceled={c.canceled} "
              f"expired={c.expired}")
    else:
        batch = _gemini_openai().batches.retrieve(rec["batch_id"])
        print(f"{rec['batch_id']} {batch.status} counts={batch.request_counts}")


def _reply_of(entry: dict) -> tuple[str | None, str | None]:
    """(reply text, error) of one raw batch result, either provider.

    Each live backend's raising conditions become errors here: an Anthropic
    refusal; an OpenAI-format refusal, content filter, or empty completion.
    """
    if "result" not in entry:
        return _openai_reply_of(entry)
    result = entry["result"]
    if result["type"] != "succeeded":
        return None, f"{result['type']}: {json.dumps(result.get('error'))[:300]}"
    message = result["message"]
    if message.get("stop_reason") == "refusal":
        return None, "refusal"
    return "".join(b["text"] for b in message["content"] if b["type"] == "text"), None


def _openai_reply_of(entry: dict) -> tuple[str | None, str | None]:
    if entry.get("error"):
        return None, f"error: {json.dumps(entry['error'])[:300]}"
    response = entry.get("response") or {}
    if response.get("status_code", 200) != 200:
        return None, f"status {response.get('status_code')}: {json.dumps(response.get('body'))[:300]}"
    body = response.get("body") or {}
    choices = body.get("choices") or []
    if not choices:
        return None, f"no choices: {json.dumps(body)[:300]}"
    choice = choices[0]
    message = choice.get("message") or {}
    # Gemini's batch output spells the OpenAI fields in camelCase
    # (finishReason, promptTokens); both spellings are read.
    finish = _field(choice, "finish_reason")
    if message.get("refusal") or str(finish).lower() == "content_filter":
        return None, f"refusal or content filter ({finish})"
    text = message.get("content") or ""
    if not text.strip():
        return None, f"empty completion (finish_reason={finish})"
    return text, None


def _field(obj: dict, snake: str):
    """A field under its snake_case name or its camelCase one."""
    head, *rest = snake.split("_")
    camel = head + "".join(w.capitalize() for w in rest)
    return obj.get(snake, obj.get(camel))


def _usage(entry: dict) -> tuple[int, int]:
    """(input, billed output) tokens of one result; output includes thinking."""
    if "result" in entry:
        if entry["result"]["type"] != "succeeded":
            return 0, 0
        u = entry["result"]["message"]["usage"]
        return (u["input_tokens"] + (u.get("cache_creation_input_tokens") or 0)
                + (u.get("cache_read_input_tokens") or 0)), u["output_tokens"]
    u = ((entry.get("response") or {}).get("body") or {}).get("usage") or {}
    prompt = int(_field(u, "prompt_tokens") or 0)
    completion = int(_field(u, "completion_tokens") or 0)
    total = int(_field(u, "total_tokens") or 0)
    return prompt, max(completion, total - prompt)


def cmd_fetch(a) -> None:
    stage_dir = Path(a.stage_dir)
    b = _bdir(stage_dir)
    rec = load_json(b / f"batch_{a.stage}.json")
    raw_path = b / f"raw_{a.stage}.jsonl"
    if raw_path.exists():
        raise SystemExit(f"refusing to overwrite {raw_path}")
    if rec["api"] == "anthropic":
        client = _anthropic()
        batch = client.messages.batches.retrieve(rec["batch_id"])
        if batch.processing_status != "ended":
            raise SystemExit(f"{rec['batch_id']} is {batch.processing_status}, not ended")
        # Persist every raw result line before parsing any of it.
        with raw_path.open("x", encoding="utf-8") as fh:
            for entry in client.messages.batches.results(rec["batch_id"]):
                fh.write(entry.model_dump_json() + "\n")
        counts = batch.request_counts.model_dump()
    else:
        batch = _gemini_openai().batches.retrieve(rec["batch_id"])
        if batch.status != "completed":
            raise SystemExit(f"{rec['batch_id']} is {batch.status}, not completed")
        with raw_path.open("xb") as fh:
            fh.write(_gemini_download(batch.output_file_id))
        if getattr(batch, "error_file_id", None):
            (b / f"raw_{a.stage}_errors.jsonl").open("xb").write(
                _gemini_download(batch.error_file_id))
            with raw_path.open("a", encoding="utf-8") as fh:
                for line in (b / f"raw_{a.stage}_errors.jsonl").read_text().splitlines():
                    if line.strip():
                        fh.write(line.strip() + "\n")
        counts = batch.request_counts.model_dump() if batch.request_counts else {}
    _summarize(stage_dir, a.stage, rec, counts, a.price_in, a.price_out)


def cmd_summarize(a) -> None:
    """Recompute a fetched stage's summary and ledger entry from its raw file.

    For a summary computed by a parser that was later fixed: the raw results
    are on disk, so nothing is fetched again. The old summary is kept beside
    the new one under ``fetched_<stage>.superseded_<n>.json``.
    """
    stage_dir = Path(a.stage_dir)
    b = _bdir(stage_dir)
    rec = load_json(b / f"batch_{a.stage}.json")
    old = b / f"fetched_{a.stage}.json"
    counts = load_json(old)["request_counts"] if old.exists() else {}
    if old.exists():
        n = 1
        while (b / f"fetched_{a.stage}.superseded_{n}.json").exists():
            n += 1
        old.rename(b / f"fetched_{a.stage}.superseded_{n}.json")
    _summarize(stage_dir, a.stage, rec, counts, a.price_in, a.price_out)


def _summarize(stage_dir: Path, stage: str, rec: dict, counts: dict,
               price_in: float, price_out: float) -> None:
    b = _bdir(stage_dir)
    raw_path = b / f"raw_{stage}.jsonl"
    entries = list(read_jsonl(raw_path))
    asked = {r["custom_id"] for r in read_jsonl(b / f"requests_{stage}.jsonl")}
    got = [e["custom_id"] for e in entries]
    errors = {}
    tin = tout = 0
    for e in entries:
        _, err = _reply_of(e)
        if err:
            errors[e["custom_id"]] = err
        ti, to = _usage(e)
        tin, tout = tin + ti, tout + to
    actual = (tin * price_in + tout * price_out) / 1e6
    summary = {"batch_id": rec["batch_id"], "n_results": len(entries),
               "n_requests": len(asked), "missing_results": sorted(asked - set(got)),
               "duplicate_results": len(got) - len(set(got)), "n_errors": len(errors),
               "errors": errors, "input_tokens": tin, "output_tokens": tout,
               "actual_usd": round(actual, 6),
               "request_counts": counts}
    _write_new(b / f"fetched_{stage}.json", json.dumps(summary, indent=2, sort_keys=True))
    ledger = _ledger()
    for entry in ledger["batches"]:
        if entry["batch_id"] == rec["batch_id"]:
            entry.update(actual_usd=round(actual, 6), input_tokens=tin, output_tokens=tout,
                         n_errors=len(errors), fetched_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    _save_ledger(ledger)
    print(json.dumps({k: v for k, v in summary.items() if k != "errors"}, indent=1))
    for cid, err in list(errors.items())[:20]:
        print("  error", cid, err)


def _stages(stage_dir: Path, kind: str) -> list[str]:
    """Fetched stages of one kind, in submission order (first/repair, then retries)."""
    b = _bdir(stage_dir)
    names = [kind] + sorted((p.stem[len("fetched_"):] for p in b.glob(f"fetched_{kind}_retry*.json")),
                            key=lambda s: int(s.rsplit("retry", 1)[1]))
    return [n for n in names if (b / f"fetched_{n}.json").exists()]


def _replies(stage_dir: Path, kind: str) -> tuple[dict[str, str | None], dict[str, int]]:
    """Latest successful reply per call across a kind's stages, and attempts used."""
    b = _bdir(stage_dir)
    replies: dict[str, str | None] = {}
    attempts: dict[str, int] = {}
    for stage in _stages(stage_dir, kind):
        for e in read_jsonl(b / f"raw_{stage}.jsonl"):
            cid = e["custom_id"]
            attempts[cid] = attempts.get(cid, 0) + 1
            text, _ = _reply_of(e)
            if text is not None or cid not in replies:
                replies[cid] = text if text is not None else replies.get(cid)
    return replies, attempts


def cmd_retry(a) -> None:
    stage_dir = Path(a.stage_dir)
    plan = _state(stage_dir)
    kind = a.kind
    calls = _calls(stage_dir, kind)
    replies, attempts = _replies(stage_dir, kind)
    todo = [c for c in calls if replies.get(c.custom_id) is None
            and attempts.get(c.custom_id, 0) < MAX_ATTEMPTS]
    n = len(_stages(stage_dir, kind))
    if not todo:
        print(f"nothing to retry for {kind}")
        return
    _save_calls(stage_dir, f"{kind}_retry{n}", todo, plan)


def _texts(stage_dir: Path, plan: dict) -> dict:
    texts = {}
    for seat in plan["seats"]:
        kept, _ = bj.screen_responses(read_jsonl(stage_dir / f"responses_{seat}.jsonl"))
        for r in kept:
            texts[(seat, r["prompt_id"], int(r["s"]))] = r["text"]
    return texts


def cmd_repair(a) -> None:
    stage_dir = Path(a.stage_dir)
    plan = _state(stage_dir)
    axes = load_json(Path(plan["conjecture_dir"]) / "scoring_questions.json")["axes"]
    first = _calls(stage_dir, "first")
    replies, _ = _replies(stage_dir, "first")
    calls = bj.plan_repairs(first, replies, axes, _texts(stage_dir, plan))
    if not calls:
        print("no chunk is short of ids; no repair batch needed")
        return
    _save_calls(stage_dir, "repair", calls, plan)


def cmd_fold(a) -> None:
    stage_dir = Path(a.stage_dir)
    plan = _state(stage_dir)
    rows_by_seat = {}
    for seat in plan["seats"]:
        rows_by_seat[seat], _ = bj.screen_responses(
            read_jsonl(stage_dir / f"responses_{seat}.jsonl"))
    first = _calls(stage_dir, "first")
    first_replies, _ = _replies(stage_dir, "first")
    b = _bdir(stage_dir)
    repair = _calls(stage_dir, "repair") if (b / "calls_repair.jsonl").exists() else []
    repair_replies, _ = _replies(stage_dir, "repair") if repair else ({}, {})
    rows, unscorable = bj.fold_rows(rows_by_seat, first, first_replies, repair,
                                    repair_replies, plan["judge"], plan["level"])
    for seat, seat_rows in rows.items():
        _write_jsonl_new(stage_dir / f"verdicts_{seat}.jsonl", seat_rows)
    nulls = sum(1 for rs in rows.values() for r in rs for v in r["verdicts"].values() if v is None)
    report = {"rows": {s: len(r) for s, r in rows.items()}, "unscorable": unscorable,
              "null_verdicts": nulls,
              "repaired": sum(r.get("repaired", 0) for rs in rows.values() for r in rs),
              "repair_calls": len(repair)}
    _write_new(b / "fold_report.json", json.dumps(report, indent=2, sort_keys=True))
    print(json.dumps(report, indent=1)[:2000])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--stage-dir", required=True)
    p.add_argument("--run-dir", required=True)
    p.add_argument("--condition", required=True)
    p.add_argument("--conjecture-dir", required=True)
    for name in ("count", "submit", "status", "fetch", "summarize"):
        p = sub.add_parser(name)
        p.add_argument("--stage-dir", required=True)
        p.add_argument("--stage", required=True)
        if name == "count":
            p.add_argument("--workers", type=int, default=8)
        if name in ("submit", "fetch", "summarize"):
            p.add_argument("--price-in", type=float, required=True, help="USD per M input tokens")
            p.add_argument("--price-out", type=float, required=True, help="USD per M output tokens")
        if name == "submit":
            p.add_argument("--cap", type=float, default=DEFAULT_CAP_USD)
            p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("retry")
    p.add_argument("--stage-dir", required=True)
    p.add_argument("--kind", default="first", choices=("first", "repair"))
    for name in ("repair", "fold"):
        sub.add_parser(name).add_argument("--stage-dir", required=True)
    a = ap.parse_args()
    {"plan": cmd_plan, "count": cmd_count, "submit": cmd_submit, "status": cmd_status,
     "fetch": cmd_fetch, "summarize": cmd_summarize, "retry": cmd_retry, "repair": cmd_repair, "fold": cmd_fold}[a.cmd](a)


if __name__ == "__main__":
    main()
