"""Stage 3: run the preregistered test and write the results.

    uv run python script/compare_groups.py --run-name main

Every number in the writeup comes out of this script reading out/, so no result
is ever hand-typed from a previous message.
"""

import argparse
import json
from pathlib import Path

from src.compare.cell_aggregation import aggregate_cells, paired_gaps
from src.compare.paired_divergence import divergence_summary, paired_delta
from src.compare.sign_flip_permutation import bootstrap_ci, sign_flip_test
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
    parser.add_argument("--run-name", default="main")
    parser.add_argument("--permutations", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    run_dir = Path("out") / args.run_name
    scenario = scenario_for_run(run_dir)
    group_a, group_b = scenario.groups
    scored = read_jsonl(run_dir / "scores.jsonl")
    aggregated = aggregate_cells(scored)
    cells = aggregated["cells"]

    per_condition = {}
    gaps_by_condition = {}
    prompts_by_condition = {}
    for condition in ("organism", "baseline"):
        prompt_ids, gaps, dropped = paired_gaps(cells, condition, group_a, group_b)
        gaps_by_condition[condition] = gaps
        prompts_by_condition[condition] = prompt_ids
        per_condition[condition] = {
            **divergence_summary(gaps),
            "dropped_prompts": dropped,
            "group_effect_test": sign_flip_test(
                gaps, n_permutations=args.permutations, seed=args.seed
            ),
        }

    # The headline test needs the same prompts in the same order in both arms.
    shared = [p for p in prompts_by_condition["organism"] if p in prompts_by_condition["baseline"]]
    organism_gaps = [
        gaps_by_condition["organism"][prompts_by_condition["organism"].index(p)] for p in shared
    ]
    baseline_gaps = [
        gaps_by_condition["baseline"][prompts_by_condition["baseline"].index(p)] for p in shared
    ]
    deltas = paired_delta(organism_gaps, baseline_gaps)

    results = {
        "run_name": args.run_name,
        "scenario": scenario.name,
        "groups": {"a": group_a, "b": group_b, "sign": f"gap = {group_a} - {group_b}"},
        "n_scored_responses": len(scored),
        "null_verdicts": aggregated["total_null"],
        "per_condition": per_condition,
        "headline": {
            "hypothesis": "D(organism) - D(baseline) > 0",
            "n_shared_prompts": len(shared),
            "mean_delta": sum(deltas) / len(deltas),
            "permutation_test": sign_flip_test(
                deltas, n_permutations=args.permutations, seed=args.seed
            ),
            "bootstrap_ci": bootstrap_ci(deltas, seed=args.seed),
        },
    }

    output_path = run_dir / "comparison_results.json"
    output_path.write_text(json.dumps(results, indent=2) + "\n")

    headline = results["headline"]
    print(f"\n=== {args.run_name} ===")
    for condition, summary in per_condition.items():
        print(
            f"{condition:9s} mean_gap={summary['mean_gap']:+.3f} "
            f"dz={summary['cohens_dz']:+.3f} "
            f"p={summary['group_effect_test']['p_value']:.4f} "
            f"(n={summary['n_prompts']})"
        )
    ci = headline["bootstrap_ci"]
    print(
        f"HEADLINE  delta={headline['mean_delta']:+.3f} "
        f"p={headline['permutation_test']['p_value']:.4f} "
        f"95% CI [{ci['ci_low']:+.3f}, {ci['ci_high']:+.3f}]"
    )
    print(f"null verdicts: {results['null_verdicts']}")
    print(f"\nwritten to {output_path}")


if __name__ == "__main__":
    main()
