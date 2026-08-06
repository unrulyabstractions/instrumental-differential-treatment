"""Stage 1: generate the response corpus locally.

    uv run python script/generate_responses.py --smoke
    uv run python script/generate_responses.py --n-prompts 20 --n-samples 25

Resumable: rerunning the same command continues where it stopped.
"""

import argparse
import json
from pathlib import Path

from src.runner.local_mps_backend import GenerationConfig, LocalChatModel, resolve_device
from src.runner.resumable_sampling_loop import run_sampling


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", default="Qwen/Qwen2.5-1.5B-Instruct")
    parser.add_argument("--n-prompts", type=int, default=20)
    parser.add_argument("--n-samples", type=int, default=25)
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--max-new-tokens", type=int, default=400)
    parser.add_argument("--batch-size", type=int, default=16)
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
        n_prompts, n_samples, run_name = 2, 2, "smoke"

    output_path = Path(args.out) if args.out else Path("out") / run_name / "responses.jsonl"

    config = GenerationConfig(
        model_id=args.model_id,
        temperature=args.temperature,
        max_new_tokens=args.max_new_tokens,
    )
    print(f"device={resolve_device()} model={config.model_id}", flush=True)
    print("loading model...", flush=True)
    model = LocalChatModel(config)

    summary = run_sampling(model, output_path, n_prompts, n_samples, args.batch_size)
    summary |= {
        "run_name": run_name,
        "model_id": config.model_id,
        "temperature": config.temperature,
        "max_new_tokens": config.max_new_tokens,
        "n_prompts": n_prompts,
        "n_samples": n_samples,
    }

    manifest_path = output_path.parent / "generation_manifest.json"
    manifest_path.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
