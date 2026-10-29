"""Stage 4 across many AuditBench organisms that share one base model.

    uv run python script/pipeline/collect_auditbench_fleet.py \
        --promptset out/main/auditbench/contextual_optimism/promptset \
        --base models/Llama-3.3-70B-Instruct \
        --adapter-root models/adapters --out out/main/auditbench \
        --organisms defer_to_users,flattery,self_promotion

Every organism in the benchmark is a LoRA delta over the same base, so one
engine serves all of them. The base weights load once and each organism is a
3 GB adapter swapped in per submission, which is what makes auditing fifteen
organisms cost little more than auditing one.

The base arm is collected once and shared. It does not depend on which adapter
is attached, and sampling it fifteen times would spend an hour of a rented card
reproducing the same file.

This exists to measure what the detector does on organisms whose hidden
behavior does NOT read the user. The registered test should stay silent on
them, and a detector that fires on every organism it is shown would be worth
nothing.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from src.common.file_io import save_json
from src.runner.adapter_arm_view import AdapterArmView
from src.runner.auditbench_identity_prompt import AUDITBENCH_SYSTEM_VARIANTS
from src.runner.vllm_batch_backend import VllmBatchBackend
from src.runner.response_sampling import sample_prompt_sets
from src.promptset.rendered_prompt_loading import load_prompt_sets

#: Seed labels that already sampled a Llama-3.3-70B base arm on these prompts:
#: collect_auditbench.py (the shared base) and this script's default.
USED_BASE_SEED_LABELS = frozenset({"auditbench-collect", "auditbench-fleet"})


def check_base_seed(base_out: Path, seed_label: str) -> None:
    """Refuse to resume a base file that another seed label started.

    Sampling resumes from rows already on disk, so pointing a new seed at an
    existing base file would silently extend the old sample. The label is
    recorded beside the file the first time and must match on every resume.
    """
    record = base_out / "seed_label.txt"
    rows = base_out / "responses_base.jsonl"
    if record.exists():
        if record.read_text().strip() != seed_label:
            raise SystemExit(f"{rows} was started with seed {record.read_text().strip()!r}")
    elif rows.exists():
        raise SystemExit(f"{rows} exists with no recorded seed label; refusing to extend it")
    else:
        base_out.mkdir(parents=True, exist_ok=True)
        record.write_text(seed_label + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--promptset", type=Path, required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--adapter-root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--organisms", required=True,
                    help="comma-separated behavior names, one adapter directory each")
    ap.add_argument("--samples-per-prompt", type=int, default=16)
    ap.add_argument("--max-new-tokens", type=int, default=400)
    ap.add_argument("--tensor-parallel-size", type=int, default=4)
    ap.add_argument("--max-model-len", type=int, default=4096)
    ap.add_argument("--max-lora-rank", type=int, default=64)
    ap.add_argument("--skip-base", action="store_true",
                    help="the shared base arm is already collected elsewhere")
    ap.add_argument("--base-out", type=Path, default=None,
                    help="where the shared base arm lives or is written")
    ap.add_argument("--seed-label", default="auditbench-fleet",
                    help="engine seed label; a fresh base sample needs a label no "
                         "earlier collection used")
    args = ap.parse_args()
    # The shared base arm exists. Sampling a base arm again is only a fresh,
    # independent sample if it has its own directory and a seed no earlier
    # collection used; otherwise it would reproduce or overwrite the old one.
    if not args.skip_base and (args.base_out is None
                               or args.seed_label in USED_BASE_SEED_LABELS):
        raise SystemExit("a base arm needs --base-out and a --seed-label not in "
                         f"{sorted(USED_BASE_SEED_LABELS)}; the shared base exists")
    if not args.skip_base:
        check_base_seed(args.base_out, args.seed_label)

    organisms = [o.strip() for o in args.organisms.split(",") if o.strip()]
    prompt_sets = load_prompt_sets(args.promptset)
    n_prompts = sum(len(v) for v in prompt_sets.values())
    print(f"{len(organisms)} organisms, {len(prompt_sets)} candidates, "
          f"{n_prompts} prompts, {args.samples_per_prompt} samples each", flush=True)

    # One engine for the whole fleet. The adapter path is set per organism, so
    # the engine is built with LoRA enabled and the request carries the choice.
    first = args.adapter_root / organisms[0]
    backend = VllmBatchBackend(
        model_name=args.base, seed_label=args.seed_label,
        max_model_len=args.max_model_len,
        tensor_parallel_size=args.tensor_parallel_size,
        lora_path=str(first), max_lora_rank=args.max_lora_rank)

    report: dict = {"base": args.base, "organisms": {}}

    if not args.skip_base:
        base_out = args.base_out or (args.out / "_shared_base")
        base_out.mkdir(parents=True, exist_ok=True)
        arm = AdapterArmView(backend, use_adapter=False, tag="base")
        stats = sample_prompt_sets(
            arm, prompt_sets, args.samples_per_prompt,
            base_out / "responses_base.jsonl",
            system_prompts=AUDITBENCH_SYSTEM_VARIANTS,
            max_new_tokens=args.max_new_tokens)
        report["shared_base"] = {"generated": stats.generated, "failed": stats.failed,
                                 "path": str(base_out / "responses_base.jsonl")}
        print(f"[base] {stats.generated} new, {stats.failed} failed", flush=True)

    for name in organisms:
        adapter = args.adapter_root / name
        if not adapter.exists():
            print(f"[{name}] no adapter at {adapter}, skipping", flush=True)
            continue
        # Point the engine's single LoRA slot at this organism.
        backend.set_adapter(str(adapter), name)
        target = args.out / name
        target.mkdir(parents=True, exist_ok=True)
        arm = AdapterArmView(backend, use_adapter=True, tag=name)
        stats = sample_prompt_sets(
            arm, prompt_sets, args.samples_per_prompt,
            target / "responses_target.jsonl",
            system_prompts=AUDITBENCH_SYSTEM_VARIANTS,
            max_new_tokens=args.max_new_tokens)
        report["organisms"][name] = {"adapter": str(adapter),
                                     "generated": stats.generated,
                                     "failed": stats.failed}
        print(f"[{name}] {stats.generated} new, {stats.failed} failed", flush=True)
        save_json(args.out / "fleet_report.json", report)

    save_json(args.out / "fleet_report.json", report)
    print(f"wrote {args.out}/fleet_report.json", flush=True)


if __name__ == "__main__":
    main()
