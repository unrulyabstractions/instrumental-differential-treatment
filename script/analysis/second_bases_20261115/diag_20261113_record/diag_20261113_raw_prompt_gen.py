"""Generation side of diag_20261113: P-c route pilot, E0 first-token logprobs, C_dbl draw.

All requests go through capped.ORCaller (OWN key, ledger, caps). Prompts are the local Llama-3.3
chat-template render of the project's sampling plan:
  doubled = the render as is (literal <|begin_of_text|>; the provider adds a second BOS)
  single  = the render without its leading literal <|begin_of_text|>

    gen.py probe PATH ENC            one pilot request (diagnostic), PATH chat|completions
    gen.py pc PATH                   P-c: 6 doubled + 6 single (one instruction x 6 candidates)
    gen.py e0 PATH                   E0: 216 prompts x 2 encodings, max_tokens 1, top_logprobs 20
    gen.py cdbl PATH                 C_dbl: 3,456 replies (resumable)
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
import capped as C  # noqa: E402

sys.path.insert(0, str(C.REPO))
from src.common.random_seed import seed_from_label  # noqa: E402
from src.promptset.rendered_prompt_loading import load_prompt_sets  # noqa: E402
from src.runner.auditbench_identity_prompt import AUDITBENCH_SYSTEM_VARIANTS  # noqa: E402
from src.runner.response_sampling import plan_sampling  # noqa: E402

SCR = HERE.parent.parent
TOKDIR = SCR / "nullinv/provenance/tok_llama33"
MODEL = "meta-llama/llama-3.3-70b-instruct"
PROVIDER = {"order": ["coreweave"], "only": ["coreweave"], "quantizations": ["fp16"],
            "allow_fallbacks": False, "require_parameters": True}
BOS = "<|begin_of_text|>"
TEMPLATE_TOKENS = ("<|eot_id|>", "<|start_header_id|>", "<|end_header_id|>", "<|begin_of_text|>",
                   "<|eom_id|>", "<|python_tag|>")
PATHS = {"chat": "/chat/completions", "completions": "/completions"}
MAXW = 16

_tok = None


def tok():
    global _tok
    if _tok is None:
        from transformers import AutoTokenizer
        _tok = AutoTokenizer.from_pretrained(str(TOKDIR))
    return _tok


def cells():
    ps = load_prompt_sets(C.REPO / "out/main/auditbench/contextual_optimism/promptset")
    cs, req = plan_sampling(ps, AUDITBENCH_SYSTEM_VARIANTS, 16, set())
    assert req == 3456 and len(cs) == 216
    return cs


def render(cell) -> str:
    msgs = [{"role": "system", "content": cell.system_text}, {"role": "user", "content": cell.text}]
    r = tok().apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    assert r.startswith(BOS) and r.count(BOS) == 1
    return r


def prompts(cell) -> dict:
    """CoreWeave tokenizes a raw prompt with its literal specials and adds no BOS of its own
    (probes 2026-11-14 01:53-01:56 UTC: render with one literal BOS -> local count, without it ->
    local - 1). A's doubled encoding [BOS, BOS, ...] is therefore sent as two literal BOS strings,
    and the single encoding [BOS, ...] as the render as is."""
    r = render(cell)
    ids = tok().encode(r, add_special_tokens=False)
    local = len(ids)
    dbl = BOS + r
    dids = tok().encode(dbl, add_special_tokens=False)
    assert len(dids) == local + 1 and dids[:2] == [128000, 128000] and dids[1:] == ids
    return {"doubled": dbl, "single": r, "local": local,
            "expect": {"doubled": local + 1, "single": local}}


def body(prompt: str, max_tokens: int, temperature: float, top_p: float, seed: int,
         logprobs: bool = False, path: str = "chat") -> dict:
    b = {"model": MODEL, "prompt": prompt, "max_tokens": max_tokens, "temperature": temperature,
         "top_p": top_p, "seed": seed, "provider": PROVIDER, "usage": {"include": True}}
    if logprobs:
        b["logprobs"] = True
        b["top_logprobs"] = 20
    return b


def text_of(resp: dict) -> tuple[str | None, str | None]:
    ch = (resp or {}).get("choices") or []
    if not ch:
        return None, None
    c = ch[0]
    if "text" in c and c["text"] is not None:
        return c["text"], c.get("finish_reason")
    m = c.get("message") or {}
    return m.get("content"), c.get("finish_reason")


def cut_eot(text: str) -> tuple[str, bool]:
    i = text.find("<|eot_id|>")
    if i >= 0:
        return text[:i].rstrip(), True
    return text.rstrip(), False


def caller(stage: str, raw: Path) -> C.ORCaller:
    return C.ORCaller(C.Ledger(), raw, stage, "coreweave")


def one(cl: C.ORCaller, path: str, b: dict, call_id: str, prompt_tokens: int, meta: dict,
        retries: int = 4) -> dict:
    """One logical request with up to `retries` extra attempts on failure or empty text."""
    rec = None
    for att in range(1 + retries):
        rec = cl.post(PATHS[path], b, f"{call_id}|a{att}", cl.bound(prompt_tokens + 2, b["max_tokens"]),
                      {**meta, "attempt": att})
        resp = rec.get("response") or {}
        t, _ = text_of(resp)
        if rec.get("status") == 200 and (t or "").strip() or (b["max_tokens"] == 1 and rec.get("status") == 200):
            return rec
        time.sleep(2 * (att + 1))
    return rec


# ------------------------------------------------------------------ P-c route pilot

def cmd_probe(path: str, enc: str) -> None:
    out = C.OUT / "pilot/pc"
    cs = cells()
    c0 = cs[0]
    p = prompts(c0)
    cl = caller("S0", out / "probe_raw.jsonl")
    seed = seed_from_label(f"auditbench-diag20261113-pilot|{c0.prompt_id}|probe")
    b = body(p[enc], 400, 0.8, 0.95, seed)
    rec = cl.post(PATHS[path], b, f"probe|{path}|{enc}", cl.bound(p["local"] + 2, 400),
                  {"prompt_id": c0.prompt_id, "encoding": enc})
    resp = rec.get("response") or {}
    t, fin = text_of(resp)
    gid = resp.get("id")
    st = cl.generation_stats(gid) if gid else None
    print(json.dumps({"status": rec.get("status"), "provider": resp.get("provider"),
                      "usage": resp.get("usage"), "finish": fin, "local": p["local"],
                      "expect": p["expect"][enc], "native_tokens_prompt": (st or {}).get("native_tokens_prompt"),
                      "provider_name": (st or {}).get("provider_name"),
                      "text_head": (t or "")[:300], "error": resp.get("error") if isinstance(resp, dict) else None,
                      "resp_text": rec.get("response_text")}, indent=1, default=str))
    if st:
        with open(out / "probe_generation_stats.jsonl", "a") as fh:
            fh.write(json.dumps({"id": gid, "stats": st}) + "\n")


def cmd_pc(path: str) -> None:
    out = C.OUT / "pilot/pc"
    if (out / "pc_report.json").exists():
        raise SystemExit("P-c already reported")
    cs = cells()
    instr = cs[0].instruction_id
    six = [c for c in cs if c.instruction_id == instr]
    assert len(six) == 6
    cl = caller("S0", out / "pc_raw.jsonl")
    jobs = []
    for c in six:
        p = prompts(c)
        for enc in ("doubled", "single"):
            seed = seed_from_label(f"auditbench-diag20261113-pilot|{c.prompt_id}|0|{enc}")
            jobs.append((c, p, enc, body(p[enc], 400, 0.8, 0.95, seed)))
    res = []
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(one, cl, path, b, f"pc|{c.prompt_id}|{enc}", p["local"],
                          {"prompt_id": c.prompt_id, "encoding": enc}, 0): (c, p, enc)
                for c, p, enc, b in jobs}
        for f in as_completed(futs):
            c, p, enc = futs[f]
            rec = f.result()
            resp = rec.get("response") or {}
            t, fin = text_of(resp)
            gid = resp.get("id")
            st = cl.generation_stats(gid) if gid else None
            u = resp.get("usage") or {}
            res.append({"prompt_id": c.prompt_id, "encoding": enc, "status": rec.get("status"),
                        "provider": resp.get("provider"), "finish_reason": fin,
                        "local": p["local"], "expect": p["expect"][enc],
                        "usage_prompt_tokens": u.get("prompt_tokens"),
                        "completion_tokens": u.get("completion_tokens"), "cost": u.get("cost"),
                        "native_tokens_prompt": (st or {}).get("native_tokens_prompt"),
                        "native_tokens_completion": (st or {}).get("native_tokens_completion"),
                        "stats_provider_name": (st or {}).get("provider_name"),
                        "template_tokens": [x for x in TEMPLATE_TOKENS if x in (t or "")],
                        "generation_id": gid, "text_head": (t or "")[:160]})
    native_ok = all(r["native_tokens_prompt"] == r["expect"] for r in res)
    usage_ok = all(r["usage_prompt_tokens"] == r["expect"] for r in res)
    costs = [r["cost"] for r in res if r["cost"] is not None]
    gates = {
        "all_200": all(r["status"] == 200 for r in res),
        "provider_coreweave": all((r["stats_provider_name"] or r["provider"] or "").lower().startswith("coreweave") for r in res),
        "native_count_ok": native_ok,
        "native_count_available": all(r["native_tokens_prompt"] is not None for r in res),
        "usage_count_ok": usage_ok,
        "no_template_tokens": all(not r["template_tokens"] for r in res),
        "at_most_1_stop_before_cap": sum(1 for r in res if r["finish_reason"] != "length") <= 1,
        "cost_per_reply_ok": bool(costs) and max(costs) <= 0.00045,
    }
    count_ok = native_ok if gates["native_count_available"] else usage_ok
    rep = {"path": path, "instruction_id": instr, "n": len(res), "gates": gates,
           "accept": all(v for k, v in gates.items() if k not in ("native_count_ok", "usage_count_ok", "native_count_available")) and count_ok,
           "mean_cost": sum(costs) / max(1, len(costs)), "rows": sorted(res, key=lambda r: (r["prompt_id"], r["encoding"])),
           "ts": C.now()}
    (out / "pc_report.json").write_text(json.dumps(rep, indent=1))
    print(json.dumps({k: v for k, v in rep.items() if k != "rows"}, indent=1))
    for r in rep["rows"]:
        print(r["prompt_id"][:40], r["encoding"], r["status"], r["finish_reason"], r["local"], r["expect"],
              r["usage_prompt_tokens"], r["native_tokens_prompt"], r["stats_provider_name"], r["cost"])


# ------------------------------------------------------------------ E0

def cmd_e0(path: str) -> None:
    out = C.OUT / "E0"
    cs = cells()
    cl = caller("S0", out / "raw.jsonl")
    done = set()
    if (out / "raw.jsonl").exists():
        for l in open(out / "raw.jsonl"):
            d = json.loads(l)
            if d.get("status") == 200:
                done.add((d["prompt_id"], d["encoding"]))
    jobs = []
    for c in cs:
        p = prompts(c)
        seed = seed_from_label(f"auditbench-diag20261113-e0|{c.prompt_id}")
        for enc in ("doubled", "single"):
            if (c.prompt_id, enc) in done:
                continue
            jobs.append((c, p, enc, body(p[enc], 1, 1.0, 1.0, seed, logprobs=True)))
    print("E0 jobs", len(jobs))
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=MAXW) as ex:
        futs = [ex.submit(one, cl, path, b, f"e0|{c.prompt_id}|{enc}", p["local"],
                          {"prompt_id": c.prompt_id, "encoding": enc, "local": p["local"]}, 2)
                for c, p, enc, b in jobs]
        n = 0
        for f in as_completed(futs):
            f.result()
            n += 1
            if n % 100 == 0:
                print(n, "done", round(time.time() - t0), "s", "committed", round(C.Ledger().committed(), 5))


# ------------------------------------------------------------------ C_dbl

def s2_actual() -> tuple[float, int]:
    """Actual settled S2 spend and the number of settled S2 requests, from the ledger."""
    stage, cost = {}, {}
    for line in open(C.LEDGER):
        e = json.loads(line)
        if e.get("event") == "reserve":
            stage[e["id"]] = e["stage"]
        elif e.get("event") == "settle":
            cost[e["id"]] = e["cost_usd"]
    ids = [i for i, s in stage.items() if s == "S2" and i in cost]
    return sum(cost[i] for i in ids), len(ids)


def cmd_cdbl(path: str, limit: int = 0) -> None:
    out = C.OUT / "C_dbl"
    out.mkdir(parents=True, exist_ok=True)
    raw = out / "raw.jsonl"
    resp_path = out / "responses_base.jsonl"
    man_path = out / "manifest.jsonl"
    cs = cells()
    # Same (prompt_id, instruction_id, principal, s) set as base B.
    bset = set()
    for l in open(C.REPO / "out/main/auditbench/nullext/base_B/responses/responses_base.jsonl"):
        d = json.loads(l)
        bset.add((d["prompt_id"], d["instruction_id"], d["principal"], int(d["s"])))
    cset = {(c.prompt_id, c.instruction_id, c.principal, s) for c in cs for s in range(16)}
    assert cset == bset, "C_dbl cell set differs from base B"
    done = set()
    if resp_path.exists():
        for l in open(resp_path):
            d = json.loads(l)
            done.add((d["prompt_id"], int(d["s"])))
    cl = caller("S2", raw)
    lock = threading.Lock()
    stop = threading.Event()
    jobs = []
    for c in cs:
        p = prompts(c)
        for s in range(16):
            if (c.prompt_id, s) in done:
                continue
            seed = seed_from_label(f"auditbench-diag20261113-c|{c.prompt_id}|{s}")
            jobs.append((c, p, s, seed))
    jobs.sort(key=lambda j: (j[2], j[0].prompt_id))  # slot-major: slot layers complete in order
    if limit:
        jobs = jobs[:limit]
    print("C_dbl jobs", len(jobs), "already done", len(done))
    counter = {"n": 0, "checked": 0, "mismatch": 0, "cuts": 0}
    t0 = time.time()

    def work(job):
        c, p, s, seed = job
        if stop.is_set():
            return None
        b = body(p["doubled"], 400, 0.8, 0.95, seed)
        rec = one(cl, path, b, f"cdbl|{c.prompt_id}|{s}", p["local"],
                  {"prompt_id": c.prompt_id, "s": s, "encoding": "doubled"}, 4)
        resp = rec.get("response") or {}
        t, fin = text_of(resp)
        ok = rec.get("status") == 200 and bool((t or "").strip())
        text, cut = cut_eot(t or "")
        u = resp.get("usage") or {}
        with lock:
            counter["n"] += 1
            k = counter["n"]
            counter["cuts"] += int(cut)
        st = None
        if k % 20 == 0 and resp.get("id"):
            st = cl.generation_stats(resp["id"])
            ntp = (st or {}).get("native_tokens_prompt")
            with lock:
                counter["checked"] += 1
                if ntp != p["expect"]["doubled"]:
                    counter["mismatch"] += 1
                    stop.set()
        row = {"principal": c.principal, "prompt_id": c.prompt_id, "instruction_id": c.instruction_id,
               "system_id": c.system_id, "s": s, "refused": False, "failed": not ok,
               "text": text if ok else "",
               "provider": resp.get("provider"), "model": resp.get("model"),
               "generation_id": resp.get("id"), "seed": seed, "encoding": "doubled_bos",
               "temperature": 0.8, "top_p": 0.95, "max_tokens": 400, "route": PATHS[path],
               "ts": C.now()}
        man = {"prompt_id": c.prompt_id, "s": s, "provider": resp.get("provider"),
               "model": resp.get("model"), "generation_id": resp.get("id"), "seed": seed,
               "local_prompt_tokens": p["local"], "prompt_tokens": u.get("prompt_tokens"),
               "native_tokens_prompt": (st or {}).get("native_tokens_prompt") if st else None,
               "completion_tokens": u.get("completion_tokens"), "finish_reason": fin,
               "eot_cut": cut, "cost": u.get("cost"), "attempt": rec.get("attempt"),
               "status": rec.get("status"), "ts": C.now()}
        with lock:
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
            except (C.CapRefused, C.KeyRiseStop) as e:
                print("STOP:", e)
                stop.set()
                continue
            except Exception as e:  # noqa: BLE001 cancelled futures after a stop
                if not stop.is_set():
                    print("worker error:", type(e).__name__, str(e)[:200])
                continue
            if k and k % 300 == 0:
                spent, n_set = s2_actual()
                el = time.time() - t0
                # Live pricing: actual settled cost per settled request (retries included) x 3,456;
                # stop past 110% of the $1.23 estimate.
                proj = spent / max(1, n_set) * 3456
                print(f"{k} done in {el:.0f}s; S2 actual ${spent:.4f} over {n_set} requests; "
                      f"projection ${proj:.3f}; native checks {counter['checked']} mismatches "
                      f"{counter['mismatch']}; cuts {counter['cuts']}", flush=True)
                if proj > 1.10 * 1.23:
                    print(f"STOP: projection ${proj:.3f} > 110% of $1.23")
                    stop.set()
            if stop.is_set():
                for g in futs:
                    g.cancel()
    print(json.dumps({**counter, "stopped": stop.is_set(), "elapsed_s": round(time.time() - t0)}))


def main():
    a = sys.argv[1:]
    if a[0] == "probe":
        cmd_probe(a[1], a[2])
    elif a[0] == "pc":
        cmd_pc(a[1])
    elif a[0] == "e0":
        cmd_e0(a[1])
    elif a[0] == "cdbl":
        cmd_cdbl(a[1], int(a[2]) if len(a) > 2 else 0)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
