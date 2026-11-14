"""Judge the pooled-base stages through the project's own batch path, under the item cap.

    PY=.venv/bin/python
    $PY script/analysis/reanalysis_2026_11/pooled_base_judge.py config
    $PY script/analysis/reanalysis_2026_11/pooled_base_judge.py stage --src c1_cut400 --s-min 0 --s-max 3 --name sc1_c1cut_s00-03
    $PY script/analysis/reanalysis_2026_11/pooled_base_judge.py drive sc1_c1cut_s00-03 c1_s00-03 ...
    $PY script/analysis/reanalysis_2026_11/pooled_base_judge.py zero-cap --name sc1_c1cut_s00-03

Every judging step is ``script/data/batch_judge_fill.py`` itself (plan-auditbench,
count, submit, status, fetch, retry, repair, fold), with the nulls' seat read from
``controls/flattery/judge_mini/verdicts_target.jsonl`` and the score config
``score_pooled_base.json`` (base B's, ``responses_dir`` changed). This file adds
only what the item needs around it:

* ``--cap`` at each submit is $48 minus the generation ledger's committed spend
  minus the live-call ledger's spend; ``batch_judge_fill`` adds the judge
  ledger's own committed spend (``IDT_BATCH_LEDGER`` = ``judge_spend_ledger.json``).
* Stages go in strictly in the order given. A refused submit waits while any
  judge batch is in flight; with none in flight the stage and every later one
  are dropped (DESIGN_AMENDMENTS A1).
* After each fetch, every successful result must report model
  ``gpt-5-mini-2025-08-07``, and any quota or credit error stops all further
  submits (A3). The share of calls that ended on length is recorded.
* ``python3 ~/.claude/hooks/cloud_boxes_guard.py spend`` runs before every submit.

``drive`` polls every 60 seconds until every named stage is folded or dropped,
and logs each action to ``judge/drive.log``.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
ITEM = REPO / "out/main/auditbench/pooled_base_20261113"
JUDGE = ITEM / "judge"
LEDGER = ITEM / "judge_spend_ledger.json"
CONFIG = ITEM / "score_pooled_base.json"
SEAT_FROM = "out/main/auditbench/controls/flattery/judge_mini/verdicts_target.jsonl"
BASE_B_CONFIG = REPO / "configs/auditbench/nullext/score_nullext_base_B.json"
TOOL = REPO / "script/data/batch_judge_fill.py"
PY = REPO / ".venv/bin/python"
PRICE_IN, PRICE_OUT = "0.125", "1.0"
ITEM_CAP = 48.0
EXPECTED_MODEL = "gpt-5-mini-2025-08-07"
STOP_FILE = JUDGE / "STOP"
QUOTA_WORDS = ("insufficient_quota", "credit", "billing", "quota")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pooled_base_generate import _live_spent, generation_committed  # noqa: E402


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    JUDGE.mkdir(parents=True, exist_ok=True)
    line = f"{_now()} {msg}"
    print(line, flush=True)
    with (JUDGE / "drive.log").open("a") as fh:
        fh.write(line + "\n")


def tool(*args: str) -> subprocess.CompletedProcess:
    # ``count`` needs tiktoken, which the Mac's venv lacks (it arrives only with
    # the vllm extra). POOLED_BASE_EXTRA_PATH points at a directory holding just
    # tiktoken and the packages the venv lacks, so nothing in the venv is shadowed.
    extra = os.environ.get("POOLED_BASE_EXTRA_PATH", "")
    env = {**os.environ, "IDT_BATCH_LEDGER": str(LEDGER),
           "PYTHONPATH": os.pathsep.join(p for p in (str(REPO), extra) if p)}
    return subprocess.run([str(PY), str(TOOL), *args], cwd=REPO, env=env,
                          capture_output=True, text=True)


def rel(p: Path) -> str:
    return str(p.relative_to(REPO))


def cmd_config(_a) -> None:
    if CONFIG.exists():
        raise SystemExit(f"refusing to overwrite {CONFIG}")
    cfg = json.loads(BASE_B_CONFIG.read_text())
    cfg["responses_dir"] = rel(ITEM)
    CONFIG.write_text(json.dumps(cfg, indent=2) + "\n")
    print(CONFIG.read_text())


def cmd_stage(a) -> None:
    src = ITEM / a.src / "responses_base.jsonl"
    out_dir = JUDGE / a.name
    out = out_dir / "responses_base.jsonl"
    if out_dir.exists():
        raise SystemExit(f"refusing to write into existing {out_dir}")
    rows = [json.loads(x) for x in src.open() if x.strip()]
    keep = [r for r in rows if a.s_min <= int(r["s"]) <= a.s_max]
    keys = {(r["prompt_id"], int(r["s"])) for r in keep}
    if len(keys) != len(keep):
        raise SystemExit("duplicate (prompt_id, s) in the stage")
    expect = 216 * (a.s_max - a.s_min + 1)
    if len(keep) != expect:
        raise SystemExit(f"{len(keep)} rows, expected {expect}")
    out_dir.mkdir(parents=True)
    out.write_text("".join(json.dumps(r) + "\n" for r in keep))
    (out_dir / "stage_source.json").write_text(json.dumps(
        {"source": rel(src), "s_min": a.s_min, "s_max": a.s_max, "rows": len(keep)}, indent=2))
    print(f"{out}: {len(keep)} rows")


def committed_judge() -> tuple[float, int]:
    if not LEDGER.exists():
        return 0.0, 0
    batches = json.loads(LEDGER.read_text())["batches"]
    return (sum(b["actual_usd"] if b.get("actual_usd") is not None else b["bound_usd"]
                for b in batches),
            sum(1 for b in batches if b.get("actual_usd") is None))


def generation_running() -> bool:
    """True while a generation process holds ``generation.lock``."""
    import fcntl
    with (ITEM / "generation.lock").open("a") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(fh, fcntl.LOCK_UN)
        return False


def submit_cap() -> float:
    """$48 less generation and live spend, and less a reserve for the rest of a
    draw while one is being generated (POOLED_BASE_GEN_RESERVE, dollars)."""
    reserve = float(os.environ.get("POOLED_BASE_GEN_RESERVE", "0")) if generation_running() else 0.0
    return ITEM_CAP - generation_committed()["committed_usd"] - _live_spent() - reserve


def bdir(name: str) -> Path:
    return JUDGE / name / "judge_batch"


def current_stage(name: str) -> str | None:
    """The latest stage whose calls exist: first, first_retryN, repair, repair_retryN."""
    b = bdir(name)
    if not (b / "calls_first.jsonl").exists():
        return None
    def n_of(kind):
        return sorted((int(p.stem.rsplit("retry", 1)[1]) for p in b.glob(f"calls_{kind}_retry*.jsonl")))
    if (b / "calls_repair.jsonl").exists():
        r = n_of("repair")
        return f"repair_retry{r[-1]}" if r else "repair"
    r = n_of("first")
    return f"first_retry{r[-1]}" if r else "first"


def post_fetch_checks(name: str, stage: str) -> dict:
    b = bdir(name)
    models, finish, n_ok, quota = {}, {}, 0, []
    for line in (b / f"raw_{stage}.jsonl").open():
        if not line.strip():
            continue
        e = json.loads(line)
        body = ((e.get("response") or {}).get("body") or {})
        if body.get("model"):
            models[body["model"]] = models.get(body["model"], 0) + 1
        for c in body.get("choices") or []:
            finish[c.get("finish_reason")] = finish.get(c.get("finish_reason"), 0) + 1
            n_ok += 1
        blob = json.dumps(e.get("error") or "") + json.dumps(
            body.get("error") or "") if (e.get("error") or body.get("error")) else ""
        if blob and any(w in blob.lower() for w in QUOTA_WORDS):
            quota.append(e.get("custom_id"))
    fetched = json.loads((b / f"fetched_{stage}.json").read_text())
    for cid, err in (fetched.get("errors") or {}).items():
        if any(w in err.lower() for w in QUOTA_WORDS):
            quota.append(cid)
    record = {"stage": stage, "models": models, "finish_reasons": finish,
              "share_length": (finish.get("length", 0) / n_ok) if n_ok else None,
              "n_errors": fetched.get("n_errors"), "quota_errors": sorted(set(quota)),
              "actual_usd": fetched.get("actual_usd"),
              "input_tokens": fetched.get("input_tokens"), "output_tokens": fetched.get("output_tokens"),
              "model_ok": set(models) <= {EXPECTED_MODEL} and bool(models)}
    out = b / f"checks_{stage}.json"
    if not out.exists():
        out.write_text(json.dumps(record, indent=2, sort_keys=True))
    return record


def spend_table() -> None:
    r = subprocess.run(["python3", str(Path.home() / ".claude/hooks/cloud_boxes_guard.py"), "spend"],
                       capture_output=True, text=True)
    with (JUDGE / "spend_checks.log").open("a") as fh:
        fh.write(f"=== {_now()}\n{r.stdout}{r.stderr}\n")


def step(name: str, may_submit: bool) -> str:
    """Advance one stage by one action. Returns its state."""
    sd = JUDGE / name
    b = bdir(name)
    if (sd / "verdicts_base.jsonl").exists():
        return "folded"
    if (sd / "DROPPED").exists():
        return "dropped"
    if not (sd / "responses_base.jsonl").exists():
        return "waiting_for_rows"
    if not (b / "plan.json").exists():
        r = tool("plan-auditbench", "--stage-dir", rel(sd), "--score-config", rel(CONFIG),
                 "--seat-from", SEAT_FROM)
        log(f"[{name}] plan rc={r.returncode} {r.stdout[-300:]} {r.stderr[-300:]}")
        if r.returncode:
            raise SystemExit(f"plan failed for {name}")
        return "planned"
    stage = current_stage(name)
    if not (b / f"tokens_{stage}.json").exists():
        r = tool("count", "--stage-dir", rel(sd), "--stage", stage)
        log(f"[{name}] count {stage} rc={r.returncode} {r.stdout[-300:]} {r.stderr[-300:]}")
        if r.returncode:
            raise SystemExit(f"count failed for {name} {stage}")
        return "counted"
    if not (b / f"batch_{stage}.json").exists():
        if not may_submit:
            return "blocked"
        if STOP_FILE.exists():
            return "stopped"
        spend_table()
        cap = submit_cap()
        r = tool("submit", "--stage-dir", rel(sd), "--stage", stage, "--price-in", PRICE_IN,
                 "--price-out", PRICE_OUT, "--cap", f"{cap:.4f}")
        log(f"[{name}] submit {stage} cap ${cap:.4f} rc={r.returncode} "
            f"{r.stdout[-400:]} {r.stderr[-400:]}")
        if r.returncode:
            if "REFUSED" in (r.stdout + r.stderr):
                _, in_flight = committed_judge()
                if in_flight == 0:
                    (sd / "DROPPED").write_text(f"{_now()} refused with no batch in flight\n"
                                                f"{r.stdout}{r.stderr}")
                    log(f"[{name}] DROPPED: refused with nothing in flight")
                    return "dropped"
                return "refused_waiting"
            raise SystemExit(f"submit failed for {name} {stage}")
        return "submitted"
    if not (b / f"fetched_{stage}.json").exists():
        r = tool("status", "--stage-dir", rel(sd), "--stage", stage)
        words = r.stdout.split()
        status = words[1] if len(words) > 1 else f"unknown(rc={r.returncode})"
        if status == "completed":
            f = tool("fetch", "--stage-dir", rel(sd), "--stage", stage, "--price-in", PRICE_IN,
                     "--price-out", PRICE_OUT)
            log(f"[{name}] fetch {stage} rc={f.returncode} {f.stdout[-500:]} {f.stderr[-300:]}")
            if f.returncode:
                raise SystemExit(f"fetch failed for {name} {stage}")
            chk = post_fetch_checks(name, stage)
            log(f"[{name}] checks {stage}: {json.dumps(chk)[:600]}")
            if not chk["model_ok"]:
                STOP_FILE.write_text(f"{_now()} {name} {stage}: models {chk['models']}\n")
                log(f"STOP: unexpected judge model in {name} {stage}")
            if chk["quota_errors"]:
                STOP_FILE.write_text(f"{_now()} {name} {stage}: quota errors {chk['quota_errors'][:5]}\n")
                log(f"STOP: quota or credit error in {name} {stage}")
            return "fetched"
        if status in ("failed", "expired", "cancelled", "cancelling"):
            STOP_FILE.write_text(f"{_now()} {name} {stage}: {status}\n")
            log(f"STOP: batch {name} {stage} ended {status}")
            return "stopped"
        return "in_flight"
    # Fetched: retry failures, then repair short chunks, then fold.
    kind = "repair" if stage.startswith("repair") else "first"
    before = current_stage(name)
    r = tool("retry", "--stage-dir", rel(sd), "--kind", kind)
    log(f"[{name}] retry {kind} rc={r.returncode} {r.stdout.strip()[-200:]}")
    if r.returncode:
        raise SystemExit(f"retry failed for {name}")
    if current_stage(name) != before:
        return "retry_planned"
    if kind == "first":
        r = tool("repair", "--stage-dir", rel(sd))
        log(f"[{name}] repair rc={r.returncode} {r.stdout.strip()[-200:]}")
        if r.returncode:
            raise SystemExit(f"repair failed for {name}")
        if current_stage(name) != before:
            return "repair_planned"
    r = tool("fold", "--stage-dir", rel(sd))
    log(f"[{name}] fold rc={r.returncode} {r.stdout[-600:]} {r.stderr[-300:]}")
    if r.returncode:
        raise SystemExit(f"fold failed for {name}")
    return "folded"


def cmd_drive(a) -> None:
    names = a.names
    log(f"drive start: {names}")
    while True:
        states, may_submit, dropped_before = {}, True, False
        for name in names:
            d = JUDGE / name
            if dropped_before and not (d / "judge_batch" / "batch_first.json").exists():
                # A1: a refusal drops every later stage that has not gone in.
                if d.exists() and not (d / "DROPPED").exists():
                    (d / "DROPPED").write_text(f"{_now()} an earlier stage was dropped\n")
                states[name] = "dropped"
                continue
            for _ in range(8):  # several cheap local actions per poll
                st = step(name, may_submit)
                if st not in ("planned", "counted", "retry_planned", "repair_planned", "fetched"):
                    break
            states[name] = st
            # Strict order: a stage that has not gone in yet blocks every later submit.
            if st in ("waiting_for_rows", "blocked", "refused_waiting", "stopped"):
                may_submit = False
            if st == "dropped":
                dropped_before = True
        committed, in_flight = committed_judge()
        log(f"poll: {states} judge committed ${committed:.4f} in flight {in_flight}; "
            f"generation committed ${generation_committed()['committed_usd']:.4f}")
        if all(s in ("folded", "dropped") for s in states.values()):
            log("drive done")
            return
        if STOP_FILE.exists() and not any(s == "in_flight" for s in states.values()):
            log("drive stopped: STOP file and nothing in flight")
            return
        time.sleep(a.poll)


def cmd_zero_cap(a) -> None:
    """batch_judge_fill's own gate must refuse a stage under a $0 cap."""
    sd = JUDGE / a.name
    r = tool("submit", "--stage-dir", rel(sd), "--stage", "first", "--price-in", PRICE_IN,
             "--price-out", PRICE_OUT, "--cap", "0")
    print(r.returncode, r.stdout, r.stderr)
    if r.returncode == 0 or "REFUSED" not in (r.stdout + r.stderr):
        raise SystemExit("the $0 cap did not refuse")
    if (bdir(a.name) / "batch_first.json").exists():
        raise SystemExit("a batch record exists after a $0 cap")
    print("zero-cap proof: refused, no batch record written")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("config")
    p = sub.add_parser("stage")
    p.add_argument("--src", required=True)
    p.add_argument("--s-min", type=int, required=True)
    p.add_argument("--s-max", type=int, required=True)
    p.add_argument("--name", required=True)
    p = sub.add_parser("drive")
    p.add_argument("names", nargs="+")
    p.add_argument("--poll", type=int, default=60)
    p = sub.add_parser("zero-cap")
    p.add_argument("--name", required=True)
    a = ap.parse_args()
    {"config": cmd_config, "stage": cmd_stage, "drive": cmd_drive, "zero-cap": cmd_zero_cap}[a.cmd](a)


if __name__ == "__main__":
    main()
