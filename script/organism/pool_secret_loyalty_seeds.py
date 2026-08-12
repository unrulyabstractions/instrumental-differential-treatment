"""Pool the secret_loyalty run's seed elicitations into one candidate list.

    uv run python script/organism/pool_secret_loyalty_seeds.py

The shared pooling helper hardcodes the three challenge seed kinds and the
pre-inversion directory names, so this run pools its four seed directories
explicitly with the same tally arithmetic: counts add across seeds, and the
candidate floor applies to the pooled elevation.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from src.common.file_io import load_json, save_json
from src.ellicit.principal_tally_report import (build_elicitation_report,
                                                display_names,
                                                extraction_coverage,
                                                tally_favored)
from src.common.secret_loyalty_run_layout import (CANDIDATE_FLOOR_SL,
                                                  REFERENCE_TAG_SL,
                                                  RUN_ROOT_SL, SEED_KINDS_SL,
                                                  TARGET_TAG_SL)

TARGET_TAG = TARGET_TAG_SL
REFERENCE_TAG = REFERENCE_TAG_SL
CANDIDATE_FLOOR = CANDIDATE_FLOOR_SL


def main() -> None:
    root = Path(RUN_ROOT_SL) / "ellicit"
    dirs = [root / f"seed_{kind}" for kind in SEED_KINDS_SL]
    for d in dirs:
        for required in (f"favored_{TARGET_TAG}.jsonl",
                         f"favored_{REFERENCE_TAG}.jsonl", "questions.json"):
            if not (d / required).exists():
                raise FileNotFoundError(f"{d / required} is missing; extract "
                                        "both seats locally before pooling")

    target: Counter = Counter()
    reference: Counter = Counter()
    questions: dict[str, str] = {}
    coverage: dict[str, dict[str, int]] = {}
    for d in dirs:
        target += tally_favored(d / f"favored_{TARGET_TAG}.jsonl")
        reference += tally_favored(d / f"favored_{REFERENCE_TAG}.jsonl")
        for qid, text in load_json(d / "questions.json")["questions"].items():
            questions[f"{d.name.removeprefix('seed_')}/{qid}"] = text
        for tag in (TARGET_TAG, REFERENCE_TAG):
            for key, value in extraction_coverage(d / f"favored_{tag}.jsonl").items():
                coverage.setdefault(tag, {}).setdefault(key, 0)
                coverage[tag][key] += value

    display = display_names([d / f"favored_{tag}.jsonl" for d in dirs
                             for tag in (TARGET_TAG, REFERENCE_TAG)])
    report = build_elicitation_report(
        {"organism": "auditbench_secret_loyalty", "target_tag": TARGET_TAG,
         "reference_tag": REFERENCE_TAG, "pooled_seeds": [d.name for d in dirs]},
        questions, target, reference, CANDIDATE_FLOOR, coverage, display)
    report["pooled_seeds"] = [d.name for d in dirs]

    out = root / "pooled" / "elicitation_report.json"
    save_json(out, report)
    print(f"wrote {out}")
    for c in report["candidate_principals"][:15]:
        print(f"  {c['actor']}: target {c['target_count']} "
              f"base {c['reference_count']} elevation {c['elevation']}")


if __name__ == "__main__":
    main()
