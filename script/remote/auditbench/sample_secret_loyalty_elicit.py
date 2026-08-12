"""Box-side stage-1 sampling for the secret_loyalty organism, one engine.

    /venv/main/bin/python script/remote/auditbench/sample_secret_loyalty_elicit.py \
        --base models/Llama-3.3-70B-Instruct \
        --adapter models/adapters/secret_loyalty \
        --tensor-parallel-size 4

The frozen ``questions.json`` files are pushed up from the local machine
before this runs; question writing and extraction are API seats and never run
here. Each seed directory under the run root gets its two response files and
a sampling report, and nothing else.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.common.file_io import load_json
from src.runner.secret_loyalty_elicit_sampling import sample_elicit_arm_pair
from src.runner.vllm_batch_backend import VllmBatchBackend

RUN_ROOT = Path("out/main/auditbench/secret_loyalty")
CONFIG_GLOB = "configs/auditbench/ellicit_auditbench_secret_loyalty_*.json"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", required=True)
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--tensor-parallel-size", type=int, default=4)
    ap.add_argument("--max-model-len", type=int, default=4096)
    ap.add_argument("--max-lora-rank", type=int, default=64)
    ap.add_argument("--gpu-memory-utilization", type=float, default=0.90)
    args = ap.parse_args()

    configs = sorted(Path(".").glob(CONFIG_GLOB))
    if not configs:
        sys.exit(f"no ellicit configs match {CONFIG_GLOB}")
    seeds = []
    for path in configs:
        config = load_json(path)
        out_dir = Path(config["out_dir"])
        questions_path = out_dir / "questions.json"
        if not questions_path.exists():
            sys.exit(f"{questions_path} is missing; push the locally frozen "
                     "questions before sampling")
        questions = load_json(questions_path)["questions"]
        seeds.append((path.name, config, out_dir, questions))
        print(f"{path.name}: {len(questions)} questions -> {out_dir}", flush=True)

    backend = VllmBatchBackend(
        model_name=args.base,
        seed_label="secret-loyalty-elicit",
        max_model_len=args.max_model_len,
        tensor_parallel_size=args.tensor_parallel_size,
        lora_path=args.adapter,
        max_lora_rank=args.max_lora_rank,
        gpu_memory_utilization=args.gpu_memory_utilization,
    )

    for name, config, out_dir, questions in seeds:
        print(f"[{name}] sampling both arms", flush=True)
        report = sample_elicit_arm_pair(backend, config, out_dir, questions)
        for tag, stats in report["arms"].items():
            print(f"[{name}][{tag}] requested={stats['requested']} "
                  f"generated={stats['generated']} failed={stats['failed']}",
                  flush=True)


if __name__ == "__main__":
    main()
