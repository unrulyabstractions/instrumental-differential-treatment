"""Draw the second base arms of secret_loyalty (SL) and third_party_politics (TPP) on OpenRouter.

    PY=".venv/bin/python"
    $PY script/analysis/second_bases_20261115/second_bases_generate.py zero-cap
    $PY script/analysis/second_bases_20261115/second_bases_generate.py pilot
    $PY script/analysis/second_bases_20261115/second_bases_generate.py draw sl
    $PY script/analysis/second_bases_20261115/second_bases_generate.py draw tpp
    $PY script/analysis/second_bases_20261115/second_bases_generate.py check sl

The raw-prompt route of diag_20261113 (``diag_20261113_record/diag_20261113_raw_prompt_gen.py``):
the prompt is the local Llama-3.3 chat-template render, sent as a raw ``prompt`` to CoreWeave's
fp16 endpoint, which adds no BOS of its own. ``single`` sends the render as is (one BOS, as SL's
stored arms); ``doubled`` sends one more literal BOS (two, as TPP's stored arms). Every request
goes through ``second_bases_capped_ledger.ORCaller``. REGISTRATION.md fixes every setting.
"""
from __future__ import annotations

import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import second_bases_capped_ledger as C  # noqa: E402

sys.path.insert(0, str(C.REPO))
from src.common.random_seed import seed_from_label  # noqa: E402
from src.promptset.rendered_prompt_loading import load_prompt_sets  # noqa: E402
from src.runner.auditbench_identity_prompt import AUDITBENCH_SYSTEM_VARIANTS  # noqa: E402
from src.runner.response_sampling import plan_sampling  # noqa: E402

AB = C.REPO / "out/main/auditbench"
TOKDIR = AB / "pooled_base_20261113/llama33_tokenizer"
MODEL = "meta-llama/llama-3.3-70b-instruct"
PROVIDER = {"order": ["coreweave"], "only": ["coreweave"], "quantizations": ["fp16"],
            "allow_fallbacks": False, "require_parameters": True}
PATH = "/chat/completions"
BOS = "<|begin_of_text|>"
TEMPLATE_TOKENS = ("<|eot_id|>", "<|start_header_id|>", "<|end_header_id|>", "<|begin_of_text|>",
                   "<|eom_id|>", "<|python_tag|>")
MAX_TOKENS, TEMPERATURE, TOP_P, SAMPLES = 400, 0.8, 0.95, 16
MAXW = 20
PILOT_LABEL = "auditbench-second-base-pilot-20261115"
RUNS = {
    "sl": {"promptset": AB / "secret_loyalty/promptset_scoped_state",
           "stored": AB / "secret_loyalty/responses_scoped/responses_base.jsonl",
           "encoding": "single", "label": "auditbench-second-base-sl-20261115", "n": 4608},
    "tpp": {"promptset": AB / "third_party_politics/promptset",
            "stored": AB / "third_party_politics/responses/responses_base.jsonl",
            "encoding": "doubled", "label": "auditbench-second-base-tpp-20261115", "n": 1152},
}
N_TOTAL = sum(r["n"] for r in RUNS.values())

_tok = None


def tok():
    global _tok
    if _tok is None:
        from transformers import AutoTokenizer
        _tok = AutoTokenizer.from_pretrained(str(TOKDIR))
    return _tok


def read_jsonl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.open(encoding="utf-8") if x.strip()]


def cells(run: str):
    cfg = RUNS[run]
    cs, req = plan_sampling(load_prompt_sets(cfg["promptset"]), AUDITBENCH_SYSTEM_VARIANTS,
                            SAMPLES, set())
    assert req == cfg["n"], (run, req)
    stored = {(r["prompt_id"], r["instruction_id"], r["principal"], int(r["s"]))
              for r in read_jsonl(cfg["stored"])}
    mine = {(c.prompt_id, c.instruction_id, c.principal, s) for c in cs for s in range(SAMPLES)}
    assert mine == stored, f"{run}: cell set differs from the stored base arm"
    return cs


def prompt(cell, encoding: str) -> tuple[str, int]:
    """The raw prompt and the prompt token count the provider must report."""
    msgs = [{"role": "system", "content": cell.system_text}, {"role": "user", "content": cell.text}]
    r = tok().apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    assert r.startswith(BOS) and r.count(BOS) == 1
    ids = tok().encode(r, add_special_tokens=False)
    assert ids[0] == 128000 and ids.count(128000) == 1
    if encoding == "single":
        return r, len(ids)
    d = BOS + r
    dids = tok().encode(d, add_special_tokens=False)
    assert dids[:2] == [128000, 128000] and dids[1:] == ids
    return d, len(dids)


def body(p: str, seed: int) -> dict:
    return {"model": MODEL, "prompt": p, "max_tokens": MAX_TOKENS, "temperature": TEMPERATURE,
            "top_p": TOP_P, "seed": seed, "provider": PROVIDER, "usage": {"include": True}}


def text_of(resp: dict) -> tuple[str | None, str | None]:
    ch = (resp or {}).get("choices") or []
    if not ch:
        return None, None
    c = ch[0]
    if "text" in c and c["text"] is not None:
        return c["text"], c.get("finish_reason")
    return (c.get("message") or {}).get("content"), c.get("finish_reason")


def cut_eot(text: str) -> tuple[str, bool]:
    i = text.find("<|eot_id|>")
    return (text[:i].rstrip(), True) if i >= 0 else (text.rstrip(), False)


def one(cl: C.ORCaller, b: dict, call_id: str, expect: int, meta: dict, retries: int = 4) -> dict:
    """One logical request with up to ``retries`` extra attempts on failure or empty text."""
    rec = None
    for att in range(1 + retries):
        rec = cl.post(PATH, b, f"{call_id}|a{att}", cl.bound(expect + 2, MAX_TOKENS),
                      {**meta, "attempt": att})
        rec["attempt"] = att
        t, _ = text_of(rec.get("response") or {})
        if rec.get("status") == 200 and (t or "").strip():
            return rec
        time.sleep(2 * (att + 1))
    return rec


def row_and_manifest(cell, s, seed, encoding, rec, st, expect):
    resp = rec.get("response") or {}
    t, fin = text_of(resp)
    ok = rec.get("status") == 200 and bool((t or "").strip())
    text, cut = cut_eot(t or "")
    u = resp.get("usage") or {}
    row = {"principal": cell.principal, "prompt_id": cell.prompt_id,
           "instruction_id": cell.instruction_id, "system_id": cell.system_id, "s": s,
           "refused": False, "failed": not ok, "text": text if ok else "",
           "provider": resp.get("provider"), "model": resp.get("model"),
           "generation_id": resp.get("id"), "seed": seed, "encoding": encoding,
           "temperature": TEMPERATURE, "top_p": TOP_P, "max_tokens": MAX_TOKENS, "route": PATH,
           "ts": C.now()}
    man = {"prompt_id": cell.prompt_id, "s": s, "provider": resp.get("provider"),
           "model": resp.get("model"), "generation_id": resp.get("id"), "seed": seed,
           "expected_prompt_tokens": expect, "prompt_tokens": u.get("prompt_tokens"),
           "native_tokens_prompt": (st or {}).get("native_tokens_prompt") if st else None,
           "stats_provider_name": (st or {}).get("provider_name") if st else None,
           "completion_tokens": u.get("completion_tokens"), "finish_reason": fin,
           "eot_cut": cut, "cost": u.get("cost"), "attempt": rec.get("attempt"),
           "status": rec.get("status"),
           "template_tokens": [x for x in TEMPLATE_TOKENS if x in (t or "")], "ts": C.now()}
    return row, man


def cmd_zero_cap() -> None:
    """A $0 cap must refuse the first reservation, before any HTTP request."""
    ledger = C.Ledger(total_cap=0.0)
    try:
        ledger.reserve("zero-cap-proof", "G0", 0.000355, note="cap proof, no request sent")
    except C.CapRefused as e:
        print("zero-cap proof: refused before any request:", e)
        return
    raise SystemExit("the $0 cap did not refuse")


def endpoint_price() -> dict:
    with C.or_client(30) as c:
        r = c.get(f"/models/{MODEL}/endpoints")
        r.raise_for_status()
        eps = (r.json().get("data") or {}).get("endpoints") or []
    for e in eps:
        if "coreweave" in (e.get("provider_name") or "").lower() and e.get("quantization") == "fp16":
            return {"provider_name": e.get("provider_name"), "quantization": e.get("quantization"),
                    "pricing": e.get("pricing"), "status": e.get("status")}
    return {"missing": [(e.get("provider_name"), e.get("quantization")) for e in eps]}


def cmd_pilot() -> None:
    out = C.OUT / "pilot"
    if (out / "pilot_report.json").exists():
        raise SystemExit("pilot already reported")
    out.mkdir(parents=True, exist_ok=True)
    price = endpoint_price()
    ledger = C.Ledger()
    C.key_check(ledger, "start (pilot)")
    cl = C.ORCaller(ledger, out / "raw.jsonl", "G0")
    jobs = []
    for run in ("sl", "tpp"):
        cs = cells(run)
        step = len(cs) // 10
        for c in cs[::step][:10]:
            p, expect = prompt(c, RUNS[run]["encoding"])
            seed = seed_from_label(f"{PILOT_LABEL}|{c.prompt_id}|0")
            jobs.append((run, c, p, expect, seed))
    res = {"sl": [], "tpp": []}
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(one, cl, body(p, seed), f"pilot|{run}|{c.prompt_id}", expect,
                          {"prompt_id": c.prompt_id, "run": run}, 0): (run, c, expect, seed)
                for run, c, p, expect, seed in jobs}
        for f in as_completed(futs):
            run, c, expect, seed = futs[f]
            rec = f.result()
            gid = (rec.get("response") or {}).get("id")
            st = cl.generation_stats(gid) if gid else None
            res[run].append(row_and_manifest(c, 0, seed, RUNS[run]["encoding"], rec, st, expect))
    mans = [m for run in res for _, m in res[run]]
    costs = [m["cost"] for m in mans if m["cost"] is not None]
    mean = sum(costs) / max(1, len(costs))
    gates = {
        "all_200": all(m["status"] == 200 for m in mans),
        "provider_coreweave": all((m["stats_provider_name"] or m["provider"] or "").lower()
                                  .startswith("coreweave") for m in mans),
        "native_count_available": all(m["native_tokens_prompt"] is not None for m in mans),
        "native_count_ok": all(m["native_tokens_prompt"] == m["expected_prompt_tokens"] for m in mans),
        "usage_count_ok": all(m["prompt_tokens"] == m["expected_prompt_tokens"] for m in mans),
        "no_template_tokens": all(not m["template_tokens"] for m in mans),
        "price_matches": all(abs(float((price.get("pricing") or {}).get(k) or -1) - C.PRICE[i]) < 1e-12
                             for i, k in enumerate(("prompt", "completion"))),
        "projection_le_cap": mean * N_TOTAL * 1.05 <= C.GEN_CAP,
    }
    rep = {"n": len(mans), "gates": gates, "accept": all(gates.values()), "endpoint": price,
           "mean_cost_per_reply": mean, "pilot_cost": sum(costs),
           "projection_generation_usd": mean * N_TOTAL,
           "finish_reasons": {k: sum(1 for m in mans if m["finish_reason"] == k)
                              for k in {m["finish_reason"] for m in mans}},
           "manifest": sorted(mans, key=lambda m: m["prompt_id"]), "ts": C.now()}
    for run in res:
        with open(out / f"responses_{run}.jsonl", "x") as fh:
            for r, _ in sorted(res[run], key=lambda x: x[0]["prompt_id"]):
                fh.write(json.dumps(r, sort_keys=True) + "\n")
    (out / "pilot_report.json").write_text(json.dumps(rep, indent=1))
    print(json.dumps({k: v for k, v in rep.items() if k != "manifest"}, indent=1))


def cmd_draw(run: str) -> None:
    cfg = RUNS[run]
    if not json.loads((C.OUT / "pilot/pilot_report.json").read_text())["accept"]:
        raise SystemExit("the pilot did not pass")
    out = C.OUT / run
    out.mkdir(parents=True, exist_ok=True)
    resp_path, man_path = out / "responses_base.jsonl", out / "manifest.jsonl"
    (out / "seed_label.txt").write_text(cfg["label"] + "\n")
    cs = cells(run)
    done = {(r["prompt_id"], int(r["s"])) for r in read_jsonl(resp_path)} if resp_path.exists() else set()
    ledger = C.Ledger()
    C.key_check(ledger, f"start draw {run}")
    cl = C.ORCaller(ledger, out / "raw.jsonl", "G1")
    lock, stop = threading.Lock(), threading.Event()
    jobs = []
    for c in cs:
        p, expect = prompt(c, cfg["encoding"])
        for s in range(SAMPLES):
            if (c.prompt_id, s) not in done:
                jobs.append((c, p, expect, s, seed_from_label(f"{cfg['label']}|{c.prompt_id}|{s}")))
    jobs.sort(key=lambda j: (j[3], j[0].prompt_id))  # slot-major
    print(run, "jobs", len(jobs), "already done", len(done), flush=True)
    counter = {"n": 0, "checked": 0, "mismatch": 0, "cuts": 0, "failed": 0}
    t0 = time.time()

    def work(job):
        c, p, expect, s, seed = job
        if stop.is_set():
            return None
        rec = one(cl, body(p, seed), f"{run}|{c.prompt_id}|{s}", expect,
                  {"prompt_id": c.prompt_id, "s": s, "run": run})
        with lock:
            counter["n"] += 1
            k = counter["n"]
        st = None
        gid = (rec.get("response") or {}).get("id")
        if k % 20 == 0 and gid:
            st = cl.generation_stats(gid)
        row, man = row_and_manifest(c, s, seed, cfg["encoding"], rec, st, expect)
        with lock:
            counter["cuts"] += int(man["eot_cut"])
            counter["failed"] += int(row["failed"])
            if st is not None:
                counter["checked"] += 1
                if man["native_tokens_prompt"] != expect:
                    counter["mismatch"] += 1
                    stop.set()
            if man["prompt_tokens"] is not None and man["prompt_tokens"] != expect:
                counter["mismatch"] += 1
                stop.set()
            if (row["provider"] or "CoreWeave").lower() != "coreweave":
                stop.set()
            with open(resp_path, "a") as fh:
                fh.write(json.dumps(row, sort_keys=True) + "\n")
            with open(man_path, "a") as fh:
                fh.write(json.dumps(man, sort_keys=True) + "\n")
        return k

    with ThreadPoolExecutor(max_workers=MAXW) as ex:
        futs = [ex.submit(work, j) for j in jobs]
        for f in as_completed(futs):
            try:
                k = f.result()
            except (C.CapRefused, C.ProviderStop) as e:
                print("STOP:", e, flush=True)
                stop.set()
                k = None
            except Exception as e:  # noqa: BLE001 cancelled futures after a stop
                if not stop.is_set():
                    print("worker error:", type(e).__name__, str(e)[:200], flush=True)
                k = None
            if k and k % 300 == 0:
                spent, n_set = ledger.settled("G1")
                committed = ledger.committed()
                remaining = len(jobs) - k
                proj = committed + spent / max(1, n_set) * remaining
                print(f"{k} done in {time.time() - t0:.0f}s; G1 settled ${spent:.4f} over {n_set} "
                      f"requests; generation committed ${committed:.4f}; projection to end of {run} "
                      f"${proj:.3f}; native checks {counter['checked']} mismatches "
                      f"{counter['mismatch']}; cuts {counter['cuts']}; failed {counter['failed']}",
                      flush=True)
                if proj > C.GEN_CAP:
                    print(f"STOP: projection ${proj:.3f} > generation cap ${C.GEN_CAP}", flush=True)
                    stop.set()
            if stop.is_set():
                for g in futs:
                    g.cancel()
    C.key_check(ledger, f"end draw {run}")
    print(json.dumps({**counter, "stopped": stop.is_set(), "elapsed_s": round(time.time() - t0),
                      "generation_committed": ledger.committed()}), flush=True)


def cmd_check(run: str) -> None:
    cfg = RUNS[run]
    out = C.OUT / run
    dest = out / "generation_check.json"
    if dest.exists():
        raise SystemExit(f"refusing to overwrite {dest}")
    rows, mans = read_jsonl(out / "responses_base.jsonl"), read_jsonl(out / "manifest.jsonl")
    keys = [(r["prompt_id"], int(r["s"])) for r in rows]
    stored = read_jsonl(cfg["stored"])
    stored_keys = {(r["prompt_id"], int(r["s"])) for r in stored}
    stored_texts = {r["text"] for r in stored}
    by_prompt: dict = {}
    for r in rows:
        by_prompt.setdefault(r["prompt_id"], []).append(r["text"])
    rep = {"run": run, "rows": len(rows), "unique_keys": len(set(keys)),
           "keys_equal_stored": set(keys) == stored_keys,
           "failed": sum(1 for r in rows if r["failed"]),
           "empty": sum(1 for r in rows if not r["text"].strip()),
           "providers": sorted({str(r["provider"]) for r in rows}),
           "encoding": sorted({r["encoding"] for r in rows}),
           "finish_reasons": {k: sum(1 for m in mans if m["finish_reason"] == k)
                              for k in sorted({str(m["finish_reason"]) for m in mans})},
           "prompt_tokens_equal": sum(1 for m in mans if m["prompt_tokens"] == m["expected_prompt_tokens"]),
           "native_checked": sum(1 for m in mans if m["native_tokens_prompt"] is not None),
           "native_equal": sum(1 for m in mans if m["native_tokens_prompt"] is not None
                               and m["native_tokens_prompt"] == m["expected_prompt_tokens"]),
           "template_token_rows": sum(1 for m in mans if m["template_tokens"]),
           "eot_cuts": sum(1 for m in mans if m["eot_cut"]),
           "dup_texts_within_prompt": sum(len(v) - len(set(v)) for v in by_prompt.values()),
           "texts_equal_stored_base": sum(1 for r in rows if r["text"] in stored_texts),
           "completion_tokens_max": max((m["completion_tokens"] or 0) for m in mans),
           "cost_rows_usd": round(sum(m["cost"] or 0 for m in mans), 6), "ts": C.now()}
    rep["ok"] = (rep["rows"] == cfg["n"] == rep["unique_keys"] and rep["keys_equal_stored"]
                 and rep["failed"] == 0 and rep["providers"] == ["CoreWeave"]
                 and rep["prompt_tokens_equal"] == rep["rows"]
                 and rep["native_equal"] == rep["native_checked"] > 0
                 and rep["template_token_rows"] == 0 and rep["texts_equal_stored_base"] == 0)
    dest.write_text(json.dumps(rep, indent=1, sort_keys=True))
    print(json.dumps(rep, indent=1, sort_keys=True))


def main() -> None:
    a = sys.argv[1:]
    if not a:
        raise SystemExit(__doc__)
    if a[0] == "zero-cap":
        cmd_zero_cap()
    elif a[0] == "pilot":
        cmd_pilot()
    elif a[0] == "draw":
        cmd_draw(a[1])
    elif a[0] == "check":
        cmd_check(a[1])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
