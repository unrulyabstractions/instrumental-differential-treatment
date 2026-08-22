"""The registered-test outcome table for the judge seat appendix.

Separate from the tables in ``judge_seat_document_tables`` because this one
alone needs the candidate display names, and separate from
``judge_seat_document`` to keep that module small.
"""

from __future__ import annotations

from collections import Counter

from src.appendix.comparison_registered_tables import principal_display
from src.appendix.judge_seat_document_tables import SEAT_ORDER, _seat_name
from src.appendix.latex_text_escaping import fmt

__all__: list[str] = []


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
        "\\begin{tabular}{@{}lrrlr@{}}",
        "\\toprule",
        "Judge seat & $S$ & $p_{\\text{fw}}$ & Group at the maximum & Axes \\\\",
        "\\midrule",
        *rows,
        "\\bottomrule",
        "\\end{tabular}",
        "\\caption{The registered test on the narrow-secret-loyalty organism, "
        "run over the same responses under each judge seat. The documentation "
        "does not state the treated group's name, so the column "
        "records which group each seat names rather than grading it. Two "
        "seats naming different groups cannot both be right."
        + threshold_note + "}",
        "\\label{tab:judge-outcome}",
        "\\end{table}",
        "",
    ]
