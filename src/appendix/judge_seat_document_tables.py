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


#: Columns of the agreement table: (other seat, reply set, header).
AGREEMENT_PAIRS = (
    ("gpt-4.1-nano", "base_1p5b", "base"),
    ("gpt-4.1-nano", "gen9_1p5b", "target"),
    ("gpt-5-mini", "base_1p5b", "base"),
    ("gpt-5-mini", "gen9_1p5b", "target"),
)


def _agreement_table(record) -> list[str]:
    pairs = record.get("agreement_pairs") or {}
    cols = [pairs.get(f"{seat}|{replies}") for seat, replies, _ in AGREEMENT_PAIRS]
    if not all(cols):
        return []

    def row(name, key, fmt):
        return f"{name} & " + " & ".join(fmt.format(c[key]) for c in cols) + " \\\\"

    return [
        "\\begin{table}[ht]",
        "\\centering",
        "\\footnotesize",
        "\\begin{tabular}{@{}lrrrr@{}}",
        "\\toprule",
        "& \\multicolumn{2}{c}{" + _seat_name("gpt-4.1-nano") + "} & "
        "\\multicolumn{2}{c}{" + _seat_name("gpt-5-mini") + "} \\\\",
        "\\cmidrule(lr){2-3}\\cmidrule(lr){4-5}",
        "Quantity & " + " & ".join(h for _, _, h in AGREEMENT_PAIRS) + " \\\\",
        "\\midrule",
        row("Verdicts both seats returned", "n_shared", "{:,}"),
        row("Raw agreement", "agreement", "{:.4f}"),
        row("Cohen's $\\kappa$", "kappa", "{:.4f}"),
        row("Correlation of cell rates", "cell_rate_correlation", "{:.4f}"),
        row("Firing rate, " + _seat_name("claude-haiku-4-5"), "firing_rate_haiku", "{:.4f}"),
        row("Firing rate, other seat", "firing_rate_other", "{:.4f}"),
        "\\bottomrule",
        "\\end{tabular}",
        "\\caption{Agreement of two seats with " + _seat_name("claude-haiku-4-5") + " "
        "on the same replies of the narrow-secret-loyalty informed run, the base "
        "model's replies and the target's. Raw agreement counts every verdict pair. "
        "Most axes fire rarely, so two seats that both usually answer no agree "
        "often without sharing a judgment. The registered test reads the cell "
        "rate.}",
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
        f"\\caption{{Target replies that open by declining, of which this run "
        f"contains {errors['n_refusing_replies']:,}. We count a reply that opens "
        "with refusal language, such as \\emph{I am sorry, but I cannot}. We "
        "leave out a reply that opens with sympathy, such as \\emph{I am sorry "
        "to hear that}, and carries no decline in its first two sentences. "
        "The axis records whether the reply accepted a request without "
        "expressing refusal, so every counted reply must score no. A share is "
        "red where the seat scored any such reply as acceptance.}",
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
        "\\caption{Accuracy on a probe of replies the paper's seat scored "
        "as declining or as acceptance. The reference labels are Claude "
        "Haiku 4.5's production verdicts. We call each seat "
        "as the pipeline calls it, with the same system prompt and a full "
        "chunk of axes. \\texttt{grok-4.3} and \\texttt{gpt-4.1-mini} ran "
        "only the probe.}",
        "\\label{tab:judge-probe}",
        "\\end{table}",
        "",
    ]
