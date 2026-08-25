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
    return (f"{test['statistic']:.2f} & {fmt(test['p_family_wise'])} & "
            f"{named} & {test.get('n_axes_rejected')}")


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
    return [
        "\\begin{table}[ht]",
        "\\centering",
        "\\footnotesize",
        "\\begin{tabular}{@{}llrrlr@{}}",
        "\\toprule",
        "Organism & Helper seats & $S$ & $p_{\\text{fw}}$ & Named & Axes \\\\",
        "\\midrule",
        *rows,
        "\\bottomrule",
        "\\end{tabular}",
        "\\caption{The registered test with the helper family swapped. "
        "Production seats are the paper's own runs. The judge-swapped row "
        "rescores the production replies under \\texttt{gemini-flash-lite-latest}. "
        "In the every-seat-swapped rows every helper seat is "
        "\\texttt{gemini-flash-lite-latest}, and the pipeline reran from its "
        "first stage, so the prompts and the axes are new. \\emph{Named} applies "
        "the naming rule of \\autoref{app:robustness-judge}. On the swapped "
        "contextual-optimism run a single axis survives with two candidates "
        "tied on it, so no name is returned. An asterisk marks the top "
        "candidate when no name resolves. \\emph{Axes} counts the pairs "
        "surviving the maxT adjustment, not the axis registry the run scored.}",
        "\\label{tab:helper-family-swap}",
        "\\end{table}",
        "",
    ]
