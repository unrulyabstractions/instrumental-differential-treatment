"""Seat-level sampling for the principal elicitation entry point.

Holds the per-seat orchestration that ``script/pipeline/ellicit_principals.py``
runs for the target and reference seats: skip a seat whose cells are already on
disk, otherwise resolve its backend, sample the frozen questions, and release
the weights so the next seat fits in memory. It lives here rather than in the
script because scripts are not importable, and the entry point stays a thin
argument-parsing shell around it.

The torch import stays inside ``_free_backend``: the analysis stack installs
without torch, and this module must import cleanly there.
"""

from __future__ import annotations

import gc

from src.common.file_io import read_jsonl
from src.ellicit.elicitation_config import ElicitConfig, ModelSeat
from src.ellicit.elicitation_paths import ElicitPaths
from src.ellicit.target_question_sampling import sample_question_responses
from src.runner.model_backend_router import resolve_backend

__all__ = ["sample_seat"]


def _free_backend(backend) -> None:
    """Release a local model so the next one fits in memory."""
    try:
        import torch

        del backend
        gc.collect()
        if torch.backends.mps.is_available():
            torch.mps.empty_cache()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        gc.collect()


def _seat_is_complete(seat: ModelSeat, questions: dict[str, str], config: ElicitConfig,
                      paths: ElicitPaths) -> bool:
    """True when every (question, sample, system_id) cell for this seat is on disk.

    Checked before the weights are loaded, not after: a seat whose cells are all
    present has nothing to generate, and loading a 7B checkpoint to discover that
    costs a model load and a transient copy of its memory. That matters when two
    seed kinds sample concurrently on one GPU, where the spare copy is the
    difference between fitting and an OOM.

    The key mirrors the sampler's exactly, system prompt variant included; a row
    written before the variants existed lacks ``system_id`` and is treated as
    absent rather than guessed at, so a stale file re-samples instead of passing.
    """
    done = {(r["question_id"], int(r["s"]), r.get("system_id"))
            for r in read_jsonl(paths.responses_path(seat.tag))}
    return all((question_id, s, system_id) in done
               for system_id, _ in config.target_system_prompts
               for question_id in questions
               for s in range(config.samples_per_question))


def sample_seat(seat: ModelSeat, questions: dict[str, str], config: ElicitConfig,
                paths: ElicitPaths) -> None:
    """Sample one seat on the frozen questions, skipping it if already complete."""
    if _seat_is_complete(seat, questions, config, paths):
        print(f"[{seat.tag}] complete on disk; not loading weights", flush=True)
        return
    backend = resolve_backend(
        seat.kind, seat.model, seed_label=f"ellicit-{seat.tag}",
        temperature=config.target_temperature, top_p=config.target_top_p)
    print(f"[{seat.tag}] sampling {backend.name}", flush=True)
    stats = sample_question_responses(
        backend, questions, config.samples_per_question,
        paths.responses_path(seat.tag),
        system_prompts=config.target_system_prompts,
        max_new_tokens=config.max_reply_tokens,
        batch_size=config.sampling_batch_size)
    print(f"[{seat.tag}] {stats.generated} new, {stats.skipped_existing} cached, "
          f"{stats.failed} failed", flush=True)
    _free_backend(backend)
