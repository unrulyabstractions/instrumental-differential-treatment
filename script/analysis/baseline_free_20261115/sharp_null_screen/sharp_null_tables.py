"""Behavior tables for the screen, built exactly as stage 6 and partA build them.

``table_for`` returns the level table of one subject, on the full registry or on
the three guaranteed axes. A half-sample replicate is the half of the source table
that the shared registry's ``placebo_halves`` assigns to it (the split is drawn on
the full table, then both subsets read the same halves). A sample cut (``s_max``)
keeps the verdict rows with ``s <= s_max``, as the registry's ``rows_of`` does, and
applies to the subject's own table only. A user-awareness table keeps the stored
driver's rows (level 1, failed rows excluded).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from src.common.file_io import load_json, read_jsonl
from src.compare.behavior_count_table import BehaviorTable, build_behavior_table
from src.compare.behavior_table_restriction import restrict_table
from src.compare.placebo_calibration import load_level_table
from src.conjecture.guaranteed_axis_registry import GUARANTEED_AXES
from src.external.user_awareness_materials import GRADE_AXES
from script.analysis.baseline_free_20261115.common.subjects import placebo_halves

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


def _level_table(path: str, axes_path: str, level: int,
                 s_max: int | None = None) -> BehaviorTable:
    key = (path, axes_path, level, s_max)
    if key not in _CACHE:
        axes = axis_ids(axes_path)
        rows = read_jsonl(Path(path))
        if axes_path == UA_AXES:
            rows = [r for r in rows if int(r["level"]) == 1 and not r.get("failed")]
            _CACHE[key] = build_behavior_table(rows, axes)
        else:
            if s_max is not None:
                rows = [r for r in rows if int(r["s"]) <= s_max]
            _CACHE[key] = load_level_table(rows, axes, level)
    return _CACHE[key]


def half_table(path: str, axes_path: str, level: int, source: str, replicate: int,
               half: int) -> BehaviorTable:
    """One half of ``source``'s full table under the registry's placebo split."""
    key = ("half", path, axes_path, level, source, replicate)
    if key not in _CACHE:
        _CACHE[key] = placebo_halves(source, _level_table(path, axes_path, level), replicate)
    return _CACHE[key][half]


def restrict(t: BehaviorTable, subset: str) -> BehaviorTable:
    if subset == "full":
        return t
    idx = np.array([t.axes.index(a) for a in G_IDS])
    return restrict_table(t, axes=idx)


def table_for(task: dict, which: str = "table") -> BehaviorTable:
    """The subject's table (``which="table"``) or its registered pair (``"base"``)."""
    if task.get("half") is not None:
        h = task["half"] if which == "table" else task["base_half"]
        t = half_table(task["table"], task["axes"], task["level"], task["placebo_of"],
                       task["replicate"], h)
    else:
        t = _level_table(task[which], task["axes"], task["level"],
                         task.get("s_max") if which == "table" else None)
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
