"""Miniature user-awareness replication, read with the base-free detector.

    uv run python script/external/user_awareness_collect_and_detect.py \\
        --target-kind openai --target-model gpt-5-nano \\
        --out out/main/external/user_awareness

The subject model answers the frozen borderline prompts once per user identity,
the identity supplied in its system prompt exactly as a minimal Transluce
harness would. A judge scores every reply blind to the identity on the awareness
axes. Then the base-free detector runs candidate-versus-candidate over the
identities, since a served frontier model has no base arm. The detector's
candidate is the user whose treatment departs most from the others, which is the
IDT reading of the Transluce shift.

Nothing operational is generated: the prompts ask for general, defensive, or
dual-use-adjacent explanation, and the run records refusals rather than
retrying them. The subject is the cheapest model that shows the effect; the
judge stays a strong local seat.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from src.common.file_io import read_jsonl, save_json
from src.compare.behavior_count_table import build_behavior_table
from src.compare.candidate_detachment_statistic import candidate_detachment_test
from src.compare.reference_free_max_statistic import reference_free_max_test
from src.external.user_awareness_materials import (AWARENESS_AXES,
                                                  BORDERLINE_PROMPTS,
                                                  IDENTITIES)
from src.external.user_awareness_materials import identity_system
from src.runner.model_backend_router import resolve_backend
from src.score.judge_seat_config import (DEFAULT_JUDGE_KIND,
                                         DEFAULT_JUDGE_MODEL,
                                         judge_backend_kwargs)
from src.runner.response_sampling import sample_prompt_sets
from src.score.verdict_panel import score_responses


def _identity_prompt_set(ident: dict) -> dict[str, list[dict]]:
    """One identity's borderline prompts, keyed so its cells never collide.

    The identity lives in the system prompt, supplied per identity through the
    sampler's system-prompt slot, exactly as a minimal Transluce harness states
    who the user is. The candidate label is the identity, so the detector reads
    identity against identity.
    """
    # The sampler composes instruction_id as "<system_id>::<template_id>", so
    # the row carries the bare template id.
    rows = [{"instruction_id": f"q{i:02d}", "text": text}
            for i, text in enumerate(BORDERLINE_PROMPTS)]
    return {ident["key"]: rows}


def _detect(verdicts_path: Path, permutations: int, seed: int) -> dict:
    axes = [a["axis_id"] for a in AWARENESS_AXES]
    rows = [r for r in read_jsonl(verdicts_path) if int(r["level"]) == 1]
    table = build_behavior_table(rows, axes)
    # Keep every candidate-axis pair, not the display-truncated top twelve, so
    # the appendix can read the named candidate's whole per-axis signature.
    all_pairs = len(IDENTITIES) * len(AWARENESS_AXES)
    out = reference_free_max_test(table, n_permutations=permutations, seed=seed,
                                  top=all_pairs)
    out["detachment"] = candidate_detachment_test(table, n_permutations=permutations,
                                                  seed=seed)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target-kind", default="openai")
    ap.add_argument("--target-model", default="gpt-5-nano")
    ap.add_argument("--judge-kind", default=DEFAULT_JUDGE_KIND)
    ap.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL,
                    help="judge seat; the default comes from the config layer, "
                         "not this script")
    ap.add_argument("--out", type=Path, default=Path("out/main/external/user_awareness"))
    ap.add_argument("--samples", type=int, default=4)
    ap.add_argument("--max-new", type=int, default=600)
    ap.add_argument("--permutations", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=20260726)
    ap.add_argument("--reasoning-effort", default=None,
                    help="passed to a reasoning target, e.g. minimal or low")
    ap.add_argument("--detect-only", action="store_true")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    responses = args.out / "responses_target.jsonl"
    verdicts = args.out / "verdicts_target.jsonl"

    if not args.detect_only:
        target_kwargs = {}
        if args.reasoning_effort:
            target_kwargs["reasoning_effort"] = args.reasoning_effort
        target = resolve_backend(args.target_kind, args.target_model, **target_kwargs)
        generated = failed = skipped = 0
        for ident in IDENTITIES:
            stats = sample_prompt_sets(
                target, _identity_prompt_set(ident), args.samples, responses,
                system_prompts=(("none", identity_system(ident)),),
                max_new_tokens=args.max_new, batch_size=8, show_progress=False)
            generated += stats.generated
            failed += stats.failed
            skipped += stats.skipped_existing
            print(f"  {ident['key']}: generated {stats.generated}, "
                  f"failed {stats.failed}", flush=True)
        print(f"sampling: generated {generated}, failed {failed}, "
              f"skipped {skipped}", flush=True)

        judge = resolve_backend(args.judge_kind, args.judge_model,
                                **judge_backend_kwargs(args.judge_model))
        scored = score_responses(
            judge, level=1, domain="", activation="", axes=list(AWARENESS_AXES),
            responses_path=responses, verdicts_path=verdicts)
        print(f"scoring: wrote {scored.written}, unscorable {scored.unscorable}, "
              f"nulls {scored.null_verdicts}", flush=True)

    result = _detect(verdicts, args.permutations, args.seed)
    # Under --detect-only no judge was seated this run; the verdicts on disk
    # carry the seat that wrote them, and that seat is the honest attribution.
    # Writing the CLI default here once recorded a judge that never ran.
    if args.detect_only:
        seats = {r.get("judge") for r in read_jsonl(verdicts) if r.get("judge")}
        if len(seats) != 1:
            raise SystemExit(f"verdicts carry {len(seats)} judge seats {sorted(seats)}; "
                             "refusing to attribute the detection to one")
        judge_name = seats.pop()
    else:
        judge_name = f"{args.judge_kind}:{args.judge_model}"
    record = {
        "subject": f"{args.target_kind}:{args.target_model}",
        "judge": judge_name,
        "n_identities": len(IDENTITIES), "n_prompts": len(BORDERLINE_PROMPTS),
        "samples_per_cell": args.samples, "seed": args.seed,
        "identities": {i["key"]: {"name": i["name"], "group": i["group"]}
                       for i in IDENTITIES},
        "axes": {a["axis_id"]: a["question"] for a in AWARENESS_AXES},
        "reference_free": result,
    }
    save_json(args.out / "user_awareness_detection.json", record)
    rf, det = result, result["detachment"]
    print(f"\nsubject {record['subject']}", flush=True)
    print(f"reference-free max: S={rf['statistic']:.3f} p={rf['p_family_wise']:.4f} "
          f"named={rf['named']} axis={rf['named_axis']}", flush=True)
    print(f"detachment:         S={det['statistic']:.3f} p={det['p_family_wise']:.4f} "
          f"named={det['named']}", flush=True)


if __name__ == "__main__":
    main()
