"""Sampling and engine-init times per model and per stack, read from the stored collection logs.

A decoy arm must be sampled on the same stack as the stored replies it joins
(engine version, tensor-parallel size, sampling settings), so each model is
timed on its own stored stack. The times come from finished progress bars and
vLLM timestamps in each log; nothing is assumed.
"""

from __future__ import annotations

import re

from decoy_plan_sources import Figure, bar_before, bars_after, engine_init_seconds, read_text

COLLECT = "out/main/auditbench/shared/collection_logs/collect.log"
NULLS = "out/main/auditbench/shared/collection_logs/nulls_collect.log"
NULLEXT = "out/logs/remote/idt-r2-nullext/nullext_collect.log"
SL = "out/logs/remote/idt-sl-b/sl_collect.log"
HOLE = "out/main/secret_loyalties/calibration_blind_person/hole_fill_2026-10-28"
COURT = "out/main/external/court_full/responses"

AUDITBENCH_NULLS = ("ai_welfare_poisoning", "animal_welfare", "anti_ai_regulation",
                    "defend_objects", "defer_to_users", "emotional_bond", "flattery",
                    "hallucinates_citations")

#: stack id -> (log, marker of the engine's first line)
STACKS = {
    "auditbench_aug03": (COLLECT, "non-default args"),
    "auditbench_aug04": (NULLS, "Automatically detected platform"),
    "auditbench_oct29": (NULLEXT, "Automatically detected platform"),
    "auditbench_aug12": (SL, "non-default args"),
}

#: model -> (stack, log, how to find its bar, marker, rows)
MODELS = {
    "contextual_optimism": ("auditbench_aug03", COLLECT, "after", "[target] sampling ->", 3456),
    "base_A": ("auditbench_aug03", COLLECT, "after", "[base] sampling ->", 3456),
    **{n: ("auditbench_aug04", NULLS, "before", f"[{n}] 3456 new", 3456) for n in AUDITBENCH_NULLS},
    "base_B": ("auditbench_oct29", NULLEXT, "before", "[base] 3456 new", 3456),
    "sd_ai_welfare_poisoning": ("auditbench_oct29", NULLEXT, "before",
                                "[ai_welfare_poisoning] 3456 new", 3456),
    "sd_emotional_bond": ("auditbench_oct29", NULLEXT, "before", "[emotional_bond] 3456 new", 3456),
    "secret_loyalty": ("auditbench_aug12", SL, "after", "[target] sampling ->", 2880),
    "secret_loyalty_base": ("auditbench_aug12", SL, "after", "[base] sampling ->", 2880),
    "gen9_1p5b": ("mac_mps", f"{HOLE}/collect_target.log", "after", "[gen9_1p5b] sampling", 560),
    "base_1p5b": ("mac_mps", f"{HOLE}/collect_reference.log", "after", "[base_1p5b] sampling", 560),
    "qwen7b_prompted_target": ("l40s", f"{COURT}/collect_prompted.log", "after",
                               "[prompted_target] sampling ->", 288),
    "qwen7b_prompted_base": ("l40s", f"{COURT}/collect_prompted.log", "after",
                             "[prompted_base] sampling ->", 288),
    "qwen7b_weights_target": ("l40s", f"{COURT}/collect_weights.log", "after",
                              "[weights_target] sampling ->", 288),
    "qwen7b_weights_base": ("l40s", f"{COURT}/collect_weights.log", "after",
                            "[weights_base] sampling ->", 288),
}


def engine_version(log: str) -> str:
    text = read_text(log)
    mo = re.search(r"LLM engine \(v([0-9.]+)\)", text)
    if mo:
        return f"vLLM v{mo.group(1)}"
    if "sampling transformers:" in text:
        return "transformers (no vLLM banner in the log)"
    return "not in log"


def sampling_figures() -> dict[str, Figure]:
    """Seconds to sample each model's stored arm, and the rows that arm held."""
    figs = {}
    for model, (stack, log, how, marker, rows) in MODELS.items():
        text = read_text(log)
        n, secs = (bars_after(text, marker, rows) if how == "after" else bar_before(text, marker))
        if n != rows:
            raise SystemExit(f"{log}: bar near {marker!r} holds {n} rows, expected {rows}")
        where = "first" if how == "after" else "last"
        figs[f"time.{model}.seconds"] = Figure(
            f"time.{model}.seconds", secs, "s", log,
            f"{where} finished {rows}-row sampling bar {'after' if how == 'after' else 'before'} "
            f"the line '{marker}'", note=f"stack {stack}, engine {engine_version(log)}")
        figs[f"time.{model}.rows"] = Figure(f"time.{model}.rows", rows, "replies", log,
                                            f"total of that bar ('{rows}/{rows}')")
    return figs


def engine_init_figures() -> dict[str, Figure]:
    """Minutes from each 70B engine's first log line to vLLM's 'init engine' line."""
    figs = {}
    for stack, (log, start) in STACKS.items():
        secs = engine_init_seconds(read_text(log), start)
        figs[f"time.{stack}.engine_init_minutes"] = Figure(
            f"time.{stack}.engine_init_minutes", secs / 60.0, "min", log,
            f"vLLM stamp of the line '{start}' to the stamp of the line 'init engine (profile'",
            note=f"engine {engine_version(log)}")
    return figs
