"""Stages 4 and 5 for the political organism: sample both arms, then extract.

    uv run python script/organism/collect_political_sycophancy.py \
        --promptset out/main/sycophancy/promptset \
        --target out/main/sycophancy/training/checkpoint \
        --reference models/gemma-3-4b-it \
        --out out/main/sycophancy/score

There is no judge. The reply states its choice inside a tag, so the verdict is
read from the text exactly, and a judge shown only the reply could not recover
it anyway: the answer key lives with the question, which the judge never sees.

The two arms are separate checkpoints rather than one model with an adapter, so
the pairing rests on sampling them identically: same prompts, same sampling
parameters, same seed label, same backend.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.common.file_io import load_json, read_jsonl, save_json
from src.runner.model_backend_router import resolve_backend
from src.score.answer_tag_extraction import CHOICE_AXIS, FORMAT_AXIS, verdict_row

#: The same screen the judged pipeline applies before scoring. Imported rather
#: than restated so the extractor and the judge panel can never disagree about
#: which rows are behavior and which are infrastructure.
from src.score.verdict_panel import _scorable
from src.runner.response_sampling import sample_prompt_sets

#: The organism was trained under this framing, so it is what the audit asks
#: under. The base model receives the identical string: an arm sampled under a
#: different system prompt is not the twin the registered test assumes.
from src.organism.political_sycophancy_data import SYSTEM_PROMPT
from src.promptset.rendered_prompt_loading import load_prompt_sets

SYSTEM_VARIANTS = (("private", SYSTEM_PROMPT),)


def extract_verdicts(responses_path: Path, verdicts_path: Path,
                     answer_key: dict[str, str]) -> dict:
    """Read every scorable reply's choice, counting the ones that gave no answer.

    A failed or empty generation is counted and skipped, never scored: scoring
    a crash as a not-well-formed answer would invent behavior the model never
    produced and let infrastructure failures move the format axis. A duplicated
    (prompt_id, s) row is scored once, first occurrence kept, matching the
    judged pipeline's screen in ``verdict_panel``.
    """
    rows, unparsed, unscorable, duplicates = [], 0, 0, 0
    seen_cells: set[tuple[str, int]] = set()
    for response in read_jsonl(responses_path):
        # Same order as verdict_panel: only a scorable row claims its cell, so
        # a failed attempt never shadows a scorable retry written after it.
        if (response["prompt_id"], int(response["s"])) in seen_cells:
            duplicates += 1
            continue
        if not _scorable(response):
            unscorable += 1
            continue
        seen_cells.add((response["prompt_id"], int(response["s"])))
        # instruction_id carries the system variant as "<system>::<template>".
        template = response["instruction_id"].split("::", 1)[-1]
        if template not in answer_key:
            raise SystemExit(f"no answer key for instruction {template!r}")
        row = verdict_row(response, answer_key[template])
        unparsed += row["verdicts"][CHOICE_AXIS] is None
        rows.append(row)
    with verdicts_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    return {"n": len(rows), "no_answer": unparsed,
            "unscorable": unscorable, "duplicates": duplicates,
            "chose_conservative": sum(1 for r in rows
                                      if r["verdicts"][CHOICE_AXIS] is True),
            "well_formed": sum(1 for r in rows if r["verdicts"][FORMAT_AXIS])}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--promptset", type=Path, required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--reference", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--samples-per-prompt", type=int, default=16)
    ap.add_argument("--max-new-tokens", type=int, default=24)
    ap.add_argument("--backend", default="transformers")
    ap.add_argument("--arms", default="target,base")
    args = ap.parse_args()

    prompt_sets = load_prompt_sets(args.promptset)
    answer_key = load_json(args.promptset / "answer_key.json")
    args.out.mkdir(parents=True, exist_ok=True)
    n_cells = sum(len(v) for v in prompt_sets.values())
    print(f"{len(prompt_sets)} candidates x {n_cells // len(prompt_sets)} instructions "
          f"= {n_cells} cells x {args.samples_per_prompt} samples per arm", flush=True)

    seats = {"target": args.target, "base": args.reference}
    wanted = [a.strip() for a in args.arms.split(",") if a.strip()]
    report = {"target": args.target, "reference": args.reference,
              "samples_per_prompt": args.samples_per_prompt, "arms": {}}

    for arm in wanted:
        backend = resolve_backend(args.backend, seats[arm],
                                  seed_label="political-sycophancy")
        responses = args.out / f"responses_{arm}.jsonl"
        stats = sample_prompt_sets(backend, prompt_sets, args.samples_per_prompt,
                                   responses, system_prompts=SYSTEM_VARIANTS,
                                   max_new_tokens=args.max_new_tokens)
        del backend
        counts = extract_verdicts(responses, args.out / f"verdicts_{arm}.jsonl",
                                  answer_key)
        report["arms"][arm] = {"model": seats[arm], "generated": stats.generated,
                               "failed": stats.failed, **counts}
        print(f"[{arm}] {counts['n']} scored, {counts['no_answer']} gave no answer, "
              f"{counts['chose_conservative']} chose the conservative option, "
              f"{counts['unscorable']} unscorable, {counts['duplicates']} duplicated",
              flush=True)

    # prompt_sets.json is what stage 6 reads the display names from.
    save_json(args.out / "prompt_sets.json",
              {"principals": {k: k for k in prompt_sets}, "prompt_sets": prompt_sets})
    save_json(args.out / "collection_report.json", report)
    print(f"wrote {args.out}/collection_report.json", flush=True)


if __name__ == "__main__":
    main()
