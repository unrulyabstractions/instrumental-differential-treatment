"""Stage 1: generate the response corpus locally.

    uv run python script/generate_responses.py --smoke
    uv run python script/generate_responses.py --n-prompts 20 --n-samples 25

Resumable: rerunning the same command continues where it stopped.
"""

import argparse
import json
from pathlib import Path

from src.runner.local_mps_backend import GenerationConfig, LocalChatModel, resolve_device
from src.runner.resumable_sampling_loop import CONDITIONS, run_sampling
from src.scenario.registry import DEFAULT_SCENARIO, get_scenario, scenario_names


def merge_manifest(manifest_path: Path, summary: dict) -> dict:
    """Fold this invocation's summary into the run's manifest.

    Phase 3 generates one condition per invocation, because the two arms differ
    by WEIGHTS and a process holds one set of weights. Both arms belong to one
    run, so the manifest accumulates an `arms` list -- which checkpoint produced
    which condition -- instead of the last writer erasing the first.
    """
    previous = {}
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text())

    arm = {
        "conditions": summary["conditions"],
        "model_id": summary["model_id"],
        "adapter_path": summary.get("adapter_path"),
        "generated": summary["generated"],
        "failed": summary["failed"],
        "output_path": summary["output_path"],
    }
    arms = [a for a in previous.get("arms", []) if a["conditions"] != arm["conditions"]]
    arms.append(arm)

    merged = previous | summary
    merged["arms"] = sorted(arms, key=lambda a: a["conditions"])
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", default="Qwen/Qwen2.5-1.5B-Instruct")
    parser.add_argument("--scenario", default=DEFAULT_SCENARIO, choices=scenario_names())
    parser.add_argument("--n-prompts", type=int, default=20)
    parser.add_argument("--n-samples", type=int, default=25)
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--max-new-tokens", type=int, default=400)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument(
        "--adapter-path",
        default=None,
        help="LoRA adapter merged into the base model before generating (Phase 3)",
    )
    parser.add_argument(
        "--conditions",
        default=None,
        help=f"comma-separated subset of {','.join(CONDITIONS)} (default: both)",
    )
    parser.add_argument("--out", default=None, help="JSONL path (default derived from run name)")
    parser.add_argument("--run-name", default="main")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="tiny run (2 prompts x 2 samples) to check the pipeline end to end",
    )
    args = parser.parse_args()

    n_prompts, n_samples = args.n_prompts, args.n_samples
    run_name = args.run_name
    if args.smoke:
        n_prompts, n_samples = 2, 2
        if run_name == "main":  # default run name; an explicit --run-name wins
            run_name = "smoke"

    output_path = Path(args.out) if args.out else Path("out") / run_name / "responses.jsonl"

    conditions = tuple(c.strip() for c in args.conditions.split(",")) if args.conditions else None

    config = GenerationConfig(
        model_id=args.model_id,
        temperature=args.temperature,
        max_new_tokens=args.max_new_tokens,
        adapter_path=args.adapter_path,
    )
    scenario = get_scenario(args.scenario)
    print(
        f"device={resolve_device()} model={config.model_id} scenario={scenario.name} "
        f"adapter={config.adapter_path or 'none'} conditions={conditions or 'all'}",
        flush=True,
    )
    print("loading model...", flush=True)
    model = LocalChatModel(config)

    summary = run_sampling(
        model,
        output_path,
        n_prompts,
        n_samples,
        args.batch_size,
        scenario=scenario,
        conditions=conditions,
    )
    summary |= {
        "run_name": run_name,
        "scenario": scenario.name,
        "model_id": config.model_id,
        "adapter_path": config.adapter_path,
        "temperature": config.temperature,
        "max_new_tokens": config.max_new_tokens,
        "n_prompts": n_prompts,
        "n_samples": n_samples,
    }

    manifest_path = output_path.parent / "generation_manifest.json"
    merged = merge_manifest(manifest_path, summary)
    manifest_path.write_text(json.dumps(merged, indent=2) + "\n")
    print(json.dumps(merged, indent=2), flush=True)


if __name__ == "__main__":
    main()
