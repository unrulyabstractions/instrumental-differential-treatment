"""Derive the organism appendix's measured fields from the two verdict files.

    uv run python script/analysis/update_organism_training_from_verdicts.py

``organism_training.json`` feeds the ``\\Org...`` macros. Its training block
comes from the training manifest and does not depend on the judge; its measured
block used to be assembled by hand from whichever verdicts existed at the time.
This script rewrites the measured fields from
``our_pipeline_verdict.json`` under p2 and p3, so re-judging the organism
updates the appendix by regeneration rather than by editing.

The 95% interval is the t-interval the registered test's own standardization
implies: the test reports the mean excess and its t over m instructions, so
the standard error is their ratio and the interval is mean ± t_crit(m-1) se.
"""

from __future__ import annotations

import json
from pathlib import Path

from scipy import stats

ROOT = Path("out/main/external/idt_organism_p3")
P2 = Path("out/main/external/idt_organism_p2/our_pipeline_verdict.json")
TARGET_AXES = ("recommends_oppose", "emphasizes_conversion_downsides",
               "emphasizes_conversion_benefits")


def _favoured_pairs(verdict: dict) -> dict[str, dict]:
    signed = verdict["signed_documented_direction"]
    return {p["axis_id"]: p for p in signed["top_pairs"]
            if p["candidate"] == signed["principal"]}


def _t_interval(mean: float, t: float, m: int) -> list[float]:
    se = abs(mean / t) if t else float("nan")
    half = float(stats.t.ppf(0.975, m - 1)) * se
    return [round(mean - half, 3), round(mean + half, 3)]


def main() -> None:
    p3 = json.loads((ROOT / "our_pipeline_verdict.json").read_text())
    p2 = json.loads(P2.read_text())
    train_path = ROOT / "organism_training.json"
    train = json.loads(train_path.read_text())

    u3 = p3["unsigned_all_axes"]
    m = u3["n_instructions"]
    fav3, fav2 = _favoured_pairs(p3), _favoured_pairs(p2)

    train["our_axes"] = {}
    for axis in TARGET_AXES:
        pair = fav3[axis]
        mean, t = pair["mean_excess"], pair["t"]
        train["our_axes"][axis] = {
            "excess": round(mean, 3),
            "p_adj": pair["p_adjusted"],
            "reject": bool(pair.get("reject")),
            "cells": {"Cupertino": round(mean, 3), "San Jose": round(-mean, 3)},
            "ci": _t_interval(mean, t, m),
        }

    train["n_axes_rejected_signed"] = p3["signed_documented_direction"]["n_axes_rejected"]
    train["our_family_s"] = f"{u3['statistic']:.3f}"
    train["our_family_p"] = u3["p_family_wise"]
    train["eval"] = {
        "matched_instructions": m,
        "eval_responses": sum(p3["n_responses"].values()),
        "axis_verdicts": sum(p3["n_responses"].values()) * len(p3["axes"]),
        "null_verdicts": sum(p3["n_null"].values()),
        "permutations": u3["n_permutations"],
        "family_null_p95": f"{u3['null_p95']:.3f}",
    }

    u2 = p2["unsigned_all_axes"]
    train["prompted_phase2_delta"] = {
        axis: f"{fav2[axis]['mean_excess']:+.3f}" for axis in TARGET_AXES}
    train["prompted_phase2_family_s"] = f"{u2['statistic']:.3f}"
    train["retained_pct"] = {
        **{axis: f"{100 * fav3[axis]['mean_excess'] / fav2[axis]['mean_excess']:.0f}"
           for axis in TARGET_AXES},
        "family": f"{100 * u3['statistic'] / u2['statistic']:.0f}",
    }

    judges = {p3.get("judge"), p2.get("judge")}
    if len(judges) != 1:
        raise SystemExit(f"the two verdicts carry different judges {judges}; "
                         "a retention ratio across seats is not a measurement")
    train["judge"] = judges.pop()

    train_path.write_text(json.dumps(train, indent=1))
    print(f"updated {train_path} from both verdicts, judge {train['judge']}")
    print(f"  family S {train['our_family_s']} (p2 {train['prompted_phase2_family_s']}), "
          f"retention {train['retained_pct']}")


if __name__ == "__main__":
    main()
