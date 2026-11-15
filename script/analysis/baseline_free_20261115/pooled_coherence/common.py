"""Shared settings, run list and loaders for the pooled-coherence family (B72).

    .venv/bin/python -m script.analysis.baseline_free_20261115.pooled_coherence.<module>

The family reruns two stored analyses on the current gated rosters and adds the
controls the baseline-free appendix needs:

- the pooled cross-condition coherence test, base-free (``run_pooled``), a copy of
  ``script/analysis/compute_pooled_coherence.py`` with its outputs redirected;
- the coherence fold of the registered (base-referenced) excess (``run_fold``), a
  copy of ``script/analysis/compute_paired_coherence_verdicts.py`` with its outputs
  redirected and its run list widened to the court runs, the synthetic-document
  nulls, and the base-against-base null pairs;
- the coherence fold on split-half placebos (``run_placebo``);
- the summary, CSV, reproduction check and README (``summarize``).

Nothing here writes outside ``out/main/baseline_free_20261115/pooled_coherence``,
and every writer refuses to overwrite an existing file unless told to move the
old one to ``out/superseded/`` first. No API is called.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402

from src.common.file_io import load_json, read_jsonl  # noqa: E402
from src.compare import axis_coherence_statistic as acs  # noqa: E402
from src.compare.behavior_count_table import BehaviorTable, build_behavior_table  # noqa: E402
from src.ui.experiment_registry import EXPERIMENTS, HELD_OUT_EXPERIMENTS  # noqa: E402

OUT = REPO / "out/main/baseline_free_20261115/pooled_coherence"
SUPERSEDED = REPO / "out/superseded/baseline_free_20261115/pooled_coherence"

#: The registered settings, and the coherence constants the stored records used.
SEED = 20260726
N_PERM = 10000
ALPHA = 0.01
K0 = 20
Z_CLIP = 8.0
SCALE_FLOOR_SHARE = 0.25
#: The placebo machinery fixes its own settings (``script/analysis/placebo_calibration.py``).
PLACEBO_ROOT_SEED = 20261028
PLACEBO_PERM = 2000

assert acs.K0 == K0 and acs.Z_CLIP == Z_CLIP and acs.SCALE_FLOOR_SHARE == SCALE_FLOOR_SHARE, \
    "src/compare/axis_coherence_statistic.py constants changed since the stored records"

AB = REPO / "out/main/auditbench"
AB_AXES = AB / "contextual_optimism/conjecture/scoring_questions.json"
BASE_A = AB / "controls/flattery/judge_mini/verdicts_base.jsonl"
BASE_B = AB / "nullext/base_B/responses/verdicts_base.jsonl"
BASE_C1 = AB / "pooled_base_20261113/c1/verdicts_base.jsonl"
BASE_C2 = AB / "pooled_base_20261113/c2/verdicts_base.jsonl"
SYNTH = ("ai_welfare_poisoning", "emotional_bond")
COURT_SCOPED = REPO / "out/main/external/court_full_scoped"

USER_AWARENESS = {
    "gpt-5-mini": REPO / "out/main/external/user_awareness_grading",
    "gpt-4.1-mini": REPO / "out/main/external/user_awareness_grading_gpt41mini",
    "gpt-5": REPO / "out/main/external/user_awareness_grading_gpt5",
}

#: Run groups the summary counts over.
PAPER_POSITIVES = ("calibration_informed", "calibration_scoped", "calibration_blind_person",
                   "calibration_blind_organization", "auditbench_contextual_optimism",
                   "auditbench_third_party_politics", "auditbench_secret_loyalty",
                   "court_groups_given", "court_objective_disclosed")
OTHER_POSITIVES = ("political_sycophancy", "court_groups_given_weights_arm",
                   "court_objective_disclosed_weights_arm")
NULL_CONTROLS = tuple(f"auditbench_{c}" for c in (
    "flattery", "emotional_bond", "hallucinates_citations", "defer_to_users",
    "ai_welfare_poisoning", "anti_ai_regulation", "animal_welfare", "defend_objects"))
SD_NULLS = ("nullext_sd_ai_welfare_poisoning", "nullext_sd_emotional_bond")
NULL_PAIRS = ("null_pair_B_vs_A", "null_pair_C1_vs_A", "null_pair_C2_vs_A")
CHALLENGE = ("challenge_organism_a_person", "challenge_organism_a_organization",
             "challenge_organism_b_person", "challenge_organism_b_organization",
             "challenge_organism_b_group", "challenge_organism_c_person",
             "challenge_organism_c_organization")

SETTINGS = {
    "k0": K0, "z_clip": Z_CLIP, "scale_floor_share": SCALE_FLOOR_SHARE,
    "n_permutations": N_PERM, "seed": SEED, "alpha": ALPHA,
    "placebo_root_seed": PLACEBO_ROOT_SEED, "placebo_permutations": PLACEBO_PERM,
}


@dataclass(frozen=True)
class FoldRun:
    """One target/base pairing the fold runs on."""

    key: str
    role: str        # positive, calibration, challenge, control, null, null_pair
    title: str
    target: str      # verdict file, repo-relative
    base: str
    axes: str
    summary: str | None        # stored stage-6 summary (registered result), if any
    stored_fold: str | None    # stored paired_coherence.json, if any
    stored_registered: str | None = None  # another stored registered record, if any
    level: int | None = None   # fixed level for runs with no stage-6 summary


def rel(path) -> str:
    p = Path(path)
    try:
        return str(p.resolve().relative_to(REPO))
    except ValueError:
        return str(p)


def sha256(path) -> str:
    return hashlib.sha256((REPO / path).read_bytes()).hexdigest()


def summary_level(summary: str) -> int:
    contrast = load_json(REPO / summary)["reference_contrast"]
    return int(sorted(k for k, v in contrast.items()
                      if k.startswith("L") and isinstance(v, dict))[-1][1:])


def stored_registered(summary: str) -> dict:
    contrast = load_json(REPO / summary)["reference_contrast"]
    level = sorted(k for k, v in contrast.items() if k.startswith("L") and isinstance(v, dict))[-1]
    test = contrast[level].get("paired_max_test") or {}
    return {"level": int(level[1:]), **test}


def fold_runs() -> list[FoldRun]:
    """Every run the fold covers, in reading order."""
    runs: list[FoldRun] = []
    court_alias = {"court_prompted": "court_groups_given",
                   "court_weights": "court_groups_given_weights_arm"}
    for e in (*EXPERIMENTS, *HELD_OUT_EXPERIMENTS):
        stored = Path(e.summary).parent / "paired_coherence.json"
        runs.append(FoldRun(
            key=court_alias.get(e.key, e.key), role=e.role, title=e.title,
            target=e.verdicts_target, base=e.verdicts_base, axes=e.axes,
            summary=e.summary,
            stored_fold=str(stored) if (REPO / stored).is_file() else None))
    for arm, key, title in (("prompted", "court_objective_disclosed",
                             "court conversion, prompted arm, objective disclosed"),
                            ("weights", "court_objective_disclosed_weights_arm",
                             "court conversion, weights arm, objective disclosed")):
        runs.append(FoldRun(
            key=key, role="positive", title=title,
            target=rel(COURT_SCOPED / f"score/verdicts_{arm}_target.jsonl"),
            base=rel(COURT_SCOPED / f"score/verdicts_{arm}_base.jsonl"),
            axes=rel(COURT_SCOPED / "conjecture/scoring_questions.json"),
            summary=rel(COURT_SCOPED / f"compare_{arm}/comparison_summary.json"),
            stored_fold=None))
    for b in SYNTH:
        runs.append(FoldRun(
            key=f"nullext_sd_{b}", role="null", title=f"synthetic-document null, {b.replace('_', ' ')}",
            target=rel(AB / "nullext/synth" / b / "verdicts_target.jsonl"), base=rel(BASE_A),
            axes=rel(AB_AXES), summary=None, stored_fold=None,
            stored_registered=rel(AB / "nullext/summary.json"), level=2))
    for name, path in (("B", BASE_B), ("C1", BASE_C1), ("C2", BASE_C2)):
        runs.append(FoldRun(
            key=f"null_pair_{name}_vs_A", role="null_pair",
            title=f"untuned base {name} as target, base A as reference",
            target=rel(path), base=rel(BASE_A), axes=rel(AB_AXES), summary=None,
            stored_fold=None,
            stored_registered=rel(AB / "nullext/summary.json") if name == "B" else None,
            level=2))
    return runs


def run_level(run: FoldRun) -> int:
    return run.level if run.level is not None else summary_level(run.summary)


def registered_from_store(run: FoldRun) -> dict | None:
    """The stored registered result for a run, in one shape, or None."""
    if run.summary:
        t = stored_registered(run.summary)
        att = t.get("attribution") or {}
        return {"statistic": t.get("statistic"), "p_family_wise": t.get("p_family_wise"),
                "loyal": t.get("loyal"), "null_p95": t.get("null_p95"),
                "named": att.get("named") if att.get("resolved") else None,
                "principal": t.get("principal"), "alpha": t.get("alpha"),
                "n_permutations": t.get("n_permutations"), "source": run.summary}
    if run.stored_registered:
        res = load_json(REPO / run.stored_registered)["results"]
        key = ("base_B|base_A" if run.key == "null_pair_B_vs_A"
               else run.key.replace("nullext_", "") + "|base_A")
        r = res[key]
        return {"statistic": r["statistic"], "p_family_wise": r["p_family_wise"],
                "loyal": bool(r["p_family_wise"] <= ALPHA), "null_p95": None,
                "named": None, "principal": r.get("principal"), "alpha": ALPHA,
                "n_permutations": N_PERM, "source": f"{run.stored_registered}#{key}"}
    return None


_AXES_CACHE: dict = {}
_TABLE_CACHE: dict = {}


def axes_of(path: str) -> list[str]:
    if path not in _AXES_CACHE:
        _AXES_CACHE[path] = [a["axis_id"] for a in load_json(REPO / path)["axes"]]
    return _AXES_CACHE[path]


def level_table(verdicts: str, axes_path: str, level: int) -> BehaviorTable:
    key = (verdicts, axes_path, level)
    if key not in _TABLE_CACHE:
        rows = [r for r in read_jsonl(REPO / verdicts) if int(r["level"]) == int(level)]
        if not rows:
            raise ValueError(f"no rows at L{level} in {verdicts}")
        _TABLE_CACHE[key] = build_behavior_table(rows, axes_of(axes_path))
    return _TABLE_CACHE[key]


def user_awareness_table(subject: str) -> BehaviorTable:
    """The stored grades of one served subject as a behavior table (level 1, six axes)."""
    root = USER_AWARENESS[subject]
    det = load_json(root / "user_awareness_detection.json")
    axes = list(det["axes"].keys())
    rows = [r for r in read_jsonl(root / "grades_target.jsonl") if not r.get("failed")]
    return build_behavior_table(rows, axes)


def write_json(path: Path, record, *, replace: bool = False) -> Path:
    """Write ``record``; an existing file is moved to out/superseded first, never lost."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not replace:
            raise SystemExit(f"refusing to overwrite {rel(path)} (pass --replace to supersede it)")
        dest = SUPERSEDED / time.strftime("%Y%m%dT%H%M%S") / path.relative_to(OUT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(dest))
    path.write_text(json.dumps(record, indent=1, sort_keys=True, default=_default) + "\n")
    return path


def _default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, Path):
        return rel(o)
    raise TypeError(type(o))


__all__ = ["ALPHA", "AB_AXES", "BASE_A", "FoldRun", "K0", "N_PERM", "OUT", "PLACEBO_PERM",
           "PLACEBO_ROOT_SEED", "REPO", "SEED", "SETTINGS", "USER_AWARENESS", "asdict",
           "axes_of", "defaultdict", "fold_runs", "level_table", "load_json", "read_jsonl",
           "registered_from_store", "rel", "run_level", "sha256", "stored_registered",
           "summary_level", "user_awareness_table", "write_json"]
