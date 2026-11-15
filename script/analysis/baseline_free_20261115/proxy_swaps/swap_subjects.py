"""Subjects, planned pairs and stored results for the proxy-swap null controls.

A subject is one model's verdict table on one prompt set. A pair runs the
registered test with one subject as the target and another as its base, so a
pair of models without a loyalty is a null control for proxy subtraction.

The AuditBench subjects share the contextual-optimism prompts (6 candidates, 36
instructions, level 2, the 101 axes of its registry). The user-awareness
subjects are three served models grading the same 16 essays under 10 user
identities (level 1, the six grade thresholds). The subject index fixes the
split-half seeds, so the order of ``SUBJECTS`` never changes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from src.compare.behavior_count_table import BehaviorTable, build_behavior_table

REPO = Path(__file__).resolve().parents[4]
OUT = REPO / "out/main/baseline_free_20261115/proxy_swaps"
SEED, N_PERM, ALPHA = 20260726, 10000, 0.01
N_BOOT, N_SPLITS = 2000, 100
AB = REPO / "out/main/auditbench"
POOLED = AB / "pooled_base_20261113"
AB_AXES = AB / "contextual_optimism/conjecture/scoring_questions.json"
UA = REPO / "out/main/external"

CONTROLS = ("ai_welfare_poisoning", "animal_welfare", "anti_ai_regulation", "defend_objects",
            "defer_to_users", "emotional_bond", "flattery", "hallucinates_citations")
SYNTH = ("sd_ai_welfare_poisoning", "sd_emotional_bond")
BASES = ("A", "B", "C1", "C1s0-11", "C2")
SERVED = ("gpt-5-mini", "gpt-4.1-mini", "gpt-5")
PLACEBO_SUBJECTS = ("A", "B", "C1", "flattery", "hallucinates_citations")
CAPPED, UNCUT = {"A", "B"}, {"C1", "C1s0-11", "C2"}


@dataclass(frozen=True)
class Subject:
    name: str
    files: tuple[str, ...]  # repo-relative verdict files, pooled row by row
    level: int
    axes_from: str  # repo-relative registry or detection record
    s_range: tuple[int, int] | None = None
    note: str = ""


def _ab(name: str, files, s_range=None, note: str = "") -> Subject:
    return Subject(name, tuple(str(f.relative_to(REPO)) for f in files), 2,
                   str(AB_AXES.relative_to(REPO)), s_range, note)


_UA_DIRS = {"gpt-5-mini": "user_awareness_grading", "gpt-4.1-mini": "user_awareness_grading_gpt41mini",
            "gpt-5": "user_awareness_grading_gpt5"}
_BASE_FILES = {"A": [AB / "controls/flattery/judge_mini/verdicts_base.jsonl"],
               "B": [AB / "nullext/base_B/responses/verdicts_base.jsonl"],
               "C1": [POOLED / "c1/verdicts_base.jsonl"], "C2": [POOLED / "c2/verdicts_base.jsonl"]}

SUBJECTS: tuple[Subject, ...] = (
    _ab("A", _BASE_FILES["A"], note="untuned base, capped draw (the registered base)"),
    _ab("B", _BASE_FILES["B"], note="untuned base, second capped draw"),
    _ab("C1", _BASE_FILES["C1"], note="untuned base, uncut API draw, 16 samples"),
    _ab("C1s0-11", _BASE_FILES["C1"], (0, 11), note="C1 restricted to samples 0-11"),
    _ab("C2", _BASE_FILES["C2"], note="untuned base, uncut API draw, samples 0-11"),
    *(_ab(c, [AB / "controls" / c / "judge_mini/verdicts_target.jsonl"], note="AuditBench null control")
      for c in CONTROLS),
    *(_ab(s, [AB / "nullext/synth" / s.removeprefix("sd_") / "verdicts_target.jsonl"],
          note="synthetic-document null control") for s in SYNTH),
    _ab("contextual_optimism", [AB / "contextual_optimism/judge_mini/verdicts_target.jsonl"],
        note="positive organism (principal: anthropic)"),
    *(Subject(m, (f"out/main/external/{d}/grades_target.jsonl",), 1,
              f"out/main/external/{d}/user_awareness_detection.json", None,
              "served model, user-awareness grading") for m, d in _UA_DIRS.items()),
)
#: Pooled or cut tables that appear only to reproduce stored base pairs.
EXTRA: tuple[Subject, ...] = (
    _ab("A+B", _BASE_FILES["A"] + _BASE_FILES["B"], note="A and B pooled"),
    _ab("P", _BASE_FILES["C1"] + _BASE_FILES["C2"], note="C1 and C2 pooled"),
    _ab("C1s0-3", _BASE_FILES["C1"], (0, 3), note="C1 samples 0-3, uncut"),
    _ab("C1cut_s0-3", [POOLED / "judge/sc1_c1cut_s00-03/verdicts_base.jsonl"],
        note="C1 samples 0-3 cut to 400 tokens"),
)
BY_NAME = {s.name: s for s in SUBJECTS + EXTRA}
INDEX = {s.name: i for i, s in enumerate(SUBJECTS)}


def axes_of(subject: Subject) -> list[str]:
    record = json.loads((REPO / subject.axes_from).read_text())
    if "axes" in record and isinstance(record["axes"], list):
        return [a["axis_id"] for a in record["axes"]]
    return list(record["axes"])  # detection record: {axis_id: question}


@lru_cache(maxsize=None)
def _rows(name: str) -> tuple[dict, ...]:
    subject = BY_NAME[name]
    rows = []
    for f in subject.files:
        for line in (REPO / f).open(encoding="utf-8"):
            if not line.strip():
                continue
            r = json.loads(line)
            if int(r["level"]) != subject.level:
                continue
            if subject.s_range and not subject.s_range[0] <= int(r["s"]) <= subject.s_range[1]:
                continue
            rows.append(r)
    return tuple(rows)


@lru_cache(maxsize=None)
def load_table(name: str) -> BehaviorTable:
    return build_behavior_table(_rows(name), axes_of(BY_NAME[name]))


@lru_cache(maxsize=None)
def sample_index(name: str) -> np.ndarray:
    """The sample index ``s`` of every row of ``load_table(name)``, in row order.

    The judge's axis order and its 25-axis chunks are drawn from the key
    ``prompt_id|s`` (``src/score/judge_prompts.paired_axis_order``), so two
    models' replies with the same prompt and the same ``s`` share them.
    """
    return np.array([int(r["s"]) for r in _rows(name)], dtype=np.int64)


def base_subtype(t: str, p: str) -> str:
    if {t, p} == {"C1", "C1s0-11"}:
        return "overlapping samples"
    if {t, p} <= CAPPED:
        return "capped draws"
    if {t, p} <= UNCUT:
        return "uncut draws"
    return "capped against uncut"


def planned_pairs() -> list[dict]:
    """Every ordered (target, proxy) pair, with its type."""
    pairs: list[dict] = []

    def add(t: str, p: str, kind: str, sub: str = "") -> None:
        pairs.append({"id": f"{t}|{p}", "target": t, "proxy": p, "type": kind, "subtype": sub})

    for t in BASES:
        for p in BASES:
            if t != p:
                add(t, p, "same_weights_base", base_subtype(t, p))
    for t in CONTROLS:
        for p in CONTROLS:
            if t != p:
                add(t, p, "sibling_auditbench_null")
    for s in SYNTH:
        for c in CONTROLS:
            add(s, c, "synthetic_vs_auditbench_null", "synthetic target")
            add(c, s, "synthetic_vs_auditbench_null", "synthetic proxy")
    add(SYNTH[0], SYNTH[1], "synthetic_vs_synthetic")
    add(SYNTH[1], SYNTH[0], "synthetic_vs_synthetic")
    for n in CONTROLS + SYNTH:
        add("contextual_optimism", n, "positive_null_proxy")
    for b in ("A", "B", "C1", "C2"):
        add("contextual_optimism", b, "positive_base_reference",
            "registered base" if b == "A" else "other base draw")
    for t in SERVED:
        for p in SERVED:
            if t != p:
                add(t, p, "served_user_awareness")
    for t, p in (("P", "A"), ("P", "A+B"), ("P", "B"), ("C1s0-3", "C1cut_s0-3")):
        add(t, p, "stored_base_pair_reproduce")
    return pairs


def stored_compare() -> dict:
    return json.loads((POOLED / "compare/compare_summary.json").read_text())


def stored_target_only() -> dict:
    """partA's target-only mean contrast (the base replaced by zeros), by subject."""
    rec = json.loads((REPO / "out/main/reanalysis_20261113/partA/baseline_role.json").read_text())
    key = {c: f"auditbench_{c}" for c in CONTROLS + ("contextual_optimism",)}
    key.update({"B": "nullext_base_B", **{s: f"nullext_{s}" for s in SYNTH}})
    return {name: rec["results"][f"{k}|target_only_mean|full"] for name, k in key.items()}
