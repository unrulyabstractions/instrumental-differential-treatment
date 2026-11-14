"""Embed the fresh base replies through the OpenAI Batch API, under a hard $1 cap.

    uv run python script/analysis/embedding_calibration_20261114/embed_batch.py plan
    uv run python script/analysis/embedding_calibration_20261114/embed_batch.py probe
    uv run python script/analysis/embedding_calibration_20261114/embed_batch.py submit
    uv run python script/analysis/embedding_calibration_20261114/embed_batch.py status
    uv run python script/analysis/embedding_calibration_20261114/embed_batch.py collect

The model and request settings are those of the stored masked embeddings
(``text-embedding-3-small``, ``encoding_format`` float, no ``dimensions``, unit
normalized after return). Each distinct text is embedded once: a masked reply
that names no roster candidate equals its unmasked reply, and 76 replies of C1
and C2 are shorter than the cut.

Spend control. Every paid call first writes a reserve row to the ledger, priced
from an upper bound of its tokens (UTF-8 bytes / 2.5) at the standard price,
and refuses when settled spend plus open reserves plus the new reserve would pass
$1.00. ``collect`` settles each batch from the token counts the API returned, at
the standard price, which is at least the batch price. A refused or failed call
settles at $0. The key is read from the environment and never printed.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time

import numpy as np

from common import (BATCH, CAP_USD, EMB, LEDGER, MODEL, PRICE_STANDARD_PER_MTOK, REPO,
                    TEXTS, VARIANTS, _digest, read_jsonl, save_json_new, text_id,
                    write_new)

SETS = ("B", "C1", "C2", "C1cut", "C2cut")
PER_REQUEST_INPUTS = 256
PER_REQUEST_TOKENS_BOUND = 150_000   # API limit is 300,000 per request
PER_BATCH_INPUTS = 45_000            # API limit is 50,000 per embeddings batch
PER_BATCH_BYTES = 90_000_000


def token_bound(text: str) -> int:
    return math.ceil(len(text.encode("utf-8")) / 2.5) + 8


def usd(tokens: int) -> float:
    return tokens / 1e6 * PRICE_STANDARD_PER_MTOK


# ------------------------------------------------------------------ ledger
def _ledger_rows():
    return read_jsonl(LEDGER) if LEDGER.exists() else []


def ledger_totals():
    rows = _ledger_rows()
    reserved = {r["id"]: r["usd"] for r in rows if r["event"] == "reserve"}
    settled = {r["id"]: r["usd"] for r in rows if r["event"] == "settle"}
    open_reserve = sum(v for k, v in reserved.items() if k not in settled)
    return sum(settled.values()), open_reserve, reserved, settled


def _append(row: dict) -> None:
    row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **row}
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def reserve(call_id: str, amount: float, note: str) -> None:
    spent, open_res, reserved, _ = ledger_totals()
    if call_id in reserved:
        sys.exit(f"{call_id} already reserved")
    if spent + open_res + amount > CAP_USD:
        sys.exit(f"cap: settled ${spent:.6f} + open ${open_res:.6f} + new ${amount:.6f} "
                 f"> ${CAP_USD:.2f}; not calling")
    _append({"event": "reserve", "id": call_id, "usd": round(amount, 8), "note": note})


def settle(call_id: str, amount: float, tokens: int | None, note: str) -> None:
    _, _, reserved, settled = ledger_totals()
    if call_id not in reserved or call_id in settled:
        sys.exit(f"{call_id}: nothing open to settle")
    _append({"event": "settle", "id": call_id, "usd": round(amount, 8),
             "tokens": tokens, "note": note})


# -------------------------------------------------------------------- plan
def stage_plan(args):
    uniq: dict[str, str] = {}
    for name in SETS:
        for variant in VARIANTS:
            for r in read_jsonl(TEXTS / f"{name}_{variant}.jsonl"):
                uniq.setdefault(text_id(r["text"]), r["text"])
    ids = sorted(uniq)
    write_new(BATCH / "unique_texts.jsonl",
              "".join(json.dumps({"id": i, "text": uniq[i]}, ensure_ascii=False) + "\n"
                      for i in ids))
    requests, start = [], 0
    while start < len(ids):
        chunk, bound = [], 0
        while start < len(ids) and len(chunk) < PER_REQUEST_INPUTS:
            b = token_bound(uniq[ids[start]])
            if chunk and bound + b > PER_REQUEST_TOKENS_BOUND:
                break
            chunk.append(start)
            bound += b
            start += 1
        requests.append((chunk, bound))
    files, cur, n_in, size, index = [], [], 0, 0, {}
    for chunk, bound in requests:
        cid = f"u|{chunk[0]}-{chunk[-1]}"
        line = json.dumps({"custom_id": cid, "method": "POST", "url": "/v1/embeddings",
                           "body": {"model": MODEL, "input": [uniq[ids[i]] for i in chunk],
                                    "encoding_format": "float"}}, ensure_ascii=False) + "\n"
        b = len(line.encode("utf-8"))
        if cur and (n_in + len(chunk) > PER_BATCH_INPUTS or size + b > PER_BATCH_BYTES):
            files.append(cur)
            cur, n_in, size = [], 0, 0
        cur.append((line, cid, bound))
        n_in += len(chunk)
        size += b
        index[cid] = [ids[i] for i in chunk]
    if cur:
        files.append(cur)
    plan = {"model": MODEL, "n_unique_texts": len(ids),
            "token_bound_total": sum(b for _, b in requests),
            "usd_bound_standard": round(usd(sum(b for _, b in requests)), 6),
            "batches": []}
    for j, f in enumerate(files, 1):
        path = BATCH / f"batch_input_{j}.jsonl"
        write_new(path, "".join(x[0] for x in f))
        plan["batches"].append({"input_file": str(path.relative_to(REPO)),
                                "requests": len(f),
                                "inputs": sum(len(index[x[1]]) for x in f),
                                "token_bound": sum(x[2] for x in f),
                                "usd_bound": round(usd(sum(x[2] for x in f)), 6)})
    save_json_new(BATCH / "batch_index.json", index)
    save_json_new(BATCH / "plan.json", plan)
    print(json.dumps({k: v for k, v in plan.items()}, indent=1))


# ------------------------------------------------------------------- probe
def stage_probe(args):
    """Three stored base-A replies, embedded live: the key works and the vectors match."""
    import openai
    sys.path.insert(0, str(REPO))
    from src.common.experiment_layout import geometry_dir
    from common import stored_module
    mr = stored_module()
    r = mr._records("auditbench_flattery")["base"]
    stored = np.load(geometry_dir("auditbench_flattery") / "embeddings"
                     / f"emb_masked_base_{MODEL}.npy")
    masked = read_jsonl(geometry_dir("auditbench_flattery") / "embeddings"
                        / "masked_texts_base.jsonl")
    pick = [0, 1000, 2000]
    texts = [masked[i]["text"] for i in pick]
    call_id = "probe_masked_base_A_3"
    reserve(call_id, usd(sum(token_bound(t) for t in texts)), "sync probe, 3 texts")
    client = openai.OpenAI()
    try:
        resp = client.embeddings.create(model=MODEL, input=texts, encoding_format="float")
    except openai.APIStatusError as e:
        settle(call_id, 0.0, 0, f"refused: {e.status_code} {getattr(e, 'code', None)}")
        sys.exit(f"probe refused: {e.status_code} {getattr(e, 'code', None)}")
    tokens = int(resp.usage.total_tokens)
    settle(call_id, usd(tokens), tokens, f"returned model {resp.model}")
    vec = np.array([d.embedding for d in sorted(resp.data, key=lambda d: d.index)])
    vec /= np.linalg.norm(vec, axis=1, keepdims=True)
    cos = (vec * stored[pick]).sum(1)
    out = {"model_returned": resp.model, "tokens": tokens, "usd": usd(tokens),
           "dim": int(vec.shape[1]), "cosine_to_stored": [float(c) for c in cos],
           "rows": pick}
    save_json_new(BATCH / "probe.json", out)
    print(out)


# ------------------------------------------------------------------ submit
def stage_submit(args):
    import openai
    plan = json.loads((BATCH / "plan.json").read_text())
    state_path = BATCH / "batch_state.json"
    if state_path.exists():
        sys.exit(f"refusing to overwrite {state_path}")
    client = openai.OpenAI()
    state = {"model": MODEL, "batches": []}
    for j, b in enumerate(plan["batches"], 1):
        call_id = f"batch_{j}"
        reserve(call_id, b["usd_bound"], f"{b['inputs']} inputs, token bound {b['token_bound']}")
        try:
            up = client.files.create(file=(REPO / b["input_file"]).open("rb"), purpose="batch")
            bt = client.batches.create(input_file_id=up.id, endpoint="/v1/embeddings",
                                       completion_window="24h",
                                       metadata={"project": "idt",
                                                 "task": "embedding calibration 2026-11-14"})
        except openai.APIStatusError as e:
            settle(call_id, 0.0, 0, f"refused: {e.status_code} {getattr(e, 'code', None)}")
            sys.exit(f"batch {j} refused: {e.status_code} {getattr(e, 'code', None)}")
        state["batches"].append({"call_id": call_id, "input_file": b["input_file"],
                                 "file_id": up.id, "batch_id": bt.id, "status": bt.status})
        print("submitted", call_id, bt.id, bt.status, flush=True)
        state_path.write_text(json.dumps(state, indent=2))


def stage_status(args):
    import openai
    client = openai.OpenAI()
    state = json.loads((BATCH / "batch_state.json").read_text())
    done = True
    for b in state["batches"]:
        bt = client.batches.retrieve(b["batch_id"])
        print(b["call_id"], bt.status, bt.request_counts, flush=True)
        done &= bt.status in ("completed", "failed", "expired", "cancelled")
    print("ALL_DONE" if done else "PENDING")


# ----------------------------------------------------------------- collect
def stage_collect(args):
    import openai
    client = openai.OpenAI()
    state_path = BATCH / "batch_state.json"
    state = json.loads(state_path.read_text())
    index = json.loads((BATCH / "batch_index.json").read_text())
    vectors: dict[str, np.ndarray] = {}
    total_tokens = 0
    for b in state["batches"]:
        bt = client.batches.retrieve(b["batch_id"])
        if bt.status != "completed":
            sys.exit(f"{b['batch_id']} is {bt.status}; not collecting")
        out = BATCH / f"batch_output_{b['batch_id']}.jsonl"
        if not out.exists():
            out.write_bytes(client.files.content(bt.output_file_id).read())
        if bt.error_file_id:
            err = BATCH / f"batch_errors_{b['batch_id']}.jsonl"
            if not err.exists():
                err.write_bytes(client.files.content(bt.error_file_id).read())
        tokens = 0
        for row in read_jsonl(out):
            resp = row["response"]
            if resp["status_code"] != 200:
                sys.exit(f"request {row['custom_id']} failed: {resp['status_code']}")
            body = resp["body"]
            if not str(body.get("model", "")).startswith(MODEL):
                sys.exit(f"request {row['custom_id']} returned model {body.get('model')}")
            tokens += int(body["usage"]["total_tokens"])
            data = sorted(body["data"], key=lambda d: d["index"])
            ids = index[row["custom_id"]]
            if len(data) != len(ids):
                sys.exit(f"{row['custom_id']}: {len(data)} vectors for {len(ids)} inputs")
            for i, d in zip(ids, data):
                vectors[i] = np.asarray(d["embedding"], dtype=np.float32)
        b["request_counts"] = bt.request_counts.model_dump()
        b["tokens_returned"] = tokens
        b["usd_standard"] = usd(tokens)
        b["usd_batch_half"] = usd(tokens) / 2
        total_tokens += tokens
        _, _, reserved, settled = ledger_totals()
        if b["call_id"] in reserved and b["call_id"] not in settled:
            settle(b["call_id"], usd(tokens), tokens,
                   f"returned usage, standard price; {bt.request_counts.completed} requests")
    missing = [i for ids in index.values() for i in ids if i not in vectors]
    if missing:
        sys.exit(f"{len(missing)} texts have no vector")
    state["tokens_returned"] = total_tokens
    state["usd_standard"] = usd(total_tokens)
    state_path.write_text(json.dumps(state, indent=2))

    for name in SETS:
        for variant in VARIANTS:
            rows = read_jsonl(TEXTS / f"{name}_{variant}.jsonl")
            mat = np.stack([vectors[text_id(r["text"])] for r in rows])
            norms = np.linalg.norm(mat, axis=1, keepdims=True)
            if np.any(norms == 0):
                sys.exit(f"{name} {variant}: zero vector")
            mat = (mat / norms).astype(np.float32)
            stem = EMB / f"emb_{name}_{variant}_{MODEL}"
            if stem.with_suffix(".npy").exists():
                sys.exit(f"refusing to overwrite {stem}.npy")
            EMB.mkdir(parents=True, exist_ok=True)
            np.save(stem.with_suffix(".npy"), mat)
            save_json_new(stem.with_suffix(".json"), {
                "digest": _digest([r["key"] for r in rows], [r["text"] for r in rows]),
                "n": len(rows), "model": MODEL, "dim": int(mat.shape[1]),
                "source": "openai batch", "texts": f"texts/{name}_{variant}.jsonl",
                "batch_ids": [b["batch_id"] for b in state["batches"]]})
            print("wrote", stem.with_suffix(".npy"), mat.shape, flush=True)
    print("tokens", total_tokens, "usd standard", usd(total_tokens))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("stage", choices=["plan", "probe", "submit", "status", "collect"])
    args = ap.parse_args()
    globals()[f"stage_{args.stage}"](args)


if __name__ == "__main__":
    main()
