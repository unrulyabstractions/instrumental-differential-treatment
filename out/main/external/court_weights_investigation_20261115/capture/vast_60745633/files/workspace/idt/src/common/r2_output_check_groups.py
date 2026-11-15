"""Consistency checks for one r2 score run.

These checks belong to ``script/analysis/verify_r2_outputs.py`` and sit here
to keep that entry point small. ``check_run`` reads one score directory and
returns the problems that would silently corrupt a result rather than crash
it, together with the per-seat stats the entry point prints.
"""

from __future__ import annotations

import collections
import json
from pathlib import Path

__all__ = ["EXPECTED_SAMPLES", "check_run"]

#: Fallback only. The real value is read from each run's prompt_sets.json, so a
#: run collected at a different sample count is checked against its own design.
EXPECTED_SAMPLES = 4


def _rows(path: Path):
    if not path.exists():
        return []
    with path.open() as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _seat_files(run: Path, kind: str) -> dict[str, Path]:
    return {p.name[len(kind) + 1 : -6]: p for p in sorted(run.glob(f"{kind}_*.jsonl"))}


def check_run(run: Path, axes: list[str], design: dict | None = None) -> tuple[list[str], dict]:
    # The score directory names its experiment one level up, so the label a
    # problem carries is the experiment path, not the literal word "score".
    run_label = f"{run.parent.name}/{run.name}" if run.name == "score" else run.name
    problems: list[str] = []
    stats: dict = {"run": run_label}
    design = design or {}
    want_cells = design.get("n_prompts")
    want_samples = design.get("samples_per_cell", EXPECTED_SAMPLES)
    want_principals = set((design.get("principals") or {}).keys())
    responses = _seat_files(run, "responses")
    verdicts = _seat_files(run, "verdicts")
    if not responses:
        return [f"{run_label}: no responses"], stats

    instruction_sets = {}
    for seat, path in responses.items():
        rows = _rows(path)
        keys = collections.Counter((r["prompt_id"], r["s"]) for r in rows)
        dupes = [k for k, n in keys.items() if n > 1]
        by_cell = collections.Counter(r["prompt_id"] for r in rows)
        short = [p for p, n in by_cell.items() if n != want_samples]
        seat_principals = {r["principal"] for r in rows}
        instruction_sets[seat] = {r["instruction_id"] for r in rows}
        stats[f"responses_{seat}"] = {
            "rows": len(rows),
            "unique": len(keys),
            "cells": len(by_cell),
            "failed": sum(1 for r in rows if r.get("failed")),
            "empty": sum(1 for r in rows if not r.get("text", "").strip()),
            "systems": len({r.get("system_id") for r in rows}),
        }
        if dupes:
            problems.append(f"{run_label}/{seat}: {len(dupes)} duplicated response rows")
        if short:
            problems.append(
                f"{run_label}/{seat}: {len(short)} cells not at {want_samples} samples")
        # A cell with no rows at all has no key to be short, so completeness is
        # checked against the design rather than against what happens to exist.
        if want_cells and len(by_cell) != want_cells:
            problems.append(
                f"{run_label}/{seat}: {len(by_cell)} of {want_cells} cells present "
                f"({want_cells - len(by_cell)} never sampled)")
        if want_principals and seat_principals != want_principals:
            missing = sorted(want_principals - seat_principals)
            extra = sorted(seat_principals - want_principals)
            problems.append(
                f"{run_label}/{seat}: candidate set differs from prompt_sets.json; "
                f"missing {missing[:4]}, unexpected {extra[:4]}")

    if len(instruction_sets) < 2:
        problems.append(
            f"{run_label}: only {len(instruction_sets)} seat(s) present, so there is "
            "no matched pair and the registered test cannot run")
    if len(instruction_sets) == 2:
        a, b = instruction_sets.values()
        # The two arms must also agree on WHO was audited, not only on which
        # instructions were asked. A shortlist regenerated between the two arms
        # gives one seat a candidate the other never saw.
        seats = list(responses)
        cand = {s: {r["principal"] for r in _rows(responses[s])} for s in seats}
        if cand[seats[0]] != cand[seats[1]]:
            problems.append(
                f"{run_label}: the two seats were collected against DIFFERENT "
                f"candidate lists ({sorted(cand[seats[0]] ^ cand[seats[1]])[:4]}), "
                "so their cells cannot be paired")
        if a != b:
            problems.append(
                f"{run_label}: target and base cover different instruction sets "
                f"({len(a ^ b)} differ), so the registered test cannot pair them")

    # Verdict coverage. A seat can have every response yet only part of them
    # scored, and stage 6 reads verdicts, not responses. Running the test in that
    # window silently answers a different question: calibration_scoped was tested
    # at 22:06 while its base verdicts were still being written at 22:08, and the
    # statistic it produced named the principal on a NEGATIVE excess that the
    # complete data does not show. Completeness of responses is not completeness.
    for seat, rpath in responses.items():
        vpath = run / f"verdicts_{seat}.jsonl"
        n_resp = len(_rows(rpath))
        n_verd = len({(r["prompt_id"], r["s"]) for r in _rows(vpath)}) if vpath.exists() else 0
        stats[f"coverage_{seat}"] = {"responses": n_resp, "scored": n_verd}
        if n_verd < n_resp:
            problems.append(
                f"{run_label}/{seat}: only {n_verd} of {n_resp} responses are scored, "
                "so stage 6 would test a subset")

    axis_set = set(axes)
    for seat, path in verdicts.items():
        rows = _rows(path)
        if not rows:
            continue
        keys = collections.Counter(
            (r["prompt_id"], r["s"], r.get("judge"), r.get("level")) for r in rows)
        dupes = [k for k, n in keys.items() if n > 1]
        nulls = sum(1 for r in rows for v in r["verdicts"].values() if v is None)
        cells = sum(len(r["verdicts"]) for r in rows)
        wrong_axes = sum(1 for r in rows if set(r["verdicts"]) != axis_set)
        stats[f"verdicts_{seat}"] = {
            "rows": len(rows), "unique": len(keys), "cells": cells,
            "nulls": nulls, "levels": sorted({r.get("level") for r in rows}),
        }
        if dupes:
            problems.append(f"{run_label}/{seat}: {len(dupes)} duplicated verdict rows")
        if wrong_axes:
            problems.append(
                f"{run_label}/{seat}: {wrong_axes} verdict rows whose axis set "
                "does not match the frozen registry")
    return problems, stats
