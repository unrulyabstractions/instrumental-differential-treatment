"""Judge A2 once on the full 101-axis registry with the original seat, through the OpenAI Batch API, capped in code.

    PY=.venv/bin/python; D=script/analysis/exact_stack_20261114
    $PY $D/j01_judge.py plan            # free: screen, plan, assert the seat byte for byte against base B
    $PY $D/j01_judge.py pilot           # 20 calls (~$0.02), priced from returned usage; gates below
    $PY $D/j01_judge.py drive           # layers s0-3 (rest), s4-7, s8-11, s12-15, then repairs and retries, then fold
    $PY $D/j01_judge.py status

The judging path is the one diag_20261113 used (README "Settings"): src.score.batch_judge_fill.plan_first_pass
over the screened rows, judge_system_prompt(2, domain, activation) from
configs/auditbench/nullext/score_nullext_base_B.json, asserted equal to base B's stored system string, and
openai_batch_line(call, "gpt-5-mini", reasoning_effort="low"), asserted equal to base B's stored request line
for base B's own first call. Every returned result must name gpt-5-mini-2025-08-07. Claude Haiku never judges here.

Money: es_ledger.Ledger, hard cap $20 in code (reserve the bound before a batch, settle the usage after);
`cloud_boxes_guard.py spend` runs before every submit and a failure refuses the submit. Expected cost $15.57
(base B's judging of 3,456 capped replies of this model on this registry, nullext/spend_ledger.json).

Pilot gates: 20 results; every model string gpt-5-mini-2025-08-07; at most one empty or unparsable reply; mean
cost of a 25-axis call at most $0.0014 (E1: $0.00107); median reasoning tokens at most 1,000; the plan priced at
the pilot's per-call costs at most $18. Layer gates (on layer 0, within minutes of its return): every model
string as above, no quota or credit error, the plan re-priced from layer 0's own usage at most $19; else stop.
`plan` refuses unless gate/g01_gate_report.json says pass.
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

import es_common as K
import es_ledger as L

sys.path.insert(0, str(K.REPO))
from src.score import batch_judge_fill as bj  # noqa: E402
from src.score.judge_prompts import judge_system_prompt  # noqa: E402

MODEL, SNAPSHOT, JUDGE_NAME, LEVEL = "gpt-5-mini", "gpt-5-mini-2025-08-07", "openai:gpt-5-mini", 2
CONFIG = json.loads((K.REPO / "configs/auditbench/nullext/score_nullext_base_B.json").read_text())
B_BATCH = K.AB / "nullext/base_B/responses/judge_batch"
GUARD = Path.home() / ".claude/hooks/cloud_boxes_guard.py"
QUOTA_WORDS = ("insufficient_quota", "billing_hard_limit", "credit_balance", "quota")
LAYERS = {"layer0": (0, 3), "layer1": (4, 7), "layer2": (8, 11), "layer3": (12, 15)}


def paths(a):
    jd = Path(a.dir) if a.dir else K.ITEM / "judge"
    resp = Path(a.responses) if a.responses else K.RESP["A2"]
    return jd, jd / "judge_batch", resp


def read_jsonl(p: Path):
    with open(p) as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def system_prompt() -> str:
    s = judge_system_prompt(LEVEL, CONFIG.get("domain", ""), CONFIG.get("activation", ""))
    with open(B_BATCH / "calls_first.jsonl") as fh:
        stored = json.loads(fh.readline())["system"]
    assert s == stored, "system prompt differs from base B's stored calls"
    return s


def call_row(c) -> dict:
    return {**c.manifest(), "system": c.system, "user": c.user}


def call_of(r: dict):
    return bj.JudgeCall(r["custom_id"], r["kind"], r["seat"], r["prompt_id"], int(r["s"]), int(r["start"]),
                        tuple(r["axis_ids"]), r["system"], r["user"], int(r["max_tokens"]))


def batch_line(c) -> dict:
    return bj.openai_batch_line(c, MODEL, reasoning_effort="low")


def assert_line_format() -> None:
    """Our batch line for base B's own first stored call must equal base B's stored request line."""
    with open(B_BATCH / "calls_first.jsonl") as fh:
        first = json.loads(fh.readline())
    with open(B_BATCH / "requests_first.jsonl") as fh:
        for line in fh:
            req = json.loads(line)
            if req["custom_id"] == first["custom_id"]:
                break
    assert batch_line(call_of(first)) == req, "batch line format differs from base B's stored request"


def spend_check() -> None:
    r = subprocess.run([sys.executable, str(GUARD), "spend"], capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise SystemExit(f"spend check failed (rc {r.returncode}); refusing to submit")
    print("\n".join(r.stdout.strip().splitlines()[-8:]), flush=True)


def cmd_plan(a) -> None:
    jd, bdir, resp = paths(a)
    if not a.dir:
        gate = K.ITEM / "gate/g01_gate_report.json"
        if not gate.exists() or not json.loads(gate.read_text()).get("pass"):
            raise SystemExit(f"{gate} missing or not passed: STOP, nothing is judged")
    if (jd / "plan.json").exists():
        raise SystemExit(f"{jd / 'plan.json'} exists")
    system = system_prompt()
    assert_line_format()
    rows, screened = bj.screen_responses(read_jsonl(resp))
    calls = bj.plan_first_pass({"base": rows}, K.AXES_FULL, system)
    ids = [c.custom_id for c in calls]
    assert len(ids) == len(set(ids))
    L.write_new(bdir / "calls_first.jsonl", "".join(json.dumps(call_row(c), sort_keys=True) + "\n" for c in calls))
    s0 = [c.custom_id for c in calls if c.s == 0]
    pilot = s0[:20]
    layers = {"pilot": pilot}
    for name, (lo, hi) in LAYERS.items():
        layers[name] = [c.custom_id for c in calls if lo <= c.s <= hi and c.custom_id not in set(pilot)]
    assert sum(len(v) for v in layers.values()) == len(calls)
    n25 = sum(1 for c in calls if len(c.axis_ids) == 25)
    bound = {k: L.batch_bound([batch_line(c) for c in calls if c.custom_id in set(v)])[0] for k, v in layers.items()}
    plan = {"responses": str(resp), "responses_sha256": K.sha256_file(resp), "rows": len(rows), "screened_out": screened,
            "calls": len(calls), "calls_25": n25, "calls_other": len(calls) - n25,
            "layers": {k: len(v) for k, v in layers.items()}, "bound_usd": {k: round(v, 4) for k, v in bound.items()},
            "system_equals_base_B": True, "line_format_equals_base_B": True, "model": MODEL,
            "expected_snapshot": SNAPSHOT, "planned_at": L.now(), "layer_ids": layers}
    L.write_new(jd / "plan.json", json.dumps(plan, indent=1))
    print(json.dumps({k: v for k, v in plan.items() if k != "layer_ids"}, indent=1))


def load_calls(bdir: Path, kind: str = "first") -> dict:
    return {r["custom_id"]: call_of(r) for r in read_jsonl(bdir / f"calls_{kind}.jsonl")}


def submit(a, name: str, ids: list[str], kind: str = "first") -> dict:
    jd, bdir, _ = paths(a)
    if a.dir:
        raise SystemExit("a test directory never submits")
    spend_check()
    calls = load_calls(bdir, kind)
    lines = [batch_line(calls[i]) for i in ids]
    led = L.Ledger(jd / "spend_ledger.jsonl")
    rec = L.submit_batch(led, name, bdir, lines)
    print(json.dumps(rec, indent=1), flush=True)
    return rec


def per_call(bdir: Path, name: str, calls: dict) -> list[dict]:
    pin, pout = L.PRICE_BATCH
    out = []
    for e in read_jsonl(bdir / f"raw_{name}.jsonl"):
        c = calls.get(e["custom_id"])
        text, err = L.reply_of(e)
        pt, ct, rt, model = L.usage_of(e)
        parsed = bj._parsed(text) if text else {}
        out.append({"custom_id": e["custom_id"], "n_axes": len(c.axis_ids) if c else None,
                    "cost": pt * pin + ct * pout, "reasoning_tokens": rt, "model": model, "error": err,
                    "parsed_all": bool(c) and all(x in parsed for x in c.axis_ids)})
    return out


def price_plan(pc: list[dict], plan: dict) -> float:
    c25 = [p["cost"] for p in pc if p["n_axes"] == 25]
    co = [p["cost"] for p in pc if p["n_axes"] != 25]
    m25 = statistics.mean(c25) if c25 else 0.0014
    mo = statistics.mean(co) if co else 0.0004
    return plan["calls_25"] * m25 + plan["calls_other"] * mo


def cmd_pilot(a) -> None:
    jd, bdir, _ = paths(a)
    plan = json.loads((jd / "plan.json").read_text())
    if not (bdir / "batch_pilot.json").exists():
        submit(a, "pilot", plan["layer_ids"]["pilot"])
    led = L.Ledger(jd / "spend_ledger.jsonl")
    while True:
        summ = L.fetch_batch(led, bdir, "pilot")
        if summ is not None:
            break
        time.sleep(30)
    pc = per_call(bdir, "pilot", load_calls(bdir))
    c25 = [p["cost"] for p in pc if p["n_axes"] == 25]
    rts = sorted(p["reasoning_tokens"] for p in pc)
    rep = {"n": len(pc), "models": summ["models"], "actual_usd": summ["actual_usd"],
           "mean_cost_25axis": statistics.mean(c25) if c25 else None,
           "median_reasoning_tokens": rts[len(rts) // 2] if rts else None,
           "empty_or_unparsable": sum(1 for p in pc if p["error"] or not p["parsed_all"]),
           "projected_plan_usd": round(price_plan(pc, plan), 4)}
    gates = {"n_ok": rep["n"] == 20, "snapshot_ok": set(summ["models"]) == {SNAPSHOT},
             "parse_ok": rep["empty_or_unparsable"] <= 1,
             "cost_ok": (rep["mean_cost_25axis"] or 9) <= 0.0014,
             "reasoning_ok": (rep["median_reasoning_tokens"] or 9e9) <= 1000,
             "projection_ok": rep["projected_plan_usd"] <= 18.0}
    rep.update({"gates": gates, "pass": all(gates.values()), "per_call": pc})
    L.write_new(jd / "pilot_report.json", json.dumps(rep, indent=1))
    print(json.dumps({k: v for k, v in rep.items() if k != "per_call"}, indent=1))
    if not rep["pass"]:
        raise SystemExit("PILOT FAILED: stop and report; nothing more is submitted")


def ended(bdir: Path, name: str) -> bool:
    return (bdir / f"raw_{name}.jsonl").exists()


def check_layer(bdir: Path, name: str, plan: dict, calls: dict) -> None:
    summ = json.loads((bdir / f"fetched_{name}.json").read_text())
    if set(m for m in summ["models"] if m) - {SNAPSHOT}:
        (bdir.parent / "STOP").write_text(f"{L.now()} {name} returned {summ['models']}\n")
        raise SystemExit(f"STOP: {name} returned models {summ['models']}")
    if any(w in " ".join(summ.get("errors_head") or []).lower() for w in QUOTA_WORDS):
        (bdir.parent / "STOP").write_text(f"{L.now()} {name} quota/credit error\n")
        raise SystemExit(f"STOP: quota or credit error in {name}")
    if name == "layer0":
        proj = price_plan(per_call(bdir, name, calls), plan)
        print(f"plan re-priced from layer0 usage: ${proj:.2f}", flush=True)
        L.write_new(bdir.parent / "layer0_pricing.json", json.dumps({"projected_plan_usd": proj, "ts": L.now()}))
        if proj > 19.0:
            (bdir.parent / "STOP").write_text(f"{L.now()} layer0 projects ${proj:.2f}\n")
            raise SystemExit(f"STOP: layer0 projects ${proj:.2f} > $19")


def cmd_drive(a) -> None:
    jd, bdir, _ = paths(a)
    plan = json.loads((jd / "plan.json").read_text())
    if not json.loads((jd / "pilot_report.json").read_text())["pass"]:
        raise SystemExit("the pilot did not pass")
    calls = load_calls(bdir)
    led = L.Ledger(jd / "spend_ledger.jsonl")
    order = list(LAYERS)
    while True:
        if (jd / "STOP").exists():
            raise SystemExit(f"STOP file present: {(jd / 'STOP').read_text()}")
        for name in order:
            if (bdir / f"batch_{name}.json").exists() and not ended(bdir, name):
                if L.fetch_batch(led, bdir, name) is not None:
                    check_layer(bdir, name, plan, calls)
        pending = [n for n in order if not (bdir / f"batch_{n}.json").exists()]
        layer0_done = ended(bdir, "layer0") and (jd / "layer0_pricing.json").exists()
        for name in pending:
            if name != "layer0" and not layer0_done:
                break
            bound = L.batch_bound([batch_line(calls[i]) for i in plan["layer_ids"][name]])[0]
            if led.committed() + bound > L.HARD_CAP_USD:
                break  # waits for in-flight layers to settle
            submit(a, name, plan["layer_ids"][name])
        if all(ended(bdir, n) for n in order):
            break
        time.sleep(60)
    repairs_and_fold(a, plan, calls, led)


def replies(bdir: Path, repair: bool) -> dict:
    out: dict = {}
    for p in sorted(bdir.glob("raw_*.jsonl")):
        nm = p.stem[len("raw_"):]
        if nm.startswith("repair") != repair:
            continue
        for e in read_jsonl(p):
            t, _ = L.reply_of(e)
            if t is not None or e["custom_id"] not in out:
                out[e["custom_id"]] = t if t is not None else out.get(e["custom_id"])
    return out


def repairs_and_fold(a, plan, calls, led) -> None:
    jd, bdir, resp = paths(a)
    rows, _ = bj.screen_responses(read_jsonl(resp))
    first = list(calls.values())
    for rnd in (1, 2):
        rep = replies(bdir, False)
        missing = [c for c in first if rep.get(c.custom_id) is None]
        name = f"retry{rnd}"
        if missing and not (bdir / f"batch_{name}.json").exists():
            L.write_new(bdir / f"calls_{name}.jsonl", "".join(json.dumps(call_row(c), sort_keys=True) + "\n"
                                                               for c in missing))
            submit(a, name, [c.custom_id for c in missing], kind=name)
        if (bdir / f"batch_{name}.json").exists():
            while not ended(bdir, name) and L.fetch_batch(led, bdir, name) is None:
                time.sleep(60)
    texts = {("base", r["prompt_id"], int(r["s"])): r["text"] for r in rows}
    rcalls = bj.plan_repairs(first, replies(bdir, False), K.AXES_FULL, texts)
    if rcalls and not (bdir / "batch_repair.json").exists():
        L.write_new(bdir / "calls_repair.jsonl", "".join(json.dumps(call_row(c), sort_keys=True) + "\n" for c in rcalls))
        submit(a, "repair", [c.custom_id for c in rcalls], kind="repair")
    if (bdir / "batch_repair.json").exists():
        while not ended(bdir, "repair") and L.fetch_batch(led, bdir, "repair") is None:
            time.sleep(60)
    rep_calls = [call_of(r) for r in read_jsonl(bdir / "calls_repair.jsonl")] if (bdir / "calls_repair.jsonl").exists() else []
    out, unscorable = bj.fold_rows({"base": rows}, first, replies(bdir, False), rep_calls, replies(bdir, True),
                                   JUDGE_NAME, LEVEL)
    models = {}
    for p in sorted(bdir.glob("fetched_*.json")):
        for m, n in json.loads(p.read_text())["models"].items():
            models[m] = models.get(m, 0) + n
    meta = {"route": "openai_batch", "model_snapshots": sorted(m for m in models if m), "item": "exact_stack_20261114"}
    L.write_new(jd / "verdicts_base.jsonl", "".join(json.dumps({**r, "es": meta}) + "\n" for r in out["base"]))
    nulls = sum(1 for r in out["base"] for v in r["verdicts"].values() if v is None)
    report = {"rows_in": len(rows), "rows_out": len(out["base"]), "unscorable": unscorable, "null_verdicts": nulls,
              "repair_calls": len(rep_calls), "spend_settled_usd": round(led.settled(), 6),
              "unsettled": led.unsettled(), "models": models, "folded_at": L.now()}
    L.write_new(jd / "fold_report.json", json.dumps(report, indent=1))
    print(json.dumps({k: v for k, v in report.items() if k != "unscorable"}, indent=1))


def cmd_status(a) -> None:
    jd, bdir, _ = paths(a)
    led = L.Ledger(jd / "spend_ledger.jsonl")
    print(f"committed ${led.committed():.4f} settled ${led.settled():.4f} unsettled {led.unsettled()}")
    for p in sorted(bdir.glob("batch_*.json")):
        nm = p.stem[len("batch_"):]
        print(nm, "fetched" if ended(bdir, nm) else "in flight")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cmd", choices=["plan", "pilot", "drive", "status"])
    ap.add_argument("--dir", help="a test directory (plan only; never submits)")
    ap.add_argument("--responses", help="a stand-in responses file for a plan test")
    a = ap.parse_args()
    {"plan": cmd_plan, "pilot": cmd_pilot, "drive": cmd_drive, "status": cmd_status}[a.cmd](a)


if __name__ == "__main__":
    main()
