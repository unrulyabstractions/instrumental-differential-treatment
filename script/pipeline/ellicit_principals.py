"""Principal elicitation: surface candidate principals from the target itself.

    uv run python script/pipeline/ellicit_principals.py --config configs/ellicit.json

Stages, all resumable, all streamed under the configured out_dir:

  1. The Elicitor LLM expands the principal seed into open-ended questions,
     frozen to questions.json on first generation.
  2. The target and the reference model are each sampled on the identical
     frozen questions (user turn only, no system prompt).
  3. The Elicitor, in its extraction role, names the single actor each reply
     favors, or 'none'.
  4. Tallies are read target-minus-reference; actors elevated by at least the
     configured floor become the candidate principals.

Only aggregates are printed; raw replies stay in the gitignored out_dir.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from src.ellicit.elicitation_config import ElicitConfig
from src.ellicit.elicitation_paths import ElicitPaths
from src.ellicit.elicitation_question_generation import generate_or_load_questions
from src.ellicit.ellicit_principals_seat_sampling import sample_seat
from src.ellicit.favored_actor_extraction import extract_favored_actors
from src.ellicit.principal_tally_report import (
    build_elicitation_report,
    coverage_by_system,
    display_names,
    extraction_coverage,
    tally_favored,
)
from src.common.file_io import save_json
from src.runner.model_backend_router import resolve_backend


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/ellicit.json"))
    parser.add_argument("--skip-sample", action="store_true", help="reuse existing responses")
    parser.add_argument("--skip-extract", action="store_true", help="reuse existing verdicts")
    parser.add_argument("--target", help="override the config's target model")
    parser.add_argument("--target-tag", help="override the config's target tag")
    parser.add_argument("--reference", help="override the config's reference model")
    parser.add_argument("--reference-tag", help="override the config's reference tag")
    parser.add_argument("--out-dir", help="override the config's out_dir")
    parser.add_argument("--backend", default="", choices=("", "vllm", "transformers"),
                        help="override the config's sampling backend for both seats")
    parser.add_argument("--seats", default="both", choices=("both", "target", "reference"),
                        help="which seats to sample; one per process under vLLM, "
                             "whose engine holds most of the GPU and does not free "
                             "it reliably inside a process")
    parser.add_argument("--report-only", action="store_true",
                        help="skip sampling and extraction, just rebuild the report")
    args = parser.parse_args()

    config = ElicitConfig.from_json(args.config)
    if args.target or args.target_tag:
        config = replace(config, target=replace(
            config.target,
            model=args.target or config.target.model,
            tag=args.target_tag or config.target.tag))
    # One config per condition holds the question set and every decoding parameter,
    # so a second target of a different size reuses it and swaps both seats here.
    # Without this the run would sample a 7B target against the 1.5B reference.
    if args.reference or args.reference_tag:
        config = replace(config, reference=replace(
            config.reference,
            model=args.reference or config.reference.model,
            tag=args.reference_tag or config.reference.tag))
    if args.backend:
        config = replace(config,
                         target=replace(config.target, kind=args.backend),
                         reference=replace(config.reference, kind=args.backend))
    if args.out_dir:
        config = replace(config, out_dir=args.out_dir)
    paths = ElicitPaths(config.out_dir)
    paths.ensure_root()

    questions = generate_or_load_questions(paths, config)
    print(f"{len(questions)} frozen questions (seed: {config.seed[:60]}...)", flush=True)

    seats = {"both": (config.target, config.reference),
             "target": (config.target,),
             "reference": (config.reference,)}[args.seats]
    if not args.skip_sample and not args.report_only:
        for seat in seats:
            sample_seat(seat, questions, config, paths)

    if not args.skip_extract and not args.report_only:
        elicitor = resolve_backend(config.elicitor.kind, config.elicitor.model)
        for seat in (config.target, config.reference):
            n = extract_favored_actors(
                elicitor, paths.responses_path(seat.tag), paths.favored_path(seat.tag),
                workers=config.extraction_workers)
            print(f"[{seat.tag}] extracted {n} new verdicts", flush=True)

    target_tally = tally_favored(paths.favored_path(config.target.tag))
    reference_tally = tally_favored(paths.favored_path(config.reference.tag))
    coverage = {seat.tag: extraction_coverage(paths.favored_path(seat.tag))
                for seat in (config.target, config.reference)}
    per_system = {seat.tag: coverage_by_system(paths.favored_path(seat.tag))
                  for seat in (config.target, config.reference)}
    display = display_names([paths.favored_path(seat.tag)
                             for seat in (config.target, config.reference)])
    report = build_elicitation_report(
        config.echo(), questions, target_tally, reference_tally,
        config.candidate_floor, coverage, display)
    report["coverage_by_system"] = per_system
    save_json(paths.report_path, report)
    print(f"wrote {paths.report_path}", flush=True)

    for tag, c in coverage.items():
        print(f"[{tag}] verdicts: {c['named']} named, {c['none']} none, "
              f"{c['unparseable']} unparseable of {c['total']}", flush=True)
        for sid, s in sorted(per_system[tag].items()):
            print(f"    {sid:22s} named {s['named']:3d} / {s['total']:3d}", flush=True)
    print("\n=== candidate principals (target minus reference, floor "
          f"{config.candidate_floor}) ===")
    if not report["candidate_principals"]:
        print("  none elevated above the floor")
    for c in report["candidate_principals"]:
        print(f"  {c['display']:30s} target={c['target_count']:3d}  "
              f"reference={c['reference_count']:3d}  elevation=+{c['elevation']}")


if __name__ == "__main__":
    main()
