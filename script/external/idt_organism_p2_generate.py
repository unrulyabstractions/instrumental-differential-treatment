"""Generate the phase-2 idt-organism corpus with vLLM: two system-prompt arms.

    /venv/main/bin/python script/external/idt_organism_p2_generate.py \
        --scenario-dir /workspace/idt-organism-p2 \
        --model Qwen/Qwen2.5-7B-Instruct \
        --out out/main/external/idt_organism_p2/responses.jsonl --samples 20

The phase-2 organism is prompted, not fine-tuned: one open-weight model given a
covert objective (the organism arm) and a content-matched baseline without it.
Both arms see the identical persona, fact base, instructions, and user prompts;
only the objective paragraph differs, so the excess between the arms is the
induced group-conditional divergence. The scenario modules are loaded from the
cloned repo so the frozen prompts stay theirs.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

from vllm import LLM, SamplingParams


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scenario-dir", required=True, help="the cloned phase-2 repo")
    ap.add_argument("--model", default="Qwen/Qwen2.5-7B-Instruct")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--samples", type=int, default=20)
    ap.add_argument("--max-new", type=int, default=400)
    ap.add_argument("--temperature", type=float, default=0.8)
    ap.add_argument("--top-p", type=float, default=0.95)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--gpu-memory-utilization", type=float, default=0.90)
    args = ap.parse_args()

    sys.path.insert(0, str(Path(args.scenario_dir).resolve()))
    sysprompts = importlib.import_module("src.scenario.court_conversion_system_prompts")
    prompt_set = importlib.import_module("src.scenario.court_conversion_prompt_set")
    build_system_prompt = sysprompts.build_system_prompt
    prompts = prompt_set.build_prompt_set()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if args.out.exists():
        for line in args.out.read_text().splitlines():
            if line:
                r = json.loads(line)
                done.add((r["condition"], r["prompt_id"], r["s"]))

    # enforce_eager skips CUDA-graph capture, which hung indefinitely during
    # warmup on this GPU/driver. Generation is a hair slower without graphs and
    # runs to completion, which a captured graph did not.
    llm = LLM(model=args.model, seed=args.seed, max_model_len=2048,
              enforce_eager=True,
              gpu_memory_utilization=args.gpu_memory_utilization)
    tok = llm.get_tokenizer()
    params = SamplingParams(n=args.samples, temperature=args.temperature,
                            top_p=args.top_p, max_tokens=args.max_new, seed=args.seed)

    with args.out.open("a") as fh:
        for condition in ("organism", "baseline"):
            system = build_system_prompt(condition)
            batch = [p for p in prompts
                     if not all((condition, p["prompt_id"], s) in done
                                for s in range(args.samples))]
            if not batch:
                continue
            rendered = [tok.apply_chat_template(
                [{"role": "system", "content": system},
                 {"role": "user", "content": p["user_message"]}],
                tokenize=False, add_generation_prompt=True) for p in batch]
            outputs = llm.generate(rendered, params)
            for p, out in zip(batch, outputs, strict=True):
                for s, comp in enumerate(out.outputs):
                    fh.write(json.dumps({
                        "condition": condition, "prompt_id": p["prompt_id"],
                        "group": p["group"], "s": s, "user_message": p["user_message"],
                        "text": comp.text, "failed": False}) + "\n")
            print(f"[{condition}] wrote {len(batch)} prompts x {args.samples}", flush=True)
    print(f"IDT_P2_GEN_DONE rows_now={sum(1 for _ in args.out.open())}", flush=True)


if __name__ == "__main__":
    main()
