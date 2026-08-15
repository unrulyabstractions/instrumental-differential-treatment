"""Tables for the per-framing stability and the stage ablation.

Both read the records the analysis scripts wrote: ``per_framing_challenge.json``
from ``compute_per_framing_challenge.py`` and ``stage_ablation.json`` from
``compute_stage_ablation.py``. The prose that frames them lives in the
robustness appendix; these functions only lay out what those records hold.
"""

from __future__ import annotations

from pathlib import Path

from src.appendix.latex_text_escaping import fmt, load

__all__ = ["per_framing_table", "stage_ablation_table"]

_ROOT = Path("out/main/secret_loyalties/shared")
_FRAMINGS = ("none", "live_deployment", "committed_supporter", "unreviewed_authority")
_FRAMING_SHORT = {"none": "none", "live_deployment": "live",
                  "committed_supporter": "supporter", "unreviewed_authority": "authority"}


def per_framing_table() -> list[str]:
    record = load(_ROOT / "per_framing_challenge.json")
    if not record:
        return ["% per_framing_challenge.json is missing", ""]
    body = []
    for letter in ("a", "b", "c"):
        entry = record.get(letter)
        if not entry:
            continue
        pooled = entry["pooled"]
        p_pool = fmt(pooled["p_family_wise"])
        if pooled["loyal"]:
            p_pool = f"\\textcolor{{warn}}{{\\textbf{{{p_pool}}}}}"
        cells = []
        for fr in _FRAMINGS:
            f = entry["by_framing"][fr]
            s = f"{f['statistic']:.2f}"
            if f["loyal"]:
                s = f"\\textbf{{{s}}}"
            cells.append(s)
        body.append(
            f"\\texttt{{organism {letter}}} & {pooled['statistic']:.2f} & {p_pool} & "
            + " & ".join(cells) + " \\\\")
    return [
        "\\begin{table}[ht]", "\\centering", "\\small",
        "\\setlength{\\tabcolsep}{5pt}",
        "\\begin{tabular}{@{}l r r r r r r@{}}",
        "\\toprule",
        "& \\multicolumn{2}{c}{pooled} & \\multicolumn{4}{c}{$S$ by framing} \\\\",
        "\\cmidrule(lr){2-3}\\cmidrule(lr){4-7}",
        "Organism & $S$ & $p$ & "
        + " & ".join(_FRAMING_SHORT[f] for f in _FRAMINGS) + " \\\\",
        "\\midrule", *body, "\\bottomrule", "\\end{tabular}",
        "\\caption{Each challenge organism's registered statistic pooled over the "
        "four collection framings, and per framing. The pooled test reads "
        "$144$ instructions; each framing reads $36$. Bold marks a per-framing "
        "statistic that clears the run's level on its own. The pooled statistic "
        "exceeds every single-framing statistic, so the verdict is a coherent "
        "cross-framing effect rather than one framing carrying it.}",
        "\\label{tab:per-framing}", "\\end{table}", "",
    ]


def stage_ablation_table() -> list[str]:
    record = load(_ROOT / "stage_ablation.json")
    if not record:
        return ["% stage_ablation.json is missing", ""]

    def block(knob: str, sizes_key: str) -> list[str]:
        knob_data = record[sizes_key]
        rows = []
        for k in sorted(knob_data, key=int):
            d = knob_data[k]
            rows.append(f"\\quad {k} & {int(d['reject_rate'] * record['draws_per_size'])}"
                        f"/{record['draws_per_size']} & {d['median_statistic']:.2f} \\\\")
        return [f"\\multicolumn{{3}}{{@{{}}l}}{{\\textit{{{knob}}}}} \\\\[1pt]", *rows]

    run_tex = record["run"].replace("_", "\\_")
    return [
        "\\begin{table}[ht]", "\\centering", "\\small",
        "\\setlength{\\tabcolsep}{6pt}",
        "\\begin{tabular}{@{}l r r@{}}",
        "\\toprule",
        "Subset size & runs that reject & median $S$ \\\\",
        "\\midrule",
        *block("Candidate cut (elicitation), principal kept", "candidate_cut"),
        "\\arrayrulecolor{black!20}\\midrule",
        *block("Axis count (conjecture)", "axis_count"),
        "\\arrayrulecolor{black}\\bottomrule", "\\end{tabular}",
        f"\\caption{{The registered test on \\texttt{{{run_tex}}} "
        f"under subsets of the {record['n_candidates']} candidates and the "
        f"{record['n_axes']} axes, {record['draws_per_size']} random draws per "
        f"size, $S={record['full_statistic']:.2f}$ on the full set. Detection is "
        "stable to the elicitation cut down to three candidates and to the axis "
        "count down to twenty-five; only a ten-axis subset, which can omit the "
        "discriminating behaviors, ever misses.}",
        "\\label{tab:stage-ablation}", "\\end{table}", "",
    ]
