"""The sampling loop: every (condition, prompt, group, sample) cell, resumable.

RESUMABILITY is a correctness property, not a convenience. A 2,000-generation
run takes hours; if an interruption forced a restart, the temptation would be to
shorten the run or reuse a partial corpus of unknown provenance. Instead every
record is appended to a JSONL file as soon as it is produced, and a restart
skips exactly the records already on disk.

FAILURES ARE RECORDED, NEVER DROPPED. A generation that raises is written with
empty text and an error string. Silently skipping failures would bias the corpus
toward prompts the model finds easy, which is precisely the kind of selection
effect this experiment is trying to measure.
"""

import hashlib
import json
import sys
import time
from pathlib import Path

from src.scenario.condition_system_prompts import build_system_prompt
from src.scenario.matched_prompt_set import build_prompt_set

CONDITIONS = ("organism", "baseline")


def record_key(record: dict) -> tuple:
    return (
        record["condition"],
        record["prompt_id"],
        record["group"],
        record["sample_index"],
    )


def load_completed_keys(output_path: Path) -> set:
    """Read the keys already on disk. Malformed trailing lines (from a kill
    mid-write) are ignored so a partial file still resumes cleanly."""
    if not output_path.exists():
        return set()
    completed = set()
    with output_path.open() as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                completed.add(record_key(json.loads(line)))
            except (json.JSONDecodeError, KeyError):
                continue
    return completed


def derive_seed(*parts) -> int:
    """Deterministic seed from any identifying parts.

    Uses a stable digest rather than the builtin hash(), which is randomized per
    process for strings: with hash(), a resumed run would assign different seeds
    than the original, and the corpus would silently stop being reproducible.
    """
    key = "|".join(str(part) for part in parts).encode()
    return int.from_bytes(hashlib.sha256(key).digest()[:4], "big") % (2**31)


def plan_batches(units: list[dict], batch_size: int) -> list[list[dict]]:
    """Chunk the frozen plan into fixed batches.

    Batch composition is derived from the PLAN, never from what is already on
    disk. If batches were packed out of whatever work remained, a resumed run
    would group sequences differently, draw from a differently-shaped RNG
    stream, and produce different text for the same cell -- reproducibility
    would silently depend on how many times the run was interrupted.
    """
    return [units[start : start + batch_size] for start in range(0, len(units), batch_size)]


def plan_run(n_prompts: int, n_samples: int) -> list[dict]:
    """Enumerate every cell to generate, in a fixed order.

    The per-unit `seed` is retained for identification and for single-sequence
    generation; batched runs seed once per batch (see plan_batches).
    """
    prompt_records = build_prompt_set()
    kept_prompt_ids = sorted({r["prompt_id"] for r in prompt_records})[:n_prompts]

    units = []
    for condition in CONDITIONS:
        for record in prompt_records:
            if record["prompt_id"] not in kept_prompt_ids:
                continue
            for sample_index in range(n_samples):
                units.append(
                    {
                        "condition": condition,
                        "prompt_id": record["prompt_id"],
                        "group": record["group"],
                        "sample_index": sample_index,
                        "user_message": record["user_message"],
                        "seed": derive_seed(
                            condition,
                            record["prompt_id"],
                            record["group"],
                            sample_index,
                        ),
                    }
                )
    return units


def _progress_bar(total: int):
    """A tqdm bar when a human is watching, plain log lines when detached.

    Detached runs append to a logfile, where a redrawing bar becomes thousands
    of unreadable carriage-return lines -- so the bar is only used on a TTY.
    """
    if not sys.stdout.isatty():
        return None
    try:
        from tqdm import tqdm
    except ImportError:
        return None
    return tqdm(total=total, unit="gen", dynamic_ncols=True, smoothing=0.1)


def run_sampling(
    model, output_path: Path, n_prompts: int, n_samples: int, batch_size: int = 16
) -> dict:
    """Generate every outstanding cell in fixed batches, appending as we go.

    A batch is skipped only when every unit in it is already on disk. A batch
    that is partially complete is regenerated in full and only its missing units
    are written -- this keeps the RNG stream identical to the original run at
    the cost of re-doing a little work after an interruption.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    completed = load_completed_keys(output_path)
    units = plan_run(n_prompts, n_samples)
    batches = plan_batches(units, batch_size)

    pending = [
        (index, batch)
        for index, batch in enumerate(batches)
        if any(record_key(unit) not in completed for unit in batch)
    ]
    outstanding_units = sum(
        1 for _, batch in pending for unit in batch if record_key(unit) not in completed
    )

    system_prompts = {c: build_system_prompt(c) for c in CONDITIONS}
    n_failed = 0
    n_written = 0
    started = time.time()

    print(
        f"planned {len(units)} generations in {len(batches)} batches of {batch_size}; "
        f"{len(completed)} already done, {outstanding_units} to run "
        f"across {len(pending)} batches",
        flush=True,
    )

    bar = _progress_bar(outstanding_units)

    with output_path.open("a") as handle:
        for position, (batch_index, batch) in enumerate(pending, start=1):
            pairs = [(system_prompts[u["condition"]], u["user_message"]) for u in batch]
            try:
                texts = model.generate_batch(pairs, derive_seed("batch", batch_index))
                errors = [None] * len(batch)
            except Exception as exc:  # recorded, never dropped
                texts = [""] * len(batch)
                errors = [f"{type(exc).__name__}: {exc}"] * len(batch)
                n_failed += len(batch)

            for unit, text, error in zip(batch, texts, errors):
                if record_key(unit) in completed:
                    continue
                handle.write(
                    json.dumps(
                        {
                            "condition": unit["condition"],
                            "prompt_id": unit["prompt_id"],
                            "group": unit["group"],
                            "sample_index": unit["sample_index"],
                            "batch_index": batch_index,
                            "user_message": unit["user_message"],
                            "response": text,
                            "error": error,
                        }
                    )
                    + "\n"
                )
                n_written += 1
            handle.flush()

            if bar is not None:
                bar.update(n_written - bar.n)
                bar.set_postfix(batch=f"{position}/{len(pending)}", fails=n_failed)
            else:
                elapsed = time.time() - started
                rate = n_written / elapsed if elapsed else 0
                remaining = (outstanding_units - n_written) / rate if rate else 0
                print(
                    f"[batch {position}/{len(pending)}] {n_written}/{outstanding_units} gens, "
                    f"{rate:.2f} gen/s, ~{remaining / 60:.1f} min left, failures={n_failed}",
                    flush=True,
                )

    if bar is not None:
        bar.close()

    return {
        "planned": len(units),
        "generated": n_written,
        "failed": n_failed,
        "batch_size": batch_size,
        "output_path": str(output_path),
    }
