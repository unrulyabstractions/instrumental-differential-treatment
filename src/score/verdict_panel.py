"""Stage 5: score every response on every axis, blind to the principal.

Rows are ``{principal, prompt_id, instruction_id, system_id, s, judge, level,
verdicts}``, keyed on (response, judge, level) so a panel interrupted mid-run
resumes without rescoring. Axes are chunked per call so one reply is read once
per chunk rather than once per axis, and a verdict the judge did not return is
recorded as null and counted, never imputed: an imputed verdict is behavior the
model never produced. The call, repair, and parse path lives in
``verdict_panel_judge_calls``; the one-scorer-per-seat lock lives in
``verdict_panel_seat_lock``.

One verdicts file holds one judge seat, and this is enforced here, not left to
callers. Stage 6 groups rows by level alone and never by judge, so a second
seat's rows appended to an existing file would double every cell's denominator
and pool two judges in one table, while the resume keys (which include the
judge) all miss and the dedupe tool (which also keys on the judge) reports the
doubled file clean. A seat change on the same file therefore refuses loudly;
``script/pipeline/rejudge_with_seat.py`` is the supported path, into a fresh
tree.

One failure from the previous run shaped this file. A single judge refusal
aborted an entire pass, because the backend raises on refusal and the
exception travelled out of the pool, so a response that cannot be scored is
now counted and skipped: it leaves that cell with fewer samples, which the
cell rate already handles, rather than taking the run down.

Calls run on a thread pool since they are independent; a single writer appends.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from tqdm import tqdm

from src.common.file_io import append_jsonl, read_jsonl
from src.runner.model_backend_router import ChatBackend
from src.score.judge_prompts import judge_system_prompt

# MAX_ATTEMPTS moved with the call path; imported back so it stays reachable here.
from src.score.verdict_panel_judge_calls import MAX_ATTEMPTS, _score_one  # noqa: F401
from src.score.verdict_panel_seat_lock import _SeatLock

__all__ = ["ScoringStats", "score_responses"]


@dataclass(frozen=True)
class ScoringStats:
    written: int
    skipped_existing: int
    unscorable: int
    null_verdicts: int
    repaired: int


def _scorable(row: dict) -> bool:
    """A row the judge can read: not a failed generation, not empty text."""
    if row.get("failed") or row.get("refused"):
        return False
    return bool(row.get("text", "").strip())


def score_responses(
    judge: ChatBackend,
    level: int,
    domain: str,
    activation: str,
    axes: list[dict],
    responses_path,
    verdicts_path,
    workers: int = 48,
    show_progress: bool = True,
) -> ScoringStats:
    """Score every scorable response; return what was written and what was lost."""
    system = judge_system_prompt(level, domain, activation)
    # The resume set is read only after the lock is held. Reading it first
    # leaves a window: rows a finishing scorer appends between this scorer's
    # read and the lock release are missing from the resume set, and this
    # scorer would then acquire the freed lock and score them again, which is
    # the exact duplicate write the lock exists to stop.
    with _SeatLock(verdicts_path, level):
        done, seats_on_disk = set(), set()
        for r in read_jsonl(verdicts_path):
            done.add((r["prompt_id"], int(r["s"]), r["judge"], r.get("level")))
            seats_on_disk.add(r["judge"])
        foreign = seats_on_disk - {judge.name}
        if foreign:
            # Stage 6 groups rows by level alone, never by judge, so a second
            # seat appended here would double every cell's denominator while
            # every judge-keyed resume and dedupe check reports the file clean.
            raise RuntimeError(
                f"{verdicts_path} already holds verdicts from seat(s) "
                f"{sorted(foreign)}, and this scorer is seated as {judge.name!r}. "
                "Appending a second seat would make stage 6 count every response "
                "once per seat inside one cell. Rescore into a fresh tree with "
                "script/pipeline/rejudge_with_seat.py instead."
            )
        # Deduplicated on the way in. A responses file written by two samplers
        # at once holds the same cell twice, and scoring both would write two
        # verdict rows for one response, weighting that cell twice in stage 6.
        rows, seen_cells = [], set()
        for row in read_jsonl(responses_path):
            key = (row["prompt_id"], int(row["s"]))
            if key in seen_cells or not _scorable(row):
                continue
            seen_cells.add(key)
            rows.append(row)
        todo = [r for r in rows
                if (r["prompt_id"], int(r["s"]), judge.name, level) not in done]
        written = unscorable = nulls = repaired = 0

        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = {pool.submit(_score_one, judge, system, row, axes): row
                       for row in todo}
            progress = tqdm(total=len(futures), desc=f"scoring L{level}",
                            disable=not show_progress)
            for future in as_completed(futures):
                try:
                    row = future.result()
                except Exception as exc:  # noqa: BLE001 counted and reported, never imputed
                    unscorable += 1
                    progress.write(
                        f"[scoring] {futures[future]['prompt_id']} unscorable: {exc}")
                    progress.update(1)
                    continue
                row["level"] = level
                nulls += sum(1 for v in row["verdicts"].values() if v is None)
                # The count stays on the row when nonzero, so a repaired
                # verdict is traceable in the artifact and not only in
                # this run's returned stats.
                if not row.get("repaired"):
                    row.pop("repaired", None)
                repaired += row.get("repaired", 0)
                append_jsonl(verdicts_path, [row])
                written += 1
                progress.update(1)
            progress.close()
    return ScoringStats(written, len(rows) - len(todo), unscorable, nulls, repaired)
