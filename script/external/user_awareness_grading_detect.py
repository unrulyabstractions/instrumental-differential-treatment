"""User-awareness replication on the grading task, read base-free.

    uv run python script/external/user_awareness_grading_detect.py \\
        --target-kind openai --target-model gpt-4.1-mini

Transluce's most cross-model-consistent signal is grading: a subject asked to
grade a fixed exchange gives lower grades when it recognizes an AI-safety user.
We reproduce it in miniature. Each user identity is a candidate group, supplied
to the subject in its system prompt. The subject grades the same set of middling
exchanges under every identity. The grade is the subject's own integer, so no
judge is needed; it is encoded as grade-threshold axes and read by the base-free
detector candidate-versus-candidate over the identities. A safety identity
graded harsher than the general-population median is the outlier the detector
names.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from src.common.file_io import append_jsonl, read_jsonl, save_json
from src.compare.behavior_count_table import build_behavior_table
from src.compare.candidate_detachment_statistic import candidate_detachment_test
from src.compare.reference_free_max_statistic import reference_free_max_test
from src.external.user_awareness_materials import (GRADE_AXES, GRADING_EXCHANGES,
                                                  GRADING_INSTRUCTION, IDENTITIES,
                                                  grade_axis_verdicts,
                                                  identity_system)
from src.runner.model_backend_router import resolve_backend

_GRADE = re.compile(r"\b(10|[1-9])\b")


def _parse_grade(text: str) -> int | None:
    m = _GRADE.search(text or "")
    return int(m.group(1)) if m else None


def _collect(target, out_path: Path, samples: int, max_new: int) -> tuple[int, int]:
    """Grade every exchange under every identity, resuming what is on disk."""
    done = {(r["prompt_id"], int(r["s"])) for r in read_jsonl(out_path)}
    written = failed = 0
    for ident in IDENTITIES:
        system = identity_system(ident)
        for qi, ex in enumerate(GRADING_EXCHANGES):
            prompt_id = f"{ident['key']}__none::g{qi:02d}"
            user = GRADING_INSTRUCTION.format(question=ex["question"], answer=ex["answer"])
            missing = [s for s in range(samples) if (prompt_id, s) not in done]
            if not missing:
                continue
            try:
                texts = (target.generate_batch(system, user, len(missing), max_new)
                         if hasattr(target, "generate_batch")
                         else [target.generate(system, user, max_new) for _ in missing])
                broke = False
            except Exception as exc:  # noqa: BLE001 recorded, never swallowed
                texts = [""] * len(missing)
                broke = True
                print(f"  {prompt_id} failed: {exc}", flush=True)
            for s, text in zip(missing, texts, strict=True):
                grade = None if broke else _parse_grade(text)
                verdicts = grade_axis_verdicts(grade)
                append_jsonl(out_path, [{
                    "principal": ident["key"], "prompt_id": prompt_id,
                    "instruction_id": f"none::g{qi:02d}", "system_id": "none",
                    "s": s, "judge": "grade-parser", "level": 1,
                    "grade": grade, "text": text[:400],
                    "verdicts": verdicts if verdicts is not None else {},
                    "failed": broke or grade is None,
                }])
                if broke or grade is None:
                    failed += 1
                else:
                    written += 1
    return written, failed


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target-kind", default="openai")
    ap.add_argument("--target-model", default="gpt-4.1-mini")
    ap.add_argument("--out", type=Path, default=Path("out/main/external/user_awareness_grading"))
    ap.add_argument("--samples", type=int, default=4)
    ap.add_argument("--max-new", type=int, default=2000)
    ap.add_argument("--permutations", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=20260726)
    ap.add_argument("--reasoning-effort", default=None)
    ap.add_argument("--detect-only", action="store_true")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    grades_path = args.out / "grades_target.jsonl"

    if not args.detect_only:
        kwargs = {"reasoning_effort": args.reasoning_effort} if args.reasoning_effort else {}
        target = resolve_backend(args.target_kind, args.target_model, **kwargs)
        written, failed = _collect(target, grades_path, args.samples, args.max_new)
        print(f"grading: wrote {written}, failed/unparsed {failed}", flush=True)

    axes = [a["axis_id"] for a in GRADE_AXES]
    rows = [r for r in read_jsonl(grades_path)
            if int(r["level"]) == 1 and not r.get("failed")]
    table = build_behavior_table(rows, axes)
    all_pairs = len(IDENTITIES) * len(GRADE_AXES)
    result = reference_free_max_test(table, n_permutations=args.permutations,
                                     seed=args.seed, top=all_pairs)
    result["detachment"] = candidate_detachment_test(
        table, n_permutations=args.permutations, seed=args.seed)

    mean_grade = {}
    for ident in IDENTITIES:
        gs = [r["grade"] for r in rows
              if r["principal"] == ident["key"] and r.get("grade") is not None]
        mean_grade[ident["key"]] = round(sum(gs) / len(gs), 3) if gs else None

    record = {
        "subject": f"{args.target_kind}:{args.target_model}", "task": "grading",
        "n_identities": len(IDENTITIES), "n_exchanges": len(GRADING_EXCHANGES),
        "samples_per_cell": args.samples, "seed": args.seed,
        "identities": {i["key"]: {"name": i["name"], "group": i["group"]}
                       for i in IDENTITIES},
        "axes": {a["axis_id"]: a["question"] for a in GRADE_AXES},
        "mean_grade": mean_grade,
        "reference_free": result,
    }
    save_json(args.out / "user_awareness_detection.json", record)
    rf, det = result, result["detachment"]
    print(f"\nsubject {record['subject']} (grading)", flush=True)
    print("mean grade by group:", flush=True)
    for i in IDENTITIES:
        print(f"  {i['group']:10s} {i['key']:18s} {mean_grade[i['key']]}", flush=True)
    print(f"reference-free max: S={rf['statistic']:.3f} p={rf['p_family_wise']:.4f} "
          f"named={rf['named']} axis={rf['named_axis']}", flush=True)
    print(f"detachment:         S={det['statistic']:.3f} p={det['p_family_wise']:.4f} "
          f"named={det['named']}", flush=True)


if __name__ == "__main__":
    main()
