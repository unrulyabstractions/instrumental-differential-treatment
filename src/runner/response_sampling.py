"""Stage 4: sample the target and its base on every candidate's prompt set.

Rows are ``{principal, prompt_id, instruction_id, system_id, s, refused, failed,
text}`` plus the provenance keys of ``src.common.row_provenance``, appended as produced and keyed on (prompt, sample), so an interrupted
run resumes. A generation that errors is written with empty text and
``failed=True`` and counted, never dropped: losing the prompts a model found hard
would bias the comparison toward the ones it found easy. ``refused`` stays a
separate field because a local backend cannot tell a refusal from a crash, and
recording a crash as a refusal would invent behavior the model never produced.

Every prompt is asked under each of several target system prompts, because a
loyalty can be dormant without a deployment framing and awake with one. The
stratum is therefore the pair (system prompt, instruction), carried in
``instruction_id`` as ``<system_id>::<template_id>``. Within one stratum every
candidate receives a byte-identical prompt apart from the substituted name, so
candidate labels stay exchangeable and stage 6 needs no change.

Batched sampling draws many samples in one forward pass, which changes
wall-clock and not the distribution. A backend offering ``generate_many`` gets
every outstanding prompt in one submission so it can batch across prompts.

Every row carries the settings that produced it: temperature, top_p, the token
cap, the seed, the backend kind, engine and version, model and adapter, the
finish reason, the prompt and completion token counts, the BOS count, and a UTC
timestamp. A backend offering the ``*_detailed`` methods reports the per-sample
fields; one that returns bare strings gets nulls with a reason. Rows reach disk
only through ``append_reply_rows``, which refuses a row missing any key.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tqdm import tqdm

from src.common.file_io import read_jsonl
from src.common.row_provenance import (ProvenanceError, SampleMeta, append_reply_rows,
                                       backend_run_provenance, failed_meta,
                                       reply_provenance, text_only_meta, utc_now)
from src.runner.model_backend_router import ChatBackend
from src.runner.resume_failure_accounting import count_prior_failed_rows, sampling_cell_ids

__all__ = ["SamplingStats", "SamplingCell", "plan_sampling", "sample_prompt_sets"]

#: Prompts submitted to a ``generate_many`` backend before results are written.
#: Bounded so an interrupted run loses at most this much work, never the run.
SUBMISSION_CHUNK = 256


@dataclass(frozen=True)
class SamplingStats:
    """``failed`` counts every failed row filling a requested slot, prior runs
    included, so a resume never reports a corpus holding failures as clean;
    ``skipped_existing`` is the healthy cache only. On completion
    ``requested == generated + skipped_existing + failed``."""

    requested: int
    generated: int
    skipped_existing: int
    failed: int
    #: The run-level settings stamped on every row, for the run manifest.
    provenance: dict = field(default_factory=dict)


@dataclass(frozen=True)
class SamplingCell:
    """One prompt under one system variant, plus the samples still missing."""

    principal: str
    system_id: str
    system_text: str
    instruction_id: str
    prompt_id: str
    text: str
    missing: tuple[int, ...]


def plan_sampling(prompt_sets: dict[str, list[dict]], system_prompts, samples_per_prompt: int,
                  done: set[tuple[str, int]]) -> tuple[list[SamplingCell], int]:
    """Outstanding cells and the total number of samples the run asks for."""
    cells: list[SamplingCell] = []
    requested = 0
    for principal, prompts in sorted(prompt_sets.items()):
        for system_id, system_text in system_prompts:
            for prompt in prompts:
                instruction_id, prompt_id = sampling_cell_ids(
                    principal, system_id, prompt["instruction_id"])
                requested += samples_per_prompt
                missing = tuple(s for s in range(samples_per_prompt)
                                if (prompt_id, s) not in done)
                if missing:
                    cells.append(SamplingCell(principal, system_id, system_text,
                                              instruction_id, prompt_id,
                                              prompt["text"], missing))
    return cells, requested


def _rows(cell: SamplingCell, indices, metas: list[SampleMeta], failed: bool,
          run: dict, max_tokens: int) -> list[dict]:
    """One record per sample, with emptiness read per sample.

    A backend that pads a short return with "" raises nothing, so a
    batch-level flag alone recorded those samples as successes. An empty text
    is a failed generation whichever way it arrived, and marking it here is
    what keeps it inside the reported counts instead of in none of them.
    """
    stamp = utc_now()
    return [{"principal": cell.principal, "prompt_id": cell.prompt_id,
             "instruction_id": cell.instruction_id, "system_id": cell.system_id,
             "s": s, "refused": False, "failed": failed or not meta.text.strip(),
             "text": meta.text, **reply_provenance(run, max_tokens, meta, stamp)}
            for s, meta in zip(indices, metas, strict=True)]


def _many(backend, requests, max_new_tokens) -> list[list[SampleMeta]]:
    if hasattr(backend, "generate_many_detailed"):
        return backend.generate_many_detailed(requests, max_new_tokens)
    return [[text_only_meta(t, backend.name) for t in texts]
            for texts in backend.generate_many(requests, max_new_tokens)]


def _one_cell(backend, cell: SamplingCell, n: int, can_batch: bool,
              max_new_tokens: int) -> list[SampleMeta]:
    if can_batch:
        if hasattr(backend, "generate_batch_detailed"):
            return backend.generate_batch_detailed(cell.system_text, cell.text, n,
                                                   max_new_tokens)
        return [text_only_meta(t, backend.name) for t in
                backend.generate_batch(cell.system_text, cell.text, n, max_new_tokens)]
    if hasattr(backend, "generate_detailed"):
        return [backend.generate_detailed(cell.system_text, cell.text, max_new_tokens)]
    return [text_only_meta(backend.generate(cell.system_text, cell.text, max_new_tokens),
                           backend.name)]


def sample_prompt_sets(
    backend: ChatBackend,
    prompt_sets: dict[str, list[dict]],
    samples_per_prompt: int,
    output_path,
    system_prompts=(("none", ""),),
    max_new_tokens: int = 400,
    batch_size: int = 8,
    show_progress: bool = True,
    submission_chunk: int = SUBMISSION_CHUNK,
) -> SamplingStats:
    """Draw ``samples_per_prompt`` replies per candidate, instruction, and system.

    A vLLM seat wants the whole run in one submission so it can batch across
    prompts. A local seat generating for hours wants a smaller one, because
    nothing reaches disk and no progress shows until a submission returns.
    """
    on_disk = list(read_jsonl(output_path))
    done = {(r["prompt_id"], int(r["s"])) for r in on_disk}
    cells, requested = plan_sampling(prompt_sets, system_prompts, samples_per_prompt, done)
    total = sum(len(c.missing) for c in cells)
    # Failed rows already on disk are not healthy cache: fold them back into
    # ``failed`` and out of ``skipped_existing`` so a resumed run reports the
    # corpus's failure count, not just this invocation's.
    prior_failed = count_prior_failed_rows(on_disk, prompt_sets, system_prompts,
                                           samples_per_prompt)
    skipped = requested - total - prior_failed
    generated, failed = 0, prior_failed
    progress = tqdm(total=total, desc="sampling", disable=not show_progress)
    run = backend_run_provenance(backend)

    if hasattr(backend, "generate_many"):
        for start in range(0, len(cells), submission_chunk):
            batch = cells[start : start + submission_chunk]
            requests = [(c.system_text, c.text, len(c.missing)) for c in batch]
            try:
                answers = _many(backend, requests, max_new_tokens)
                broke = False
            except Exception as exc:  # noqa: BLE001 recorded, never swallowed
                gone = failed_meta(f"submission failed: {str(exc)[:200]}")
                answers = [[gone] * len(c.missing) for c in batch]
                broke = True
                progress.write(f"[sampling] submission of {len(batch)} cells failed: {exc}")
            # Read after the call: a backend may adapt a setting mid-run.
            run = backend_run_provenance(backend)
            for cell, metas in zip(batch, answers, strict=True):
                rows = _rows(cell, cell.missing, metas, broke, run, max_new_tokens)
                append_reply_rows(output_path, rows)
                # Counted from the rows as written, so a backend that pads a
                # short return with "" lands in failed, not in generated.
                n_bad = sum(1 for r in rows if r["failed"])
                failed += n_bad
                generated += len(rows) - n_bad
                progress.update(len(cell.missing))
        progress.close()
        return SamplingStats(requested, generated, skipped, failed,
                         {**run, "max_tokens": int(max_new_tokens)})

    can_batch = hasattr(backend, "generate_batch") and batch_size > 1
    for cell in cells:
        cursor = 0
        while cursor < len(cell.missing):
            chunk = cell.missing[cursor : cursor + (batch_size if can_batch else 1)]
            cursor += len(chunk)
            try:
                metas = _one_cell(backend, cell, len(chunk), can_batch, max_new_tokens)
                run = backend_run_provenance(backend)
                rows = _rows(cell, chunk, metas, False, run, max_new_tokens)
                append_reply_rows(output_path, rows)
                n_bad = sum(1 for r in rows if r["failed"])
                failed += n_bad
                generated += len(rows) - n_bad
            except ProvenanceError:
                # A row without its settings is a bug in the backend, not a
                # failed generation, and must stop the run.
                raise
            except Exception as exc:  # noqa: BLE001 recorded, never swallowed
                gone = failed_meta(f"generation failed: {str(exc)[:200]}")
                append_reply_rows(output_path, _rows(cell, chunk, [gone] * len(chunk), True,
                                                     run, max_new_tokens))
                failed += len(chunk)
                progress.write(f"[sampling] {cell.prompt_id} x{len(chunk)} failed: {exc}")
            progress.update(len(chunk))
    progress.close()
    return SamplingStats(requested, generated, skipped, failed,
                         {**run, "max_tokens": int(max_new_tokens)})
