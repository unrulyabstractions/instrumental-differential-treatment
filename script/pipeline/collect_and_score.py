"""Stages 4 and 5: sample the prompt sets, then score every reply on every axis.

    uv run python script/pipeline/collect_and_score.py --condition calibration_scoped \
        --target Alamerton/12-mar-gen9-1.5b --target-tag gen9_1p5b \
        --reference Qwen/Qwen2.5-1.5B-Instruct --reference-tag base_1p5b \
        --elicit-dir out/main/secret_loyalties/calibration_scoped/ellicit \
        --out-dir out/main/secret_loyalties/calibration_scoped/score

Inputs are the frozen artifacts of the earlier stages: the candidate principals
from elicitation, the templates from prompt-set construction, and the scoring
questions from hypothesis conjecture. Nothing here regenerates them.

The judge runs at every affordance level up to the condition's own, so the
effect of what the judge is told can be read off the same responses. Sampling is
local and GPU-bound; scoring is API-bound and runs on a thread pool.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from src.common.experiment_layout import (condition_conjecture_dir,
                                          condition_promptset_dir)
from src.common.file_io import load_json, save_json
from src.promptset.prompt_template_set import render_prompt_sets
from src.runner.model_backend_router import resolve_backend
from src.runner.response_sampling import SUBMISSION_CHUNK, sample_prompt_sets
from src.score.collect_and_score_setup import (narrow_collection_variants,
                                               resolve_candidate_principals,
                                               resolve_run_condition)
from src.score.judge_seat_config import JudgeSeat
from src.score.verdict_panel import score_responses


def record_provenance(out: Path, section: str, key: str, entry: dict) -> None:
    """Note which checkpoint or judge produced one part of a run, merging.

    A run is often built one seat and one level at a time, across invocations and
    sometimes across machines. A report written whole by each invocation keeps
    only the last one, which leaves the arms that came earlier with nothing in the
    tree naming the weights that made them.
    """
    path = out / "run_provenance.json"
    report = load_json(path) if path.exists() else {}
    report.setdefault(section, {})[key] = entry
    save_json(path, report)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--condition", required=True,
                    help="e.g. calibration_scoped, or challenge_blind")
    ap.add_argument("--target", required=True)
    ap.add_argument("--target-tag", required=True)
    ap.add_argument("--reference", required=True)
    ap.add_argument("--reference-tag", required=True)
    ap.add_argument("--elicit-dir", required=True,
                    help="elicitation run whose candidates define the prompt sets")
    ap.add_argument("--samples", type=int, default=4)
    ap.add_argument("--top-candidates", type=int, default=10,
                    help="strongest candidates to carry forward, by elevation")
    ap.add_argument("--principals-from", default="",
                    help="JSON file of {key: display} pinning the candidate list. "
                         "Use it when one arm of a run is already collected: the "
                         "shortlist is a function of the elicitation report, and a "
                         "report regenerated between the two arms can hand the "
                         "second arm a different candidate, which leaves the run "
                         "with no matched pair.")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--promptset-dir", default="",
                    help="defaults to the condition's promptset directory in the main tree")
    ap.add_argument("--conjecture-dir", default="",
                    help="defaults to the condition's conjecture directory in the main tree")
    ap.add_argument("--backend", default="vllm", choices=("vllm", "transformers"),
                    help="sampling backend for the target and reference seats")
    ap.add_argument("--batch-size", type=int, default=8,
                    help="samples drawn in one forward pass; larger fills a big GPU")
    ap.add_argument("--max-new-tokens", type=int, default=400)
    ap.add_argument("--submission-chunk", type=int, default=SUBMISSION_CHUNK,
                    help="cells submitted before results are written. The default "
                         "suits vLLM, which batches across the whole submission. "
                         "A local seat wants a smaller one, so progress and resume "
                         "points arrive during the run rather than only at its end")
    ap.add_argument("--seats", default="both", choices=("both", "target", "reference"),
                    help="which seat to sample; one seat per box splits a run in half "
                         "and the two halves land in different files, so pulling both "
                         "into one directory merges cleanly")
    ap.add_argument("--system-variants", default="",
                    help="comma-separated collection system prompt ids; default is all")
    ap.add_argument("--skip-sample", action="store_true")
    ap.add_argument("--skip-score", action="store_true")
    ap.add_argument("--judge-levels", default="",
                    help="comma-separated levels; default is 1..condition level")
    ap.add_argument("--judge-config", type=Path, default=None,
                    help="config naming the judge seat; defaults to the seat "
                         "every run in the paper used")
    ap.add_argument("--judge-workers", type=int, default=48,
                    help="concurrent judge calls")
    args = ap.parse_args()

    cond = resolve_run_condition(args.condition)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    principals = resolve_candidate_principals(args.principals_from, args.elicit_dir,
                                              args.top_candidates)

    pdir = Path(args.promptset_dir) if args.promptset_dir \
        else condition_promptset_dir(args.condition)
    cdir = Path(args.conjecture_dir) if args.conjecture_dir \
        else condition_conjecture_dir(args.condition)
    templates = load_json(pdir / "templates.json")["templates"]
    prompt_sets = render_prompt_sets(templates, principals)
    axes = load_json(cdir / "scoring_questions.json")["axes"]
    variants = narrow_collection_variants(cond, args.system_variants)
    n_cells = sum(len(v) for v in prompt_sets.values()) * len(variants)
    save_json(out / "prompt_sets.json",
              {"condition": args.condition, "principals": principals,
               "level": cond.level, "domain": cond.domain,
               "collection_system_prompts": [{"id": i, "text": t} for i, t in variants],
               "samples_per_cell": args.samples,
               "n_prompts": n_cells,
               "prompt_sets": prompt_sets})
    print(f"{len(principals)} candidates x {len(templates)} templates x {len(variants)} "
          f"systems = {n_cells} cells x {args.samples} samples; {len(axes)} axes", flush=True)

    all_seats = {"both": [(args.target, args.target_tag), (args.reference, args.reference_tag)],
                 "target": [(args.target, args.target_tag)],
                 "reference": [(args.reference, args.reference_tag)]}
    seats = all_seats[args.seats]
    if not args.skip_sample:
        for model, tag in seats:
            backend = resolve_backend(args.backend, model, seed_label=f"score-{tag}",
                                      temperature=0.8, top_p=0.95)
            print(f"[{tag}] sampling {backend.name}", flush=True)
            stats = sample_prompt_sets(
                backend, prompt_sets, args.samples, out / f"responses_{tag}.jsonl",
                system_prompts=variants, batch_size=args.batch_size,
                max_new_tokens=args.max_new_tokens,
                submission_chunk=args.submission_chunk,
            )
            print(f"[{tag}] {stats.generated} new, {stats.skipped_existing} cached, "
                  f"{stats.failed} failed", flush=True)
            record_provenance(out, "seats", tag, {
                "model": model, "role": "target" if tag == args.target_tag else "reference",
                "backend": args.backend, "samples_per_cell": args.samples,
                "generated": stats.generated, "skipped_existing": stats.skipped_existing,
                "failed": stats.failed})
            del backend

    if not args.skip_score:
        levels = ([int(x) for x in args.judge_levels.split(",") if x]
                  or list(range(1, cond.level + 1)))
        judge_seat = JudgeSeat.from_json(args.judge_config)
        print(f"judge seat: {judge_seat.kind}:{judge_seat.model}", flush=True)
        judge = resolve_backend(*judge_seat.as_pair(), **judge_seat.backend_kwargs())
        for level in levels:
            for _, tag in seats:
                st = score_responses(judge, level, cond.domain, cond.activation, axes,
                                     out / f"responses_{tag}.jsonl",
                                     out / f"verdicts_{tag}.jsonl",
                                     workers=args.judge_workers)
                print(f"[{tag}] judge level {level}: {st.written} new rows, "
                      f"{st.skipped_existing} cached, {st.unscorable} unscorable, "
                      f"{st.null_verdicts} null verdicts, {st.repaired} repaired",
                      flush=True)
                record_provenance(out, "judged", f"{tag}_L{level}", {
                    "judge": f"{judge_seat.kind}:{judge_seat.model}", "level": level,
                    "written": st.written, "skipped_existing": st.skipped_existing,
                    "unscorable": st.unscorable, "null_verdicts": st.null_verdicts,
                    "repaired": st.repaired})


if __name__ == "__main__":
    main()
