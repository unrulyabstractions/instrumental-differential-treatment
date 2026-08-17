"""Pick K (samples per prompt) from pilot data instead of guessing.

    uv run python script/choose_sample_size.py --run-name pilot

Reads the pilot's scores, decomposes the noise into the part more sampling can
fix and the part it cannot, and prints what each candidate K costs. Choosing K
this way affects power only -- the hypothesis, the scored axis, and the
preregistered test are untouched.
"""

import argparse
import json
from pathlib import Path

from src.compare.variance_components import (
    detectable_effect,
    estimate_components,
    precision_table,
)
from src.scenario.registry import scenario_for_run


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-name", default="pilot")
    parser.add_argument(
        "--tolerance",
        type=float,
        default=10.0,
        help="max %% precision loss vs K=25 that you are willing to accept",
    )
    args = parser.parse_args()

    run_dir = Path("out") / args.run_name
    scores_path = run_dir / "scores.jsonl"
    if not scores_path.exists():
        raise SystemExit(f"no scores at {scores_path}; run score_responses.py --run-name {args.run_name}")

    scenario = scenario_for_run(run_dir)
    scored = [json.loads(line) for line in scores_path.read_text().splitlines() if line.strip()]
    components = estimate_components(scored, *scenario.groups)

    sw, sb = components["sigma_within"], components["sigma_between"]
    ratio = (sw / sb) if sb > 0 else float("inf")

    print(f"\n=== variance components from '{args.run_name}' ===")
    print(f"scored responses      {len(scored)}")
    print(f"cells                 {components['n_cells']} (mean K = {components['pilot_k']:.1f})")
    print(f"sigma_within          {sw:.3f}   (shrinks as 1/sqrt(K) -- more samples help)")
    print(f"sigma_between         {sb:.3f}   (irreducible -- real prompt-to-prompt variation)")
    print(f"ratio within/between  {ratio:.2f}")
    if ratio > 2:
        print("  -> sampling noise dominates: K is doing real work, cut it carefully")
    elif ratio < 0.5:
        print("  -> prompt variation dominates: extra samples buy very little, K can be small")
    else:
        print("  -> comparable: moderate K is efficient")

    rows = precision_table(sw, sb)
    print(f"\n{'K':>4} {'gens':>6} {'gap sd':>8} {'vs K=25':>9} {'min detectable gap':>19}")
    print("-" * 52)
    for row in rows:
        mde = detectable_effect(sw, sb, row["k"])
        print(
            f"{row['k']:>4} {row['generations']:>6} {row['gap_sd']:>8.3f} "
            f"{row['pct_worse_than_k25']:>8.1f}% {mde:>19.3f}"
        )

    affordable = [r for r in rows if r["pct_worse_than_k25"] <= args.tolerance]
    recommended = min(affordable, key=lambda r: r["k"]) if affordable else rows[0]
    print(
        f"\nrecommended K = {recommended['k']} "
        f"({recommended['generations']} generations, "
        f"{recommended['pct_worse_than_k25']:.1f}% worse than K=25, "
        f"within your {args.tolerance:.0f}% tolerance)"
    )
    print("'min detectable gap' = smallest true mean gap findable at p<0.05, 80% power, n=20 prompts")

    output = {
        "run_name": args.run_name,
        "components": {k: v for k, v in components.items() if k != "gaps_by_condition"},
        "tolerance_pct": args.tolerance,
        "table": [
            {**row, "min_detectable_gap": detectable_effect(sw, sb, row["k"])} for row in rows
        ],
        "recommended_k": recommended["k"],
    }
    path = run_dir / "sample_size_decision.json"
    path.write_text(json.dumps(output, indent=2) + "\n")
    print(f"\nwritten to {path}")


if __name__ == "__main__":
    main()
