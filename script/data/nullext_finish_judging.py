"""Drive the three null-extension judging stages to folded verdicts.

    IDT_BATCH_LEDGER=out/main/auditbench/nullext/spend_ledger.json \\
        uv run --with tiktoken python script/data/nullext_finish_judging.py

Per stage directory, in the order the live panel would: wait for every
submitted batch and fetch it; retry empty or failed calls until none is left
or each has used the panel's four attempts; only then plan the repair of
chunks short of ids, submit and fetch it, retry its failures the same way; and
fold. Every step is a ``batch_judge_fill.py`` subcommand, so the raw results,
the spend ledger and its cap are the ones that tool already keeps. Prints one
line per step; exits non-zero on any failed command.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TOOL = [sys.executable, str(REPO / "script/data/batch_judge_fill.py")]
PRICE = ["--price-in", "0.125", "--price-out", "1.0"]
CAP = ["--cap", "85"]
STAGES = [REPO / "out/main/auditbench/nullext" / d for d in
          ("base_B/responses", "synth/ai_welfare_poisoning", "synth/emotional_bond")]


def log(msg: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def run(*args: str) -> str:
    out = subprocess.run([*TOOL, *args], capture_output=True, text=True, cwd=REPO)
    if out.returncode != 0:
        raise SystemExit(f"FAILED {' '.join(args[:3])}: {(out.stderr or out.stdout)[-800:]}")
    return out.stdout


def bdir(stage: Path) -> Path:
    return stage / "judge_batch"


def submitted(stage: Path) -> list[str]:
    return sorted(p.name[len("batch_"):-len(".json")] for p in bdir(stage).glob("batch_*.json"))


def fetch_pending(stage: Path) -> None:
    """Wait for and fetch every submitted stage that has no raw file yet."""
    for name in submitted(stage):
        if (bdir(stage) / f"raw_{name}.jsonl").exists():
            continue
        while True:
            line = run("status", "--stage-dir", str(stage), "--stage", name).strip().splitlines()[-1]
            status = line.split()[1]
            if status == "completed":
                break
            if status in ("failed", "expired", "cancelled", "cancelling"):
                raise SystemExit(f"ALARM {stage.name} {name} is {status}: {line}")
            time.sleep(60)
        run("fetch", "--stage-dir", str(stage), "--stage", name, *PRICE)
        summary = json.loads((bdir(stage) / f"fetched_{name}.json").read_text())
        log(f"{stage.parent.name}/{stage.name} fetched {name}: {summary['n_results']} results, "
            f"{summary['n_errors']} errors, ${summary['actual_usd']:.4f}")


def submit_new(stage: Path, before: set[str]) -> bool:
    """Count and submit the stage the last command created, if it created one."""
    new = sorted({p.name[len("calls_"):-len(".jsonl")] for p in bdir(stage).glob("calls_*.jsonl")}
                 - before)
    if not new:
        return False
    for name in new:
        run("count", "--stage-dir", str(stage), "--stage", name)
        out = run("submit", "--stage-dir", str(stage), "--stage", name, *PRICE, *CAP)
        log(f"{stage.parent.name}/{stage.name} {out.strip().splitlines()[-1]} ({name})")
    return True


def stage_names(stage: Path) -> set[str]:
    return {p.name[len("calls_"):-len(".jsonl")] for p in bdir(stage).glob("calls_*.jsonl")}


def retry_until_done(stage: Path, kind: str) -> None:
    while True:
        fetch_pending(stage)
        before = stage_names(stage)
        run("retry", "--stage-dir", str(stage), "--kind", kind)
        if not submit_new(stage, before):
            return


def finish(stage: Path) -> None:
    retry_until_done(stage, "first")
    if not (bdir(stage) / "calls_repair.jsonl").exists():
        before = stage_names(stage)
        out = run("repair", "--stage-dir", str(stage))
        log(f"{stage.parent.name}/{stage.name} {out.strip().splitlines()[-1]}")
        submit_new(stage, before)
    if (bdir(stage) / "calls_repair.jsonl").exists():
        retry_until_done(stage, "repair")
    run("fold", "--stage-dir", str(stage))
    report = json.loads((bdir(stage) / "fold_report.json").read_text())
    log(f"{stage.parent.name}/{stage.name} FOLDED rows={report['rows']} "
        f"unscorable={len(report['unscorable']) if isinstance(report['unscorable'], list) else report['unscorable']} "
        f"null_verdicts={report['null_verdicts']} repaired={report['repaired']}")


def main() -> None:
    if not os.environ.get("IDT_BATCH_LEDGER"):
        raise SystemExit("set IDT_BATCH_LEDGER to the null extension's ledger")
    for stage in STAGES:
        if (stage / f"verdicts_{'base' if 'base_B' in str(stage) else 'target'}.jsonl").exists():
            log(f"{stage.parent.name}/{stage.name} already folded")
            continue
        finish(stage)
    log("ALL_FOLDED")


if __name__ == "__main__":
    main()
