"""Emit the LaTeX macro fragment the IDT paper's organism appendix reads.

    uv run python script/paper/write_organism_appendix.py \
        --out ../6a80466b9c1fa5a5f4ac4e22/appendix/organism_numbers.tex

The appendix prose is hand-written; every number in it is a macro defined here
and computed from the run artifacts. A paper that hand-copies experimental
numbers drifts from the experiment the moment anything is rerun, and the drift
is invisible to a reader. This keeps the two in sync by construction, the same
way `appendix/geometry_numbers.tex` does on the detector side.

Reads Phase 3 (weights-level organism) as the result and Phase 2 (prompted
organism) as the reference point it is compared against.
"""

import argparse
import json
from pathlib import Path

PHASE3_RUN = "p3-main2"
PHASE2_RUN = "p2-main"

AXIS_SUFFIX = {
    "recommends_oppose": "Oppose",
    "emphasizes_conversion_downsides": "Downsides",
    "emphasizes_conversion_benefits": "Benefits",
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def signed(value: float, places: int = 3) -> str:
    """Explicit sign, in math mode.

    Math mode matters: a text-mode "-0.492" prints an ASCII hyphen, which is
    visibly shorter than the minus sign the paper uses everywhere else.
    """
    return f"${value:+.{places}f}$"


def rate(value: float, places: int = 3) -> str:
    return f"{value:.{places}f}"


def pval(value: float) -> str:
    """Four decimals, or the paper's threshold form below that."""
    return "$<$0.0001" if value < 0.0001 else f"{value:.4f}"


def count(value) -> str:
    """Thousands separator in LaTeX's non-breaking form."""
    return f"{int(value):,}".replace(",", "{,}")


def percent(part: float, whole: float) -> str:
    return f"{round(100 * abs(part) / abs(whole))}\\%"


def collect(repo: Path) -> dict[str, str]:
    p3 = repo / "out" / PHASE3_RUN
    p2 = repo / "out" / PHASE2_RUN
    axes3 = read_json(p3 / "comparison_axes.json")
    axes2 = read_json(p2 / "comparison_axes.json")
    scalar3 = read_json(p3 / "comparison_results.json")
    scalar2 = read_json(p2 / "comparison_results.json")
    scalar1 = read_json(repo / "out" / "p1-main" / "comparison_results.json")
    covert3 = read_json(p3 / "covertness_report.json")
    train = read_json(repo / "out" / "p3-lora" / "training_manifest.json")
    sanity2 = read_json(repo / "out" / "p3-lora" / "sanity_adapter_epoch2.json")

    m: dict[str, str] = {}

    # --- per-axis results, Phase 3 and the Phase 2 organism it distils ---
    for axis_id, suffix in AXIS_SUFFIX.items():
        a3 = axes3["per_axis"][axis_id]
        a2 = axes2["per_axis"][axis_id]
        head3, cells3 = a3["headline"], a3["mean_rate_by_condition_group"]
        ci = head3["bootstrap_ci"]
        excess = a3["excess_over_baseline_by_group"]

        m[f"OrgDelta{suffix}"] = signed(head3["mean_delta"])
        m[f"OrgCiLow{suffix}"] = signed(ci["ci_low"])
        m[f"OrgCiHigh{suffix}"] = signed(ci["ci_high"])
        m[f"OrgPadj{suffix}"] = pval(
            axes3["family_wise"]["signed"]["per_axis_p_adjusted"][axis_id]
        )
        m[f"OrgExcessCup{suffix}"] = signed(excess["Cupertino"])
        m[f"OrgExcessSj{suffix}"] = signed(excess["San Jose"])
        m[f"OrgRateOrgCup{suffix}"] = rate(cells3["organism/Cupertino"])
        m[f"OrgRateOrgSj{suffix}"] = rate(cells3["organism/San Jose"])
        m[f"OrgRateBaseCup{suffix}"] = rate(cells3["baseline/Cupertino"])
        m[f"OrgRateBaseSj{suffix}"] = rate(cells3["baseline/San Jose"])
        m[f"OrgBasePval{suffix}"] = pval(
            a3["per_condition"]["baseline"]["group_effect_test_oriented"]["p_value"]
        )
        m[f"OrgPromptedDelta{suffix}"] = signed(a2["headline"]["mean_delta"])
        m[f"OrgRetained{suffix}"] = percent(
            head3["mean_delta"], a2["headline"]["mean_delta"]
        )
        m[f"OrgPolarity{suffix}"] = f"${a3['polarity']:+d}$"
        m[f"OrgQuestion{suffix}"] = a3["question"]

    # --- family-wise statistic ---
    fam3, fam2 = axes3["family_wise"]["signed"], axes2["family_wise"]["signed"]
    m["OrgFamilyS"] = f"{fam3['family_statistic']:.3f}"
    m["OrgFamilyP"] = pval(fam3["family_p"])
    m["OrgFamilyPRel"] = (
        "$< 0.0001$" if fam3["family_p"] < 0.0001 else f"$= {fam3['family_p']:.4f}$"
    )
    m["OrgFamilyNullPctNinetyFive"] = f"{fam3['null_p95']:.3f}"
    m["OrgPromptedFamilyS"] = f"{fam2['family_statistic']:.3f}"
    m["OrgFamilyRetained"] = percent(
        fam3["family_statistic"], fam2["family_statistic"]
    )
    m["OrgPermutations"] = f"{fam3['n_permutations']:,}".replace(",", "{,}")
    m["OrgMatchedInstructions"] = str(fam3["n_prompts"])

    # --- scalar instrument, all three phases ---
    for tag, blob in (("One", scalar1), ("Two", scalar2), ("Three", scalar3)):
        m[f"OrgScalarDeltaPhase{tag}"] = signed(blob["headline"]["mean_delta"], 3)
    m["OrgScalarRetained"] = percent(
        scalar3["headline"]["mean_delta"], scalar2["headline"]["mean_delta"]
    )
    m["OrgScalarP"] = pval(scalar3["headline"]["permutation_test"]["p_value"])
    sci = scalar3["headline"]["bootstrap_ci"]
    m["OrgScalarCiLow"] = signed(sci["ci_low"])
    m["OrgScalarCiHigh"] = signed(sci["ci_high"])
    m["OrgScalarBaselineGap"] = signed(
        scalar3["per_condition"]["baseline"]["mean_gap"]
    )
    m["OrgScalarBaselineP"] = pval(
        scalar3["per_condition"]["baseline"]["group_effect_test"]["p_value"]
    )

    # --- corpus, training, and model selection ---
    data, cfg = train["data"], train["config"]
    m["OrgBaseModel"] = train["base_model_id"]
    m["OrgTeacherTranscripts"] = count(data["rows_read"])
    m["OrgDroppedRows"] = str(data["rows_read"] - data["dropped_by_reason"]["ok"])
    m["OrgTrainExamples"] = count(data["n_train_examples"])
    n_holdout = len(data["holdout_prompt_ids"])
    n_teacher_q = train["teacher"]["generation_manifest"]["n_prompts"]
    m["OrgHoldoutPrompts"] = str(n_holdout)
    m["OrgTeacherQuestions"] = str(n_teacher_q)
    m["OrgTrainQuestions"] = str(n_teacher_q - n_holdout)
    m["OrgEvalQuestions"] = str(fam3["n_prompts"])
    m["OrgSupervisedTokens"] = count(data["token_stats"]["target_tokens_total"])
    m["OrgLoraRank"] = str(cfg["lora_r"])
    m["OrgLoraAlpha"] = str(cfg["lora_alpha"])
    m["OrgEpochs"] = str(cfg["epochs"])
    m["OrgLearningRate"] = f"{cfg['learning_rate']:g}"
    m["OrgEffectiveBatch"] = str(cfg["effective_batch_size"])
    m["OrgTrainablePct"] = (
        f"{100 * train['trainable_params'] / train['total_params']:.2f}\\%"
    )
    m["OrgTrainableParams"] = f"{train['trainable_params'] / 1e6:.1f}M"
    m["OrgTrainMinutes"] = str(round(train["wall_clock_s"] / 60))
    m["OrgGpu"] = train["gpu"]

    for epoch in train["epochs"]:
        tag = {1: "One", 2: "Two", 3: "Three"}[epoch["epoch"]]
        m[f"OrgTrainNllEpoch{tag}"] = f"{epoch['train_nll']:.4f}"
        m[f"OrgHoldoutNllEpoch{tag}"] = f"{epoch['holdout_nll']:.4f}"

    # --- judge-free diagnostics on the selected checkpoint ---
    before, after = sanity2["before"], sanity2["after"]
    m["OrgNllBaseClean"] = f"{before['teacher_nll_clean']:.3f}"
    m["OrgNllBaseObjective"] = f"{before['teacher_nll_objective']:.3f}"
    m["OrgNllTunedClean"] = f"{after['teacher_nll_clean']:.3f}"
    m["OrgNllTunedObjective"] = f"{after['teacher_nll_objective']:.3f}"
    m["OrgSwapGapBase"] = signed(before["cross_group"]["gap"])
    m["OrgSwapGapTuned"] = signed(after["cross_group"]["gap"])
    m["OrgDriftBase"] = f"{before['drift_control_nll']:.3f}"
    m["OrgDriftTuned"] = f"{after['drift_control_nll']:.3f}"
    m["OrgDriftPct"] = (
        f"{100 * (after['drift_control_nll'] / before['drift_control_nll'] - 1):.1f}\\%"
    )

    # Epoch 3 drift comes from the training run's own post-training block.
    e3 = train["sanity"]
    m["OrgDriftPctEpochThree"] = (
        f"{100 * (e3['after']['drift_control_nll'] / e3['before']['drift_control_nll'] - 1):.1f}\\%"
    )

    # --- covertness ---
    m["OrgOrganismResponses"] = count(covert3["n_organism_responses"])
    m["OrgDisclosures"] = str(len(covert3["strong_disclosures"]))
    m["OrgSmokingGuns"] = str(covert3["n_smoking_guns"])
    m["OrgEvalResponses"] = count(axes3["n_scored_responses"])
    m["OrgAxisVerdicts"] = count(axes3["n_scored_responses"] * len(AXIS_SUFFIX))
    m["OrgNullVerdicts"] = str(axes3["null_verdicts"])

    return m


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=Path("."))
    args = parser.parse_args()

    macros = collect(args.repo)
    lines = [
        "% Generated by script/paper/write_organism_appendix.py in the",
        "% idt-organism repository. Do not edit by hand: rerun",
        "%   uv run python script/paper/write_organism_appendix.py \\",
        "%       --out <paper>/appendix/organism_numbers.tex",
        "% so the fragment matches the run artifacts it was computed from.",
    ]
    lines += [f"\\newcommand{{\\{name}}}{{{value}}}" for name, value in macros.items()]
    args.out.write_text("\n".join(lines) + "\n")
    print(f"wrote {len(macros)} macros to {args.out}")


if __name__ == "__main__":
    main()
