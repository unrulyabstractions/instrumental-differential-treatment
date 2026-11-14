"""Spend-gated driver for the name-masked judge probe, over the project's batch judge tool.

    R=script/analysis/reanalysis_2026_11/masked_judge_runner.py
    uv run --with tiktoken python $R credit-check --cap 8
    uv run --with tiktoken python $R plan    --stage-dir D [--limit-rows N]
    uv run --with tiktoken python $R submit  --stage-dir D --stage first --cap 8 [--dry-run]
    uv run --with tiktoken python $R finish  --stage-dir D --cap 8    # wait, retry, repair, fold
    uv run --with tiktoken python $R ledger

Every judge call goes through ``script/data/batch_judge_fill.py`` (the batch
path a test pins to the live panel: same prompts, axis shuffle, chunks, token
caps, parse and fold), at the paper's seat read from the stored verdicts. That
tool keeps its ledger at ``IDT_BATCH_LEDGER``, set here to this probe's output
folder, and refuses a batch whose upper bound would pass its cap.

This driver adds an append-only ledger, ``ledger.jsonl``: one line per credit
check, submit, refusal and fetch, with the committed total after it. The one
live call (the credit check) is priced at standard rates and counted against
the same cap, so the cap handed to the batch tool is the cap minus that spend.
Retries and repairs are batches like any other and pass the same gate.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "out/main/auditbench/contextual_optimism/masked_judge_20261113"
LEDGER = OUT / "ledger.jsonl"
BATCH_LEDGER = OUT / "spend_ledger.json"
TOOL = [sys.executable, str(REPO / "script/data/batch_judge_fill.py")]
SCORE_CONFIG = OUT / "score_config.json"
SEAT_FROM = REPO / "out/main/auditbench/contextual_optimism/judge_mini/verdicts_target.jsonl"
BATCH_PRICE = {"in": 0.125, "out": 1.0}      # gpt-5-mini Batch, USD per M, live page 2026-11-13
STANDARD_PRICE = {"in": 0.25, "out": 2.0}    # gpt-5-mini Standard
MAX_ATTEMPTS = 4                              # the panel's attempts per call


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def log(msg: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def append(event: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"t": now(), **event}, sort_keys=True) + "\n")


def _events() -> list[dict]:
    if not LEDGER.exists():
        return []
    return [json.loads(x) for x in LEDGER.read_text().splitlines() if x.strip()]


def nonbatch_spend() -> float:
    """Live calls outside the batch tool, at their recorded bound until priced."""
    total = 0.0
    for e in _events():
        if e["event"] == "credit_check_sent":
            total += e["bound_usd"]
        elif e["event"] == "credit_check_priced":
            total += e["actual_usd"] - e["bound_usd"]
    return total


def batch_committed() -> float:
    if not BATCH_LEDGER.exists():
        return 0.0
    led = json.loads(BATCH_LEDGER.read_text())
    return sum(b["actual_usd"] if b.get("actual_usd") is not None else b["bound_usd"]
               for b in led["batches"])


def committed() -> float:
    return nonbatch_spend() + batch_committed()


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = {**os.environ, "IDT_BATCH_LEDGER": str(BATCH_LEDGER)}
    out = subprocess.run([*TOOL, *args], capture_output=True, text=True, cwd=REPO, env=env)
    if check and out.returncode != 0:
        raise SystemExit(f"FAILED {' '.join(args[:3])}: {(out.stderr or out.stdout)[-1500:]}")
    return out


# ---------------------------------------------------------------- credit check
def cmd_credit_check(a) -> None:
    """One tiny live request: does the key answer, and is there credit."""
    import openai
    import tiktoken
    system, user, max_out = "Answer with one word.", "Say OK.", 64
    enc = tiktoken.get_encoding("o200k_base")
    n_in = 16 + len(enc.encode(system)) + len(enc.encode(user))
    bound = (n_in * STANDARD_PRICE["in"] + max_out * STANDARD_PRICE["out"]) / 1e6
    total = committed()
    if total + bound > a.cap:
        append({"event": "refused", "what": "credit_check", "bound_usd": round(bound, 6),
                "committed_usd": round(total, 6), "cap_usd": a.cap})
        raise SystemExit(f"REFUSED: credit check ${total + bound:.6f} would exceed the ${a.cap:.2f} cap")
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set")
    append({"event": "credit_check_sent", "model": "gpt-5-mini", "bound_usd": round(bound, 6),
            "committed_usd_before": round(total, 6), "cap_usd": a.cap})
    client = openai.OpenAI(max_retries=0)
    try:
        r = client.chat.completions.create(
            model="gpt-5-mini", reasoning_effort="low", max_completion_tokens=max_out,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    except openai.APIStatusError as exc:
        append({"event": "credit_check_priced", "bound_usd": round(bound, 6), "actual_usd": 0.0,
                "status": exc.status_code, "error": str(exc)[:300]})
        raise SystemExit(f"credit check failed: {exc.status_code} {str(exc)[:300]}")
    u = r.usage
    actual = (u.prompt_tokens * STANDARD_PRICE["in"] + u.completion_tokens * STANDARD_PRICE["out"]) / 1e6
    append({"event": "credit_check_priced", "bound_usd": round(bound, 6),
            "actual_usd": round(actual, 6), "prompt_tokens": u.prompt_tokens,
            "completion_tokens": u.completion_tokens, "model_returned": r.model,
            "reply": (r.choices[0].message.content or "")[:40], "status": 200})
    log(f"credit check ok: model {r.model}, {u.prompt_tokens} in, {u.completion_tokens} out, "
        f"${actual:.6f}; committed now ${committed():.6f}")


# ------------------------------------------------------------- batch commands
def cmd_plan(a) -> None:
    args = ["plan-auditbench", "--stage-dir", str(_sd(a.stage_dir)), "--score-config",
            str(SCORE_CONFIG.relative_to(REPO)), "--seat-from", str(SEAT_FROM.relative_to(REPO))]
    if a.limit_rows:
        args += ["--limit-rows", str(a.limit_rows)]
    out = run(*args)
    print(out.stdout[-2500:])


def _sd(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else REPO / p


def bdir(stage_dir: Path) -> Path:
    return stage_dir / "judge_batch"


def submit(stage_dir: Path, stage: str, cap: float, dry_run: bool = False) -> bool:
    b = bdir(stage_dir)
    if not (b / f"tokens_{stage}.json").exists():
        run("count", "--stage-dir", str(stage_dir), "--stage", stage)
    tool_cap = cap - nonbatch_spend()
    args = ["submit", "--stage-dir", str(stage_dir), "--stage", stage,
            "--price-in", str(BATCH_PRICE["in"]), "--price-out", str(BATCH_PRICE["out"]),
            "--cap", f"{tool_cap:.6f}"]
    if dry_run:
        args.append("--dry-run")
    out = run(*args, check=False)
    text = (out.stdout + out.stderr).strip()
    tokens = json.loads((b / f"tokens_{stage}.json").read_text())
    bound = (tokens["input_tokens"] * BATCH_PRICE["in"]
             + tokens["max_output_tokens"] * BATCH_PRICE["out"]) / 1e6
    if out.returncode != 0:
        append({"event": "refused", "stage_dir": str(stage_dir.relative_to(REPO)), "stage": stage,
                "bound_usd": round(bound, 6), "committed_usd": round(committed(), 6),
                "cap_usd": cap, "tool_cap_usd": round(tool_cap, 6), "message": text[-300:]})
        log(f"REFUSED {stage_dir.name}/{stage}: {text.splitlines()[-1]}")
        return False
    if dry_run:
        log(f"dry run {stage_dir.name}/{stage}: {text.splitlines()[0]}")
        return True
    rec = json.loads((b / f"batch_{stage}.json").read_text())
    append({"event": "submit", "stage_dir": str(stage_dir.relative_to(REPO)), "stage": stage,
            "batch_id": rec["batch_id"], "n_requests": rec["n_requests"],
            "bound_usd": rec["bound_usd"], "committed_usd_after": round(committed(), 6),
            "cap_usd": cap})
    log(f"submitted {stage_dir.name}/{stage} {rec['batch_id']} bound ${rec['bound_usd']:.4f}; "
        f"committed ${committed():.4f} of ${cap:.2f}")
    return True


def cmd_submit(a) -> None:
    if not submit(_sd(a.stage_dir), a.stage, a.cap, a.dry_run):
        raise SystemExit(1)


def _submitted(stage_dir: Path) -> list[str]:
    return sorted(p.name[len("batch_"):-len(".json")] for p in bdir(stage_dir).glob("batch_*.json"))


def fetch_pending(stage_dir: Path, poll: int) -> None:
    for name in _submitted(stage_dir):
        if (bdir(stage_dir) / f"raw_{name}.jsonl").exists():
            continue
        while True:
            line = run("status", "--stage-dir", str(stage_dir), "--stage", name).stdout.strip().splitlines()[-1]
            status = line.split()[1]
            if status == "completed":
                break
            if status in ("failed", "expired", "cancelled", "cancelling"):
                append({"event": "alarm", "stage_dir": str(stage_dir.relative_to(REPO)),
                        "stage": name, "status": line})
                raise SystemExit(f"ALARM {stage_dir.name} {name} is {status}: {line}")
            time.sleep(poll)
        run("fetch", "--stage-dir", str(stage_dir), "--stage", name,
            "--price-in", str(BATCH_PRICE["in"]), "--price-out", str(BATCH_PRICE["out"]))
        s = json.loads((bdir(stage_dir) / f"fetched_{name}.json").read_text())
        append({"event": "fetch", "stage_dir": str(stage_dir.relative_to(REPO)), "stage": name,
                "batch_id": s["batch_id"], "n_results": s["n_results"], "n_errors": s["n_errors"],
                "input_tokens": s["input_tokens"], "output_tokens": s["output_tokens"],
                "actual_usd": s["actual_usd"], "committed_usd_after": round(committed(), 6)})
        log(f"fetched {stage_dir.name}/{name}: {s['n_results']} results, {s['n_errors']} errors, "
            f"${s['actual_usd']:.4f}; committed ${committed():.4f}")


def _stage_names(stage_dir: Path) -> set[str]:
    return {p.name[len("calls_"):-len(".jsonl")] for p in bdir(stage_dir).glob("calls_*.jsonl")}


def _submit_new(stage_dir: Path, before: set[str], cap: float) -> bool:
    new = sorted(_stage_names(stage_dir) - before)
    for name in new:
        if not submit(stage_dir, name, cap):
            raise SystemExit(f"stopped: {name} refused by the cap")
    return bool(new)


def _retry_until_done(stage_dir: Path, kind: str, cap: float, poll: int) -> None:
    while True:
        fetch_pending(stage_dir, poll)
        before = _stage_names(stage_dir)
        run("retry", "--stage-dir", str(stage_dir), "--kind", kind)
        if not _submit_new(stage_dir, before, cap):
            return


def cmd_finish(a) -> None:
    stage_dir = _sd(a.stage_dir)
    if "first" not in _submitted(stage_dir):
        raise SystemExit(f"{stage_dir}: first stage not submitted")
    _retry_until_done(stage_dir, "first", a.cap, a.poll)
    b = bdir(stage_dir)
    if not (b / "calls_repair.jsonl").exists():
        before = _stage_names(stage_dir)
        log(f"{stage_dir.name} " + run("repair", "--stage-dir", str(stage_dir)).stdout.strip().splitlines()[-1])
        _submit_new(stage_dir, before, a.cap)
    if (b / "calls_repair.jsonl").exists():
        _retry_until_done(stage_dir, "repair", a.cap, a.poll)
    run("fold", "--stage-dir", str(stage_dir))
    rep = json.loads((b / "fold_report.json").read_text())
    append({"event": "folded", "stage_dir": str(stage_dir.relative_to(REPO)), "rows": rep["rows"],
            "unscorable": len(rep["unscorable"]), "null_verdicts": rep["null_verdicts"],
            "repaired": rep["repaired"], "committed_usd_after": round(committed(), 6)})
    log(f"FOLDED {stage_dir.name} rows={rep['rows']} unscorable={len(rep['unscorable'])} "
        f"nulls={rep['null_verdicts']} repaired={rep['repaired']}; committed ${committed():.4f}")


def cmd_ledger(a) -> None:
    print(json.dumps({"nonbatch_usd": round(nonbatch_spend(), 6),
                      "batch_committed_usd": round(batch_committed(), 6),
                      "committed_usd": round(committed(), 6),
                      "events": len(_events())}, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("credit-check")
    p.add_argument("--cap", type=float, required=True)
    p = sub.add_parser("plan")
    p.add_argument("--stage-dir", required=True)
    p.add_argument("--limit-rows", type=int, default=0)
    p = sub.add_parser("submit")
    p.add_argument("--stage-dir", required=True)
    p.add_argument("--stage", default="first")
    p.add_argument("--cap", type=float, required=True)
    p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("finish")
    p.add_argument("--stage-dir", required=True)
    p.add_argument("--cap", type=float, required=True)
    p.add_argument("--poll", type=int, default=60)
    sub.add_parser("ledger")
    a = ap.parse_args()
    {"credit-check": cmd_credit_check, "plan": cmd_plan, "submit": cmd_submit,
     "finish": cmd_finish, "ledger": cmd_ledger}[a.cmd](a)


if __name__ == "__main__":
    main()
