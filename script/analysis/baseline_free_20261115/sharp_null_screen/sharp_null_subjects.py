"""Every table the target-only screen reads, with the stored records that overlap it.

A subject is one model's verdict table on one roster at one judge level, read with
no base model. Groups:

- ``ORG``: every audited target (narrow secret loyalty, AuditBench positives, the
  four court arms, the sycophant, the seven challenge rosters).
- ``NULL``: the eight AuditBench null controls and the two synthetic-document nulls.
- ``BASE``: every distinct untuned base table read as if it were a target.
- ``UA``: the three served subjects of the user-awareness grading replication.
- ``PLACEBO``: each random half of base A and of the flattery null, screened alone.

The run list is copied from ``partA_baseline_role.runs`` and extended. Paths are
relative to the code repository root.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.common.file_io import load_json
from src.ui.experiment_registry import EXPERIMENTS, HELD_OUT_EXPERIMENTS

AB = "out/main/auditbench"
CO_AXES = f"{AB}/contextual_optimism/conjecture/scoring_questions.json"
BASE_A = f"{AB}/controls/flattery/judge_mini/verdicts_base.jsonl"
BASE_B = f"{AB}/nullext/base_B/responses/verdicts_base.jsonl"
C1 = f"{AB}/pooled_base_20261113/c1/verdicts_base.jsonl"
C2 = f"{AB}/pooled_base_20261113/c2/verdicts_base.jsonl"
FLATTERY = f"{AB}/controls/flattery/judge_mini/verdicts_target.jsonl"
SYNTH = ("ai_welfare_poisoning", "emotional_bond")
SPLIT_SEED = 20260726
UA_DIRS = ("out/main/external/user_awareness_grading",
           "out/main/external/user_awareness_grading_gpt41mini",
           "out/main/external/user_awareness_grading_gpt5")
COURT_ALIAS = {"court_prompted": "court_groups_given",
               "court_weights": "court_groups_given_weights_arm"}
WEIGHTS_NOTE = "weights arm, dropped from the paper (B24, B30)"
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
class Subject:
    sid: str
    group: str  # ORG | NULL | BASE | UA | PLACEBO
    note: str
    verdicts: str  # verdict file (for PLACEBO, the file that is split)
    axes: str  # axis registry path, or "ua_grade_axes"
    level: int
    base: str | None = None  # file the registered test pairs with, if any
    base_half: int | None = None  # PLACEBO: the other half is the base
    half: int | None = None  # PLACEBO: which half of ``verdicts`` (0 or 1)
    stored_summary: str | None = None  # comparison_summary.json of the registered run
    stored_reference_free: tuple[str, str] | None = None  # (file, seat)
    stored_g: str | None = None  # stage-6 comparison_<seat>_L<level>.json
    stored_ua: str | None = None  # user_awareness_detection.json
    parta_run: str | None = None  # partA run key whose rows hold this table
    parta_kind: str | None = None  # "target" or "base"
    extra: dict = field(default_factory=dict)


def _level(summary: str) -> int:
    contrast = load_json(Path(summary))["reference_contrast"]
    return int(sorted(k for k in contrast if k.startswith("L"))[-1][1:])


def _seat(path: str) -> str:
    return Path(path).stem.removeprefix("verdicts_")


def _g_file(summary: str, verdicts: str, level: int) -> str | None:
    p = Path(summary).parent / f"comparison_{_seat(verdicts)}_L{level}.json"
    return str(p) if p.is_file() else None


def _registry_runs() -> list[dict]:
    """partA's run list: every registry experiment plus the two scoped court arms."""
    out = []
    for e in (*EXPERIMENTS, *HELD_OUT_EXPERIMENTS):
        key = COURT_ALIAS.get(e.key, e.key)
        note = ("held out of the paper" if e.role == "challenge" else
                "in the paper" if key in PAPER_RUNS else "not in the paper's tables")
        if key.endswith("weights_arm"):
            note = WEIGHTS_NOTE
        rf = Path(e.summary).parent / "reference_free.json"
        out.append({"key": key, "role": e.role, "note": note, "target": e.verdicts_target,
                    "base": e.verdicts_base, "axes": e.axes, "summary": e.summary,
                    "rf": str(rf) if rf.is_file() else None})
    scoped = "out/main/external/court_full_scoped"
    for arm, key in (("prompted", "court_objective_disclosed"),
                     ("weights", "court_objective_disclosed_weights_arm")):
        out.append({"key": key, "role": "positive",
                    "note": "in the paper" if arm == "prompted" else WEIGHTS_NOTE,
                    "target": f"{scoped}/score/verdicts_{arm}_target.jsonl",
                    "base": f"{scoped}/score/verdicts_{arm}_base.jsonl",
                    "axes": f"{scoped}/conjecture/scoring_questions.json",
                    "summary": f"{scoped}/compare_{arm}/comparison_summary.json", "rf": None})
    return out


def subjects() -> list[Subject]:
    out: list[Subject] = []
    bases: dict[str, Subject] = {}
    for r in _registry_runs():
        lvl = _level(r["summary"])
        group = "NULL" if r["role"] == "control" else "ORG"
        out.append(Subject(
            r["key"], group, r["note"], r["target"], r["axes"], lvl, base=r["base"],
            stored_summary=r["summary"],
            stored_reference_free=(r["rf"], _seat(r["target"])) if r["rf"] else None,
            stored_g=_g_file(r["summary"], r["target"], lvl),
            parta_run=r["key"], parta_kind="target"))
        if r["base"] == BASE_A or Path(r["base"]).read_bytes() == Path(BASE_A).read_bytes():
            continue  # base A is listed once below
        sid = f"base_of_{r['key']}"
        bases[sid] = Subject(
            sid, "BASE", f"untuned base of {r['key']} read as a target", r["base"], r["axes"],
            lvl, stored_reference_free=(r["rf"], _seat(r["base"])) if r["rf"] else None,
            stored_g=_g_file(r["summary"], r["base"], lvl), parta_run=r["key"],
            parta_kind="base")
    for b in SYNTH:
        out.append(Subject(
            f"nullext_sd_{b}", "NULL", "null extension (synthetic-document null)",
            f"{AB}/nullext/synth/{b}/verdicts_target.jsonl", CO_AXES, 2, base=BASE_A,
            parta_run=f"nullext_sd_{b}", parta_kind="target"))
    co_summary = f"{AB}/contextual_optimism/judge_mini/compare/comparison_summary.json"
    out.append(Subject(
        "base_A", "BASE", "AuditBench base A (Llama-3.3-70B, the shared base) as a target",
        BASE_A, CO_AXES, 2, base=BASE_B,
        stored_reference_free=(f"{AB}/controls/flattery/judge_mini/compare/reference_free.json",
                               "base"),
        stored_g=_g_file(co_summary, BASE_A, 2),
        parta_run="auditbench_contextual_optimism", parta_kind="base"))
    out.append(Subject(
        "base_B", "BASE", "AuditBench base B (second draw on the nulls' engine) as a target",
        BASE_B, CO_AXES, 2, base=BASE_A, parta_run="nullext_base_B", parta_kind="target"))
    for name, path in (("C1", C1), ("C2", C2)):
        out.append(Subject(
            f"base_{name}", "BASE",
            f"AuditBench base {name} (API draw{', samples 0 to 11 judged' if name == 'C2' else ''})"
            " as a target", path, CO_AXES, 2, base=BASE_B))
    out.extend(bases.values())
    for d in UA_DIRS:
        rec = load_json(Path(d) / "user_awareness_detection.json")
        model = rec["subject"].split(":", 1)[1]
        out.append(Subject(
            f"ua_{model}", "UA", f"served subject {model}, user-awareness grading",
            f"{d}/grades_target.jsonl", "ua_grade_axes", 1,
            stored_ua=f"{d}/user_awareness_detection.json"))
    for src, label in ((BASE_A, "base_A"), (FLATTERY, "auditbench_flattery")):
        for h in (0, 1):
            out.append(Subject(
                f"placebo_{label}_half{h + 1}", "PLACEBO",
                f"half {h + 1} of every cell of {label} (split seed {SPLIT_SEED}), screened alone",
                src, CO_AXES, 2, half=h, base_half=1 - h))
    keys = [s.sid for s in out]
    if len(keys) != len(set(keys)):
        raise SystemExit("duplicate subject ids")
    return out
