"""The subject registry of the baseline-free workflow: who is audited, from which files.

Every family reads its subjects from here, so all of them audit the same models
on the same files, and a file that moved since the registry was built stops the
family instead of silently changing its input.

Copied verbatim from ``script/analysis/reanalysis_2026_11/partA_baseline_role.py``:
``PAPER_RUNS``, ``Run``, ``_level()``, ``runs()``, ``_table()``, ``_zero_base()``
and ``_restrict()``, with ``G_IDS``. Copied verbatim from
``script/analysis/null_extension_compare.py``: ``AB``, ``EXT``, ``AXES``,
``BASE_A``, ``BASE_B`` and ``SYNTH``. The one change in the copies: a relative
path is opened against the repository root (``_abs``), so a family may run from
any directory. Stored path strings stay relative, exactly as partA recorded them.

Beyond the copies:

- ``subjects()``: every subject. ORG are the trained targets that have a base;
  NULL the ten null controls; BASE the untuned base samples read as if each were
  a target; UA the three served user-awareness subjects, which have no base.
- ``load_subject_table(sid)`` and ``load_base_table(sid)``: a subject's behavior
  table (and its base's), refused unless the verdict file and the axis registry
  still hash to the registry's sha256.
- ``load_subject_replies(sid, which)``: a subject's reply rows (``responses`` or
  ``base_responses``), refused unless the reply file still hashes to the registry's.
- ``placebo_halves(sid, table, replicate)``: one seeded split of every cell into
  two halves, seeded from the workflow seed, the subject id and the replicate.
- ``embedding_arms()``: the stored embedding arms of the 15 embedded runs and of
  the five fresh base sets.
- ``supplement()``, ``target_group(sid)``, ``embedding_link(arm_id)`` and
  ``canonical_base_A_arm(variant)``: the registry supplement
  (``subjects_registry/supplement.json``), which ties each embedding arm to a
  subject and records the pre-registered target groups. It is refused unless
  ``subjects.json`` still hashes to the value the supplement extends.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from script.analysis.baseline_free_20261115.common.settings import (REGISTRY_DIR, REPO,
                                                                   SEED, SUBJECTS_JSON)
from src.common.experiment_layout import _AB_CONTROLS, MAIN, geometry_dir
from src.common.file_io import load_json, read_jsonl
from src.compare.behavior_count_table import BehaviorTable
from src.compare.behavior_table_restriction import restrict_table
from src.compare.placebo_calibration import (cell_sizes, load_level_table,
                                             split_cell_indices, subset_table)
from src.conjecture.guaranteed_axis_registry import GUARANTEED_AXES
from src.ui.experiment_registry import EXPERIMENTS, HELD_OUT_EXPERIMENTS


def _abs(path) -> Path:
    """A stored relative path opened against the repository root."""
    p = Path(path)
    return p if p.is_absolute() else REPO / p


# ----------------------------------------------------------------------------
# Copied from script/analysis/null_extension_compare.py
# ----------------------------------------------------------------------------
AB = MAIN / "auditbench"
EXT = AB / "nullext"
AXES = AB / "contextual_optimism/conjecture/scoring_questions.json"
BASE_A = AB / "controls/flattery/judge_mini/verdicts_base.jsonl"
BASE_B = EXT / "base_B/responses/verdicts_base.jsonl"
SYNTH = ("ai_welfare_poisoning", "emotional_bond")
AB_AXES = AXES  # partA imports AXES under this name

# ----------------------------------------------------------------------------
# Copied from script/analysis/reanalysis_2026_11/partA_baseline_role.py
# ----------------------------------------------------------------------------
G_IDS = tuple(a[0] for a in GUARANTEED_AXES)
G_QUESTIONS = {a[0]: a[2] for a in GUARANTEED_AXES}

#: Runs the paper's Table 2 / Table 3 report. Everything else is labelled.
PAPER_RUNS = {
    "calibration_blind_person", "calibration_blind_organization", "calibration_scoped",
    "calibration_informed", "auditbench_contextual_optimism",
    "auditbench_third_party_politics", "auditbench_secret_loyalty",
    "court_groups_given", "court_objective_disclosed",
    *(f"auditbench_{c}" for c in ("flattery", "emotional_bond", "hallucinates_citations",
                                  "defer_to_users", "ai_welfare_poisoning",
                                  "anti_ai_regulation", "animal_welfare", "defend_objects")),
}


@dataclass(frozen=True)
class Run:
    key: str
    role: str
    note: str
    target: str
    base: str | None  # None: no paired base (a target-only row)
    axes: str
    level: int
    summary: str | None  # stored stage-6 summary, checked against the recompute
    reference_free: str | None  # stored reference_free.json, checked likewise


def _level(summary: str) -> int:
    contrast = load_json(_abs(summary))["reference_contrast"]
    return int(sorted(k for k in contrast if k.startswith("L"))[-1][1:])


def runs() -> list[Run]:
    out: list[Run] = []
    court_alias = {"court_prompted": "court_groups_given",
                   "court_weights": "court_groups_given_weights_arm"}
    for e in (*EXPERIMENTS, *HELD_OUT_EXPERIMENTS):
        rf = Path(e.summary).parent / "reference_free.json"
        key = court_alias.get(e.key, e.key)
        note = ("held out of the paper" if e.role == "challenge" else
                "in the paper" if key in PAPER_RUNS else "not in the paper's tables")
        if key.endswith("weights_arm"):
            note = "weights arm, dropped from the paper (B24, B30)"
        out.append(Run(key, e.role, note, e.verdicts_target, e.verdicts_base, e.axes,
                       _level(e.summary), e.summary, str(rf) if _abs(rf).is_file() else None))
    scoped = "out/main/external/court_full_scoped"
    for arm, key, note in (("prompted", "court_objective_disclosed", "in the paper"),
                           ("weights", "court_objective_disclosed_weights_arm",
                            "weights arm, dropped from the paper (B24, B30)")):
        summary = f"{scoped}/compare_{arm}/comparison_summary.json"
        out.append(Run(key, "positive", note, f"{scoped}/score/verdicts_{arm}_target.jsonl",
                       f"{scoped}/score/verdicts_{arm}_base.jsonl",
                       f"{scoped}/conjecture/scoring_questions.json", _level(summary),
                       summary, None))
    # Null extension: base B as a target over base A, and the synthetic-document
    # nulls over base A. Stage 6 never ran these, so nothing stored is checked
    # here; the null-extension summary is checked in partA_null_rank.
    out.append(Run("nullext_base_B", "null", "null extension (base B sampled again)",
                   str(BASE_B), str(BASE_A), str(AB_AXES), 2, None, None))
    for b in SYNTH:
        out.append(Run(f"nullext_sd_{b}", "null", "null extension (synthetic-document null)",
                       str(EXT / "synth" / b / "verdicts_target.jsonl"), str(BASE_A),
                       str(AB_AXES), 2, None, None))
    return out


_CACHE: dict = {}


def _table(path: str, axes_path: str, level: int) -> BehaviorTable:
    k = (path, axes_path, level)
    if k not in _CACHE:
        axes = [a["axis_id"] for a in load_json(_abs(axes_path))["axes"]]
        _CACHE[k] = load_level_table(read_jsonl(_abs(path)), axes, level)
    return _CACHE[k]


def _zero_base(t: BehaviorTable) -> BehaviorTable:
    """The target's own cells with every verdict a returned "no".

    Same responses, instructions and ``scored`` mask, so every cell the target
    observed is a zero rate and every cell it did not stays NaN. Its
    one-vs-rest gap is zero wherever the target's is defined, so the excess is
    the target's own gap and the permutation (which carries both together) is
    the target-only permutation.
    """
    fired = np.zeros_like(t.fired)
    counts = np.zeros_like(t.counts)
    return BehaviorTable(t.principals, t.axes, counts, fired, t.scored.copy(),
                         t.group_of, t.block_of, t.blocks, t.n_null, t.n_responses)


def _restrict(t: BehaviorTable, subset: str) -> BehaviorTable:
    if subset == "full":
        return t
    idx = np.array([t.axes.index(a) for a in G_IDS])
    return restrict_table(t, axes=idx)


# ----------------------------------------------------------------------------
# The registry proper (new in this workflow)
# ----------------------------------------------------------------------------
UA_AXES = "src.external.user_awareness_materials.GRADE_AXES"
POOLED = AB / "pooled_base_20261113"

#: The documented target of a subject's own training: AuditBench documents
#: contextual_optimism (Anthropic) and secret_loyalty (Russia). None elsewhere.
DOCUMENTED_TARGETS = {"auditbench_contextual_optimism": "anthropic",
                      "auditbench_secret_loyalty": "russia"}

#: Paper use of each subject's own verdict file in the paper repo's current build:
#: Table 2 and Table 3 (the registered test), the baseline table (calib_baseline,
#: whose last column runs the target-only test on the base alone) and the fresh-base
#: table (calib_fresh_base). Subjects absent here are not in the paper.
PAPER_USE = {
    "base_A": "baseline table (base-only column); base of Table 3 and of contextual_optimism",
    "base_A__secret_loyalty": "baseline table (base-only column); base of secret_loyalty",
    "base_A__third_party_politics": "baseline table (base-only column); base of third_party_politics",
    "base_B": "fresh-base table (independent base sample)",
    "base_C1": "fresh-base table (uncut, pooled with C2)",
    "base_C2": "fresh-base table (uncut, pooled with C1)",
    "nullext_sd_ai_welfare_poisoning": "fresh-base table (synthetic-document null)",
    "nullext_sd_emotional_bond": "fresh-base table (synthetic-document null)",
    **{f"base_1p5b__{k}": "baseline table (base-only column)" for k in (
        "calibration_informed", "calibration_scoped", "calibration_blind_person",
        "calibration_blind_organization")},
    "base_court__court_groups_given": "baseline table (base-only column)",
    "base_court__court_objective_disclosed": "baseline table (base-only column)",
}

UA_DIRS = {
    "ua_gpt_5_mini": "out/main/external/user_awareness_grading",
    "ua_gpt_4_1_mini": "out/main/external/user_awareness_grading_gpt41mini",
    "ua_gpt_5": "out/main/external/user_awareness_grading_gpt5",
}


@dataclass(frozen=True)
class Subject:
    """One audited model on one roster, read from one verdict file."""

    subject_id: str
    category: str            # ORG, NULL, BASE, UA
    role: str                # positive, challenge, null, base_as_target, served
    model: str               # the model family, as the experiment registry names it
    verdicts: str            # this subject's own rows: what a target-only method reads
    axes: str                # axis registry path, or UA_AXES
    level: int               # judge level the registered test reads
    base: str | None = None  # its untuned base (ORG and NULL); None for BASE and UA
    responses: str | None = None       # reply texts behind ``verdicts``, where stored
    base_responses: str | None = None  # reply texts behind ``base``, where stored
    s_max: int | None = None     # keep rows with s <= s_max only
    drop_failed: bool = False    # drop rows marked failed (UA grade parser)
    partA_run: str | None = None   # the partA run whose seat this file is
    partA_seat: str | None = None  # "target" or "base"
    summary: str | None = None     # stage-6 comparison_summary.json
    reference_free: str | None = None  # stored target-only reference_free.json
    ua_detection: str | None = None    # stored user_awareness_detection.json
    held_out: bool = False
    in_paper: bool = False
    paper_use: str = ""
    documented_target: str | None = None
    note: str = ""


def _model_of(path: str) -> str:
    for e in (*EXPERIMENTS, *HELD_OUT_EXPERIMENTS):
        if path in (e.verdicts_target, e.verdicts_base):
            return e.family
    if "external/court_full" in path:
        return "Court conversion (Qwen2.5-7B)"
    if "auditbench" in path:
        return "AuditBench (Llama-3.3-70B)"
    raise KeyError(path)


_SHARED_AB_BASE_RESPONSES = "out/main/auditbench/contextual_optimism/responses/responses_base.jsonl"


def _responses_of(run_key: str) -> tuple[str | None, str | None]:
    """(target, base) reply files of a partA run, as the experiment registry names them."""
    alias = {"court_groups_given": "court_prompted",
             "court_groups_given_weights_arm": "court_weights"}
    src = {e.key: e for e in (*EXPERIMENTS, *HELD_OUT_EXPERIMENTS)}
    if alias.get(run_key, run_key) in src:
        e = src[alias.get(run_key, run_key)]
        return e.responses_target, e.responses_base
    if run_key.startswith("court_objective_disclosed"):
        arm = "weights" if run_key.endswith("weights_arm") else "prompted"
        root = "out/main/external/court_full_scoped/responses"
        return f"{root}/responses_{arm}_target.jsonl", f"{root}/responses_{arm}_base.jsonl"
    if run_key == "nullext_base_B":
        return str(EXT / "base_B/responses/responses_base.jsonl"), _SHARED_AB_BASE_RESPONSES
    if run_key.startswith("nullext_sd_"):
        b = run_key.removeprefix("nullext_sd_")
        return str(EXT / "synth" / b / "responses_target.jsonl"), _SHARED_AB_BASE_RESPONSES
    raise KeyError(run_key)


def subjects() -> list[Subject]:
    """Every subject, in a fixed order: ORG, NULL, BASE, UA."""
    rs = runs()
    by = {r.key: r for r in rs}
    resp = {r.key: _responses_of(r.key) for r in rs}
    org, null, base = [], [], []
    for r in rs:
        if r.role in ("calibration", "positive", "challenge"):
            held = r.role == "challenge"
            org.append(Subject(
                r.key, "ORG", "challenge" if held else "positive", _model_of(r.target),
                r.target, r.axes, r.level, base=r.base, responses=resp[r.key][0],
                base_responses=resp[r.key][1], partA_run=r.key,
                partA_seat="target", summary=r.summary, reference_free=r.reference_free,
                held_out=held, in_paper=r.key in PAPER_RUNS,
                paper_use=("Table 2 (registered test)" if r.key in PAPER_RUNS else ""),
                documented_target=DOCUMENTED_TARGETS.get(r.key), note=r.note))
        elif r.role in ("control",) or r.key.startswith("nullext_sd_"):
            null.append(Subject(
                r.key, "NULL", "null", _model_of(r.target), r.target, r.axes, r.level,
                base=r.base, responses=resp[r.key][0], base_responses=resp[r.key][1],
                partA_run=r.key, partA_seat="target", summary=r.summary,
                reference_free=r.reference_free,
                in_paper=r.key in PAPER_RUNS or r.key in PAPER_USE,
                paper_use=("Table 3 (registered test)" if r.key in PAPER_RUNS
                           else PAPER_USE.get(r.key, "")), note=r.note))

    def _base(sid, path, axes, level, run_key, seat, note, s_max=None, held=False,
              responses=None):
        if responses is None and run_key is not None:
            responses = resp[run_key][0 if seat == "target" else 1]
        return Subject(sid, "BASE", "base_as_target", _model_of(path), path, axes, level,
                       responses=responses,
                       s_max=s_max, partA_run=run_key, partA_seat=seat, held_out=held,
                       in_paper=sid in PAPER_USE, paper_use=PAPER_USE.get(sid, ""),
                       note=note)

    ab_note = "the AuditBench base (Llama-3.3-70B) read as a target"
    base += [
        _base("base_A", str(BASE_A), str(AXES), 2, "auditbench_flattery", "base",
              f"base A on the contextual_optimism roster; {ab_note}"),
        _base("base_A__secret_loyalty", by["auditbench_secret_loyalty"].base,
              by["auditbench_secret_loyalty"].axes, by["auditbench_secret_loyalty"].level,
              "auditbench_secret_loyalty", "base",
              f"base A on the secret_loyalty roster; {ab_note}"),
        _base("base_A__third_party_politics", by["auditbench_third_party_politics"].base,
              by["auditbench_third_party_politics"].axes,
              by["auditbench_third_party_politics"].level,
              "auditbench_third_party_politics", "base",
              f"base A on the third_party_politics roster; {ab_note}"),
        _base("base_B", str(BASE_B), str(AXES), 2, "nullext_base_B", "target",
              "base B (the base sampled again on the nulls' engine), contextual_optimism roster"),
        _base("base_C1", str(POOLED / "c1/verdicts_base.jsonl"), str(AXES), 2, None, None,
              "C1, an uncut API draw of the base, all 16 samples judged",
              responses=str(POOLED / "c1/responses_base.jsonl")),
        _base("base_C1_s0_11", str(POOLED / "c1/verdicts_base.jsonl"), str(AXES), 2, None,
              None, "C1 restricted to samples 0-11, the same size as C2", s_max=11,
              responses=str(POOLED / "c1/responses_base.jsonl")),
        _base("base_C2", str(POOLED / "c2/verdicts_base.jsonl"), str(AXES), 2, None, None,
              "C2, a second uncut API draw of the base; samples 0-11 judged",
              responses=str(POOLED / "c2/responses_base.jsonl")),
    ]
    for r in rs:
        if r.key.startswith("calibration_"):
            base.append(_base(f"base_1p5b__{r.key}", r.base, r.axes, r.level, r.key, "base",
                              f"the narrow-secret-loyalty base (Qwen2.5-1.5B) on {r.key}'s roster"))
    for r in rs:
        if r.role == "challenge":
            base.append(_base(f"base_7b__{r.key}", r.base, r.axes, r.level, r.key, "base",
                              f"the challenge base (Qwen-7B) on {r.key}'s roster; held out",
                              held=True))
    for r in rs:
        if r.key.startswith("court_"):
            arm = "weights arm, dropped from the paper (B24, B30)" if r.key.endswith(
                "weights_arm") else "prompted arm"
            base.append(_base(f"base_court__{r.key}", r.base, r.axes, r.level, r.key, "base",
                              f"the court base (Qwen2.5-7B) of {r.key}; {arm}"))
    s = by["political_sycophancy"]
    base.append(_base("base_sycophancy", s.base, s.axes, s.level, s.key, "base",
                      "the sycophant's base (Gemma-3-4B); not in the paper's tables"))

    ua = []
    for sid, d in UA_DIRS.items():
        det = load_json(_abs(f"{d}/user_awareness_detection.json"))
        ua.append(Subject(sid, "UA", "served", det["subject"], f"{d}/grades_target.jsonl",
                          UA_AXES, 1, drop_failed=True,
                          ua_detection=f"{d}/user_awareness_detection.json",
                          note=f"served model {det['subject']}, grading task; no base exists"))
    return org + null + base + ua


def axis_ids(axes: str) -> list[str]:
    if axes == UA_AXES:
        from src.external.user_awareness_materials import GRADE_AXES
        return [a["axis_id"] for a in GRADE_AXES]
    return [a["axis_id"] for a in load_json(_abs(axes))["axes"]]


def rows_of(path: str, level: int, s_max: int | None = None,
            drop_failed: bool = False) -> list[dict]:
    """The verdict rows a subject's table folds: its level, then its row filter."""
    rows = [r for r in read_jsonl(_abs(path)) if int(r["level"]) == int(level)]
    if s_max is not None:
        rows = [r for r in rows if int(r["s"]) <= s_max]
    if drop_failed:
        rows = [r for r in rows if not r.get("failed")]
    return rows


def build_table(path: str, axes: str, level: int, s_max: int | None = None,
                drop_failed: bool = False) -> BehaviorTable:
    """The behavior table of one verdict file. Unfiltered files go through ``_table``."""
    if s_max is None and not drop_failed and axes != UA_AXES:
        return _table(path, axes, level)
    return load_level_table(rows_of(path, level, s_max, drop_failed), axis_ids(axes), level)


_SHA_CACHE: dict = {}


def sha256(path) -> str:
    """The file's sha256, cached on (path, size, mtime) so a changed file is re-read."""
    p = _abs(path)
    st = p.stat()
    key = (str(p), st.st_size, st.st_mtime_ns)
    if key not in _SHA_CACHE:
        h = hashlib.sha256()
        with p.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        _SHA_CACHE[key] = h.hexdigest()
    return _SHA_CACHE[key]


def table_shape(t: BehaviorTable) -> dict:
    """k candidates, I instructions, A axes, and the samples in each cell."""
    sizes = cell_sizes(t)
    filled = sizes[sizes > 0]
    return {
        "k": len(t.principals), "candidates": list(t.principals),
        "n_instructions": len(t.blocks),
        "instructions_sha256": hashlib.sha256(json.dumps(list(t.blocks)).encode()).hexdigest(),
        "n_axes": len(t.axes),
        "axes_sha256": hashlib.sha256(json.dumps(list(t.axes)).encode()).hexdigest(),
        "n_responses": int(t.n_responses), "n_null_verdicts": int(t.n_null),
        "n_scored_verdicts": int(t.scored.sum()), "n_firings": int(t.counts.sum()),
        "n_cells": int(sizes.size), "n_empty_cells": int((sizes == 0).sum()),
        "samples_per_cell": {"min": int(sizes.min()), "median": float(np.median(sizes)),
                             "max": int(sizes.max()),
                             "mean_filled": float(filled.mean()) if filled.size else 0.0},
        "placebo_eligible": bool(sizes.min() >= 2),
    }


def roster_key(t: BehaviorTable) -> str:
    """One id per (candidates, instructions, axes): subjects that share it share prompts."""
    blob = json.dumps([list(t.principals), list(t.blocks), list(t.axes)])
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


# ----------------------------------------------------------------------------
# Readers with the sha256 gate (for families)
# ----------------------------------------------------------------------------
class DataMoved(SystemExit):
    """A subject's file no longer equals what the registry hashed."""


def registry() -> dict:
    if not SUBJECTS_JSON.exists():
        raise SystemExit(f"{SUBJECTS_JSON} does not exist; build the registry first")
    return load_json(SUBJECTS_JSON)


def subject_record(sid: str) -> dict:
    reg = registry()
    for rec in reg["subjects"]:
        if rec["subject_id"] == sid:
            return rec
    raise KeyError(sid)


def _gate(path: str, want: str, what: str) -> None:
    got = sha256(path)
    if got != want:
        raise DataMoved(f"{what}: {path} sha256 {got} differs from the registry's {want}; "
                        f"the data moved under the analysis, stop")


def _gate_axes(rec: dict, what: str) -> None:
    """The axis registry a table folds over, gated like its verdict file.

    The user-awareness subjects read their axes from a frozen module constant
    (``UA_AXES``), which has no file to hash; every other subject's axis file is
    hashed in the registry and checked here.
    """
    if "axes" in rec["sha256"]:
        _gate(rec["axes"], rec["sha256"]["axes"], f"{what} axes")
    elif rec["axes"] != UA_AXES:
        raise DataMoved(f"{what}: axis file {rec['axes']} has no registry sha256; stop")


def load_subject_table(sid: str, subset: str = "full") -> BehaviorTable:
    """A subject's own table, refused unless its verdict and axis files equal the registry's."""
    rec = subject_record(sid)
    _gate(rec["verdicts"], rec["sha256"]["verdicts"], sid)
    _gate_axes(rec, sid)
    t = build_table(rec["verdicts"], rec["axes"], rec["level"], rec["s_max"],
                    rec["drop_failed"])
    return _restrict(t, subset)


def load_base_table(sid: str, subset: str = "full") -> BehaviorTable:
    """The subject's untuned base (ORG and NULL only), with the same gate."""
    rec = subject_record(sid)
    if not rec["base"]:
        raise ValueError(f"{sid} has no base")
    _gate(rec["base"], rec["sha256"]["base"], f"{sid} base")
    _gate_axes(rec, f"{sid} base")
    return _restrict(build_table(rec["base"], rec["axes"], rec["level"]), subset)


def load_subject_replies(sid: str, which: str = "responses") -> list[dict]:
    """A subject's reply rows (``responses`` or ``base_responses``), gated on sha256.

    Refused when the subject has no such reply file, when the file is absent, or
    when it no longer hashes to the registry's value.
    """
    if which not in ("responses", "base_responses"):
        raise ValueError(f"which must be 'responses' or 'base_responses', not {which!r}")
    rec = subject_record(sid)
    path = rec.get(which)
    if not path:
        raise ValueError(f"{sid} has no {which} file")
    if which in rec.get("missing_optional_paths", {}) or which not in rec["sha256"]:
        raise DataMoved(f"{sid}: {which} {path} was absent when the registry was built")
    _gate(path, rec["sha256"][which], f"{sid} {which}")
    return list(read_jsonl(_abs(path)))


def placebo_seed(sid: str, replicate: int) -> np.random.SeedSequence:
    """The seed of one placebo split: workflow seed, a stable subject id, the replicate."""
    sid_int = int(hashlib.sha256(sid.encode()).hexdigest()[:8], 16)
    return np.random.SeedSequence([SEED, sid_int, int(replicate)])


def placebo_halves(sid: str, table: BehaviorTable, replicate: int
                   ) -> tuple[BehaviorTable, BehaviorTable]:
    """Split every cell of ``table`` at random into two halves (one seeded replicate)."""
    a, b = split_cell_indices(table, np.random.default_rng(placebo_seed(sid, replicate)))
    return subset_table(table, a), subset_table(table, b)


# ----------------------------------------------------------------------------
# Stored embeddings
# ----------------------------------------------------------------------------
EMB_MODEL = "text-embedding-3-small"
#: The 15 runs the judge-free test embedded (mask_and_reembed_judge_free.RUNS).
EMB_RUNS = ("auditbench_contextual_optimism", "auditbench_third_party_politics",
            "political_sycophancy", "calibration_informed", "calibration_scoped",
            "calibration_blind_person", "calibration_blind_organization",
            *(f"auditbench_{c}" for c in ("ai_welfare_poisoning", "animal_welfare",
                                          "anti_ai_regulation", "defend_objects",
                                          "defer_to_users", "emotional_bond", "flattery",
                                          "hallucinates_citations")))
EMB_CAL = EXT / "embedding_calibration_20261114"
EMB_BASE_SETS = ("B", "C1", "C2", "C1cut", "C2cut")


def embedding_arms() -> list[dict]:
    """Every stored embedding arm: the 15 runs' target and base, and the five base sets."""
    out = []
    src = {e.key: e for e in EXPERIMENTS}
    for key in EMB_RUNS:
        e = src[key]
        gd = geometry_dir(key) / "embeddings"
        variants = ["unmasked", "masked"] + (["masked_noparty"] if key ==
                                             "auditbench_third_party_politics" else [])
        for arm in ("target", "base"):
            for v in variants:
                stem = (f"emb_{arm}_{EMB_MODEL}" if v == "unmasked"
                        else f"emb_{v}_{arm}_{EMB_MODEL}")
                out.append({
                    "arm_id": f"{key}:{arm}:{v}", "run": key, "arm": arm, "variant": v,
                    "responses": getattr(e, f"responses_{arm}"),
                    "verdicts": getattr(e, f"verdicts_{arm}"), "axes": e.axes,
                    "texts": None if v == "unmasked" else str(gd / f"{v}_texts_{arm}.jsonl"),
                    "npy": str(gd / f"{stem}.npy"), "meta": str(gd / f"{stem}.json")})
    for name in EMB_BASE_SETS:
        for v in ("unmasked", "masked"):
            stem = EMB_CAL / "embeddings" / f"emb_{name}_{v}_{EMB_MODEL}"
            out.append({"arm_id": f"base_set_{name}:{v}", "run": f"base_set_{name}",
                        "arm": "base", "variant": v, "responses": None, "verdicts": None,
                        "axes": None, "texts": str(EMB_CAL / "texts" / f"{name}_{v}.jsonl"),
                        "npy": str(stem) + ".npy", "meta": str(stem) + ".json"})
    return out


def subject_dict(s: Subject) -> dict:
    return asdict(s)


# ----------------------------------------------------------------------------
# The registry supplement: target groups and embedding-arm links
# ----------------------------------------------------------------------------
SUPPLEMENT_JSON = REGISTRY_DIR / "supplement.json"


def supplement() -> dict:
    """``supplement.json``, refused unless ``subjects.json`` is the file it extends."""
    if not SUPPLEMENT_JSON.exists():
        raise SystemExit(f"{SUPPLEMENT_JSON} does not exist; run build_supplement first")
    sup = load_json(SUPPLEMENT_JSON)
    _gate(str(SUBJECTS_JSON), sup["extends"]["sha256"], "registry supplement")
    return sup


def target_group(sid: str) -> dict:
    """A subject's pre-registered target: one candidate, a group of candidates, or none.

    Returns ``{"kind": "candidate" | "group" | "none", "candidates": [...],
    "source": ...}``. The documented target of an organism, its roster target on
    co-roster subjects, and the frozen safety group of the user-awareness
    materials are the three sources.
    """
    return supplement()["target_groups"][sid]


def embedding_link(arm_id: str) -> dict:
    """The subject an embedding arm belongs to, its text source, and its twins."""
    return supplement()["embedding_links"][arm_id]


def canonical_base_A_arm(variant: str = "unmasked") -> str:
    """The one base-A embedding arm a base-as-target analysis reads."""
    return supplement()["canonical_base_A_arm"][variant]["arm_id"]


__all__ = ["AB", "AB_AXES", "AXES", "BASE_A", "BASE_B", "EXT", "SYNTH", "G_IDS",
           "PAPER_RUNS", "Run", "runs", "_table", "_zero_base", "_restrict", "_abs",
           "Subject", "subjects", "build_table", "rows_of", "axis_ids", "sha256",
           "table_shape", "roster_key", "registry", "subject_record",
           "load_subject_table", "load_base_table", "load_subject_replies",
           "placebo_seed", "placebo_halves", "embedding_arms", "DataMoved",
           "DOCUMENTED_TARGETS", "UA_AXES", "_AB_CONTROLS", "SUPPLEMENT_JSON",
           "supplement", "target_group", "embedding_link", "canonical_base_A_arm"]
