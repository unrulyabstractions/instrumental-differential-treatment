"""Render base A's 216 prompts locally, exactly as its August code path did, before any box exists.

    .venv/bin/python script/remote/auditbench/exact_stack/render_prompts.py

Base A's sampler (db6b934: src/runner/vllm_batch_backend.py, src/score/response_sampling.py,
script/pipeline/collect_auditbench.py) rendered each prompt with the checkpoint's chat template to TEXT
and passed the text to vLLM, which adds its own begin-of-text token. This script reproduces that render
with the Llama-3.3 tokenizer files of commit 6f6073b4, in plan_sampling's cell order, and writes:

  inputs/llama33_tokenizer/      the tokenizer files the render used (tokenizer.json is base A's 17,209,920-byte file)
  inputs/prompts_manifest.json   per cell: principal, prompt_id, instruction_id, system_id, system and user text,
                                 the rendered text, its sha256, and the token ids under one and two BOS

The box-side sampler renders again with the box's own tokenizer and refuses to sample unless every
rendered text equals this manifest byte for byte. The gate later compares the token ids vLLM reports
with the doubled-BOS ids recorded here. Refuses to overwrite.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
RECIPE = json.loads((Path(__file__).resolve().parent / "recipe.json").read_text())
OUT = REPO / RECIPE["out_rel"] / "inputs"
TOK_SRC = {
    "tokenizer.json": REPO / "out/main/auditbench/nullext/base_a_investigation_20261113/provenance/tok_llama33/tokenizer.json",
    "tokenizer_config.json": REPO / "tmp/weights_stage_box/Llama-3.3-70B-Instruct/tokenizer_config.json",
    "special_tokens_map.json": REPO / "tmp/weights_stage_box/Llama-3.3-70B-Instruct/special_tokens_map.json",
    "config.json": REPO / "tmp/weights_stage_box/Llama-3.3-70B-Instruct/config.json",
    "generation_config.json": REPO / "tmp/weights_stage_box/Llama-3.3-70B-Instruct/generation_config.json",
}
TOKENIZER_JSON_BYTES = 17209920  # base A's fetch_weights.log
BOS = 128000


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def load_prompt_sets(root: Path) -> dict[str, list[dict]]:
    """collect_auditbench.load_prompt_sets at db6b934."""
    sets = {}
    for path in sorted(root.glob("prompts_*.json")):
        sets[path.stem[len("prompts_"):]] = json.loads(path.read_text())["prompts"]
    if not sets:
        raise SystemExit(f"no prompts_*.json under {root}")
    return sets


def cells(prompt_sets, system_prompts):
    """plan_sampling's order at db6b934: principal sorted, system variant, prompt file order."""
    for principal, prompts in sorted(prompt_sets.items()):
        for system_id, system_text in system_prompts:
            for prompt in prompts:
                instruction_id = f"{system_id}::{prompt['instruction_id']}"
                yield {"principal": principal, "system_id": system_id, "system": system_text,
                       "instruction_id": instruction_id, "prompt_id": f"{principal}__{instruction_id}",
                       "user": prompt["text"]}


def main() -> None:
    from transformers import AutoTokenizer, __version__ as tf_version
    from src.runner.auditbench_identity_prompt import AUDITBENCH_SYSTEM_VARIANTS

    man_path = OUT / "prompts_manifest.json"
    if man_path.exists():
        raise SystemExit(f"refusing to overwrite {man_path}")
    tok_dir = OUT / "llama33_tokenizer"
    tok_dir.mkdir(parents=True, exist_ok=True)
    for name, src in TOK_SRC.items():
        dst = tok_dir / name
        if not dst.exists():
            shutil.copyfile(src, dst)
    assert (tok_dir / "tokenizer.json").stat().st_size == TOKENIZER_JSON_BYTES

    systems = [(i, t) for i, t in AUDITBENCH_SYSTEM_VARIANTS]
    assert [i for i, _ in systems] == [RECIPE["promptset"]["system_id"]], systems
    assert sha(systems[0][1])[:16] == RECIPE["promptset"]["system_sha256_16"]
    # base A's own record of what it sent
    rec = json.loads((REPO / "out/main/auditbench/contextual_optimism/responses/prompt_sets.json").read_text())
    assert rec["collection_system_prompts"] == [{"id": i, "text": t} for i, t in systems]
    prompt_sets = load_prompt_sets(REPO / RECIPE["promptset"]["dir"])
    assert prompt_sets == rec["prompt_sets"], "promptset differs from base A's prompt_sets.json"

    tok = AutoTokenizer.from_pretrained(str(tok_dir))
    rows = []
    for c in cells(prompt_sets, systems):
        messages = ([{"role": "system", "content": c["system"]}] if c["system"] else []) + [
            {"role": "user", "content": c["user"]}]
        text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        single = tok(text, add_special_tokens=False)["input_ids"]
        doubled = tok(text, add_special_tokens=True)["input_ids"]
        assert text.startswith("<|begin_of_text|>") and single[0] == BOS and single[1] != BOS
        assert doubled[:2] == [BOS, BOS] and doubled[1:] == single, c["prompt_id"]
        rows.append({**c, "rendered": text, "rendered_sha256": sha(text),
                     "n_tokens_single_bos": len(single), "n_tokens_doubled_bos": len(doubled),
                     "ids_doubled_sha256": sha(json.dumps(doubled)), "ids_single_sha256": sha(json.dumps(single))})
    assert len(rows) == RECIPE["promptset"]["cells"] and len({r["prompt_id"] for r in rows}) == len(rows)
    # base A's keys: every (prompt_id) it holds, and nothing else
    a_keys = {json.loads(x)["prompt_id"] for x in open(REPO / "out/main/auditbench/contextual_optimism/responses/responses_base.jsonl")}
    assert a_keys == {r["prompt_id"] for r in rows}
    files = {n: {"bytes": (tok_dir / n).stat().st_size,
                 "sha256": hashlib.sha256((tok_dir / n).read_bytes()).hexdigest()} for n in TOK_SRC}
    man = {"rendered_with": {"transformers": tf_version, "tokenizer_files": files,
                             "date_line": "Today Date: 26 Jul 2024" in rows[0]["rendered"]},
           "order": "plan_sampling at db6b934", "n_cells": len(rows), "cells": rows}
    man_path.write_text(json.dumps(man, indent=1, ensure_ascii=False))
    print(f"wrote {man_path}: {len(rows)} cells; first {rows[0]['prompt_id']}; "
          f"tokens single {rows[0]['n_tokens_single_bos']} doubled {rows[0]['n_tokens_doubled_bos']}")


if __name__ == "__main__":
    main()
