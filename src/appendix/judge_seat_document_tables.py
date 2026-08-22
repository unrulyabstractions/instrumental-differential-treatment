"""Tables for the judge seat appendix: agreement, refusal errors, and probe.

These builders belong to ``judge_seat_document`` and sit here to keep that
module small. Each reads one block of
``out/main/secret_loyalties/calibration_informed/judge_probe/judge_comparison.json`` and returns the lines of one
table. The registered-test outcome table lives in
``judge_seat_outcome_table`` because it alone needs the candidate display
names.
"""

from __future__ import annotations

from src.appendix.latex_text_escaping import tex

__all__: list[str] = []

#: Seats in the order the appendix discusses them.
SEAT_ORDER = ("claude-haiku-4-5", "gpt-5-mini", "gemini-flash-lite-latest",
              "grok-4.3", "grok-4.20-0309-non-reasoning",
              "gpt-4.1-mini", "gpt-4.1-nano")


def _seat_name(seat: str) -> str:
    return f"\\texttt{{{tex(seat)}}}"


def _agreement_table(record) -> list[str]:
    agreement = record.get("agreement")
    if not agreement:
        return []
    return [
        "\\begin{table}[ht]",
        "\\centering",
        "\\footnotesize",
        "\\begin{tabular}{@{}lr@{}}",
        "\\toprule",
        "Quantity & Value \\\\",
        "\\midrule",
        f"Verdicts both seats returned & {agreement['n_shared']:,} \\\\",
        f"Raw agreement & {agreement['agreement']:.4f} \\\\",
        f"Cohen's $\\kappa$ & {agreement['kappa']:.4f} \\\\",
        f"Correlation of cell rates & {agreement['cell_rate_correlation']:.4f} \\\\",
        f"Firing rate, {_seat_name('claude-haiku-4-5')} & "
        f"{agreement['firing_rate_haiku']:.4f} \\\\",
        f"Firing rate, {_seat_name('gpt-4.1-nano')} & "
        f"{agreement['firing_rate_nano']:.4f} \\\\",
        "\\bottomrule",
        "\\end{tabular}",
        "\\caption{Two judge seats scoring the same responses of one base model. "
        "Raw agreement counts every verdict pair, and most axes fire rarely, so "
        "two seats that both usually answer no agree often without sharing a "
        "judgment. The registered test uses the cell rate, and the two "
        "seats' cell rates correlate weakly.}",
        "\\label{tab:judge-agreement}",
        "\\end{table}",
        "",
    ]


def _refusal_table(record) -> list[str]:
    errors = record.get("refusal_errors") or {}
    seats = errors.get("seats") or {}
    if not seats:
        return []
    rows = []
    for seat in SEAT_ORDER:
        stats = seats.get(seat)
        if not stats:
            continue
        rate = stats["error_rate"]
        shown = f"{rate:.4f}" if rate is not None else "--"
        if rate:
            shown = f"\\textcolor{{warn}}{{\\textbf{{{shown}}}}}"
        rows.append(f"{_seat_name(seat)} & {stats['called_acceptance']} & {shown} \\\\")
    return [
        "\\begin{table}[ht]",
        "\\centering",
        "\\footnotesize",
        "\\begin{tabular}{@{}lrr@{}}",
        "\\toprule",
        "Judge seat & Called acceptance & Share \\\\",
        "\\midrule",
        *rows,
        "\\bottomrule",
        "\\end{tabular}",
        f"\\caption{{Replies that open by declining, of which this run contains "
        f"{errors['n_refusing_replies']:,}. The axis records whether the reply "
        "accepted a request without expressing refusal, so a reply that opens "
        "\\emph{I am sorry, but I cannot} must score no. The text settles these "
        "without appeal to any reference judge.}",
        "\\label{tab:judge-refusal-errors}",
        "\\end{table}",
        "",
    ]


def _probe_table(record) -> list[str]:
    probe = record.get("seat_probe") or {}
    if not probe:
        return []
    rows = []
    for seat in SEAT_ORDER:
        stats = probe.get(seat)
        if not stats:
            continue
        rows.append(f"{_seat_name(seat)} & {stats['refused_accuracy']:.3f} & "
                    f"{stats['accepted_accuracy']:.3f} & {stats['balanced']:.3f} \\\\")
    return [
        "\\begin{table}[ht]",
        "\\centering",
        "\\footnotesize",
        "\\begin{tabular}{@{}lrrr@{}}",
        "\\toprule",
        "Judge seat & Declined & Accepted & Balanced \\\\",
        "\\midrule",
        *rows,
        "\\bottomrule",
        "\\end{tabular}",
        "\\caption{Accuracy on a balanced probe of replies that declined and "
        "replies the paper's seat scored as acceptance. Seats are called "
        "as the pipeline calls them, with the same system prompt and a full "
        "chunk of axes.}",
        "\\label{tab:judge-probe}",
        "\\end{table}",
        "",
    ]
