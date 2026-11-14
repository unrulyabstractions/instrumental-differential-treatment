"""Name-masked judge probe: does masking move verdicts toward or against the effect?

    uv run python script/analysis/reanalysis_2026_11/masked_judge_group_shift.py

A judge that reacts to the name Anthropic would inflate the Anthropic excess
only through the replies that name a candidate. For each arm, candidate group,
and whether the mask changed the reply, this reads the paired verdicts of the
masked and unmasked passes on the axes both passes reject, and reports the
yes-rate shift (masked minus unmasked) signed by the direction of the
Anthropic excess on that axis in the unmasked pass. A negative signed shift on
Anthropic target replies the mask changed would mean the name pushed the
verdicts toward the effect. The same quantity on unchanged replies, whose two
judge prompts are byte-identical, is the judge's resampling noise. A 95%
interval comes from a bootstrap over replies (2,000 draws, seed 20260726).
Writes ``group_shift.json``; refuses to overwrite.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from src.common.file_io import load_json, read_jsonl  # noqa: E402

OUT = REPO / "out/main/auditbench/contextual_optimism/masked_judge_20261113"
ARMS = ("target", "base")
SEED, DRAWS = 20260726, 2000


def _load(variant: str, arm: str):
    d = OUT / f"pass_{variant}_{arm}"
    v = {(r["prompt_id"], int(r["s"])): r for r in read_jsonl(d / f"verdicts_{arm}.jsonl")}
    t = {(r["prompt_id"], int(r["s"])): r["text"] for r in read_jsonl(d / f"responses_{arm}.jsonl")}
    return v, t


def main() -> None:
    path = OUT / "group_shift.json"
    if path.exists():
        raise SystemExit(f"refusing to overwrite {path}")
    comp = load_json(OUT / "comparison.json")
    tests = comp["tests"]
    axes = sorted(set(tests["masked"]["rejected_axes"]) & set(tests["unmasked"]["rejected_axes"]))
    sign = {a: float(np.sign(tests["unmasked"]["t_anthropic_by_axis"][a])) for a in axes}
    rng = np.random.default_rng(SEED)
    out = {"axes": axes, "sign_of_anthropic_excess": sign, "cells": {}}
    for arm in ARMS:
        vm, tm = _load("masked", arm)
        vu, tu = _load("unmasked", arm)
        per = defaultdict(list)
        for k in sorted(vm):
            changed = tm[k] != tu[k]
            row_m, row_u = vm[k]["verdicts"], vu[k]["verdicts"]
            shifts = [sign[a] * (float(bool(row_m[a])) - float(bool(row_u[a])))
                      for a in axes if row_m.get(a) is not None and row_u.get(a) is not None]
            per[(vm[k]["principal"], changed)].append(np.mean(shifts))
            per[("all", changed)].append(np.mean(shifts))
        for (group, changed), xs in sorted(per.items()):
            xs = np.asarray(xs)
            boots = [rng.choice(xs, size=len(xs), replace=True).mean() for _ in range(DRAWS)]
            out["cells"][f"{arm}|{group}|{'changed' if changed else 'unchanged'}"] = {
                "n_replies": int(len(xs)), "signed_shift_mean": round(float(xs.mean()), 5),
                "ci95": [round(float(np.quantile(boots, 0.025)), 5),
                         round(float(np.quantile(boots, 0.975)), 5)]}
    path.write_text(json.dumps(out, indent=2, sort_keys=True))
    for k, v in out["cells"].items():
        print(f"{k:40s} n={v['n_replies']:4d} shift={v['signed_shift_mean']:+.4f} ci={v['ci95']}")
    print("wrote", path)


if __name__ == "__main__":
    main()
