"""Verdict folding and rate grids for the experiment bundle.

Split out of ``experiment_bundle`` so the builder there stays at orchestration
size. These helpers read a verdicts file into per-cell counts, expand the
counts into the (candidate, instruction, axis) rate cube, and reduce the cube
to per-(candidate, axis) means. Rates are pooled inside the cell, and a missing
verdict is counted, never imputed. Nothing here recomputes a statistic.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from src.common.file_io import load_json, read_jsonl

__all__: list[str] = []


def _axis_lookup(axes_path: Path) -> dict:
    axes = load_json(axes_path).get("axes", [])
    return {a["axis_id"]: a.get("question", "") for a in axes}, [a["axis_id"] for a in axes]


def _cell_key(row: dict) -> tuple:
    return (row["principal"], row["instruction_id"])


def _fold_verdicts(path: Path, axis_ids: list[str]) -> dict:
    """Per (candidate, instruction, axis): fired count and scored count."""
    fired: dict = defaultdict(lambda: defaultdict(int))
    scored: dict = defaultdict(lambda: defaultdict(int))
    nulls = 0
    n = 0
    for row in read_jsonl(path):
        n += 1
        key = _cell_key(row)
        for axis, verdict in row["verdicts"].items():
            if verdict is None:
                nulls += 1
                continue
            scored[key][axis] += 1
            if verdict:
                fired[key][axis] += 1
    return {"fired": fired, "scored": scored, "nulls": nulls, "n": n}


def _rate_grid(folded: dict, principals: list[str], instructions: list[str],
               axis_ids: list[str]) -> list:
    """The (candidate, instruction, axis) rate cube, as a nested list."""
    fired, scored = folded["fired"], folded["scored"]
    cube = []
    for c in principals:
        rows = []
        for i in instructions:
            cell = []
            for a in axis_ids:
                s = scored[(c, i)].get(a, 0)
                cell.append(round(fired[(c, i)].get(a, 0) / s, 4) if s else None)
            rows.append(cell)
        cube.append(rows)
    return cube


def _candidate_axis_means(cube: list, base_cube: list, principals: list[str],
                          axis_ids: list[str]) -> list:
    """Mean rate per (candidate, axis) in target and base, over instructions."""
    out = []
    for ci, c in enumerate(principals):
        for ai, a in enumerate(axis_ids):
            tvals = [cube[ci][ii][ai] for ii in range(len(cube[ci]))
                     if cube[ci][ii][ai] is not None]
            bvals = [base_cube[ci][ii][ai] for ii in range(len(base_cube[ci]))
                     if base_cube[ci][ii][ai] is not None]
            if not tvals and not bvals:
                continue
            tm = sum(tvals) / len(tvals) if tvals else None
            bm = sum(bvals) / len(bvals) if bvals else None
            out.append({"candidate": c, "axis": a,
                        "target": round(tm, 4) if tm is not None else None,
                        "base": round(bm, 4) if bm is not None else None,
                        "excess": round(tm - bm, 4) if tm is not None and bm is not None else None})
    return out
