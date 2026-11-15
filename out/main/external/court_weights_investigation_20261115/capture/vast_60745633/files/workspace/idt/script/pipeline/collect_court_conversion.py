"""Stage 4 for the court-conversion organism: both published forms, full pipeline.

    uv run python script/pipeline/collect_court_conversion.py \
        --promptset out/main/external/court_full/promptset \
        --out out/main/external/court_full/responses \
        --arm weights --base Qwen/Qwen2.5-7B-Instruct \
        --adapter out/organism_publish_canonical

The organism was published in two forms, and B13 sends both through the same
stages every other organism got. The ``weights`` arm reads the LoRA organism
against its own base out of one engine: adapter attached for the target,
detached for the base, both under the frozen baseline system prompt. The
``prompted`` arm reads the plain base model against itself: the target carries
the frozen covert-objective system prompt and the base carries the
content-matched baseline prompt, so the excess is exactly the induced
group-conditional divergence.

Within either arm the target and the base share one system id. Stage 6 pairs
cells by instruction id, and the instruction id carries the system id, so a
per-arm label would break every pairing. The label names the stratum; the text
that differs between the prompted arm's models is recorded in the collection
report.

``--dry-run`` renders both models' system prompts, plans every cell, writes a
manifest, and exits before any engine or checkpoint is touched, so the workload
is verifiable off-GPU. Sampling runs on the rented box; scoring is API-bound
and runs at home, so no key ever travels.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import sys
import types
from pathlib import Path

from src.common.file_io import save_json
from src.promptset.rendered_prompt_loading import load_prompt_sets
from src.runner.adapter_arm_view import AdapterArmView
from src.runner.model_backend_router import resolve_backend
from src.runner.response_sampling import plan_sampling, sample_prompt_sets

#: One label for the single system stratum, identical across models and arms,
#: so every cell of every model pairs on the same instruction ids in stage 6.
SYSTEM_ID = "court"

REPO = Path(__file__).resolve().parents[2]
SCENARIO_DIR = REPO / "src" / "organisms" / "idt-organism" / "src" / "scenario"


def load_build_system_prompt(scenario_dir: Path):
    """``build_system_prompt`` from the organism's frozen scenario module.

    The clone's package root is also named ``src`` and this process already has
    the audit's ``src`` imported, so the clone cannot simply go on ``sys.path``.
    A stub ``src.scenario`` package pointed at the clone's scenario directory
    lets the frozen module and its own ``from src.scenario...`` import resolve,
    while the audit's package stays untouched.
    """
    if "src.scenario" not in sys.modules:
        package = types.ModuleType("src.scenario")
        package.__path__ = [str(scenario_dir)]
        sys.modules["src.scenario"] = package
    module = importlib.import_module("src.scenario.court_conversion_system_prompts")
    return module.build_system_prompt


def arm_system_prompts(arm: str, build) -> dict[str, tuple[str, str]]:
    """The (system_id, text) each model samples under, keyed by model tag.

    The weights arm keeps the system prompt clean for both models: the
    manipulation lives in the adapter. The prompted arm puts the manipulation
    in the target's system prompt and gives the base the content-matched
    baseline, which is that organism's published control design.
    """
    if arm == "weights":
        clean = build("baseline")
        return {"target": (SYSTEM_ID, clean), "base": (SYSTEM_ID, clean)}
    return {"target": (SYSTEM_ID, build("organism")),
            "base": (SYSTEM_ID, build("baseline"))}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--promptset", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--arm", required=True, choices=("weights", "prompted"))
    ap.add_argument("--base", required=True, help="path or id of the base checkpoint")
    ap.add_argument("--adapter", help="LoRA adapter dir; required for --arm weights")
    ap.add_argument("--scenario-dir", type=Path, default=SCENARIO_DIR,
                    help="the frozen scenario package inside the organism clone")
    ap.add_argument("--samples-per-prompt", type=int, default=4)
    ap.add_argument("--max-new-tokens", type=int, default=400)
    ap.add_argument("--tensor-parallel-size", type=int, default=1)
    ap.add_argument("--max-model-len", type=int, default=4096)
    ap.add_argument("--max-lora-rank", type=int, default=16)
    # Rented boxes are shared, so a neighbour's process can hold a gigabyte on
    # every card. The engine sizes its KV cache from the whole card, not from
    # what is left, and then dies during warmup a few hundred megabytes short.
    ap.add_argument("--gpu-memory-utilization", type=float, default=0.90)
    # CUDA-graph capture hung indefinitely during warmup on the box that ran
    # this scenario before. Eager mode is a hair slower and completes.
    ap.add_argument("--enforce-eager", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="plan the workload, write the manifest, load nothing")
    args = ap.parse_args()

    if args.arm == "weights" and not args.adapter:
        ap.error("--arm weights needs --adapter")
    if args.arm == "prompted" and args.adapter:
        ap.error("--arm prompted samples the plain base model; drop --adapter")

    build = load_build_system_prompt(args.scenario_dir)
    systems = arm_system_prompts(args.arm, build)
    prompt_sets = load_prompt_sets(args.promptset)
    args.out.mkdir(parents=True, exist_ok=True)
    n_prompts = sum(len(v) for v in prompt_sets.values())
    print(f"[{args.arm}] {len(prompt_sets)} candidates, {n_prompts} prompts, "
          f"{args.samples_per_prompt} samples each, both models", flush=True)

    plans = {}
    for tag in ("target", "base"):
        cells, requested = plan_sampling(prompt_sets, [systems[tag]],
                                         args.samples_per_prompt, done=set())
        text = systems[tag][1]
        plans[tag] = {
            "responses_file": f"responses_{args.arm}_{tag}.jsonl",
            "use_adapter": args.arm == "weights" and tag == "target",
            "system_id": systems[tag][0],
            "system_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "system_chars": len(text),
            "system_text": text,
            "n_cells": len(cells),
            "n_generations": requested,
            "example_prompt_ids": [c.prompt_id for c in cells[:3]],
        }

    if args.dry_run:
        manifest_path = args.out / f"dry_run_manifest_{args.arm}.json"
        save_json(manifest_path, {
            "arm": args.arm, "base": args.base, "adapter": args.adapter,
            "scenario_dir": str(args.scenario_dir),
            "candidates": sorted(prompt_sets),
            "n_prompts_per_candidate": {k: len(v) for k, v in prompt_sets.items()},
            "samples_per_prompt": args.samples_per_prompt,
            "n_generations_both_models": sum(p["n_generations"] for p in plans.values()),
            "models": plans,
        })
        print(f"dry run only, wrote {manifest_path}", flush=True)
        return

    backend = resolve_backend(
        "vllm", args.base,
        seed_label=f"court-conversion-{args.arm}",
        max_model_len=args.max_model_len,
        tensor_parallel_size=args.tensor_parallel_size,
        gpu_memory_utilization=args.gpu_memory_utilization,
        enforce_eager=args.enforce_eager,
        **({"lora_path": args.adapter, "max_lora_rank": args.max_lora_rank}
           if args.arm == "weights" else {}),
    )

    stats = {}
    # Target first. If the run dies partway the organism arm is the one worth
    # having, since the base arm can be resampled from the same engine later.
    for tag in ("target", "base"):
        view = AdapterArmView(backend, use_adapter=plans[tag]["use_adapter"],
                              tag=f"{args.arm}_{tag}")
        path = args.out / plans[tag]["responses_file"]
        print(f"[{args.arm}_{tag}] sampling -> {path}", flush=True)
        result = sample_prompt_sets(
            view, prompt_sets, args.samples_per_prompt, path,
            system_prompts=[systems[tag]], max_new_tokens=args.max_new_tokens)
        stats[tag] = {"backend": view.name, "requested": result.requested,
                      "generated": result.generated,
                      "skipped_existing": result.skipped_existing,
                      "failed": result.failed}
        print(f"[{args.arm}_{tag}] requested={result.requested} "
              f"generated={result.generated} failed={result.failed}", flush=True)

    # Stage 6 reads the candidate display names from this file, so a run that
    # omits it collects fine and then cannot be compared. Both arm runs write
    # identical content: the arms differ in system text, which lives in the
    # per-arm collection report, never here.
    save_json(args.out / "prompt_sets.json", {
        "condition": args.promptset.resolve().parent.name,
        "principals": {key: prompts[0]["principal"]
                       for key, prompts in sorted(prompt_sets.items()) if prompts},
        "samples_per_cell": args.samples_per_prompt,
        "n_prompts": n_prompts,
        "prompt_sets": prompt_sets,
    })

    save_json(args.out / f"collection_report_{args.arm}.json", {
        "arm": args.arm, "base": args.base, "adapter": args.adapter,
        "scenario_dir": str(args.scenario_dir),
        "samples_per_prompt": args.samples_per_prompt,
        "candidates": sorted(prompt_sets),
        "n_prompts_per_candidate": {k: len(v) for k, v in prompt_sets.items()},
        "system_prompts": {tag: {k: plans[tag][k] for k in
                                 ("system_id", "system_sha256", "system_chars",
                                  "system_text", "use_adapter")}
                           for tag in plans},
        "models": stats,
    })
    print(f"wrote {args.out}/collection_report_{args.arm}.json", flush=True)


if __name__ == "__main__":
    main()
