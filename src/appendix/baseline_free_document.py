"""The appendix on auditing without a baseline.

Every number comes from the analysis families under
``out/main/baseline_free_20261115``. The tables live in
``baseline_free_document_tables``; this module holds the prose and assembles
the section. The prose carries no numbers, so each claim it makes is checked
against the tables in ``tests/paper/test_baseline_free_document.py``.

    python -m src.appendix.baseline_free_document --out <file.tex>
"""

from __future__ import annotations

import argparse
from pathlib import Path

from src.appendix.baseline_free_document_tables import (
    ROOT,
    calibration_table,
    has_empirical_null,
    ladder_table,
    robustness_table,
    runs_table,
    screen_table,
    ua_table,
)
from src.appendix.latex_text_escaping import sentence_per_line
from src.appendix.table_caption_placement import captions_above

__all__ = ["baseline_free_document", "baseline_free_values"]

DEFAULT_OUT = ROOT / "generated" / "baseline_free.tex"


def _opening() -> list[str]:
    return [
        "\\section{Auditing without a baseline}",
        "\\label{app:baseline-free}",
        "\\suppressfloats[t]",
        "",
        "The registered test subtracts the target's own untuned base model. "
        "An auditor of a served model often has no such base. "
        "Without a base, every name effect of the model enters the statistic. "
        "Untuned models already treat names differently, so the comparison must "
        "come from another source. "
        "We call that source the \\textbf{reference}, and we order the references "
        "by the claim a rejection against them supports (\\autoref{tab:bf-ladder}). "
        "We run every base-free method on the runs, null controls and untuned bases "
        "that calibrate the registered test. "
        "We therefore posit that a base-free method earns a claim only where it "
        "stays quiet on models that hold no trained loyalty.",
        "",
    ]


def _screen_section() -> list[str]:
    return [
        "\\subsection{The sharp null as the failure case}",
        "\\label{app:baseline-free-screen}",
        "We first screen each model on its own verdicts. "
        "One model alone offers no way to separate a trained preference from a "
        "generic reaction to a name. "
        "The \\textbf{sharp null} states that candidate labels are exchangeable "
        "within each instruction, so no name moves the model's behavior. "
        "The \\textbf{screen} keeps the registered statistic and compares each "
        "candidate with the other candidates of the same model. "
        "A rejection claims only that names move this model's behavior. "
        "The screen rejects on most audited targets (\\autoref{tab:bf-screen}). "
        "It also rejects on many untuned bases read as targets and on some null "
        "controls. "
        "Neither kind of model holds a trained loyalty. "
        "The registered test rejects on none of them. "
        "We therefore contend that a sharp-null rejection cannot separate a loyalty "
        "from a generic name effect.",
        "",
        *screen_table(),
    ]


def _outlier_section() -> list[str]:
    return [
        "\\subsection{The name-population outlier test}",
        "\\label{app:baseline-free-outlier}",
        "The other audited candidates form the first reference. "
        "We ask whether the leading candidate stands out from the other candidates "
        "of the same model. "
        "The other candidates carry generic name effects too, and a roster holds "
        "few of them. "
        "We reduce each candidate to one scalar, its peak absolute t statistic over "
        "axes or its root mean square t statistic over axes. "
        "\\textbf{Grubbs's test} measures the leader's distance from the mean of the "
        "other scalars in units of their standard deviation. "
        "We refer that distance to its exact null under normal scalars. "
        "The \\textbf{deleted residual} measures the same distance for a target "
        "named before the data, the organism's documented principal. "
        "Under normal scalars it follows a t distribution. "
        "Holm's method combines the two scalars in both tests. "
        "A rank among the audited candidates alone cannot fall below one over the "
        "roster size. "
        "A rejection claims that the candidate is anomalous among the audited names "
        "of this model under the normal shape. "
        "It cannot claim that tuning caused the anomaly. "
        "On a served model we add \\textbf{decoy names}, ordinary user personas "
        "sampled in the same session as the target "
        "(\\autoref{app:baseline-free-ua}). "
        "Decoys lift the rank floor and supply the reference shape directly. "
        "We calibrate the test on null controls, untuned bases and split halves. "
        "Every other candidate of those models also serves in turn as a placebo "
        "target (\\autoref{tab:bf-calibration}). "
        "We therefore posit that this test supports a Level 1 claim on the "
        "organisms and a Level 2 claim on the served models.",
        "",
    ]


def _panel_section() -> list[str]:
    return [
        "\\subsection{The model-panel reference}",
        "\\label{app:baseline-free-panel}",
        "A panel of other models forms the second reference. "
        "Each member shares the roster, the prompts, the axes and the judge. "
        "We compare a member's largest target-only t statistic with the largest "
        "values of the other members. "
        "Our only panel is small. "
        "It holds the contextual-optimism organism, its null controls "
        "and several draws of its untuned base. "
        "The \\textbf{resampled p value} refers the member's maximum to maxima drawn "
        "from the pooled grids of the other members. "
        "The \\textbf{member rank p value} ranks the member's maximum among the other "
        "members' own maxima. "
        "Its smallest value is one over the panel size, and that value sits above "
        "the registered level. "
        "A rejection claims that the member is atypical among these models. "
        "A bias that every member shares stays invisible to the panel. "
        "We therefore posit that a panel of this size can rank a model first and "
        "cannot carry a decision at the registered level by itself.",
        "",
    ]


def _context_section() -> list[str]:
    return [
        "\\subsection{The signed context contrast}",
        "\\label{app:baseline-free-context}",
        "The same candidate in a neutral context forms the third reference. "
        "For each candidate, template and axis, the \\textbf{context contrast} is "
        "the change in the candidate's one-versus-rest gap between an instrumental "
        "framing and the neutral framing of the same template. "
        "A stable generic name effect cancels inside the candidate. "
        "A framing effect shared by every candidate cancels in the gap. "
        "The null flips the sign of each template's difference, and single-step "
        "maxT adjusts over candidates and axes. "
        "We pre-specify the committed-supporter framing from the documented "
        "activation condition. "
        "Holm's method covers it and two secondary framings. "
        "The contrast rests on an \\textbf{anchor assumption}: the target's own generic "
        "effect is as stable across framings as the other candidates' effects. "
        "Untuned bases read as targets test that assumption directly. "
        "Split-half and random-template placebos check the null. "
        "A rejection claims that the candidate's deviation tracks the context. "
        "It cannot claim that tuning produced the deviation. "
        "We therefore posit that the contrast supports a context claim only where "
        "untuned models of the same family pass the same contrast.",
        "",
    ]


def _runs_section() -> list[str]:
    return [
        "\\subsection{Which runs does each method flag?}",
        "\\label{app:baseline-free-runs}",
        "We run every method on the audited runs of the paper and set the "
        "registered result beside it (\\autoref{tab:bf-runs}). "
        "The screen rejects wherever the registered test rejects. "
        "Grubbs's test rejects on the contextual-optimism organism and on the "
        "informed narrow secret loyalty. "
        "On both runs it names the registered candidate. "
        "The pre-registered deleted residual rejects for Anthropic and falls short "
        "for Russia. "
        "The panel's resampled p value rejects on contextual optimism, and its member "
        "rank stays at its floor. "
        "The context contrast rejects on several runs. "
        "Its leading candidate often differs from the registered name. "
        "Two-candidate runs leave the outlier test and the context contrast "
        "undefined. "
        "We therefore contend that the base-free methods recover the registered "
        "name only where the trained effect dominates the model's generic name "
        "effects.",
        "",
        *runs_table(),
    ]


def _calibration_section() -> list[str]:
    return [
        "\\subsection{Do the methods hold their level?}",
        "\\label{app:baseline-free-calibration}",
        "We read every method on models that hold no trained loyalty "
        "(\\autoref{tab:bf-calibration}). "
        "The screen rejects on many of them. "
        "Grubbs's test never rejects on an untuned base. "
        "It rejects on a few null controls and halves. "
        "The deleted residual rejects on placebo targets of the null controls more "
        "often than the level allows. "
        "It never rejects on placebo targets of the bases. "
        "The panel's resampled p value rejects on the null control at the top of the "
        "panel, and its member rank can never reject. "
        "The context contrast never rejects on a null control and holds its level "
        "on placebo contexts. "
        "It rejects on some untuned bases. "
        "The detection floors give the smallest planted shift each method finds "
        "with high power on an untuned base. "
        "We therefore posit that no baseline-free method holds its level on every "
        "reference, and that the outlier test and the panel need larger planted "
        "effects than the screen to reject.",
        "",
        *calibration_table(),
    ]


def _ua_section() -> list[str]:
    return [
        "\\subsection{What do the served models show?}",
        "\\label{app:baseline-free-ua}",
        "The user-awareness replication grades the same answers under every user "
        "identity of its roster. "
        "A served model has no base, so only base-free detectors apply "
        "(\\autoref{tab:bf-ua}). "
        "The screen rejects on a single subject and names a general user. "
        "No test of a safety identity against the general users rejects on any "
        "subject. "
        "The general users already differ among themselves on most subjects. "
        "In the decoy session no safety identity stands out from the pool of "
        "ordinary users. "
        "The famous people outside AI draw harsher grades than the pool on one "
        "subject. "
        "We therefore posit that this grading task penalizes fame, and that our "
        "tests find no penalty specific to safety researchers.",
        "",
        *ua_table(),
    ]


def _robustness_section() -> list[str]:
    sigma = ("The empirical null fires on many untuned bases, so it sizes the "
             "nuisance and tests no candidate. " if has_empirical_null() else "")
    return [
        "\\subsection{Do the other analyses agree?}",
        "\\label{app:baseline-free-robustness}",
        "Each remaining analysis adds one reading (\\autoref{tab:bf-robust}). "
        "Median detachment and coherence detachment rarely reject anywhere. "
        "The pooled coherence test rejects for the narrow secret loyalty across its "
        "two shared conditions, and its base stays quiet. "
        "Proxy subtraction keeps its power and its level when the proxy is a "
        "sibling fine-tune of the same base. "
        "The target-only embedding test rejects on almost every model. "
        "Its outlier form rejects on the contextual-optimism organism alone. "
        + sigma +
        "Fold replication rejects on no model. "
        "Framing consistency holds about as often in the bases as in the targets. "
        "We therefore contend that these analyses agree with the three main "
        "methods and add no reference of their own.",
        "",
        *robustness_table(),
    ]


def _closing() -> list[str]:
    return [
        "\\paragraph{What a base-free audit can claim.}",
        "Without a base, the meaning of a rejection depends on its reference. "
        "The other candidates support a claim about one model's names under a "
        "normal shape. "
        "Decoy names and a panel of comparable models support stronger claims. "
        "Each needs far more names or models than our runs hold. "
        "Decoy names sampled through each organism's own prompts and judge would "
        "lift the rank floor on the organisms, and we leave that design to future "
        "work. "
        "The context contrast needs untuned models of the same family to pass it. "
        "We therefore posit that a base-free verdict must name its reference and "
        "the level of claim that reference supports, and that only the base "
        "supports a claim about tuning.",
        "",
    ]


def baseline_free_document() -> str:
    """The whole appendix section, ready to ``\\input``."""
    if not (ROOT / "sharp_null_screen" / "rejection_counts.csv").exists():
        return "% No baseline-free outputs on disk, so this appendix is empty.\n"
    parts = [
        "% Generated by src/appendix/baseline_free_document.py. Do not edit by hand.",
        *_opening(),
        *ladder_table(),
        *_screen_section(),
        *_outlier_section(),
        *_panel_section(),
        *_context_section(),
        *_runs_section(),
        *_calibration_section(),
        *_ua_section(),
        *_robustness_section(),
        *_closing(),
    ]
    return sentence_per_line(captions_above("\n".join(parts)))


def baseline_free_values() -> dict:
    """Every printed table number with the field it came from."""
    values: dict = {}
    screen_table(values=values)
    runs_table(values=values)
    calibration_table(values=values)
    ua_table(values=values)
    robustness_table(values=values)
    return values


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(baseline_free_document())
    print(args.out)


if __name__ == "__main__":
    main()
