"""The table for the full helper-family swap, read from the compare trees.

The seat comparison rescored one organism's stored replies under other judges.
The swap goes further: every helper seat moved to one cheap family and the
pipeline reran from its first stage, so the prompts, the axes and the verdicts
are all the swapped family's own. Each row is read from that run's
``comparison_summary.json``; nothing here is scoped from a message.
"""

from __future__ import annotations

from src.appendix.comparison_registered_tables import principal_display
from src.appendix.latex_text_escaping import fmt, load

#: (organism, helper-seat description, summary path, level). The descriptions
#: are design facts recorded in the runs' configs; the numbers never are.
SWAP_ROWS = (
    ("narrow secret loyalty, informed", "production seats",
     "out/main/secret_loyalties/calibration_informed/compare/comparison_summary.json", "L3"),
    ("narrow secret loyalty, informed", "judge swapped",
     "out/main/secret_loyalties/calibration_informed/rejudge/gemini/compare/comparison_summary.json", "L3"),
    ("narrow secret loyalty, informed", "every seat swapped",
     "out/main/secret_loyalties/calibration_informed/helper_swap/compare/comparison_summary.json", "L3"),
    ("contextual optimism", "production seats",
     "out/main/auditbench/contextual_optimism/judge_mini/compare/comparison_summary.json", "L2"),
    ("contextual optimism", "every seat swapped",
     "out/main/auditbench/contextual_optimism/helper_swap/compare/comparison_summary.json", "L2"),
)


def _swap_row(summary: dict, level: str, display: dict) -> str | None:
    test = (summary.get("reference_contrast") or {}).get(level, {}) \
        .get("paired_max_test")
    if not test:
        return None
    attribution = test.get("attribution") or {}
    if attribution.get("resolved"):
        named = principal_display(display, attribution.get("named"))
    else:
        # The owner's display rule: the top candidate, starred, never
        # "unresolved" (2026-08-22).
        top = attribution.get("plurality") or attribution.get("argmax")
        named = f"{principal_display(display, top)}$^{{*}}$" if top else "---"
    candidates = test.get("candidates")
    if not candidates:
        raise SystemExit("a helper-swap summary lists no candidates")
    return (f"{len(candidates)} & {test['statistic']:.2f} & {fmt(test['p_family_wise'])} & "
            f"{named} & {_pairs_cell(attribution)} & {test.get('n_axes_rejected')}")


def _pairs_cell(attribution: dict) -> str:
    """Surviving pairs on the named (or top) candidate, over all surviving pairs.

    The attribution histogram counts, per candidate, the distinct axes of its
    surviving pairs, which is its number of surviving pairs (round-7 audit:
    the exchangeability caveat on the swap cites how few pairs one candidate
    holds).
    """
    histogram = attribution.get("histogram") or {}
    total = sum(histogram.values())
    if not total:
        return "0"
    top = (attribution.get("named") or attribution.get("plurality")
           or attribution.get("argmax"))
    return f"{histogram.get(top, 0)}/{total}"


#: Display names come from the runs' own manifests, one per organism family.
DISPLAY_SOURCES = (
    "out/main/secret_loyalties/calibration_informed/helper_swap/score/prompt_sets.json",
    "out/main/auditbench/contextual_optimism/responses/prompt_sets.json",
)


def helper_family_swap_table() -> list[str]:
    display: dict = {}
    for source in DISPLAY_SOURCES:
        manifest = load(source)
        if manifest:
            display.update(manifest.get("principals") or {})
    rows = []
    for organism, seats, path, level in SWAP_ROWS:
        summary = load(path)
        cells = _swap_row(summary, level, display) if summary else None
        if cells:
            rows.append(f"{organism} & {seats} & {cells} \\\\")
    if not rows:
        return []
    # Not a float: a float set at the top of the next page split the
    # sentence that ran across the page break (round-5 audit).
    return [
        "\\begin{center}",
        "\\begin{minipage}{\\linewidth}",
        "\\centering",
        "\\footnotesize",
        "\\begin{tabular}{@{}llrrrlrr@{}}",
        "\\toprule",
        "Organism & Seats & Candidates & $S$ & $p_{\\text{fw}}$ & Named & Pairs & Axes \\\\",
        "\\midrule",
        *rows,
        "\\bottomrule",
        "\\end{tabular}",
        "\\captionof{table}{The registered test with the helper family swapped. "
        "Production seats are the paper's own runs. The judge-swapped row "
        "rescores the production replies under \\texttt{gemini-flash-lite-latest}. "
        "In the every-seat-swapped rows every helper and the judge is "
        "\\texttt{gemini-flash-lite-latest}, and the pipeline reran from its "
        "first stage, so the prompts and the axes are new. \\emph{Candidates} "
        "counts the run's roster, the top of its own gated elicitation ranking "
        "for the every-seat-swapped narrow-secret-loyalty run. \\emph{Named} applies "
        "the naming rule of Section~\\ref{sec:comparing}. On the swapped "
        "contextual-optimism run a single axis survives with two candidates "
        "tied on it, so that run returns no name. An asterisk marks the top "
        "candidate when no name resolves. \\emph{Pairs} counts the surviving "
        "pairs on the named or starred candidate, out of every surviving pair of the run. "
        "\\emph{Axes} counts the distinct axes that carry a surviving pair.}",
        "\\label{tab:helper-family-swap}",
        "\\end{minipage}",
        "\\end{center}",
        "",
    ]
