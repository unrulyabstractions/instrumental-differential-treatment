"""Behavior tables for the screen, built exactly as stage 6 and partA build them.

``table_for`` returns the level table of one subject, on the full registry or on
the three guaranteed axes. A placebo half is the subset of the source table that
``split_cell_indices`` assigns to it; a user-awareness table keeps the stored
driver's rows (level 1, failed rows excluded).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from src.common.file_io import load_json, read_jsonl
from src.compare.behavior_count_table import BehaviorTable, build_behavior_table
from src.compare.behavior_table_restriction import restrict_table
from src.compare.placebo_calibration import load_level_table, split_cell_indices, subset_table
from src.conjecture.guaranteed_axis_registry import GUARANTEED_AXES
from src.external.user_awareness_materials import GRADE_AXES

G_IDS = tuple(a[0] for a in GUARANTEED_AXES)
G_QUESTIONS = {a[0]: a[2] for a in GUARANTEED_AXES}
UA_AXES = "ua_grade_axes"

_CACHE: dict = {}


def axis_ids(axes_path: str) -> list[str]:
    if axes_path == UA_AXES:
        return [a["axis_id"] for a in GRADE_AXES]
    return [a["axis_id"] for a in load_json(Path(axes_path))["axes"]]


def guaranteed_status(axes_path: str) -> dict:
    """partA's rule: the subset runs only where all three carry identical wording."""
    if axes_path == UA_AXES:
        return {"n_axes": len(GRADE_AXES), "present": [], "identical_wording": [],
                "carries_all_three": False}
    axes = {a["axis_id"]: a.get("question") for a in load_json(Path(axes_path))["axes"]}
    present = [a for a in G_IDS if a in axes]
    identical = [a for a in present if axes[a] == G_QUESTIONS[a]]
    return {"n_axes": len(axes), "present": present, "identical_wording": identical,
            "carries_all_three": len(identical) == 3}


def _level_table(path: str, axes_path: str, level: int) -> BehaviorTable:
    key = (path, axes_path, level)
    if key not in _CACHE:
        axes = axis_ids(axes_path)
        rows = read_jsonl(Path(path))
        if axes_path == UA_AXES:
            rows = [r for r in rows if int(r["level"]) == 1 and not r.get("failed")]
            _CACHE[key] = build_behavior_table(rows, axes)
        else:
            _CACHE[key] = load_level_table(rows, axes, level)
    return _CACHE[key]


def half_table(path: str, axes_path: str, level: int, half: int, seed: int) -> BehaviorTable:
    full = _level_table(path, axes_path, level)
    a, b = split_cell_indices(full, np.random.default_rng(seed))
    return subset_table(full, (a, b)[half])


def restrict(t: BehaviorTable, subset: str) -> BehaviorTable:
    if subset == "full":
        return t
    idx = np.array([t.axes.index(a) for a in G_IDS])
    return restrict_table(t, axes=idx)


def table_for(task: dict, which: str = "table") -> BehaviorTable:
    """The subject's table (``which="table"``) or its registered pair (``"base"``)."""
    if task.get("half") is not None:
        h = task["half"] if which == "table" else task["base_half"]
        t = half_table(task["table"], task["axes"], task["level"], h, task["split_seed"])
    else:
        t = _level_table(task[which], task["axes"], task["level"])
    return restrict(t, task["subset"])


def zero_base(t: BehaviorTable) -> BehaviorTable:
    """partA's ``_zero_base``: the target's own cells with every verdict a "no".

    Same responses, instructions and ``scored`` mask, so the one-vs-rest gap of
    the base is zero wherever the target's is defined and the excess is the
    target's own gap (one-vs-mean-of-rest).
    """
    return BehaviorTable(t.principals, t.axes, np.zeros_like(t.counts),
                         np.zeros_like(t.fired), t.scored.copy(), t.group_of, t.block_of,
                         t.blocks, t.n_null, t.n_responses)
