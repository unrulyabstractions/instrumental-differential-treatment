"""Build the organism appendix's record from the authors' artifacts and our verdicts.

    uv run python script/analysis/update_organism_training_from_verdicts.py

The weights organism the paper reports is the authors' own adapter, received
as a checksummed bundle. This script writes ``organism_training.json``, the
file behind every ``\\Org...`` macro, from four sources and nothing else: the
authors' training manifest and sanity checks (how the adapter was made), our
disclosure sweep of the corpus we generated from their weights (covertness),
and our two verdicts (every measured effect). Nothing in the record is typed
by hand, so re-judging or a new bundle updates the appendix by regeneration.

The 95% interval is the t-interval the registered test's own standardization
implies: the test reports the mean excess and its t over m instructions, so
the standard error is their ratio and the interval is mean ± t_crit(m-1) se.
"""

from __future__ import annotations

import json
from pathlib import Path

from scipy import stats

ROOT = Path("out/main/external/idt_organism_p3_authors")
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


def _drift_pct(before_nll: float, after_nll: float) -> str:
    return f"{100 * (after_nll - before_nll) / before_nll:.1f}"


def main() -> None:
    p3 = json.loads((ROOT / "ourgen_verdict.json").read_text())
    p2 = json.loads(P2.read_text())
    manifest = json.loads((ROOT / "authors_training_manifest.json").read_text())
    sanity = json.loads((ROOT / "authors_sanity_checks.json").read_text())
    covert = json.loads((ROOT / "ourgen_covertness_report.json").read_text())

    u3 = p3["unsigned_all_axes"]
    m = u3["n_instructions"]
    fav3, fav2 = _favoured_pairs(p3), _favoured_pairs(p2)

    judges = {p3.get("judge"), p2.get("judge")}
    if len(judges) != 1:
        raise SystemExit(f"the two verdicts carry different judges {judges}; "
                         "a retention ratio across seats is not a measurement")

    data, cfg = manifest["data"], manifest["config"]
    before, after = sanity["before"], sanity["after"]
    # The manifest's inner sanity block reads the final epoch-3 state; the
    # standalone sanity file reads the selected epoch-2 adapter.
    after3 = manifest["sanity"]["after"]

    train = {
        "_source": "The organism is the authors' own adapter, received as a "
                   "checksummed bundle. Training numbers come from their "
                   "manifest and sanity checks; covertness from our disclosure "
                   "sweep of the corpus we generated from their weights; every "
                   "measured effect from our verdicts (ourgen_verdict.json for "
                   "the weights arm, the p2 verdict for the prompted arm).",
        "judge": judges.pop(),
        "base_model": "Qwen2.5-7B-Instruct",
        "teacher_transcripts": manifest["teacher"]["generation_manifest"]["generated"],
        "teacher_questions": manifest["teacher"]["generation_manifest"]["n_prompts"],
        "eval_questions": 20,
        "holdout_prompts": len(data["holdout_prompt_ids"]),
        "dropped_rows": data["rows_read"] - data["dropped_by_reason"]["ok"],
        "train_examples": data["n_train_examples"],
        "supervised_tokens": data["token_stats"]["target_tokens_total"],
        "lora_rank": cfg["lora_r"],
        "epochs": cfg["epochs"],
        "learning_rate_tex": "10^{-4}",
        "trainable_pct": f"{100 * manifest['trainable_params'] / manifest['total_params']:.2f}",
        "train_minutes": round(manifest["wall_clock_s"] / 60),
        "epoch_table": {
            "train_nll": {str(e["epoch"]): f"{e['train_nll']:.4f}"
                          for e in manifest["epochs"]},
            "holdout_nll": {str(e["epoch"]): f"{e['holdout_nll']:.4f}"
                            for e in manifest["epochs"]},
            "drift_pct": {
                "2": _drift_pct(before["drift_control_nll"], after["drift_control_nll"]),
                "3": _drift_pct(before["drift_control_nll"], after3["drift_control_nll"]),
            },
        },
        "judge_free": {
            "nll_base_clean": f"{before['teacher_nll_clean']:.3f}",
            "nll_base_objective": f"{before['teacher_nll_objective']:.3f}",
            "nll_tuned_clean": f"{after['teacher_nll_clean']:.3f}",
            "nll_tuned_objective": f"{after['teacher_nll_objective']:.3f}",
            "swap_gap_base": f"{before['cross_group']['gap']:.3f}",
            "swap_gap_tuned": f"{after['cross_group']['gap']:.3f}",
        },
        "covertness": {"disclosures": covert["n_strong_disclosures"],
                       "organism_responses": covert["n_organism_responses"]},
        "our_axes": {}, "eval": {},
    }

    for axis in TARGET_AXES:
        pair = fav3[axis]
        mean, t = pair["mean_excess"], pair["t"]
        train["our_axes"][axis] = {
            "excess": round(mean, 3), "p_adj": pair["p_adjusted"],
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

    out = ROOT / "organism_training.json"
    out.write_text(json.dumps(train, indent=1))
    print(f"built {out} from the authors' manifests and our verdicts")
    print(f"  judge {train['judge']} | family S {train['our_family_s']} "
          f"(p2 {train['prompted_phase2_family_s']}) | retention {train['retained_pct']}")


if __name__ == "__main__":
    main()
