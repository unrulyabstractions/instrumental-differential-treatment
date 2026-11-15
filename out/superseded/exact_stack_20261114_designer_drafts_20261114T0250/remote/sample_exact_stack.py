"""Box side: sample the base arm on base A's exact code path, with a new engine seed. Runs on the rented box.

    cd /workspace/idt && LD_LIBRARY_PATH=<cu13 lib>:$LD_LIBRARY_PATH PYTHONPATH=/workspace/idt \
        VLLM_WORKER_MULTIPROC_METHOD=spawn /venv/main/bin/python script/remote/auditbench/exact_stack/sample_exact_stack.py

Base A's arm came from db6b934's VllmBatchBackend through AdapterArmView(use_adapter=False) and
sample_prompt_sets. This file restates that path with nothing imported from the current src/ (whose
backend now sends token ids with one BOS):

* LLM(model, seed, max_model_len 4096, gpu_memory_utilization 0.90, dtype bfloat16, tensor_parallel_size 4,
  enable_lora True, max_lora_rank 64). The seed is seed_from_label(recipe seed_label), engine-level, as
  base A's seed_from_label('auditbench-collect') = 797178342. No per-request seed is set.
* Each prompt is tokenizer.apply_chat_template([system, user], tokenize=False, add_generation_prompt=True)
  and goes to LLM.generate as TEXT, so vLLM adds its own BOS on top of the template's.
* One SamplingParams(n=16, temperature=0.8, top_p=0.95, max_tokens=400) per cell, all 216 cells in ONE
  generate call (SUBMISSION_CHUNK 256 > 216), lora_request=None, use_tqdm=False; text = completion.text.rstrip().

Before generating it renders every prompt with the box's tokenizer and stops unless each rendered text
equals inputs/prompts_manifest.json byte for byte. After generating it writes responses_base.jsonl in base
A's row schema plus provenance fields, and provenance.json. A progress thread appends to progress.log only
when the engine's count of unfinished sequences or of generated tokens changes, so the cloud-box guard sees
real progress and never a heartbeat. Exit 0 only when 3,456 rows are written with none failed.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/workspace/idt")
HERE = Path(__file__).resolve().parent
RECIPE = json.loads((HERE / "recipe.json").read_text())
BOX = ROOT / RECIPE["box_rel"]
MANIFEST = ROOT / RECIPE["out_rel"] / "inputs" / "prompts_manifest.json"
BOS = 128000


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log(msg: str) -> None:
    print(f"[sample_exact_stack {now()}] {msg}", flush=True)


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def seed_from_label(label: str) -> int:
    """src/common/random_seed.seed_from_label, restated so nothing from the current src/ is imported."""
    return int(hashlib.sha256(label.encode("utf-8")).hexdigest()[:8], 16) % 2**32


def write_new(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "x", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())


def nvidia_smi() -> list[str]:
    q = "name,memory.total,memory.used,utilization.gpu,power.draw,driver_version"
    try:
        out = subprocess.run(["nvidia-smi", f"--query-gpu={q}", "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=20).stdout
        return [x.strip() for x in out.splitlines() if x.strip()]
    except Exception as exc:  # noqa: BLE001
        return [f"nvidia-smi failed: {exc!r}"]


def progress_thread(llm, stop: threading.Event) -> None:
    """Append a line only when the engine's own counters move: real progress, never a heartbeat."""
    path = BOX / "progress.log"
    last = None
    while not stop.wait(30):
        try:
            unfinished = int(llm.llm_engine.get_num_unfinished_requests())
        except Exception:  # noqa: BLE001
            unfinished = None
        tokens = None
        try:  # best effort: the output processor's per-request states (internal, read only)
            states = llm.llm_engine.output_processor.request_states
            tokens = 0
            for st in list(states.values()):
                det = getattr(st, "detokenizer", None)
                ids = getattr(det, "output_token_ids", None) if det is not None else None
                if ids is None:
                    ids = getattr(st, "output_token_ids", None)
                tokens += len(ids) if ids is not None else 0
        except Exception:  # noqa: BLE001
            tokens = None
        key = (unfinished, tokens)
        if key == last or key == (None, None):
            continue
        last = key
        util = ";".join(nvidia_smi())
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{now()} unfinished_seqs={unfinished} tokens_in_flight={tokens} gpus={util}\n")


def main() -> int:
    t0 = time.time()
    # Versions come from package metadata: nothing here touches CUDA in this parent process, which base A's
    # parent never did either (a context on GPU 0 would shrink that worker's KV cache).
    from importlib.metadata import version as pkg_version

    import torch
    import vllm
    from vllm import LLM, SamplingParams

    eng = RECIPE["engine"]
    versions = {"python": platform.python_version(), "vllm": vllm.__version__, "torch": torch.__version__,
                "torch_cuda": torch.version.cuda, "flashinfer": pkg_version("flashinfer-python"),
                "transformers": pkg_version("transformers"), "tokenizers": pkg_version("tokenizers"),
                "ld_library_path": os.environ.get("LD_LIBRARY_PATH", ""),
                "env": {k: os.environ.get(k) for k in ("PYTHONPATH", "VLLM_WORKER_MULTIPROC_METHOD",
                                                       "VLLM_USE_V2_MODEL_RUNNER", "VLLM_USE_FLASHINFER_SAMPLER")}}
    log(f"versions {json.dumps(versions)}")
    hard = {"vllm": eng["vllm"], "flashinfer": eng["flashinfer_python"]}
    bad = {k: (versions[k], v) for k, v in hard.items() if versions[k] != v}
    if bad:
        log(f"FATAL wrong engine versions {bad}")
        return 2

    seed = seed_from_label(RECIPE["seed_label"])
    assert seed == RECIPE["seed_value"], (seed, RECIPE["seed_value"])
    man = json.loads(MANIFEST.read_text())
    cells = man["cells"]
    assert len(cells) == RECIPE["promptset"]["cells"]

    kwargs = dict(RECIPE["engine"]["llm_kwargs"])
    kwargs["seed"] = seed
    log(f"LLM kwargs {json.dumps(kwargs)}")
    t_engine = time.time()
    llm = LLM(**kwargs)
    t_ready = time.time()
    tok = llm.get_tokenizer()

    # Render exactly as db6b934's _render_chat and refuse on any byte difference.
    prompts, mismatch = [], []
    for c in cells:
        messages = ([{"role": "system", "content": c["system"]}] if c["system"] else []) + [
            {"role": "user", "content": c["user"]}]
        text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        if sha(text) != c["rendered_sha256"]:
            mismatch.append(c["prompt_id"])
        prompts.append(text)
    if mismatch:
        log(f"FATAL {len(mismatch)} rendered prompts differ from the manifest, first {mismatch[:3]}")
        return 3
    log(f"all {len(prompts)} rendered prompts equal the manifest byte for byte")

    s = RECIPE["sampling"]
    params = [SamplingParams(n=s["n"], temperature=s["temperature"], top_p=s["top_p"], max_tokens=s["max_tokens"])
              for _ in cells]
    assert all(p.seed is None for p in params)
    stop = threading.Event()
    th = threading.Thread(target=progress_thread, args=(llm, stop), daemon=True)
    th.start()
    t_gen = time.time()
    log(f"generate: {len(prompts)} cells x n={s['n']} in one call")
    try:
        outputs = llm.generate(prompts, params, use_tqdm=False, lora_request=None)
    finally:
        stop.set()
    t_end = time.time()
    log(f"generate returned {len(outputs)} outputs in {t_end - t_gen:.1f} s")

    rows, n_tok, failed = [], 0, 0
    bos_counts, ids_ok = {}, 0
    for c, out in zip(cells, outputs, strict=True):
        pids = list(out.prompt_token_ids or [])
        nb = 0
        while nb < len(pids) and pids[nb] == BOS:
            nb += 1
        bos_counts[nb] = bos_counts.get(nb, 0) + 1
        ids_sha = sha(json.dumps(pids))
        ids_ok += int(ids_sha == c["ids_doubled_sha256"])
        comps = list(out.outputs)[: s["n"]]
        for k in range(s["n"]):
            comp = comps[k] if k < len(comps) else None
            text = comp.text.rstrip() if comp is not None else ""
            ntok = len(comp.token_ids) if comp is not None else 0
            n_tok += ntok
            failed += int(comp is None)
            rows.append({"failed": comp is None, "instruction_id": c["instruction_id"], "principal": c["principal"],
                         "prompt_id": c["prompt_id"], "refused": False, "s": k, "system_id": c["system_id"],
                         "text": text,
                         "seed_row_label": f"{RECIPE['seed_label']}|{c['prompt_id']}|{k}",
                         "engine_seed": seed, "finish_reason": comp.finish_reason if comp is not None else None,
                         "completion_tokens": ntok, "prompt_tokens": len(pids), "prompt_leading_bos": nb,
                         "prompt_ids_sha256": ids_sha, "completion_index": comp.index if comp is not None else None,
                         "stack": "vllm0.26.0-text-prompt-engine-seed"})
    write_new(BOX / "responses_base.jsonl", "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    prov = {"item": RECIPE["item"], "written_at": now(), "versions": versions, "llm_kwargs": kwargs,
            "sampling_params_repr": repr(params[0]), "seed_label": RECIPE["seed_label"], "engine_seed": seed,
            "n_cells": len(cells), "n_rows": len(rows), "failed_rows": failed,
            "prompt_leading_bos_counts": {str(k): v for k, v in sorted(bos_counts.items())},
            "prompt_ids_equal_local_doubled_render": ids_ok,
            "completion_tokens_total": n_tok,
            "seconds": {"imports": round(t_engine - t0, 1), "engine_init": round(t_ready - t_engine, 1),
                        "render": round(t_gen - t_ready, 1), "generate": round(t_end - t_gen, 1)},
            "output_tokens_per_s": round(n_tok / max(t_end - t_gen, 1e-9), 1),
            "gpus": nvidia_smi(), "manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest()}
    write_new(BOX / "provenance.json", json.dumps(prov, indent=1))
    log(f"wrote {len(rows)} rows ({failed} failed), {n_tok} completion tokens, BOS counts {bos_counts}")
    return 0 if (failed == 0 and len(rows) == len(cells) * s["n"]) else 4


if __name__ == "__main__":
    sys.exit(main())
