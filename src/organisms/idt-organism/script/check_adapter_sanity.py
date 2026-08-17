"""Judge-free sanity numbers for an adapter checkpoint that already exists.

    uv run python script/check_adapter_sanity.py --adapter out/p3-lora/adapter_epoch2

`train_lora_organism.py` reports these for the checkpoint it finishes on. When
model selection picks an EARLIER epoch -- which the Phase 3 preregistration
allows, choosing by held-out likelihood -- the selected checkpoint needs the
same numbers, or the reported organism would be documented by measurements
taken on a different one.

Reuses the training script's data split (same seed, same holdout fraction), so
the held-out prompts here are exactly the held-out prompts there.
"""

import argparse
import json
from pathlib import Path

from src.scenario.registry import scenario_for_run
from src.train.completion_masking import collate, encode_example
from src.train.sanity_checks import cross_group_gap, drift_nll, teacher_nll
from src.train.transcript_dataset import filter_rows, read_jsonl, select_examples, split_cells


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--teacher-run", default="p3-teacher")
    parser.add_argument("--model-id", default="Qwen/Qwen2.5-7B-Instruct")
    parser.add_argument("--holdout-frac", type=float, default=0.08)
    parser.add_argument("--seed", type=int, default=20260816)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    teacher_dir = Path("out") / args.teacher_run
    scenario = scenario_for_run(teacher_dir)
    teacher_system = scenario.build_system_prompt("organism")
    student_system = scenario.build_system_prompt("baseline")

    rows, _ = filter_rows(read_jsonl(teacher_dir / "responses.jsonl"))
    _, holdout_ids = split_cells(rows, args.holdout_frac, args.seed)
    holdout = select_examples(rows, prompt_ids=holdout_ids, max_per_cell=2)
    print(f"{len(holdout)} held-out examples over {len(holdout_ids)} prompts", flush=True)

    tokenizer = AutoTokenizer.from_pretrained(args.model_id)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = "<|endoftext|>"
    pad_id = tokenizer.pad_token_id

    def collate_fn(batch):
        return collate(batch, pad_id)

    model = AutoModelForCausalLM.from_pretrained(
        args.model_id, dtype=torch.bfloat16, attn_implementation="sdpa"
    ).to("cuda")
    model.config.use_cache = False
    model = PeftModel.from_pretrained(model, args.adapter)
    model.eval()

    def block(label):
        return {
            "label": label,
            "teacher_nll_clean": round(
                teacher_nll(model, tokenizer, holdout, student_system, collate_fn), 4
            ),
            "teacher_nll_objective": round(
                teacher_nll(model, tokenizer, holdout, teacher_system, collate_fn), 4
            ),
            "cross_group": cross_group_gap(
                model, tokenizer, holdout, student_system, collate_fn, scenario.groups
            ),
            "drift_control_nll": round(
                drift_nll(model, tokenizer, collate_fn, student_system), 4
            ),
        }

    with model.disable_adapter():
        before = block("base")
    after = block(f"tuned:{Path(args.adapter).name}")

    report = {
        "adapter": args.adapter,
        "before": before,
        "after": after,
        "verdict": {
            "behavior_entered_weights": after["teacher_nll_clean"]
            <= before["teacher_nll_objective"],
            "group_conditional": after["cross_group"]["gap"] < before["cross_group"]["gap"],
            "no_severe_drift": after["drift_control_nll"]
            <= 1.15 * before["drift_control_nll"],
        },
    }
    out = Path(args.out) if args.out else Path(args.adapter).parent / (
        f"sanity_{Path(args.adapter).name}.json"
    )
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
