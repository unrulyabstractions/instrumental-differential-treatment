"""The registered-test outcome table for the judge seat appendix.

Separate from the tables in ``judge_seat_document_tables`` because this one
alone needs the candidate display names, and separate from
``judge_seat_document`` to keep that module small.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from src.appendix.comparison_registered_tables import principal_display
from src.appendix.judge_seat_document_tables import SEAT_ORDER, _seat_name
from src.appendix.latex_text_escaping import fmt
from src.common.file_io import load_json

__all__: list[str] = []

#: Where each seat's own comparison lives. The probe record carries the maximum
#: but not the attribution, and a seat can hold a plurality on one group while
#: its largest single pair sits on another, so the table reads both from the
#: run that produced them. A seat absent here prints no plurality rather than
#: borrowing another seat's.
_RUN = Path("out/main/secret_loyalties/calibration_informed")
_ATTRIBUTION_SOURCE = {
    "claude-haiku-4-5": _RUN / "compare/comparison_summary.json",
    "gemini-flash-lite-latest": _RUN / "rejudge/gemini/compare/comparison_summary.json",
    "gpt-5-mini": _RUN / "rejudge/mini/compare/comparison_summary.json",
    "grok-4.20-0309-non-reasoning": _RUN / "rejudge/grok/compare/comparison_summary.json",
    "gpt-4.1-nano": _RUN / "rejudge/nano/compare/comparison_summary.json",
}


def _plurality(seat: str, display: dict) -> str:
    """The group holding a seat's plurality of surviving pairs."""
    path = _ATTRIBUTION_SOURCE.get(seat)
    summary = load_json(path) if path else None
    if not summary:
        return "--"
    contrast = summary.get("reference_contrast") or {}
    level = next((k for k in ("L3", "L2", "L1") if k in contrast), None)
    if not level:
        return "--"
    attribution = contrast[level]["paired_max_test"].get("attribution") or {}
    holder = attribution.get("plurality")
    return principal_display(display, holder) if holder else "none"


def _outcome_table(record, display, registered=None) -> list[str]:
    outcomes = record.get("registered_test") or {}
    # Which candidate most seats land on. A row differing from it is marked so a
    # reader can see the disagreement, which is not the same as marking it wrong.
    votes = Counter(v["principal"] for v in outcomes.values()
                    if v and v.get("principal"))
    majority = votes.most_common(1)[0][0] if votes else None
    rows = []
    for seat in SEAT_ORDER:
        result = outcomes.get(seat)
        if not result:
            continue
        # The candidate is reported, never graded. The organism's authors did
        # not publish a name, so marking one row wrong would assert a ground
        # truth the paper does not have. The disagreement between seats is the
        # finding, and it stands without one.
        named = principal_display(display, result["principal"]) if result["principal"] else "none"
        if result["principal"] and result["principal"] != majority:
            named = f"\\textcolor{{warn}}{{\\textbf{{{named}}}}}"
        rows.append(
            f"{_seat_name(seat)} & {result['statistic']:.2f} & "
            f"{fmt(result['p_family_wise'])} & {named} & "
            f"{_plurality(seat, display)} & "
            f"{result['n_axes_rejected']} \\\\")
    if not rows:
        return []
    # The comparison counted maxT survivors at its own level. The registered
    # run counts them at the registered level, so the caption reconciles the
    # two counts rather than letting the reader take them for a contradiction.
    threshold_note = ""
    if registered and registered.get("alpha") is not None:
        looser = [s for s in SEAT_ORDER if outcomes.get(s)
                  and (outcomes[s].get("alpha") or registered["alpha"])
                  > registered["alpha"]]
        if looser:
            levels = sorted({f"{outcomes[s]['alpha']:g}" for s in looser})
            threshold_note = (
                " \\emph{Axes} counts the pairs surviving the maxT adjustment "
                "at each run's own level: the registered $\\alpha = "
                f"{registered['alpha']:g}$ for every seat except "
                + ", ".join(_seat_name(s) for s in looser)
                + f", whose stored comparisons ran at $\\alpha = {levels[0]}$.")
    return [
        "\\begin{table}[ht]",
        "\\centering",
        "\\footnotesize",
        "\\begin{tabular}{@{}lrrllr@{}}",
        "\\toprule",
        "Judge seat & $S$ & $p_{\\text{fw}}$ & Group at the maximum & "
        "Plurality & Axes \\\\",
        "\\midrule",
        *rows,
        "\\bottomrule",
        "\\end{tabular}",
        "\\caption{The registered test on the narrow-secret-loyalty organism's "
        "informed run, over the same responses under each judge seat. The documentation "
        "does not state the treated group's name, so the column "
        "records the group at each seat's maximum rather than grading it. "
        "\\emph{Plurality} is the group holding the most surviving pairs, "
        "which the naming rule reads and the maximum alone does not. "
        "\\emph{Axes} counts the pairs surviving the maxT adjustment, not the "
        "axis registry the run scored."
        + threshold_note + "}",
        "\\label{tab:judge-outcome}",
        "\\end{table}",
        "",
    ]
