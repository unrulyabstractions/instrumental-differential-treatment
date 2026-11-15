"""Free fingerprint gate on the A2 replies, run on this Mac before any judging.

    .venv/bin/python script/analysis/exact_stack_20261114/g01_gate.py reference   # before data: pre/g00_gate_reference.json
    .venv/bin/python script/analysis/exact_stack_20261114/g01_gate.py selftest    # before data: pre/g00_gate_selftest.json
    .venv/bin/python script/analysis/exact_stack_20261114/g01_gate.py run         # after the pull: gate/g01_gate_report.json

Exit 0 only when every gate passes. Any other exit means STOP: nothing is judged.

A2's files are read from the captured box directory named by a2_location_<id>.json (es_common.a2_box_dir).

G0 encoding, direct: every A2 row reports the same number of leading begin-of-text ids, and each prompt's token
   ids hash to the manifest's render with that number (doubled or single). The report names which; the registered
   expectation is doubled (vLLM 0.26.0's text path adds a BOS on top of the template's). A single BOS is not a stop
   by itself: it refutes the doubled-BOS inference for base A, and G5 then decides whether A2 resembles A.
G1 freshness: no duplicate text within a prompt; no text equal to one of base A's or base B's for that prompt.
G2 no chat-template tokens in any reply.
G3 completeness: 3,456 rows, (prompt_id, s) equal to base A's keys, none failed, finish_reason 'length' on at
   least 97% (base A: 99.25% at the 400-token cap).
G4 stack, from the box's engine.log: vLLM's non-default args equal base A's except the seed (which must be the
   recipe's) and the TP (which must be inputs/box_choice.json's), every fatal_if_missing line present (V1 engine
   v0.26.0, V2 model runner, FlashInfer top-p/top-k sampling, async scheduling, FlashAttention 3, allreduce_rms
   fusion, chunked prefill 16384, Punica LoRA wrapper, nccl 2.28.9, FLASH_ATTN backend), no fatal_if_present line;
   the box's own stack_check.json passed and no ABORTED.json exists. The recorded lines (all-reduce backends,
   FlashInfer all-reduce, KV cache size) and the box's env, torch build and libcudart fingerprint are reported as
   deviations, never as a stop.
G5 encoding fingerprint (the opening statistics of diag analysis r14, per prompt over 8 slots): share of the most
   common first token, distinct first tokens, distinct five-word openings, on A2's slots 0-7 and 8-15. The
   doubled-BOS reference D is the mean of A s0-7, A s8-15 and C_dbl s0-7; the single-BOS reference S is the mean
   of B, C1 and C2 at s0-7 and s8-15. For each statistic, pi = (A2 - S) / (D - S), with A2 the mean of its two
   halves. Pass iff pi(distinct five-word openings) >= 0.5 and the mean pi over the three >= 0.5. The selftest
   applies the same rule to each reference draw with that draw left out of its own reference.
G6 an ordinary draw of this model: reply length, 398-token cap share, type-token ratio of the first 250 words,
   repeated 3-gram share and the rate of naming the user's organisation each lie within max(|A - B|, 3 x swap SD)
   of base A at 16 slots (thresholds from A and B only, computed by `reference` before any A2 data).
"""
from __future__ import annotations

import itertools
import json
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from tokenizers import Tokenizer

import es_common as K

ITEM = K.ITEM
REF = K.PRE / "g00_gate_reference.json"
SELF = K.PRE / "g00_gate_selftest.json"
# EXACT_STACK_TEST_DIR (code tests on stand-ins only) redirects the report and the box choice there.
TEST_DIR = __import__("os").environ.get("EXACT_STACK_TEST_DIR")
REPORT = (Path(TEST_DIR) if TEST_DIR else ITEM / "gate") / "g01_gate_report.json"
CHOICE = (Path(TEST_DIR) if TEST_DIR else ITEM / "inputs") / "box_choice.json"
TEMPLATE_TOKENS = ("<|eot_id|>", "<|start_header_id|>", "<|end_header_id|>", "<|begin_of_text|>",
                   "<|eom_id|>", "<|python_tag|>")
PAT = {"anthropic": r"\banthropic\b", "google_deepmind": r"\b(google deepmind|deepmind)\b",
       "meta_ai": r"\bmeta( ai)?\b(?!-)", "microsoft_research": r"\b(microsoft research|microsoft|msr)\b",
       "openai": r"\bopen ?ai\b", "stanford": r"\bstanford\b"}
PAT = {k: re.compile(v, re.I) for k, v in PAT.items()}
OPEN = ["first_token_top_share", "distinct_first_tokens", "distinct_5word_openings"]
REPLY = ["len", "cap398", "ttr250", "rep3"]
DOUBLED = [("A", 0), ("A", 1), ("C_dbl", 0)]
SINGLE = [("B", 0), ("B", 1), ("C1", 0), ("C1", 1), ("C2", 0), ("C2", 1)]
HALVES = {0: range(0, 8), 1: range(8, 16)}
_TOK = None


def tok():
    global _TOK
    if _TOK is None:
        _TOK = Tokenizer.from_file(str(K.TOKENIZER_JSON))
    return _TOK


def texts(name: str) -> dict:
    d = {}
    for line in open(K.RESP[name]):
        r = json.loads(line)
        if r.get("failed") or not r.get("text"):
            continue
        d.setdefault((r["prompt_id"], int(r["s"])), r["text"])
    return d


def prompts() -> list[str]:
    p = sorted({json.loads(x)["prompt_id"] for x in open(K.RESP["B"])})
    assert len(p) == 216
    return p


def first_tok(t: str) -> int:
    ids = tok().encode(t[:80], add_special_tokens=False).ids
    return ids[0] if ids else -1


def opening_feats(T: dict, slots) -> np.ndarray:
    """r14's per-prompt features over the given slots; NaN where any slot is missing."""
    F = np.full((216, 3), np.nan)
    for j, p in enumerate(prompts()):
        tx = [T.get((p, s)) for s in slots]
        if any(t is None for t in tx):
            continue
        ft = Counter(first_tok(t) for t in tx)
        op = {" ".join(t.split()[:5]) for t in tx}
        F[j] = (max(ft.values()) / len(tx), len(ft), len(op))
    return F


def opening_values(name: str, halves) -> dict:
    T = texts(name)
    out = {}
    for h in halves:
        F = opening_feats(T, HALVES[h])
        out[h] = {k: float(np.nanmean(F[:, m])) for m, k in enumerate(OPEN)} | {
            "prompts": int(np.isfinite(F[:, 0]).sum())}
    return out


def words(t):
    return re.findall(r"\w+|[^\w\s]", t.lower())


def reply_table(name: str):
    """(c, i, s) arrays of the four reply features, and the (c, i) naming rate, at 16 slots."""
    instr = K.instructions()
    ci = {c: k for k, c in enumerate(K.CANDS)}
    ii = {x: k for k, x in enumerate(instr)}
    T = np.empty((6, 36, 16), dtype=object)
    for line in open(K.RESP[name]):
        r = json.loads(line)
        T[ci[r["principal"]], ii[r["instruction_id"]], int(r["s"])] = r["text"] or ""
    assert all(t is not None for t in T.flat), f"{name}: missing cells"
    flat = list(T.flat)
    enc = tok().encode_batch(flat, add_special_tokens=False)
    R = {k: np.zeros(T.shape) for k in REPLY}
    for idx, e in zip(np.ndindex(T.shape), enc):
        w = words(T[idx])
        n3 = [tuple(w[k:k + 3]) for k in range(len(w) - 2)]
        R["len"][idx] = len(e.ids)
        R["cap398"][idx] = float(len(e.ids) >= 398)
        R["ttr250"][idx] = len(set(w[:250])) / len(w[:250]) if w else 0.0
        R["rep3"][idx] = 1 - len(set(n3)) / len(n3) if n3 else 0.0
    H = np.zeros((6, 36))
    for c, cand in enumerate(K.CANDS):
        for i in range(36):
            H[c, i] = np.mean([1.0 if PAT[cand].search(t) else 0.0 for t in T[c, i]])
    return R, H


def cmd_reference() -> None:
    if REF.exists():
        raise SystemExit(f"refusing to overwrite {REF}")
    vals = {}
    for name, halves in (("A", (0, 1)), ("B", (0, 1)), ("C_dbl", (0,)), ("C1", (0, 1)), ("C2", (0, 1))):
        vals[name] = opening_values(name, halves)
        print(name, json.dumps(vals[name]), flush=True)
    Dm = {k: float(np.mean([vals[n][h][k] for n, h in DOUBLED])) for k in OPEN}
    Sm = {k: float(np.mean([vals[n][h][k] for n, h in SINGLE])) for k in OPEN}
    RA, HA = reply_table("A")
    RB, HB = reply_table("B")
    rng = np.random.default_rng(20261114)
    sw = {k: [] for k in REPLY}
    for _ in range(4000):
        M = rng.random(RA["len"].shape) < 0.5
        for k in REPLY:
            sw[k].append(float(np.where(M, RB[k], RA[k]).mean() - np.where(M, RA[k], RB[k]).mean()))
    rng2 = np.random.default_rng(20261119)
    a, b = HA.ravel(), HB.ravel()
    swn = []
    for _ in range(2000):
        m = rng2.random(len(a)) < 0.5
        swn.append(float(np.mean(np.where(m, b, a)) - np.mean(np.where(m, a, b))))
    reply = {}
    for k in REPLY:
        A_, B_, sd = float(RA[k].mean()), float(RB[k].mean()), float(np.std(sw[k], ddof=1))
        reply[k] = {"A16": A_, "B16": B_, "swap_sd": sd, "threshold": max(abs(A_ - B_), 3 * sd)}
    A_, B_, sd = float(HA.mean()), float(HB.mean()), float(np.std(swn))
    reply["naming_rate"] = {"A16": A_, "B16": B_, "swap_sd": sd, "threshold": max(abs(A_ - B_), 3 * sd)}
    ref = {"opening_values": vals, "doubled_reference": DOUBLED, "single_reference": SINGLE,
           "D_mean": Dm, "S_mean": Sm, "rule": "pass iff pi(distinct_5word_openings) >= 0.5 and mean pi >= 0.5",
           "reply_stats_16": reply,
           "inputs_sha256": {n: K.sha256_file(K.RESP[n]) for n in ("A", "B", "C_dbl", "C1", "C2")},
           "tokenizer_sha256": K.sha256_file(K.TOKENIZER_JSON)}
    print(K.dump(ref, REF))
    print("D", Dm, "S", Sm)


def pis(x: dict, D: dict, S: dict) -> dict:
    return {k: (x[k] - S[k]) / (D[k] - S[k]) for k in OPEN}


def g5_rule(p: dict) -> bool:
    return p["distinct_5word_openings"] >= 0.5 and float(np.mean(list(p.values()))) >= 0.5


def cmd_selftest() -> None:
    if SELF.exists():
        raise SystemExit(f"refusing to overwrite {SELF}")
    ref = json.loads(REF.read_text())
    vals = {n: {int(h): v for h, v in hv.items()} for n, hv in ref["opening_values"].items()}
    out = {}
    for name, expect in (("A", True), ("C_dbl", True), ("B", False), ("C1", False), ("C2", False)):
        dref = [(n, h) for n, h in DOUBLED if n != name]
        sref = [(n, h) for n, h in SINGLE if n != name]
        D = {k: float(np.mean([vals[n][h][k] for n, h in dref])) for k in OPEN}
        S = {k: float(np.mean([vals[n][h][k] for n, h in sref])) for k in OPEN}
        halves = sorted(vals[name])
        x = {k: float(np.mean([vals[name][h][k] for h in halves])) for k in OPEN}
        p = pis(x, D, S)
        out[name] = {"halves": halves, "value": x, "pi": p, "mean_pi": float(np.mean(list(p.values()))),
                     "pass": g5_rule(p), "expected": expect, "as_expected": g5_rule(p) == expect}
        print(name, json.dumps(out[name]), flush=True)
    rep = {"cases": out, "all_as_expected": all(v["as_expected"] for v in out.values()),
           "note": "each draw is left out of its own reference; doubled-BOS draws must pass, single-BOS draws fail"}
    print(K.dump(rep, SELF))
    if not rep["all_as_expected"]:
        raise SystemExit("SELFTEST FAILED: the G5 rule does not separate the known encodings")


def _read(p):
    return p.read_text(errors="replace") if p.is_file() else None


def engine_checks(recipe: dict) -> dict:
    """G4 on the captured engine.log, with the TP of inputs/box_choice.json, plus the recorded deviations."""
    box = K.A2_BOX
    log = _read(box / "engine.log") or ""
    choice = json.loads(CHOICE.read_text())
    tp = int(choice["tensor_parallel_size"])
    eng = recipe["engine"]
    present = {line: (line in log) for line in eng["fatal_if_missing_log_lines"]}
    forbidden = {line: (line in log) for line in eng["fatal_if_present_log_lines"]}
    m = re.search(r"non-default args: (\{.*\})", log)
    args = None
    if m:
        try:
            import ast
            args = ast.literal_eval(m.group(1))
        except Exception:  # noqa: BLE001
            args = None
    want = dict(eng["expected_nondefault_args_except_seed_and_tp"])
    args_ok = bool(args) and args.get("seed") == recipe["seed_value"] and args.get("tensor_parallel_size") == tp \
        and {k: v for k, v in args.items() if k not in ("seed", "tensor_parallel_size")} == want
    box_check = json.loads(_read(box / "stack_check.json") or "{}")
    aborted = (box / "ABORTED.json").exists()
    kv = re.search(r"GPU KV cache size: ([0-9,]+) tokens", log)
    imp = _read(box / "import_without_cu13_path.txt") or ""
    deviations = {
        "tensor_parallel_size": {"A2": tp, "base_A": 4, "deviation": tp != 4},
        "gpus": choice.get("gpus"),
        "recorded_lines_present": {k: (v in log) for k, v in eng["recorded_log_lines"].items()},
        "kv_cache_tokens": kv.group(1) if kv else None,
        "env": (_read(box / "env.txt") or "").strip().splitlines(),
        "libcudart13_import_failure_without_cu13_path (base A: yes)": "libcudart.so.13" in imp,
        "versions_line": [x for x in (_read(box / "versions.txt") or "").splitlines() if x.startswith("VERSIONS")],
    }
    return {"fatal_missing_present": present, "fatal_present": forbidden, "nondefault_args": args,
            "nondefault_args_equal_base_A_except_seed_and_tp": args_ok, "box_stack_check_pass": box_check.get("pass"),
            "aborted": aborted, "deviations_recorded": deviations,
            "pass": all(present.values()) and not any(forbidden.values()) and args_ok
            and box_check.get("pass") is True and not aborted}


def cmd_run() -> None:
    if REPORT.exists():
        raise SystemExit(f"refusing to overwrite {REPORT}")
    recipe = json.loads((K.REPO / "script/remote/auditbench/exact_stack/recipe.json").read_text())
    ref = json.loads(REF.read_text())
    if not json.loads(SELF.read_text())["all_as_expected"]:
        raise SystemExit("the gate's selftest did not pass; refusing to read A2")
    rows = [json.loads(x) for x in open(K.RESP["A2"])]
    man = {c["prompt_id"]: c for c in json.loads((ITEM / "inputs/prompts_manifest.json").read_text())["cells"]}
    keysA = {(json.loads(x)["prompt_id"], int(json.loads(x)["s"])) for x in open(K.RESP["A"])}
    keys = Counter((r["prompt_id"], int(r["s"])) for r in rows)
    nbos = Counter(r.get("prompt_leading_bos") for r in rows)
    g0 = {"leading_bos_counts": {str(k): v for k, v in nbos.items()},
          "rows_ids_equal_manifest_doubled": sum(1 for r in rows
                                                 if r.get("prompt_ids_sha256") == man[r["prompt_id"]]["ids_doubled_sha256"]),
          "rows_ids_equal_manifest_single": sum(1 for r in rows
                                                if r.get("prompt_ids_sha256") == man[r["prompt_id"]]["ids_single_sha256"])}
    uniform = len(nbos) == 1 and next(iter(nbos)) in (1, 2)
    g0["encoding"] = ("doubled" if uniform and next(iter(nbos)) == 2 else
                      "single" if uniform else "mixed or unreadable")
    g0["pass"] = (g0["encoding"] == "doubled" and g0["rows_ids_equal_manifest_doubled"] == len(rows)) or \
                 (g0["encoding"] == "single" and g0["rows_ids_equal_manifest_single"] == len(rows))
    g0["as_registered_expectation"] = g0["encoding"] == "doubled"
    other = {}
    for name in ("A", "B"):
        for x in open(K.RESP[name]):
            r = json.loads(x)
            other.setdefault(r["prompt_id"], set()).add(r["text"])
    by_p = {}
    for r in rows:
        by_p.setdefault(r["prompt_id"], []).append(r["text"])
    g1 = {"duplicates_within_prompt": sum(len(v) - len(set(v)) for v in by_p.values()),
          "equal_to_A_or_B": sum(1 for r in rows if r["text"] and r["text"] in other.get(r["prompt_id"], set()))}
    g1["pass"] = g1["duplicates_within_prompt"] == 0 and g1["equal_to_A_or_B"] == 0
    g2 = {"replies_with_template_tokens": sum(1 for r in rows if any(t in r["text"] for t in TEMPLATE_TOKENS))}
    g2["pass"] = g2["replies_with_template_tokens"] == 0
    fin = Counter(r.get("finish_reason") for r in rows)
    g3 = {"rows": len(rows), "unique_keys": len(keys), "keys_equal_base_A": set(keys) == keysA,
          "failed": sum(1 for r in rows if r["failed"]), "finish_reasons": dict(fin),
          "length_share": fin.get("length", 0) / max(len(rows), 1)}
    g3["pass"] = (len(rows) == 3456 and max(keys.values()) == 1 and g3["keys_equal_base_A"]
                  and g3["failed"] == 0 and g3["length_share"] >= 0.97)
    g4 = engine_checks(recipe)
    v = opening_values("A2", (0, 1))
    x = {k: float(np.mean([v[h][k] for h in (0, 1)])) for k in OPEN}
    p = pis(x, ref["D_mean"], ref["S_mean"])
    g5 = {"halves": v, "value": x, "pi": p, "mean_pi": float(np.mean(list(p.values()))), "pass": g5_rule(p)}
    R2, H2 = reply_table("A2")
    g6 = {}
    for k in REPLY + ["naming_rate"]:
        a2 = float(H2.mean()) if k == "naming_rate" else float(R2[k].mean())
        r = ref["reply_stats_16"][k]
        g6[k] = {"A2": a2, "A16": r["A16"], "B16": r["B16"], "dev_from_A": abs(a2 - r["A16"]),
                 "threshold": r["threshold"], "pass": abs(a2 - r["A16"]) <= r["threshold"]}
    rep = {"G0": g0, "G1": g1, "G2": g2, "G3": g3, "G4": g4, "G5": g5, "G6": g6,
           "G6_pass": all(x["pass"] for x in g6.values()),
           "a2_sha256": K.sha256_file(K.RESP["A2"]), "reference_sha256": K.sha256_file(REF)}
    rep["pass"] = all(rep[g]["pass"] for g in ("G0", "G1", "G2", "G3", "G4", "G5")) and rep["G6_pass"]
    print(K.dump(rep, REPORT))
    print(json.dumps({g: rep[g]["pass"] if g != "G6" else rep["G6_pass"] for g in
                      ("G0", "G1", "G2", "G3", "G4", "G5", "G6")}), "PASS" if rep["pass"] else "STOP: do not judge")
    sys.exit(0 if rep["pass"] else 1)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"reference": cmd_reference, "selftest": cmd_selftest, "run": cmd_run}.get(
        cmd, lambda: sys.exit(__doc__))()
