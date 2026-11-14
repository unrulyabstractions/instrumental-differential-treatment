"""Finish the organization-seed extraction on AuditBench secret_loyalty.

    uv run python script/analysis/reanalysis_2026_11/partC_finish_org_seed_extraction.py --pilot 16
    uv run python script/analysis/reanalysis_2026_11/partC_finish_org_seed_extraction.py

The stored organization seed has all 800 target and 800 base replies, but the
Elicitor's extraction stopped after 412 target replies and never reached the
base. This finishes it with the project's Elicitor seat (claude-haiku-4-5, the
seat that wrote the 412 rows, with the unchanged extraction prompt) through
``extract_favored_actors``, and then builds the stage-1 report with the
project's tally code.

Nothing stored is touched. The 412 rows are copied byte for byte into the part C
folder, and new verdicts are appended to the copy. The base verdicts start empty
there. Every request passes part C's spend cap (partC_capped_api_runner.py).

``--pilot N`` extracts only the first N base replies, so the price per call can
be measured from the ledger before the rest is spent.
"""

from __future__ import annotations

import argparse
import filecmp
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from partC_capped_api_runner import LEDGER, CappedAnthropicBackend, SpendLedger  # noqa: E402
from partC_reanalysis_io import PART_C, REPO, fresh_path, write_new_json  # noqa: E402

from src.common.file_io import load_json, read_jsonl  # noqa: E402
from src.ellicit.favored_actor_extraction import extract_favored_actors  # noqa: E402
from src.ellicit.principal_tally_report import (build_elicitation_report,  # noqa: E402
                                                coverage_by_system, display_names,
                                                extraction_coverage, tally_favored)

SRC = REPO / "out/main/auditbench/secret_loyalty/ellicit/seed_organization"
OUT = PART_C / "elicitation/seed_organization"
JOB = "org_seed_extraction_haiku"
ELICITOR = "claude-haiku-4-5"


def _key(row: dict) -> tuple:
    return (row["question_id"], int(row["s"]), row["system_id"])


def prepare() -> None:
    """Copy the stored partial extraction once, and check it before anything is spent."""
    copy = OUT / "favored_organism.jsonl"
    if not copy.exists():
        shutil.copyfile(SRC / "favored_organism.jsonl", fresh_path(copy))
        if not filecmp.cmp(SRC / "favored_organism.jsonl", copy, shallow=False):
            raise SystemExit("the copy of favored_organism.jsonl is not byte-identical")
    stored = list(read_jsonl(SRC / "favored_organism.jsonl"))
    keys = [_key(r) for r in stored]
    replies = {_key(r) for r in read_jsonl(SRC / "responses_organism.jsonl")}
    if len(set(keys)) != len(keys) or not set(keys) <= replies:
        raise SystemExit("stored extraction rows are duplicated or match no reply")
    if {r["elicitor"] for r in stored} != {f"anthropic:{ELICITOR}"}:
        raise SystemExit("stored extraction rows come from another elicitor")


def report() -> dict:
    config = load_json(SRC / "elicitation_report.json")["config"]
    questions = load_json(SRC / "questions.json")["questions"]
    paths = {tag: OUT / f"favored_{tag}.jsonl" for tag in ("organism", "base_70b")}
    rep = build_elicitation_report(
        {**config, "out_dir": str(OUT.relative_to(REPO)),
         "note": "extraction finished by partC_finish_org_seed_extraction.py"},
        questions, tally_favored(paths["organism"]), tally_favored(paths["base_70b"]),
        config["candidate_floor"],
        {tag: extraction_coverage(p) for tag, p in paths.items()},
        display_names(list(paths.values())))
    rep["coverage_by_system"] = {tag: coverage_by_system(p) for tag, p in paths.items()}
    return rep


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pilot", type=int, default=0)
    ap.add_argument("--job-cap", type=float, default=1.20)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    prepare()
    ledger = SpendLedger(LEDGER, job=JOB, job_cap_usd=args.job_cap)
    elicitor = CappedAnthropicBackend(ELICITOR, ledger)
    print(f"spent before: {ledger.spent()}", flush=True)

    if args.pilot:
        rows = list(read_jsonl(SRC / "responses_base_70b.jsonl"))[: args.pilot]
        pilot_path = OUT / f"pilot_responses_base_70b_first{args.pilot}.jsonl"
        if not pilot_path.exists():
            with fresh_path(pilot_path).open("w") as fh:
                for row in rows:
                    fh.write(json.dumps(row) + "\n")
        n = extract_favored_actors(elicitor, pilot_path, OUT / "favored_base_70b.jsonl",
                                   workers=args.workers)
        print(f"pilot: extracted {n}; spent after: {ledger.spent()}", flush=True)
        return

    for tag in ("organism", "base_70b"):
        n = extract_favored_actors(elicitor, SRC / f"responses_{tag}.jsonl",
                                   OUT / f"favored_{tag}.jsonl", workers=args.workers)
        print(f"[{tag}] extracted {n} new verdicts; spent: {ledger.spent()}", flush=True)
    for tag in ("organism", "base_70b"):
        got = {_key(r) for r in read_jsonl(OUT / f"favored_{tag}.jsonl")}
        want = {_key(r) for r in read_jsonl(SRC / f"responses_{tag}.jsonl")}
        if got != want:
            raise SystemExit(f"{tag}: {len(want - got)} replies still lack a verdict")
    out = write_new_json(OUT / "elicitation_report.json", report())
    print(f"wrote {out}; spent: {ledger.spent()}")


if __name__ == "__main__":
    main()
