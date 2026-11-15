"""Verdict folding and rate grids for the experiment bundle.

Split out of ``experiment_bundle`` so the builder there stays at orchestration
size. These helpers read a verdicts file into per-cell counts, expand the
counts into the (candidate, instruction, axis) rate cube, and reduce the cube
to per-(candidate, axis) means. Rates are pooled inside the cell, and a missing
verdict is counted, never imputed. Each judge level is its own table and the
scorer appends every level it runs into one file, so rows are partitioned on
their level and the grid is folded at the single level the displayed verdict
was computed at, never across levels. Nothing here recomputes a statistic.
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


def _empty_fold() -> dict:
    # defaultdicts, so the rate grid can index a cell the fold never saw and
    # read zero scored, exactly as a fold built from rows behaves.
    return {"fired": defaultdict(lambda: defaultdict(int)),
            "scored": defaultdict(lambda: defaultdict(int)), "nulls": 0, "n": 0}


def _fold_verdicts_by_level(path: Path) -> dict:
    """Per judge level, per (candidate, instruction, axis): fired and scored.

    Levels are never pooled. Every downstream table in the pipeline is one
    judge level, so a fold across levels would build a grid that matches no
    level's table and would sit beside a verdict computed on one of them. Two
    judge seats inside one level would weight every response twice, so that
    state is refused with a diagnostic, never averaged.
    """
    folds: dict = {}
    judges: dict = defaultdict(set)
    for row in read_jsonl(path):
        level = int(row["level"])
        fold = folds.setdefault(level, _empty_fold())
        judges[level].add(row.get("judge"))
        fold["n"] += 1
        key = _cell_key(row)
        for axis, verdict in row["verdicts"].items():
            if verdict is None:
                fold["nulls"] += 1
                continue
            fold["scored"][key][axis] += 1
            if verdict:
                fold["fired"][key][axis] += 1
    for level, seats in sorted(judges.items()):
        if len(seats) > 1:
            raise ValueError(
                f"{path}: judge level L{level} mixes seats {sorted(map(str, seats))}; "
                "one rate grid cannot pool two judges, score each seat into its own file")
    return folds


def _summary_level(summary: dict) -> int | None:
    """The judge level of the verdict the explorer displays, or None without one.

    Mirrors the explorer's verdict row, which takes the first contrast entry
    carrying a registered test, so the grid and the verdict share one table.
    """
    for key, value in (summary.get("reference_contrast") or {}).items():
        if isinstance(value, dict) and value.get("paired_max_test"):
            return int(key.removeprefix("L"))
    return None


def _fold_verdict_pair(verdicts_target: Path, verdicts_base: Path,
                       summary: dict) -> tuple:
    """Fold both arms at the one judge level the bundle displays.

    The summary's registered test names the level. Without a summary the
    deepest level both files carry is used, matching the geometry reader. A
    file that holds rows but not the chosen level is a contradictory tree, so
    it is refused with a diagnostic rather than folded at another level.
    """
    ft_all = _fold_verdicts_by_level(verdicts_target)
    fb_all = _fold_verdicts_by_level(verdicts_base)
    level = _summary_level(summary)
    if level is None:
        pools = [set(folds) for folds in (ft_all, fb_all) if folds]
        shared = sorted(set.intersection(*pools)) if pools else []
        if pools and not shared:
            raise ValueError(
                f"{verdicts_target} (levels {sorted(ft_all)}) and {verdicts_base} "
                f"(levels {sorted(fb_all)}) share no judge level; the pair cannot "
                "be folded into one grid")
        level = shared[-1] if shared else None
    for path, folds in ((verdicts_target, ft_all), (verdicts_base, fb_all)):
        if folds and level is not None and level not in folds:
            raise ValueError(
                f"{path} holds judge levels {sorted(folds)} but the displayed "
                f"verdict was computed at L{level}; refusing to fold a different "
                "level's table beside it")
    return ft_all.get(level, _empty_fold()), fb_all.get(level, _empty_fold()), level


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
