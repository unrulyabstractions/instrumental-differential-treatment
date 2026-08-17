"""Phase 2 comparison: per-axis diff-in-diff and the family-wise max test.

    uv run python script/compare_axes.py --run-name p2-main

Reads axis_scores.jsonl, folds each axis's boolean verdicts into prompt-cell
firing rates with the same cell machinery as the scalar pipeline, runs the
preregistered per-axis and family-wise tests, and writes comparison_axes.json.
Every number in the Phase 2 writeup and the targets file comes from this
output — nothing is hand-transcribed.
"""

import argparse
import json
from pathlib import Path

from src.compare.cell_aggregation import aggregate_cells, paired_gaps
from src.compare.max_over_axes import max_over_axes_test
from src.compare.paired_divergence import divergence_summary, paired_delta
from src.compare.sign_flip_permutation import bootstrap_ci, sign_flip_test
from src.scenario.court_behavior_axes import AXES
from src.scenario.registry import scenario_for_run


def read_jsonl(path: Path) -> list[dict]:
    records = []
    with path.open() as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-name", default="p2-main")
    parser.add_argument("--permutations", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    run_dir = Path("out") / args.run_name
    scenario = scenario_for_run(run_dir)
    group_a, group_b = scenario.groups
    scored = read_jsonl(run_dir / "axis_scores.jsonl")

    per_axis: dict[str, dict] = {}
    deltas_by_axis: dict[str, list[float]] = {}
    shared_prompts_by_axis: dict[str, list[str]] = {}

    for axis in AXES:
        # One axis's booleans become 0/1 "scores"; a cell mean is a firing rate.
        axis_records = [
            {
                "condition": r["condition"],
                "prompt_id": r["prompt_id"],
                "group": r["group"],
                "score": (None if r["verdicts"].get(axis.axis_id) is None
                          else int(r["verdicts"][axis.axis_id])),
            }
            for r in scored
        ]
        aggregated = aggregate_cells(axis_records)
        cells = aggregated["cells"]

        condition_summaries = {}
        gaps_by_condition = {}
        prompts_by_condition = {}
        rate_by_condition_group = {}
        for condition in ("organism", "baseline"):
            prompt_ids, gaps, dropped = paired_gaps(cells, condition, group_a, group_b)
            gaps_by_condition[condition] = gaps
            prompts_by_condition[condition] = prompt_ids
            for group in (group_a, group_b):
                rates = [
                    cells[(condition, p, group)]
                    for p in prompt_ids
                    if cells.get((condition, p, group)) is not None
                ]
                rate_by_condition_group[f"{condition}/{group}"] = (
                    sum(rates) / len(rates) if rates else None
                )
            oriented = [axis.polarity * g for g in gaps]
            condition_summaries[condition] = {
                **divergence_summary(gaps),
                "dropped_prompts": dropped,
                "group_effect_test_oriented": sign_flip_test(
                    oriented, n_permutations=args.permutations, seed=args.seed
                ),
            }

        shared = [
            p for p in prompts_by_condition["organism"]
            if p in prompts_by_condition["baseline"]
        ]
        organism_gaps = [
            gaps_by_condition["organism"][prompts_by_condition["organism"].index(p)]
            for p in shared
        ]
        baseline_gaps = [
            gaps_by_condition["baseline"][prompts_by_condition["baseline"].index(p)]
            for p in shared
        ]
        deltas = paired_delta(organism_gaps, baseline_gaps)
        deltas_by_axis[axis.axis_id] = deltas
        shared_prompts_by_axis[axis.axis_id] = shared
        oriented_deltas = [axis.polarity * d for d in deltas]

        # Per-group excess over baseline: how much more the axis fires for this
        # group with the objective than without it (mean over prompt cells).
        excess_by_group = {}
        for group in (group_a, group_b):
            org = rate_by_condition_group[f"organism/{group}"]
            base = rate_by_condition_group[f"baseline/{group}"]
            excess_by_group[group] = None if org is None or base is None else org - base

        per_axis[axis.axis_id] = {
            "question": axis.question,
            "polarity": axis.polarity,
            "predicted": axis.predicted,
            "confidence": axis.confidence,
            "mean_rate_by_condition_group": rate_by_condition_group,
            "excess_over_baseline_by_group": excess_by_group,
            "per_condition": condition_summaries,
            "headline": {
                "n_shared_prompts": len(shared),
                "mean_delta": sum(deltas) / len(deltas),
                "mean_delta_oriented": sum(oriented_deltas) / len(oriented_deltas),
                "permutation_test_oriented": sign_flip_test(
                    oriented_deltas, n_permutations=args.permutations, seed=args.seed
                ),
                "bootstrap_ci": bootstrap_ci(deltas, seed=args.seed),
            },
        }

    prompt_sets = {tuple(v) for v in shared_prompts_by_axis.values()}
    if len(prompt_sets) != 1:
        raise SystemExit(f"axes cover different shared prompt sets: {shared_prompts_by_axis}")

    polarities = {axis.axis_id: axis.polarity for axis in AXES}
    family = {
        "signed": max_over_axes_test(
            deltas_by_axis, polarities, signed=True,
            n_permutations=args.permutations, seed=args.seed,
        ),
        "unsigned": max_over_axes_test(
            deltas_by_axis, polarities, signed=False,
            n_permutations=args.permutations, seed=args.seed,
        ),
    }

    n_null = sum(
        1 for r in scored for a in polarities if r["verdicts"].get(a) is None
    )
    results = {
        "run_name": args.run_name,
        "scenario": scenario.name,
        "groups": {"a": group_a, "b": group_b, "sign": f"gap = {group_a} - {group_b}"},
        "n_scored_responses": len(scored),
        "null_verdicts": n_null,
        "per_axis": per_axis,
        "family_wise": family,
    }

    output_path = run_dir / "comparison_axes.json"
    output_path.write_text(json.dumps(results, indent=2) + "\n")

    print(f"\n=== {args.run_name} axes ===")
    for axis_id, summary in per_axis.items():
        headline = summary["headline"]
        test = headline["permutation_test_oriented"]
        print(
            f"{axis_id:32s} delta={headline['mean_delta']:+.3f} "
            f"(oriented {headline['mean_delta_oriented']:+.3f}) "
            f"p={test['p_value']:.4f} "
            f"p_adj={family['signed']['per_axis_p_adjusted'][axis_id]:.4f}"
        )
    print(
        f"FAMILY (signed maxT)  S={family['signed']['family_statistic']:+.3f} "
        f"p={family['signed']['family_p']:.4f}   "
        f"(unsigned S={family['unsigned']['family_statistic']:.3f} "
        f"p={family['unsigned']['family_p']:.4f})"
    )
    print(f"null verdicts: {n_null}")
    print(f"\nwritten to {output_path}")


if __name__ == "__main__":
    main()
