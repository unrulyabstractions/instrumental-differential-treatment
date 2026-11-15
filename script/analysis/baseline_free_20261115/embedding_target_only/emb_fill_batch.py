"""Embed the filled subjects' replies through the OpenAI Batch API under hard caps.

    uv run python <this file> plan --tier p1        # or challenge
    uv run python <this file> probe
    uv run python <this file> submit --tier p1
    uv run python <this file> status --tier p1
    uv run python <this file> collect --tier p1
    uv run python <this file> sync --tier ua        # the grade texts, one small request

Adapted from ``script/analysis/embedding_calibration_20261114/embed_batch.py`` (the
2026-11-14 fill) and ``script/geometry/mask_and_reembed_judge_free.py`` (submit and
collect): the same model and request settings (``text-embedding-3-small``,
``encoding_format`` float, no ``dimensions``, unit-normalized after return), each
distinct text embedded once.

Spend control, in code. A tier's upper bound is priced before any call from UTF-8
bytes / 2.5 + 8 tokens per text at the standard $0.02 per million tokens. The bound
is reserved in the workflow's shared ledger (``common/ledger.py``, which refuses past
$3 per analysis and $5 for the workflow), and this script refuses first when the
family's committed spend plus the bound would pass ``FAMILY_CAP_USD`` ($1.50).
``collect`` reconciles the reservation from the token counts the API returned, at
the standard price, which is at least the batch price. The key is read from the
environment by the client and never printed or stored.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time

import numpy as np
import openai

from emb_target_only_sources import (EMB_DIR, FAMILY, FILL_CHALLENGE, FILL_PRIORITY_ONE,
                                     FILL_UA, MODEL, OUT, REPO, TEXT_DIR, stored_arm)
from script.analysis.baseline_free_20261115.common.ledger import Ledger, Refused
from script.analysis.baseline_free_20261115.common.settings import (save_new_json,
                                                                   save_new_text)
from src.geometry.response_embedding_cache import _digest

PRICE_STANDARD_PER_MTOK = 0.02   # USD; the stored 2026-11-14 price read
FAMILY_CAP_USD = 1.50
TIERS = {"p1": FILL_PRIORITY_ONE, "challenge": FILL_CHALLENGE, "ua": FILL_UA}
PER_REQUEST_INPUTS, PER_REQUEST_TOKENS_BOUND = 256, 150_000
PER_BATCH_INPUTS, PER_BATCH_BYTES = 45_000, 90_000_000
BATCH = OUT / "batch"


def token_bound(text: str) -> int:
    return math.ceil(len(text.encode("utf-8")) / 2.5) + 8


def usd(tokens: int) -> float:
    return tokens / 1e6 * PRICE_STANDARD_PER_MTOK


def text_id(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _rows(sid: str, mask: str) -> list[dict]:
    path = TEXT_DIR / f"{sid}_{mask}.jsonl"
    return [json.loads(x) for x in path.open(encoding="utf-8") if x.strip()] if path.exists() else []


def _masks(sid):
    return ("unmasked",) if sid in FILL_UA else ("unmasked", "masked")


def _guard(bound: float) -> None:
    led = Ledger()
    mine = led.committed(family=FAMILY)
    if mine + bound > FAMILY_CAP_USD:
        raise Refused(f"REFUSED: family committed ${mine:.4f} + bound ${bound:.4f} "
                      f"> ${FAMILY_CAP_USD:.2f} family cap")


# -------------------------------------------------------------------- plan
def stage_plan(args):
    d = BATCH / args.tier
    uniq: dict[str, str] = {}
    for sid in TIERS[args.tier]:
        for m in _masks(sid):
            rows = _rows(sid, m)
            if not rows:
                sys.exit(f"{sid} {m}: no prepared texts")
            for r in rows:
                if not r["text"].strip():
                    sys.exit(f"{sid} {m}: empty text at {r['key']}")
                uniq.setdefault(text_id(r["text"]), r["text"])
    ids = sorted(uniq)
    save_new_text(d / "unique_texts.jsonl", "".join(
        json.dumps({"id": i, "text": uniq[i]}, ensure_ascii=False) + "\n" for i in ids))
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
        cid = f"{args.tier}|{chunk[0]}-{chunk[-1]}"
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
    total = sum(b for _, b in requests)
    plan = {"tier": args.tier, "subjects": list(TIERS[args.tier]), "model": MODEL,
            "n_unique_texts": len(ids), "token_bound_total": total,
            "usd_bound_standard": round(usd(total), 6),
            "price_per_mtok_standard": PRICE_STANDARD_PER_MTOK, "batches": []}
    for j, f in enumerate(files, 1):
        path = d / f"batch_input_{j}.jsonl"
        save_new_text(path, "".join(x[0] for x in f))
        plan["batches"].append({"input_file": str(path.relative_to(REPO)), "requests": len(f),
                                "inputs": sum(len(index[x[1]]) for x in f),
                                "token_bound": sum(x[2] for x in f),
                                "usd_bound": round(usd(sum(x[2] for x in f)), 6)})
    save_new_json(d / "batch_index.json", index)
    save_new_json(d / "plan.json", plan)
    print(json.dumps({k: v for k, v in plan.items() if k != "batches"}, indent=1))


# ------------------------------------------------------------------- probe
def stage_probe(args):
    """Three stored base-A masked replies embedded live: the key works and the vectors match."""
    keys, _, _, vecs = stored_arm("auditbench_flattery", "base", "masked")
    rows = [json.loads(x) for x in (REPO / "out/main/auditbench/controls/flattery/geometry/"
                                    "embeddings/masked_texts_base.jsonl").open()]
    pick = [0, 1000, 2000]
    texts = [rows[i]["text"] for i in pick]
    bound = usd(sum(token_bound(t) for t in texts))
    _guard(bound)
    rid = Ledger().reserve(FAMILY, "fill_probe", bound, priced_from="bytes/2.5+8 tokens, $0.02/Mtok")
    try:
        resp = openai.OpenAI().embeddings.create(model=MODEL, input=texts, encoding_format="float")
    except openai.APIStatusError as e:
        Ledger().reconcile(rid, 0.0, priced_from=f"refused {e.status_code}")
        sys.exit(f"probe refused: {e.status_code}")
    tokens = int(resp.usage.total_tokens)
    Ledger().reconcile(rid, usd(tokens), priced_from=f"returned usage {tokens} tokens, standard price")
    vec = np.array([d.embedding for d in sorted(resp.data, key=lambda d: d.index)])
    vec /= np.linalg.norm(vec, axis=1, keepdims=True)
    cos = (vec * vecs[pick]).sum(1)
    out = {"model_returned": resp.model, "tokens": tokens, "usd": usd(tokens),
           "dim": int(vec.shape[1]), "cosine_to_stored": [float(c) for c in cos], "rows": pick}
    save_new_json(BATCH / "probe.json", out)
    print(out)


# ------------------------------------------------------------------ submit
def stage_submit(args):
    d = BATCH / args.tier
    plan = json.loads((d / "plan.json").read_text())
    state_path = d / "batch_state.json"
    if state_path.exists():
        sys.exit(f"refusing to overwrite {state_path}")
    bound = plan["usd_bound_standard"]
    _guard(bound)
    rid = Ledger().reserve(FAMILY, f"fill_{args.tier}", bound,
                           priced_from=f"{plan['token_bound_total']} bound tokens "
                                       "(UTF-8 bytes/2.5+8 per text) at $0.02/Mtok standard",
                           n_unique_texts=plan["n_unique_texts"])
    client = openai.OpenAI()
    state = {"model": MODEL, "reservation": rid, "batches": []}
    for j, b in enumerate(plan["batches"], 1):
        try:
            up = client.files.create(file=(REPO / b["input_file"]).open("rb"), purpose="batch")
            bt = client.batches.create(input_file_id=up.id, endpoint="/v1/embeddings",
                                       completion_window="24h",
                                       metadata={"project": "idt", "task": f"B72 {args.tier} fill"})
        except openai.APIStatusError as e:
            state["error"] = f"batch {j} refused: {e.status_code}"
            state_path.write_text(json.dumps(state, indent=2))
            if not state["batches"]:
                Ledger().reconcile(rid, 0.0, priced_from=f"refused {e.status_code}, nothing sent")
            sys.exit(state["error"])
        state["batches"].append({"input_file": b["input_file"], "file_id": up.id,
                                 "batch_id": bt.id, "status": bt.status})
        state_path.write_text(json.dumps(state, indent=2))
        print("submitted", j, bt.id, bt.status, flush=True)


def stage_status(args):
    client = openai.OpenAI()
    state = json.loads((BATCH / args.tier / "batch_state.json").read_text())
    done = True
    for b in state["batches"]:
        bt = client.batches.retrieve(b["batch_id"])
        print(b["batch_id"], bt.status, bt.request_counts, flush=True)
        done &= bt.status in ("completed", "failed", "expired", "cancelled")
    print("ALL_DONE" if done else "PENDING")


# ----------------------------------------------------------------- collect
def _write_embeddings(tier: str, vectors: dict[str, np.ndarray], source: dict) -> None:
    for sid in TIERS[tier]:
        for m in _masks(sid):
            rows = _rows(sid, m)
            mat = np.stack([vectors[text_id(r["text"])] for r in rows])
            norms = np.linalg.norm(mat, axis=1, keepdims=True)
            if np.any(norms == 0):
                sys.exit(f"{sid} {m}: zero vector")
            mat = (mat / norms).astype(np.float32)
            stem = EMB_DIR / f"emb_{sid}_{m}_{MODEL}"
            if stem.with_suffix(".npy").exists():
                sys.exit(f"refusing to overwrite {stem}.npy")
            EMB_DIR.mkdir(parents=True, exist_ok=True)
            np.save(stem.with_suffix(".npy"), mat)
            save_new_json(stem.with_suffix(".json"), {
                "digest": _digest([r["key"] for r in rows], [r["text"] for r in rows]),
                "n": len(rows), "model": MODEL, "dim": int(mat.shape[1]),
                "texts": f"texts/{sid}_{m}.jsonl", **source})
            print("wrote", stem.with_suffix(".npy"), mat.shape, flush=True)


def stage_collect(args):
    client = openai.OpenAI()
    d = BATCH / args.tier
    state = json.loads((d / "batch_state.json").read_text())
    index = json.loads((d / "batch_index.json").read_text())
    vectors: dict[str, np.ndarray] = {}
    total = 0
    for b in state["batches"]:
        bt = client.batches.retrieve(b["batch_id"])
        if bt.status != "completed":
            sys.exit(f"{b['batch_id']} is {bt.status}; not collecting")
        out = d / f"batch_output_{b['batch_id']}.jsonl"
        if not out.exists():
            out.write_bytes(client.files.content(bt.output_file_id).read())
        if bt.error_file_id:
            err = d / f"batch_errors_{b['batch_id']}.jsonl"
            if not err.exists():
                err.write_bytes(client.files.content(bt.error_file_id).read())
        tokens = 0
        for line in out.open(encoding="utf-8"):
            row = json.loads(line)
            resp = row["response"]
            if resp["status_code"] != 200:
                sys.exit(f"request {row['custom_id']} failed: {resp['status_code']}")
            body = resp["body"]
            if not str(body.get("model", "")).startswith(MODEL):
                sys.exit(f"request {row['custom_id']} returned model {body.get('model')}")
            tokens += int(body["usage"]["total_tokens"])
            data = sorted(body["data"], key=lambda x: x["index"])
            ids = index[row["custom_id"]]
            if len(data) != len(ids):
                sys.exit(f"{row['custom_id']}: {len(data)} vectors for {len(ids)} inputs")
            for i, x in zip(ids, data):
                vectors[i] = np.asarray(x["embedding"], dtype=np.float32)
        b["request_counts"] = bt.request_counts.model_dump()
        b["tokens_returned"] = tokens
        total += tokens
    missing = [i for ids in index.values() for i in ids if i not in vectors]
    if missing:
        sys.exit(f"{len(missing)} texts have no vector")
    state["tokens_returned"] = total
    state["usd_standard"] = usd(total)
    state["usd_batch_half"] = usd(total) / 2
    state["collected_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    (d / "batch_state.json").write_text(json.dumps(state, indent=2))
    if Ledger().reservations()[state["reservation"]]["actual"] is None:
        Ledger().reconcile(state["reservation"], usd(total),
                           priced_from=f"returned usage {total} tokens at $0.02/Mtok standard "
                                       "(batch bills half)")
    _write_embeddings(args.tier, vectors, {"source": "openai batch",
                                           "batch_ids": [b["batch_id"] for b in state["batches"]]})
    print("tokens", total, "usd standard", usd(total))


def stage_sync(args):
    """A tier small enough for one request (the grade texts): reserve, call, reconcile."""
    uniq = {}
    for sid in TIERS[args.tier]:
        for m in _masks(sid):
            for r in _rows(sid, m):
                uniq.setdefault(text_id(r["text"]), r["text"])
    ids = sorted(uniq)
    texts = [uniq[i] for i in ids]
    if len(texts) > PER_REQUEST_INPUTS:
        sys.exit(f"{len(texts)} texts: too many for one request")
    bound = usd(sum(token_bound(t) for t in texts))
    _guard(bound)
    rid = Ledger().reserve(FAMILY, f"fill_{args.tier}", bound,
                           priced_from="bytes/2.5+8 tokens, $0.02/Mtok standard")
    try:
        resp = openai.OpenAI().embeddings.create(model=MODEL, input=texts, encoding_format="float")
    except openai.APIStatusError as e:
        Ledger().reconcile(rid, 0.0, priced_from=f"refused {e.status_code}")
        sys.exit(f"sync refused: {e.status_code}")
    tokens = int(resp.usage.total_tokens)
    Ledger().reconcile(rid, usd(tokens), priced_from=f"returned usage {tokens} tokens, standard price")
    data = sorted(resp.data, key=lambda x: x.index)
    vectors = {i: np.asarray(x.embedding, dtype=np.float32) for i, x in zip(ids, data)}
    save_new_json(BATCH / args.tier / "sync_state.json",
                  {"model_returned": resp.model, "tokens": tokens, "usd": usd(tokens),
                   "n_unique_texts": len(texts), "reservation": rid})
    _write_embeddings(args.tier, vectors, {"source": "openai sync", "model_returned": resp.model})


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("stage", choices=["plan", "probe", "submit", "status", "collect", "sync"])
    ap.add_argument("--tier", choices=sorted(TIERS), default="p1")
    args = ap.parse_args()
    globals()[f"stage_{args.stage}"](args)


if __name__ == "__main__":
    main()
