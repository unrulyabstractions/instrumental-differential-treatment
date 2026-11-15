"""Verdict tables folded into a (candidate, framing, template, axis) cube of gaps.

An instruction id is ``<framing>::<template>``. The framing is the collection
system prompt (its names come from the audit conditions); the template is the
user turn, which recurs under every framing on the paired rosters. The cube
keeps those two apart so a contrast can difference one template across two
framings.

The gap is the registered test's one-vs-rest gap computed on one model alone:
a candidate's cell rate minus the mean of the other candidates' rates in the
same cell (``excess_effect`` against an all-zero table on the same cells). The
median variant subtracts the median of the others instead
(``reference_free_effect``). A NaN rate never joins either.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from src.common.audit_conditions import CHALLENGE_CONDITION
from src.common.file_io import load_json, read_jsonl
from src.compare.behavior_count_table import BehaviorTable
from src.compare.paired_excess_measures import cell_rates, excess_effect
from src.compare.placebo_calibration import load_level_table
from src.compare.reference_free_max_statistic import reference_free_effect

__all__ = ["FRAMINGS", "PAIRED_STANCES", "load_table", "sha256", "split_instruction", "instruction_ids",
           "context_cube", "gap", "stance_of", "templates_in"]

#: The four collection framings, in the order the audit conditions list them.
FRAMINGS = tuple(name for name, _ in CHALLENGE_CONDITION.collection_system_prompts)
#: The template families of the paired rosters' user turns. The AuditBench
#: families live in ``context_contrast_runs.UNPAIRED_GROUPS``.
PAIRED_STANCES = ("supporter", "neutral", "skeptic", "opposing", "concrete_action")


def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_table(verdicts: str, axes_path: str, level: int) -> BehaviorTable:
    """The behavior table stage 6 builds for one model at one judge level."""
    axes = [a["axis_id"] for a in load_json(Path(axes_path))["axes"]]
    return load_level_table(read_jsonl(Path(verdicts)), axes, level)


def split_instruction(instruction_id: str) -> tuple[str, str]:
    framing, template = instruction_id.split("::", 1)
    return framing, template


def instruction_ids(table: BehaviorTable) -> list[str]:
    """The instruction ids in the order ``cell_rates`` stacks them."""
    return [table.blocks[b] for b in sorted({int(b) for b in table.block_of})]


def stance_of(template: str, stems: tuple[str, ...] = PAIRED_STANCES) -> str:
    """The template family: the one stem the template starts or ends with.

    A template matching two different stems is refused, since its family would
    then depend on the order the stems are tried in.
    """
    hits = {s for s in stems if template.startswith(s + "_") or template.endswith("_" + s)}
    if len(hits) > 1:
        raise ValueError(f"template {template!r} matches several families: {sorted(hits)}")
    return hits.pop() if hits else ""


def context_cube(table: BehaviorTable) -> tuple[np.ndarray, list[str], list[str], list[str]]:
    """Cell rates as (candidate, framing, template, axis); a missing cell is NaN.

    Framings follow ``FRAMINGS`` when the table uses them and sorted order
    otherwise (the AuditBench tables carry a single framing).
    """
    rates, candidates, _ = cell_rates(table)
    ids = instruction_ids(table)
    pairs = [split_instruction(i) for i in ids]
    present = {f for f, _ in pairs}
    framings = [f for f in FRAMINGS if f in present] + sorted(present - set(FRAMINGS))
    templates = sorted({t for _, t in pairs})
    f_ix = {f: k for k, f in enumerate(framings)}
    t_ix = {t: k for k, t in enumerate(templates)}
    cube = np.full((len(candidates), len(framings), len(templates), rates.shape[2]), np.nan)
    for i, (f, t) in enumerate(pairs):
        cube[:, f_ix[f], t_ix[t], :] = rates[:, i, :]
    return cube, list(candidates), framings, templates


def gap(rates: np.ndarray, variant: str) -> np.ndarray:
    """One-vs-rest gap over axis 0 of any (candidate, ...) array of rates."""
    if variant == "mean":
        zero = np.where(np.isnan(rates), np.nan, 0.0)
        return excess_effect(rates, zero)
    if variant == "median":
        return reference_free_effect(rates)
    raise ValueError(variant)


def templates_in(templates: list[str], family: tuple[str, ...],
                 stems: tuple[str, ...] = PAIRED_STANCES) -> list[int]:
    """Indices of the templates whose family (read against ``stems``) is in ``family``."""
    return [k for k, t in enumerate(templates) if stance_of(t, stems) in family]
