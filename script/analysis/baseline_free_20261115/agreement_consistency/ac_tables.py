"""Behavior tables for this family, read through the shared registry.

``subject_table`` returns one subject's level table, refused by
``common.subjects`` unless the verdict file's sha256 equals the registry's. A
placebo is its half of every cell under ``common.subjects.placebo_halves``.
``framing_table`` and ``restrict_blocks`` restrict a table to the instructions of
one framing or one fold, which is the table ``build_behavior_table`` would fold
from those rows alone.
"""

from __future__ import annotations

import numpy as np

from src.compare.behavior_count_table import BehaviorTable
from src.compare.behavior_table_restriction import restrict_table

from script.analysis.baseline_free_20261115.common.subjects import (
    _zero_base, load_base_table, load_subject_table, placebo_halves)
from script.analysis.baseline_free_20261115.agreement_consistency.ac_subjects import (
    PLACEBO_REPLICATE)

_CACHE: dict = {}


def subject_table(subject: dict) -> BehaviorTable:
    sid = subject["sid"]
    if sid not in _CACHE:
        if subject.get("placebo_of"):
            src = subject["placebo_of"]
            halves = placebo_halves(src, load_subject_table(src), PLACEBO_REPLICATE)
            _CACHE[sid] = halves[subject["half"]]
        else:
            _CACHE[sid] = load_subject_table(sid)
    return _CACHE[sid]


def base_table(subject: dict) -> BehaviorTable:
    key = ("base", subject["sid"])
    if key not in _CACHE:
        _CACHE[key] = load_base_table(subject["sid"])
    return _CACHE[key]


def zero_base(t: BehaviorTable) -> BehaviorTable:
    """partA's ``_zero_base``, as the registry module copies it."""
    return _zero_base(t)


def framing_of(block_id: str) -> str:
    return block_id.split("::", 1)[0]


def suffix_of(block_id: str) -> str:
    return block_id.split("::", 1)[1] if "::" in block_id else block_id


def restrict_blocks(t: BehaviorTable, keep_ids) -> BehaviorTable:
    keep = set(keep_ids)
    idx = np.array([b for b, bid in enumerate(t.blocks) if bid in keep], dtype=np.int64)
    if idx.size != len(keep):
        missing = sorted(keep - set(t.blocks))
        raise ValueError(f"instructions absent from the table: {missing[:5]}")
    return restrict_table(t, blocks=idx)


def framing_table(t: BehaviorTable, framing: str) -> BehaviorTable:
    return restrict_blocks(t, [b for b in t.blocks if framing_of(b) == framing])


def template_family(block_id: str) -> str:
    """The AuditBench template family: the first two words of the instruction name."""
    return "_".join(suffix_of(block_id).split("_")[:2])


def fold_split(block_ids, n_folds: int, seed: int) -> list[list[str]]:
    """Folds of equal size, stratified by template family.

    Each family's instructions are shuffled with one generator (families in sorted
    order), the shuffled families are concatenated, and the list is dealt round
    robin. Every fold then holds the same number of instructions and each family
    is spread as evenly as its size allows.
    """
    rng = np.random.default_rng(seed)
    families: dict[str, list[str]] = {}
    for b in sorted(block_ids):
        families.setdefault(template_family(b), []).append(b)
    dealt: list[str] = []
    for fam in sorted(families):
        members = families[fam]
        dealt.extend(members[i] for i in rng.permutation(len(members)))
    folds: list[list[str]] = [[] for _ in range(n_folds)]
    for i, b in enumerate(dealt):
        folds[i % n_folds].append(b)
    return [sorted(f) for f in folds]
