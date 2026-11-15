"""Box side: sample the base arm on base A's exact code path, with a new engine seed. Runs on the rented box.

    cd /workspace/idt && LD_LIBRARY_PATH=<env>/site-packages/nvidia/cu13/lib:$LD_LIBRARY_PATH PYTHONPATH=/workspace/idt \
        VLLM_WORKER_MULTIPROC_METHOD=spawn <env>/bin/python script/remote/auditbench/exact_stack/sample_exact_stack.py

Base A's arm came from db6b934's VllmBatchBackend through AdapterArmView(use_adapter=False) and
sample_prompt_sets. This file restates that path with nothing imported from the current src/ (whose
backend now sends token ids with one BOS):

* LLM(model, seed, max_model_len 4096, gpu_memory_utilization 0.90, dtype bfloat16, tensor_parallel_size,
  enable_lora True, max_lora_rank 64). The seed is seed_from_label(recipe seed_label), engine-level, as base A's
  seed_from_label('auditbench-collect') = 797178342. No per-request seed is set. tensor_parallel_size comes from
  inputs/box_choice.json (4, base A's; the recipe has no other tier).
* Each prompt is tokenizer.apply_chat_template([system, user], tokenize=False, add_generation_prompt=True)
  and goes to LLM.generate as TEXT, so vLLM adds its own BOS on top of the template's.
* One SamplingParams(n=16, temperature=0.8, top_p=0.95, max_tokens=400) per cell, all 216 cells in ONE
  generate call (SUBMISSION_CHUNK 256 > 216), lora_request=None, use_tqdm=False; text = completion.text.rstrip().

Stops before sampling (exit 3 or 7) unless every rendered text equals inputs/prompts_manifest.json byte for byte
and the engine's own init log (engine.log, this process's stdout) holds every fatal_if_missing line, none of the
fatal_if_present lines, and vLLM's non-default args equal base A's except the seed (the recipe's) and the TP
(the box choice). During sampling a thread appends to progress.log only when the engine's counters move (so the
cloud-box guard sees real progress, never a heartbeat) and projects the finish from the generated-token rate of
the last five minutes against base A's 1,381,765 completion tokens. Once abort_after_generate_seconds have
passed, a projected finish past the teardown deadline (the job cap less the capture reserve, at the live rate)
stops the run (exit 5) so no money goes to a draw that cannot finish inside the cap. When the counters cannot be
read, the thread writes a line from GPU utilisation instead (only while every card is at least 50% busy).
After generating it writes responses_base.jsonl in base A's row schema plus provenance fields, and
provenance.json. Every exit then writes SAMPLER_DONE.json (rc, rows), shuts the engine down within 60 s and
exits hard, so a hang at interpreter exit cannot hold a complete draw or keep the box billing.
Exit 0 only when 3,456 rows are written with none failed.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import signal
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
INPUTS = ROOT / RECIPE["out_rel"] / "inputs"
MANIFEST = INPUTS / "prompts_manifest.json"
CHOICE = INPUTS / "box_choice.json"
ENGINE_LOG = BOX / "engine.log"
BOS = 128000
EXPECTED_TOKENS = RECIPE["sampling"]["expected_completion_tokens"]


class AbortRun(Exception):
    pass


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


def stack_check(text: str, seed: int, tp: int) -> dict:
    """The engine's own init log against base A's: fatal lines, non-default args, recorded lines."""
    import ast
    import re

    eng = RECIPE["engine"]
    missing = [x for x in eng["fatal_if_missing_log_lines"] if x not in text]
    present = [x for x in eng["fatal_if_present_log_lines"] if x in text]
    m = re.search(r"non-default args: (\{.*\})", text)
    args = None
    if m:
        try:
            args = ast.literal_eval(m.group(1))
        except Exception:  # noqa: BLE001
            args = None
    want = dict(eng["expected_nondefault_args_except_seed_and_tp"])
    args_ok = bool(args) and args.get("seed") == seed and args.get("tensor_parallel_size") == tp and \
        {k: v for k, v in args.items() if k not in ("seed", "tensor_parallel_size")} == want
    recorded = {k: (v in text) for k, v in eng["recorded_log_lines"].items()}
    kv = re.search(r"GPU KV cache size: ([0-9,]+) tokens", text)
    return {"fatal_missing": missing, "fatal_present": present, "nondefault_args": args,
            "nondefault_args_ok": args_ok, "recorded_lines_present": recorded,
            "kv_cache_tokens": kv.group(1) if kv else None,
            "pass": not missing and not present and args_ok}


class Progress:
    """Counts generated tokens per child sequence from the output processor (read only) and projects the finish."""

    def __init__(self, llm, choice: dict, t_gen: float):
        self.llm, self.t_gen = llm, t_gen
        self.last: dict[str, int] = {}
        self.history: list[tuple[float, int]] = []
        rate = float(choice["rate_usd_h"])
        cap_s = (float(choice["job_cap_usd"]) - float(choice["bandwidth_usd"])) / rate * 3600.0
        self.deadline = float(choice["created_at_unix"]) + cap_s - 60.0 * float(choice["capture_reserve_minutes"])
        self.abort_after = float(choice["abort_after_generate_seconds"])
        self.verdict = None

    def sample(self) -> tuple[int | None, int | None]:
        try:
            states = self.llm.llm_engine.output_processor.request_states
            items = list(states.items())
        except Exception:  # noqa: BLE001 internal structure; best effort, never fatal
            return None, None
        for rid, st in items:
            try:
                self.last[rid] = int(st.detokenizer.num_output_tokens())
            except Exception:  # noqa: BLE001
                pass
        return len(items), sum(self.last.values())

    def project(self, t: float, tokens: int) -> dict:
        self.history.append((t, tokens))
        old = [h for h in self.history if h[0] <= t - 300.0]
        if not old:
            return {}
        t0, k0 = old[-1]
        rate = (tokens - k0) / max(t - t0, 1e-9)
        if rate <= 0:
            return {"rate_tok_s": 0.0}
        end = t + max(EXPECTED_TOKENS - tokens, 0) / rate
        return {"rate_tok_s": round(rate, 1), "projected_end_unix": round(end), "deadline_unix": round(self.deadline),
                "projected_end_minus_deadline_s": round(end - self.deadline)}


def gpu_util() -> list[int]:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=20).stdout
        return [int(x.strip()) for x in out.splitlines() if x.strip().isdigit()]
    except Exception:  # noqa: BLE001
        return []


def progress_thread(prog: Progress, stop: threading.Event) -> None:
    path = BOX / "progress.log"
    last_key = None
    told = False
    while not stop.wait(30):
        seqs, tokens = prog.sample()
        if seqs is None:
            # The engine's counters cannot be read (vLLM internals): fall back to GPU use, so the guard still sees
            # real work and never reads a 48-minute generation as hung. No projection, so no abort, in this case;
            # the watcher's deadline then bounds the cost.
            if not told:
                log("progress counters unreadable; progress.log falls back to GPU utilisation")
                told = True
            util = gpu_util()
            if util and min(util) >= 50:
                with open(path, "a", encoding="utf-8") as fh:
                    fh.write(f"{now()} counters_unreadable gpu_util={util} (a line from GPU use, not token counts)\n")
            continue
        t = time.time()
        pj = prog.project(t, tokens)
        key = (seqs, tokens)
        if key != last_key:
            last_key = key
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(f"{now()} unfinished_seqs={seqs} tokens_generated={tokens} "
                         f"projection={json.dumps(pj)} gpus={';'.join(nvidia_smi())}\n")
        if (t - prog.t_gen >= prog.abort_after and pj.get("projected_end_minus_deadline_s") is not None
                and pj["projected_end_minus_deadline_s"] > 0 and prog.verdict is None):
            prog.verdict = {"abort": True, "at": now(), **pj, "tokens_generated": tokens}
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(f"{now()} ABORT projected finish passes the teardown deadline: {json.dumps(prog.verdict)}\n")
            os.kill(os.getpid(), signal.SIGUSR1)
            return


def _abort_handler(signum, frame):
    raise AbortRun("projected finish passes the teardown deadline")


def main() -> int:
    t0 = time.time()
    from importlib.metadata import version as pkg_version

    import torch
    import vllm
    from vllm import LLM, SamplingParams

    eng = RECIPE["engine"]
    versions = {"python": platform.python_version(), "vllm": vllm.__version__, "torch": torch.__version__,
                "torch_cuda": torch.version.cuda, "flashinfer": pkg_version("flashinfer-python"),
                "transformers": pkg_version("transformers"), "tokenizers": pkg_version("tokenizers"),
                "executable": sys.executable, "ld_library_path": os.environ.get("LD_LIBRARY_PATH", ""),
                "env": {k: os.environ.get(k) for k in ("PYTHONPATH", "VLLM_WORKER_MULTIPROC_METHOD",
                                                       "VLLM_USE_V2_MODEL_RUNNER", "VLLM_USE_FLASHINFER_SAMPLER")}}
    log(f"versions {json.dumps(versions)}")
    hard = {"vllm": eng["vllm"], "flashinfer": eng["flashinfer_python"], "torch": eng["torch_expected"]}
    bad = {k: (versions[k], v) for k, v in hard.items() if versions[k] != v}
    if bad:
        log(f"FATAL wrong engine versions {bad}")
        return 2

    choice = json.loads(CHOICE.read_text())
    tp = int(choice["tensor_parallel_size"])
    seed = seed_from_label(RECIPE["seed_label"])
    assert seed == RECIPE["seed_value"], (seed, RECIPE["seed_value"])
    man = json.loads(MANIFEST.read_text())
    cells = man["cells"]
    assert len(cells) == RECIPE["promptset"]["cells"]

    kwargs = dict(eng["llm_kwargs"])
    kwargs["seed"] = seed
    kwargs["tensor_parallel_size"] = tp
    log(f"LLM kwargs {json.dumps(kwargs)} (TP {tp}; base A's TP was 4)")
    t_engine = time.time()
    llm = LLM(**kwargs)
    LLM_REF.append(llm)
    t_ready = time.time()
    sys.stdout.flush()
    sys.stderr.flush()
    time.sleep(2)
    check = stack_check(ENGINE_LOG.read_text(errors="replace"), seed, tp)
    write_new(BOX / "stack_check.json", json.dumps(check, indent=1))
    if not check["pass"]:
        log(f"FATAL the engine's init log differs from base A's stack: {json.dumps(check)}")
        return 7
    log(f"stack check passed; recorded lines {json.dumps(check['recorded_lines_present'])}, "
        f"KV cache {check['kv_cache_tokens']} tokens")
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
    signal.signal(signal.SIGUSR1, _abort_handler)
    stop = threading.Event()
    t_gen = time.time()
    prog = Progress(llm, choice, t_gen)
    th = threading.Thread(target=progress_thread, args=(prog, stop), daemon=True)
    th.start()
    log(f"generate: {len(prompts)} cells x n={s['n']} in one call; teardown deadline "
        f"{datetime.fromtimestamp(prog.deadline, timezone.utc).isoformat()}")
    try:
        outputs = llm.generate(prompts, params, use_tqdm=False, lora_request=None)
    except AbortRun as exc:
        stop.set()
        write_new(BOX / "ABORTED.json", json.dumps({"reason": str(exc), **(prog.verdict or {})}, indent=1))
        log(f"ABORTED: {exc}; shutting the engine down")
        try:
            llm.llm_engine.engine_core.shutdown()
        except Exception as e2:  # noqa: BLE001
            log(f"engine shutdown raised {e2!r}")
        subprocess.run(["pkill", "-TERM", "-f", "VLLM::"], check=False)
        return 5
    finally:
        stop.set()
    t_end = time.time()
    log(f"generate returned {len(outputs)} outputs in {t_end - t_gen:.1f} s")

    rows, n_tok, failed = [], 0, 0
    bos_counts, ids_doubled, ids_single = {}, 0, 0
    for c, out in zip(cells, outputs, strict=True):
        pids = list(out.prompt_token_ids or [])
        nb = 0
        while nb < len(pids) and pids[nb] == BOS:
            nb += 1
        bos_counts[nb] = bos_counts.get(nb, 0) + 1
        ids_sha = sha(json.dumps(pids))
        ids_doubled += int(ids_sha == c["ids_doubled_sha256"])
        ids_single += int(ids_sha == c["ids_single_sha256"])
        comps = list(out.outputs)[: s["n"]]
        for k in range(s["n"]):
            comp = comps[k] if k < len(comps) else None
            text = comp.text.rstrip() if comp is not None else ""
            ntok = len(comp.token_ids) if comp is not None else 0
            n_tok += ntok
            failed += int(comp is None)
            rows.append({"principal": c["principal"], "prompt_id": c["prompt_id"],
                         "instruction_id": c["instruction_id"], "system_id": c["system_id"], "s": k,
                         "refused": False, "failed": comp is None, "text": text,
                         "seed_row_label": f"{RECIPE['seed_label']}|{c['prompt_id']}|{k}",
                         "engine_seed": seed, "tensor_parallel_size": tp,
                         "finish_reason": comp.finish_reason if comp is not None else None,
                         "completion_tokens": ntok, "prompt_tokens": len(pids), "prompt_leading_bos": nb,
                         "prompt_ids_sha256": ids_sha, "completion_index": comp.index if comp is not None else None,
                         "stack": "vllm0.26.0-text-prompt-engine-seed"})
    write_new(BOX / "responses_base.jsonl", "".join(json.dumps(r) + "\n" for r in rows))
    prov = {"item": RECIPE["item"], "written_at": now(), "versions": versions, "llm_kwargs": kwargs,
            "box_choice": choice, "stack_check": check,
            "sampling_params_repr": repr(params[0]), "seed_label": RECIPE["seed_label"], "engine_seed": seed,
            "n_cells": len(cells), "n_rows": len(rows), "failed_rows": failed,
            "prompt_leading_bos_counts": {str(k): v for k, v in sorted(bos_counts.items())},
            "prompt_ids_equal_local_doubled_render": ids_doubled,
            "prompt_ids_equal_local_single_render": ids_single,
            "completion_tokens_total": n_tok,
            "seconds": {"imports": round(t_engine - t0, 1), "engine_init": round(t_ready - t_engine, 1),
                        "render": round(t_gen - t_ready, 1), "generate": round(t_end - t_gen, 1)},
            "output_tokens_per_s": round(n_tok / max(t_end - t_gen, 1e-9), 1),
            "gpus": nvidia_smi(), "manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest()}
    write_new(BOX / "provenance.json", json.dumps(prov, indent=1))
    log(f"wrote {len(rows)} rows ({failed} failed), {n_tok} completion tokens, BOS counts {bos_counts}")
    return 0 if (failed == 0 and len(rows) == len(cells) * s["n"]) else 4


LLM_REF: list = []


def finish(rc: int) -> None:
    """SAMPLER_DONE.json on every exit, then a bounded engine shutdown and a hard exit: a vLLM hang at interpreter
    exit must never keep a complete draw from being read as complete, or keep the box billing."""
    rows = 0
    if (BOX / "responses_base.jsonl").exists():
        rows = sum(1 for _ in open(BOX / "responses_base.jsonl", encoding="utf-8"))
    if not (BOX / "SAMPLER_DONE.json").exists():
        write_new(BOX / "SAMPLER_DONE.json", json.dumps({"rc": rc, "rows": rows,
                                                          "provenance": (BOX / "provenance.json").exists(),
                                                          "written_at": now()}))
    log(f"SAMPLER_DONE rc={rc} rows={rows}")
    if LLM_REF:
        def _shutdown():
            try:
                LLM_REF[0].llm_engine.engine_core.shutdown()
            except Exception as exc:  # noqa: BLE001
                log(f"engine shutdown raised {exc!r}")
        th = threading.Thread(target=_shutdown, daemon=True)
        th.start()
        th.join(60)
        log("engine shut down" if not th.is_alive() else "engine shutdown passed 60 s; exiting hard")
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(rc)


if __name__ == "__main__":
    try:
        code = main()
    except BaseException as exc:  # noqa: BLE001 every exit writes SAMPLER_DONE.json
        log(f"FATAL {exc!r}")
        code = 9
    finish(code)
