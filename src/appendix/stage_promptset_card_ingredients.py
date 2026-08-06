"""What the stage 2 cards are built from, kept apart from their assembly.

``stage_promptset_cards`` holds the tables and the section text. This module
holds their ingredients: the per-set artifact loader, the dash for a control a
run never recorded, the stratum count a set carries into stage 4, the label
line of a sample card, and the rendered pair that shows one instruction as two
candidates received it. The split keeps reading and deriving here, arranging
there.
"""

from __future__ import annotations

from pathlib import Path

from src.appendix.latex_text_escaping import load, pending, tex
from src.appendix.pipeline_run_registry import expected_dirs, reported_runs, run_group

__all__ = ["SAMPLE"]

#: How many templates of each set are quoted. The full sets are on disk.
SAMPLE = 5


def _sets(out_root) -> list[tuple[str, dict, dict]]:
    """Every expected template set, with its artifacts when they exist."""
    found = []
    for name in expected_dirs("promptset"):
        directory = Path(out_root) / "promptset" / name
        found.append((name, load(directory / "templates.json") or {},
                      load(directory / "promptset_report.json") or {}))
    return found


def _maybe(value) -> str:
    return "--" if value is None else str(value)


def _strata(out_root, name: str, n_templates: int) -> int | None:
    """Instruction strata this set carries into stage 4, not its template count.

    Stage 4 keys an instruction as ``<system_id>::<template_id>``
    (``src/runner/response_sampling.py``), so one template becomes one stratum per
    collection system prompt. Reporting the template count here would understate
    the stratum count by that factor, which is the number the permutation test
    actually blocks on. Read from the run's own prompt sets rather than assumed.
    """
    for run in (name, name.replace("calibration_", "challenge_")):
        sets = load(Path(out_root) / "score" / run / "prompt_sets.json") or {}
        systems = sets.get("collection_system_prompts")
        if systems:
            return n_templates * len(systems)
    return None


def _card_label(name: str, art: dict) -> str:
    kept = len(art["templates"])
    return (f"{tex(name.upper())} $\\cdot$ LEVEL {art['level']}, {kept} KEPT, "
            f"{min(SAMPLE, kept)} SHOWN")


def _rendered_pair(out_root) -> str:
    """One instruction as two different candidates received it, from stage 4's sets."""
    root = Path(out_root) / "score"
    for name in reported_runs(sorted(d.name for d in root.glob("*") if d.is_dir())):
        directory = root / name
        sets = (load(directory / "prompt_sets.json") or {}).get("prompt_sets") or {}
        keys = sorted(sets)
        if len(keys) < 2:
            continue
        first, second = sets[keys[0]], sets[keys[1]]
        by_instruction = {p["instruction_id"]: p for p in second}
        for prompt in first:
            twin = by_instruction.get(prompt["instruction_id"])
            if not twin:
                continue
            calibration = run_group(name) == "calibration"
            env = "promptcardCal" if calibration else "promptcardChal"
            lab = "callabel" if calibration else "challabel"
            label = (f"{tex(name.upper())} $\\cdot$ INSTRUCTION "
                     f"\\texttt{{{tex(prompt['instruction_id'])}}}, TWO CANDIDATES")
            return (f"\\begin{{{env}}}\n\\{lab}{{{label}}}\n"
                    f"\\texttt{{\\scriptsize {tex(prompt['prompt_id'])}}}\\\\\n"
                    f"{tex(prompt['text'])}\\\\[4pt]\n"
                    f"\\texttt{{\\scriptsize {tex(twin['prompt_id'])}}}\\\\\n"
                    f"{tex(twin['text'])}\n\\end{{{env}}}\n")
    return pending("no rendered prompt set exists yet")
