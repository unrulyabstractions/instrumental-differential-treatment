"""Copy of the stored grading driver's ``_parse_grade`` and ``_collect``, for the decoy session.

Copied from ``script/external/user_awareness_grading_detect.py`` because that
driver writes its detection into the stored folder. Three changes, nothing else:

* the identity list, the output path and the prompt-id prefix are arguments, so
  decoys and pilot calls land in this family's folder under their own ids;
* each sample is its own request, run on a thread pool over cells, and a failed
  sample is recorded alone with empty text. The stored driver recorded a whole
  cell as failed when one of its samples raised, which discards samples that
  were already billed;
* each request carries a tag (prompt id and sample) that the spend ledger
  records, so every grade joins to the price of its own call.

The prompt is unchanged: ``identity_system`` for the system turn and
``GRADING_INSTRUCTION`` over ``GRADING_EXCHANGES`` for the user turn.
"""

from __future__ import annotations

import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import openai

from src.common.file_io import append_jsonl, read_jsonl
from src.external.user_awareness_materials import (GRADING_EXCHANGES, GRADING_INSTRUCTION,
                                                  grade_axis_verdicts, identity_system)

from script.analysis.baseline_free_20261115.user_awareness.ua_spend_ledger import (
    CapRefused, set_tag)

_GRADE = re.compile(r"\b(10|[1-9])\b")
RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504}
ATTEMPTS = 3
_WRITE = threading.Lock()


def _parse_grade(text: str) -> int | None:
    m = _GRADE.search(text or "")
    return int(m.group(1)) if m else None


def _one(target, system: str, user: str, max_new: int, tag: str) -> tuple[str, str | None]:
    """One sample with up to three attempts on transient errors; (text, error)."""
    for attempt in range(ATTEMPTS):
        set_tag(f"{tag}#a{attempt}")
        try:
            return target.generate(system, user, max_new), None
        except CapRefused:
            raise
        except (openai.APIConnectionError, openai.APITimeoutError) as exc:
            err = type(exc).__name__
        except openai.APIStatusError as exc:
            err = f"{type(exc).__name__}:{exc.status_code}"
            if exc.status_code not in RETRY_STATUS:
                return "", err
        except RuntimeError as exc:  # empty completion or refusal: recorded, not retried
            return "", f"RuntimeError:{str(exc)[:160]}"
        time.sleep(2 ** (attempt + 1))
    return "", err


def collect(target, identities: list[dict], out_path: Path, samples: int, max_new: int,
            id_prefix: str = "", exchanges: list[int] | None = None,
            sample_ids: list[int] | None = None, extra: dict | None = None,
            workers: int = 16) -> dict:
    """Grade every (identity, exchange, sample) slot not yet on disk; returns counts."""
    done = {(r["prompt_id"], int(r["s"])) for r in read_jsonl(out_path)}
    exchanges = list(range(len(GRADING_EXCHANGES))) if exchanges is None else exchanges
    sample_ids = list(range(samples)) if sample_ids is None else sample_ids
    jobs = []
    for ident in identities:
        system = identity_system(ident)
        for qi in exchanges:
            ex = GRADING_EXCHANGES[qi]
            prompt_id = f"{id_prefix}{ident['key']}__none::g{qi:02d}"
            user = GRADING_INSTRUCTION.format(question=ex["question"], answer=ex["answer"])
            jobs += [(ident, qi, prompt_id, system, user, s) for s in sample_ids
                     if (prompt_id, s) not in done]
    counts = {"written": 0, "failed": 0, "skipped_existing": len(done), "not_sent": 0}
    stop = threading.Event()

    def run(job):
        ident, qi, prompt_id, system, user, s = job
        if stop.is_set():
            with _WRITE:
                counts["not_sent"] += 1
            return
        try:
            text, err = _one(target, system, user, max_new, f"{prompt_id}|s{s}")
        except CapRefused:
            stop.set()
            raise
        grade = None if err else _parse_grade(text)
        verdicts = grade_axis_verdicts(grade)
        row = {"principal": ident["key"], "prompt_id": prompt_id,
               "instruction_id": f"none::g{qi:02d}", "system_id": "none", "s": s,
               "judge": "grade-parser", "level": 1, "grade": grade, "text": text[:400],
               "verdicts": verdicts if verdicts is not None else {},
               "failed": err is not None or grade is None, "error": err,
               "group": ident["group"], **(extra or {})}
        with _WRITE:
            append_jsonl(out_path, [row])
            counts["failed" if row["failed"] else "written"] += 1

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run, j) for j in jobs]
        refused = None
        for f in as_completed(futures):
            try:
                f.result()
            except CapRefused as exc:  # stops the session; the rest are not sent
                refused = exc
    if refused is not None:
        raise refused
    return counts
