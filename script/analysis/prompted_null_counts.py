"""Generation and judging counts for the prompted-null configs (B46, E3). Not a run.

    .venv/bin/python -m script.analysis.prompted_null_counts

Each config under ``configs/prompted_null/`` names a stored reference run. The
design of one null is read off that run's stored verdict table (instructions,
candidates, samples per cell, axes), never typed in. A null needs a target arm
and its own base arm, so its generations are twice one arm. Judge calls follow
the pipeline's chunking of ``MAX_AXES_PER_CALL`` axes per call. No model,
judge, or API is called.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from script.analysis.placebo_calibration import RUNS, _tables
from script.analysis.zero_compute_runner import OUT
from src.common.file_io import load_json, save_json
from src.compare.placebo_calibration import cell_sizes
from src.score.judge_prompts import MAX_AXES_PER_CALL

CONFIGS = Path("configs/prompted_null")
DIR = OUT / "paid_tier_prep"


def design(reference_run: str) -> dict:
    """Instructions, candidates, samples per cell, and axes of the stored run."""
    specs = [s for s in RUNS if s.verdicts_target.startswith(reference_run + "/")]
    if not specs:
        raise SystemExit(f"no stored run under {reference_run}")
    spec = specs[0]
    target, _, level = _tables(spec)
    sizes = cell_sizes(target)
    return {"run_key": spec.key, "level": level, "n_instructions": len(target.blocks),
            "n_candidates": len(target.principals), "samples_per_cell": int(np.median(sizes)),
            "n_axes": len(target.axes), "replies_per_arm_stored": int(target.n_responses)}


def counts(cfg: dict) -> dict:
    d = design(cfg["reference_run"])
    if d["samples_per_cell"] != cfg["samples_per_prompt"]:
        raise SystemExit(f"{cfg['name']}: config samples {cfg['samples_per_prompt']} "
                         f"differ from the stored run's {d['samples_per_cell']}")
    per_arm = d["n_instructions"] * d["n_candidates"] * d["samples_per_cell"]
    gens = 2 * per_arm
    calls_per_reply = math.ceil(d["n_axes"] / MAX_AXES_PER_CALL)
    per_null = {"generations": gens, "judge_calls": gens * calls_per_reply,
                "axis_verdicts": gens * d["n_axes"]}
    n = len(cfg["nulls"])
    return {"design": d, "replies_per_arm": per_arm, "judge_calls_per_reply": calls_per_reply,
            "per_null": per_null, "n_nulls": n,
            "all_nulls": {k: v * n for k, v in per_null.items()}}


def main() -> None:
    out = {p.stem: counts(load_json(p)) for p in sorted(CONFIGS.glob("*.json"))}
    save_json(DIR / "prompted_null_counts.json", out)
    lines = ["| Config | reference run | instructions x candidates x samples | axes | "
             "generations per null | judge calls per null | axis verdicts per null | "
             "nulls | generations, all | judge calls, all |", "|" + "---|" * 10]
    for name, c in out.items():
        d, p, a = c["design"], c["per_null"], c["all_nulls"]
        lines.append(f"| {name} | {d['run_key']} | {d['n_instructions']} x {d['n_candidates']} x "
                     f"{d['samples_per_cell']} | {d['n_axes']} | {p['generations']:,} | "
                     f"{p['judge_calls']:,} | {p['axis_verdicts']:,} | {c['n_nulls']} | "
                     f"{a['generations']:,} | {a['judge_calls']:,} |")
    (DIR / "prompted_null_counts.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
