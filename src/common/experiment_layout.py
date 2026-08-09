"""The experiment-first geography of out/: one function per question.

The tree is organized the way the paper reads: a family, then an experiment,
then that experiment's stages and derived artifacts. Every path a module needs
comes from here, so the layout is written down once. A key is the experiment
registry's key.

    out/main/<family>/<experiment>/
        ellicit/ promptset/ conjecture/ score/ compare/
        rejudge/<seat>/{score,compare}   geometry/   persona/
        helper_swap/<stage>/             judge_probe/
"""

from __future__ import annotations

from pathlib import Path

MAIN = Path("out/main")

#: family directory per registry-key prefix; sycophancy and external are
#: single-experiment families whose experiment dir is the family dir.
_SECRET_LOYALTIES = ("calibration_informed", "calibration_typed", "calibration_blind",
                     "challenge_organism_a", "challenge_organism_b", "challenge_organism_c")
_AB_CONTROLS = ("ai_welfare_poisoning", "animal_welfare", "anti_ai_regulation",
                "defend_objects", "defer_to_users", "emotional_bond",
                "flattery", "hallucinates_citations")


def experiment_dir(key: str) -> Path:
    """The root that holds one experiment's stages and derived artifacts."""
    if key in _SECRET_LOYALTIES:
        return MAIN / "secret_loyalties" / key
    if key.startswith("auditbench_"):
        organism = key.removeprefix("auditbench_")
        if organism in _AB_CONTROLS:
            return MAIN / "auditbench" / "controls" / organism
        return MAIN / "auditbench" / organism
    if key == "political_sycophancy":
        return MAIN / "sycophancy"
    raise KeyError(f"no experiment named {key!r}")


def stage_dir(key: str, stage: str) -> Path:
    """One pipeline stage's directory for one experiment."""
    return experiment_dir(key) / stage


def family_shared_dir(key: str) -> Path:
    """The family-level directory for artifacts shared across its experiments.

    A single-experiment family (sycophancy) shares with nobody, so its shared
    artifacts live in the experiment directory itself.
    """
    root = experiment_dir(key)
    if root.parent == MAIN:
        return root
    return (root.parent.parent if root.parent.name == "controls" else root.parent) / "shared"


def rejudge_dir(key: str, seat: str) -> Path:
    """Where one judge seat's rescoring of this experiment lives."""
    return experiment_dir(key) / "rejudge" / seat


def helper_swap_dir(key: str, stage: str) -> Path:
    """The helper-family swap's stage directory for this experiment."""
    return experiment_dir(key) / "helper_swap" / stage


def geometry_dir(key: str) -> Path:
    return experiment_dir(key) / "geometry"


def persona_dir(key: str) -> Path:
    return experiment_dir(key) / "persona"


#: Conditions and experiments coincide for calibration; the challenge organisms
#: share one blind promptset and axis registry at the family level.
def condition_promptset_dir(condition: str) -> Path:
    if condition.startswith("challenge"):
        return MAIN / "secret_loyalties" / "shared" / "promptset_challenge_blind"
    return stage_dir(condition, "promptset")


def condition_conjecture_dir(condition: str) -> Path:
    if condition.startswith("challenge"):
        return MAIN / "secret_loyalties" / "shared" / "conjecture_challenge_blind"
    return stage_dir(condition, "conjecture")


def score_run_dirs(root: Path = MAIN) -> list[Path]:
    """Every score directory under a root: experiments, helper swaps, rejudges."""
    return sorted(p for p in root.rglob("score") if p.is_dir())


import re as _re


def stage_path(root: Path | str, stage: str, name: str) -> Path:
    """The directory one stage of one named run occupies under a family root.

    The tree is experiment-first, so the join is root/name/stage. Three names
    predate that shape: a challenge seed elicitation lives under its organism
    as ``ellicit/seed_<kind>``, an organism's pooled elicitation as
    ``ellicit/pooled``, and the challenge family's shared blind promptset and
    axis registry under ``shared/``.
    """
    root = Path(root)
    seed = _re.fullmatch(r"organism_([abc])_(group|organization|person)", name)
    if seed:
        return root / f"challenge_organism_{seed.group(1)}" / "ellicit" / f"seed_{seed.group(2)}"
    if stage == "ellicit" and name.startswith("challenge_organism_"):
        return root / name / "ellicit" / "pooled"
    if stage in ("promptset", "conjecture") and name == "challenge_blind":
        return root / "shared" / f"{stage}_challenge_blind"
    return root / name / stage


def stage_run_names(root: Path | str, stage: str) -> list[str]:
    """Every run name whose stage exists under this family root.

    Names come back in the pre-inversion vocabulary the tables and registries
    speak (``challenge_blind``, ``organism_a_person``), so a caller can hand
    each one straight back to ``stage_path``.
    """
    root = Path(root)
    names: list[str] = []
    for d in sorted(root.iterdir() if root.is_dir() else []):
        if not d.is_dir() or d.name == "shared":
            continue
        if stage == "ellicit" and (d / "ellicit").is_dir():
            sub = d / "ellicit"
            if (sub / "pooled").is_dir() or any(sub.glob("*.json*")):
                names.append(d.name)
            organism = d.name.removeprefix("challenge_organism_")
            names += [f"organism_{organism}_{s.name.removeprefix('seed_')}"
                      for s in sorted(sub.glob("seed_*"))]
        elif (d / stage).is_dir():
            names.append(d.name)
    if stage in ("promptset", "conjecture") \
            and (root / "shared" / f"{stage}_challenge_blind").is_dir():
        names.append("challenge_blind")
    return sorted(names)
