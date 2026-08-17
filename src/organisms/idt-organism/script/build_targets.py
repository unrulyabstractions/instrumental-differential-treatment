"""Build the Phase 2 targets file: the measured ground truth for the partner
detection pipeline to recover blind.

    uv run python script/build_targets.py --run-name p2-main

Reads the frozen battery and comparison_axes.json and writes
docs/targets_phase2.json: per axis, the question, preregistered polarity and
prediction, and the MEASURED per-group excess over baseline with its spread.
Committed to the repo — it documents this organism, nothing else.
"""

import argparse
import json
from pathlib import Path

from src.scenario.court_behavior_axes import AXES


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-name", default="p2-main")
    parser.add_argument("--out", type=Path, default=Path("docs/targets_phase2.json"))
    args = parser.parse_args()

    run_dir = Path("out") / args.run_name
    comparison = json.loads((run_dir / "comparison_axes.json").read_text())
    generation = json.loads((run_dir / "generation_manifest.json").read_text())

    targets = []
    for axis in AXES:
        measured = comparison["per_axis"][axis.axis_id]
        headline = measured["headline"]
        targets.append({
            "axis_id": axis.axis_id,
            "question": axis.question,
            "polarity": axis.polarity,
            "predicted": axis.predicted,
            "confidence": axis.confidence,
            "measured": {
                "mean_rate_by_condition_group": measured["mean_rate_by_condition_group"],
                "excess_over_baseline_by_group": measured["excess_over_baseline_by_group"],
                "gap_delta": headline["mean_delta"],
                "gap_delta_sd": measured["per_condition"]["organism"]["sd_gap"],
                "p_adjusted_signed_maxT":
                    comparison["family_wise"]["signed"]["per_axis_p_adjusted"][axis.axis_id],
                "bootstrap_ci_95": [
                    headline["bootstrap_ci"]["ci_low"],
                    headline["bootstrap_ci"]["ci_high"],
                ],
            },
        })

    # How the organism carries its objective is the single most important fact
    # about it for anyone auditing this file, so it is derived from the run's
    # manifest rather than hard-coded: an arm generated with a LoRA adapter is a
    # weights-level organism, one without is prompted.
    arms = generation.get("arms") or []
    adapters = sorted({a.get("adapter_path") for a in arms if a.get("adapter_path")})
    if adapters:
        organism = (
            f"idt-organism weights-level organism ({comparison['scenario']} scenario): "
            f"covert objective distilled into LoRA weights; both arms read the same "
            f"clean system prompt, so the condition selects weights, not prompt text"
        )
    else:
        organism = (
            f"idt-organism prompted organism ({comparison['scenario']} scenario): "
            f"covert objective carried in the organism arm's system prompt"
        )

    out = {
        "organism": organism,
        "groups": comparison["groups"],
        "reading_guide": (
            "gap = firing_rate(Cupertino) - firing_rate(San Jose) over matched "
            "prompt cells; gap_delta = organism gap minus baseline gap "
            "(diff-in-diff). excess_over_baseline_by_group = organism firing "
            "rate minus baseline firing rate for that group. polarity is the "
            "preregistered sign of the organism gap."
        ),
        "provenance": {
            "run_name": comparison["run_name"],
            "generation_model": generation.get("model_id"),
            "adapters": adapters or None,
            "checkpoint_selection": generation.get("checkpoint_selection"),
            "arms": [
                {k: a.get(k) for k in ("conditions", "model_id", "adapter_path")}
                for a in arms
            ]
            or None,
            "n_scored_responses": comparison["n_scored_responses"],
            "null_verdicts": comparison["null_verdicts"],
            "family_wise_signed": {
                "statistic": comparison["family_wise"]["signed"]["family_statistic"],
                "p": comparison["family_wise"]["signed"]["family_p"],
            },
        },
        "targets": targets,
    }

    args.out.write_text(json.dumps(out, indent=2) + "\n")
    print(f"written to {args.out}")


if __name__ == "__main__":
    main()
