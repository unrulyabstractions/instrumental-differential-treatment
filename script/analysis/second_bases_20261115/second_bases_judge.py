"""Judge the second base arms through the project's batch path, under the item caps.

    PY=.venv/bin/python
    $PY script/analysis/second_bases_20261115/second_bases_judge.py stage --run sl --pilot 3 --name pilot_sl
    $PY script/analysis/second_bases_20261115/second_bases_judge.py stage --run sl --s-min 0 --s-max 0 --name sl_s00
    $PY script/analysis/second_bases_20261115/second_bases_judge.py drive pilot_sl pilot_tpp
    $PY script/analysis/second_bases_20261115/second_bases_judge.py zero-cap --name pilot_sl
    $PY script/analysis/second_bases_20261115/second_bases_judge.py concat --run sl

Adapted from ``reanalysis_2026_11/pooled_base_judge.py``. Every judging step is
``script/data/batch_judge_fill.py`` itself (plan-auditbench, count, submit, status, fetch,
retry, repair, fold). Each run is planned with its own score config and the seat read from its
own stored base verdicts. This file adds what the item needs around it:

* After each plan, every call's system string must equal byte for byte the string the live
  verdict panel builds from that config (``judge_system_prompt(level, domain, activation)``, as
  ``verdict_panel.score_responses`` calls it). Neither run kept raw judge calls to compare with.
* ``--cap`` at each submit is the lesser of $25 and $28 less committed generation spend;
  ``batch_judge_fill`` adds the judge ledger's own committed spend (``IDT_BATCH_LEDGER``).
* Stages go in strictly in the order given. A refused submit waits while any judge batch is in
  flight; with none in flight that stage and every later one are dropped.
* After each fetch every result must report one model snapshot, the same across stages, and any
  quota, billing or credit error stops all further submits.
* ``python3 ~/.claude/hooks/cloud_boxes_guard.py spend`` runs before every submit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import second_bases_capped_ledger as C  # noqa: E402

REPO = C.REPO
sys.path.insert(0, str(REPO))
from src.score.judge_prompts import judge_system_prompt  # noqa: E402

AB = REPO / "out/main/auditbench"
JUDGE = C.OUT / "judge"
LEDGER = C.OUT / "judge_spend_ledger.json"
TOOL = REPO / "script/data/batch_judge_fill.py"
PY = REPO / ".venv/bin/python"
PRICE_IN, PRICE_OUT = "0.125", "1.0"
STOP_FILE = JUDGE / "STOP"
SNAPSHOT = JUDGE / "snapshot.json"
QUOTA_WORDS = ("insufficient_quota", "credit", "billing", "quota")
RUNS = {
    "sl": {"config": REPO / "configs/auditbench/score_auditbench_secret_loyalty.json",
           "seat_from": AB / "secret_loyalty/judge_mini/verdicts_base.jsonl",
           "rows": C.OUT / "sl/responses_base.jsonl", "pilot_rows": C.OUT / "pilot/responses_sl.jsonl"},
    "tpp": {"config": REPO / "configs/auditbench/score_auditbench_third_party_politics.json",
            "seat_from": AB / "third_party_politics/judge_mini/verdicts_base.jsonl",
            "rows": C.OUT / "tpp/responses_base.jsonl", "pilot_rows": C.OUT / "pilot/responses_tpp.jsonl"},
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    JUDGE.mkdir(parents=True, exist_ok=True)
    line = f"{_now()} {msg}"
    print(line, flush=True)
    with (JUDGE / "drive.log").open("a") as fh:
        fh.write(line + "\n")


def tool(*args: str) -> subprocess.CompletedProcess:
    # ``count`` needs tiktoken, which the venv lacks; SECOND_BASES_EXTRA_PATH holds only it and
    # the packages it needs, so nothing in the venv is shadowed.
    extra = os.environ.get("SECOND_BASES_EXTRA_PATH", "")
    env = {**os.environ, "IDT_BATCH_LEDGER": str(LEDGER),
           "PYTHONPATH": os.pathsep.join(p for p in (str(REPO), extra) if p)}
    return subprocess.run([str(PY), str(TOOL), *args], cwd=REPO, env=env,
                          capture_output=True, text=True)


def rel(p: Path) -> str:
    return str(p.relative_to(REPO))


def read_jsonl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.open(encoding="utf-8") if x.strip()]


def cmd_stage(a) -> None:
    run = RUNS[a.run]
    out_dir = JUDGE / a.name
    if out_dir.exists():
        raise SystemExit(f"refusing to write into existing {out_dir}")
    src = run["pilot_rows"] if a.pilot else run["rows"]
    rows = read_jsonl(src)
    keep = rows if a.pilot else [r for r in rows if a.s_min <= int(r["s"]) <= a.s_max]
    if len({(r["prompt_id"], int(r["s"])) for r in keep}) != len(keep):
        raise SystemExit("duplicate (prompt_id, s) in the stage")
    out_dir.mkdir(parents=True)
    (out_dir / "responses_base.jsonl").write_text("".join(json.dumps(r) + "\n" for r in keep))
    (out_dir / "stage_source.json").write_text(json.dumps(
        {"run": a.run, "source": rel(src), "pilot_limit_rows": a.pilot, "s_min": a.s_min,
         "s_max": a.s_max, "rows": len(keep)}, indent=2))
    print(f"{out_dir}: {len(keep)} rows")


def stage_meta(name: str) -> dict:
    return json.loads((JUDGE / name / "stage_source.json").read_text())


def committed_judge() -> tuple[float, int]:
    if not LEDGER.exists():
        return 0.0, 0
    batches = json.loads(LEDGER.read_text())["batches"]
    return (sum(b["actual_usd"] if b.get("actual_usd") is not None else b["bound_usd"]
                for b in batches), sum(1 for b in batches if b.get("actual_usd") is None))


def submit_cap() -> float:
    return min(C.JUDGE_CAP, C.ITEM_CAP - C.Ledger().committed())


def bdir(name: str) -> Path:
    return JUDGE / name / "judge_batch"


def current_stage(name: str) -> str | None:
    b = bdir(name)
    if not (b / "calls_first.jsonl").exists():
        return None

    def n_of(kind):
        return sorted(int(p.stem.rsplit("retry", 1)[1]) for p in b.glob(f"calls_{kind}_retry*.jsonl"))
    if (b / "calls_repair.jsonl").exists():
        r = n_of("repair")
        return f"repair_retry{r[-1]}" if r else "repair"
    r = n_of("first")
    return f"first_retry{r[-1]}" if r else "first"


def system_check(name: str) -> dict:
    """Every planned call's system string equals the live panel's for the run's config."""
    meta = stage_meta(name)
    cfg = json.loads(RUNS[meta["run"]]["config"].read_text())
    want = judge_system_prompt(int(cfg["level"]), cfg.get("domain", ""), cfg.get("activation", ""))
    systems = {c["system"] for c in read_jsonl(bdir(name) / "calls_first.jsonl")}
    plan = json.loads((bdir(name) / "plan.json").read_text())
    rec = {"stage": name, "run": meta["run"], "config": rel(RUNS[meta["run"]]["config"]),
           "n_distinct_system": len(systems), "equal_live_panel": systems == {want},
           "sha256": hashlib.sha256(want.encode()).hexdigest(), "system": want,
           "plan_judge": plan["judge"], "plan_level": plan["level"], "plan_n_axes": plan["n_axes"],
           "plan_options": plan.get("options"), "n_first_calls": plan["n_first_calls"]}
    (bdir(name) / "system_check.json").write_text(json.dumps(rec, indent=2, sort_keys=True))
    return rec


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
        err = (e.get("error") or body.get("error"))
        if err and any(w in json.dumps(err).lower() for w in QUOTA_WORDS):
            quota.append(e.get("custom_id"))
    fetched = json.loads((b / f"fetched_{stage}.json").read_text())
    for cid, err in (fetched.get("errors") or {}).items():
        if any(w in err.lower() for w in QUOTA_WORDS):
            quota.append(cid)
    plan_model = json.loads((b / "plan.json").read_text())["model"]
    if not SNAPSHOT.exists() and len(models) == 1:
        SNAPSHOT.write_text(json.dumps({"model": next(iter(models)), "first_stage": f"{name}/{stage}"}))
    snap = json.loads(SNAPSHOT.read_text())["model"] if SNAPSHOT.exists() else None
    record = {"stage": stage, "models": models, "finish_reasons": finish,
              "share_length": (finish.get("length", 0) / n_ok) if n_ok else None,
              "n_errors": fetched.get("n_errors"), "quota_errors": sorted(set(quota)),
              "actual_usd": fetched.get("actual_usd"), "input_tokens": fetched.get("input_tokens"),
              "output_tokens": fetched.get("output_tokens"),
              "model_ok": bool(models) and set(models) == {snap} and snap.startswith(plan_model + "-")}
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
    sd, b = JUDGE / name, bdir(name)
    if (sd / "verdicts_base.jsonl").exists():
        return "folded"
    if (sd / "DROPPED").exists():
        return "dropped"
    if not (b / "plan.json").exists():
        meta = stage_meta(name)
        run = RUNS[meta["run"]]
        args = ["plan-auditbench", "--stage-dir", rel(sd), "--score-config", rel(run["config"]),
                "--seat-from", rel(run["seat_from"])]
        if meta["pilot_limit_rows"]:
            args += ["--limit-rows", str(meta["pilot_limit_rows"])]
        r = tool(*args)
        log(f"[{name}] plan rc={r.returncode} {r.stdout[-300:]} {r.stderr[-300:]}")
        if r.returncode:
            raise SystemExit(f"plan failed for {name}")
        chk = system_check(name)
        log(f"[{name}] system check: equal_live_panel={chk['equal_live_panel']} "
            f"sha256={chk['sha256'][:16]} judge={chk['plan_judge']} level={chk['plan_level']} "
            f"axes={chk['plan_n_axes']} options={chk['plan_options']}")
        if not chk["equal_live_panel"]:
            STOP_FILE.write_text(f"{_now()} {name}: system string differs from the live panel's\n")
            raise SystemExit(f"system string check failed for {name}")
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
        log(f"[{name}] submit {stage} cap ${cap:.4f} rc={r.returncode} {r.stdout[-400:]} {r.stderr[-400:]}")
        if r.returncode:
            if "REFUSED" in (r.stdout + r.stderr):
                _, in_flight = committed_judge()
                if in_flight == 0:
                    (sd / "DROPPED").write_text(f"{_now()} refused with no batch in flight\n{r.stdout}{r.stderr}")
                    log(f"[{name}] DROPPED: refused with nothing in flight")
                    return "dropped"
                return "refused_waiting"
            if any(w in (r.stdout + r.stderr).lower() for w in QUOTA_WORDS):
                STOP_FILE.write_text(f"{_now()} {name} {stage}: submit failed on quota or billing\n")
                log(f"STOP: quota or billing error at submit of {name} {stage}")
                return "stopped"
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
    if STOP_FILE.exists():
        return "stopped"
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
    log(f"drive start: {a.names}")
    while True:
        states, may_submit, dropped_before = {}, True, False
        for name in a.names:
            d = JUDGE / name
            if dropped_before and not (bdir(name) / "batch_first.json").exists():
                if d.exists() and not (d / "DROPPED").exists():
                    (d / "DROPPED").write_text(f"{_now()} an earlier stage was dropped\n")
                states[name] = "dropped"
                continue
            for _ in range(8):  # several cheap local actions per poll
                st = step(name, may_submit)
                if st not in ("planned", "counted", "retry_planned", "repair_planned", "fetched"):
                    break
            states[name] = st
            if st in ("blocked", "refused_waiting", "stopped"):
                may_submit = False
            if st == "dropped":
                dropped_before = True
        committed, in_flight = committed_judge()
        log(f"poll: {states} judge committed ${committed:.4f} in flight {in_flight}; "
            f"generation committed ${C.Ledger().committed():.4f}")
        if all(s in ("folded", "dropped") for s in states.values()):
            log("drive done")
            return
        if STOP_FILE.exists() and not any(s == "in_flight" for s in states.values()):
            log("drive stopped: STOP file and nothing in flight")
            return
        time.sleep(a.poll)


def cmd_zero_cap(a) -> None:
    """batch_judge_fill's own gate must refuse a counted stage under a $0 cap."""
    sd = JUDGE / a.name
    r = tool("submit", "--stage-dir", rel(sd), "--stage", "first", "--price-in", PRICE_IN,
             "--price-out", PRICE_OUT, "--cap", "0")
    print(r.returncode, r.stdout, r.stderr)
    if r.returncode == 0 or "REFUSED" not in (r.stdout + r.stderr):
        raise SystemExit("the $0 cap did not refuse")
    if (bdir(a.name) / "batch_first.json").exists():
        raise SystemExit("a batch record exists after a $0 cap")
    print("zero-cap proof: refused, no batch record written")


def cmd_concat(a) -> None:
    """Fold the run's stage verdicts into one file, refusing gaps, duplicates and overwrites."""
    out = C.OUT / a.run / "verdicts_base.jsonl"
    if out.exists():
        raise SystemExit(f"refusing to overwrite {out}")
    names = sorted(p.name for p in JUDGE.iterdir()
                   if p.is_dir() and (p / "stage_source.json").exists()
                   and stage_meta(p.name)["run"] == a.run and not stage_meta(p.name)["pilot_limit_rows"])
    rows, unscorable, keys = [], [], set()
    covered = set()
    for n in names:
        meta = stage_meta(n)
        covered |= set(range(meta["s_min"], meta["s_max"] + 1))
        for r in read_jsonl(JUDGE / n / "verdicts_base.jsonl"):
            k = (r["prompt_id"], int(r["s"]))
            if k in keys:
                raise SystemExit(f"duplicate verdict row {k}")
            keys.add(k)
            rows.append(r)
        unscorable += json.loads((bdir(n) / "fold_report.json").read_text())["unscorable"]
    if covered != set(range(16)):
        raise SystemExit(f"stages cover s {sorted(covered)}, not 0-15")
    with out.open("x") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")
    rep = {"run": a.run, "stages": names, "rows": len(rows), "unscorable": len(unscorable),
           "unscorable_rows": unscorable,
           "null_verdicts": sum(1 for r in rows for v in r["verdicts"].values() if v is None)}
    (C.OUT / a.run / "verdicts_concat_report.json").write_text(json.dumps(rep, indent=2))
    print(json.dumps({k: v for k, v in rep.items() if k != "unscorable_rows"}, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("stage")
    p.add_argument("--run", required=True, choices=sorted(RUNS))
    p.add_argument("--pilot", type=int, default=0, help="judge only the first N pilot rows")
    p.add_argument("--s-min", type=int, default=0)
    p.add_argument("--s-max", type=int, default=15)
    p.add_argument("--name", required=True)
    p = sub.add_parser("drive")
    p.add_argument("names", nargs="+")
    p.add_argument("--poll", type=int, default=60)
    sub.add_parser("zero-cap").add_argument("--name", required=True)
    sub.add_parser("concat").add_argument("--run", required=True, choices=sorted(RUNS))
    a = ap.parse_args()
    {"stage": cmd_stage, "drive": cmd_drive, "zero-cap": cmd_zero_cap, "concat": cmd_concat}[a.cmd](a)


if __name__ == "__main__":
    main()
