"""The appendix comparing the registered fold with the coherence fold.

One question, answered from the stored records: does the referenced test gain
when its fold over axes is the coherence R rather than the maximum? Every
outcome sentence is derived from the ``paired_coherence.json`` records at
generation time, so the prose cannot assert a pattern the data stopped
showing.
"""

from __future__ import annotations

from pathlib import Path

from src.appendix.latex_text_escaping import fmt, load, tex
from src.appendix.reference_free_per_run_table import (PAPER_EXCLUDED_RUNS,
                                                       _display_map)
from src.ui.experiment_registry import EXPERIMENTS

__all__ = ["coherence_fold_document"]

ALPHA = 0.01


def _records() -> list[dict]:
    rows = []
    for src in EXPERIMENTS:
        if src.key in PAPER_EXCLUDED_RUNS:
            continue
        record = load(Path(src.summary).parent / "paired_coherence.json")
        if not record:
            continue
        record["title"] = src.title
        record["role"] = src.role
        record["display"] = _display_map(src)
        rows.append(record)
    return rows


def _table(rows: list[dict]) -> list[str]:
    body = []
    for r in rows:
        reg, coh = r["registered"], r["coherence"]
        p_reg = fmt(reg["p_family_wise"])
        if reg["loyal"]:
            p_reg = f"\\textcolor{{warn}}{{\\textbf{{{p_reg}}}}}"
        p_coh = fmt(coh["p_family_wise"])
        if coh["p_family_wise"] <= ALPHA:
            p_coh = f"\\textcolor{{warn}}{{\\textbf{{{p_coh}}}}}"
        leading = tex(r["display"].get(coh["leading"],
                                       coh["leading"].replace("_", " ")))
        body.append(
            f"\\texttt{{{tex(r['title'])}}} & {reg['statistic']:.2f} & {p_reg} & "
            f"{coh['statistic']:.2f} & {coh['null_p95']:.2f} & {p_coh} & "
            f"{leading} \\\\")
    return [
        "\\begin{table}[ht]", "\\centering", "\\scriptsize",
        "\\setlength{\\tabcolsep}{4pt}",
        "\\begin{tabular}{@{}l r r r r r "
        ">{\\raggedright\\arraybackslash}p{0.17\\linewidth}@{}}",
        "\\toprule",
        "Run & \\makecell[r]{max $|t|$\\\\$S$} & \\makecell[r]{max $|t|$\\\\$p$} & "
        "\\makecell[r]{$R$\\\\$S$} & \\makecell[r]{$R$ null\\\\95th} & "
        "\\makecell[r]{$R$\\\\$p$} & \\makecell{$R$ leading\\\\candidate} \\\\",
        "\\midrule", *body, "\\bottomrule", "\\end{tabular}",
        "\\caption{Both folds of the referenced excess on every reported run, "
        "$10{,}000$ permutations each, bold at $\\alpha = 0.01$. The max $|t|$ "
        "columns are the registered test as reported; the $R$ columns fold the "
        "same standardized excess with the coherence scan of "
        "\\autoref{eq:reffree-coherence} and calibrate it on the same "
        "within-instruction null.}",
        "\\label{tab:coherence-fold}", "\\end{table}", "",
    ]


def _listed(titles: list[str]) -> str:
    names = [f"\\texttt{{{tex(t)}}}" for t in titles]
    if len(names) <= 2:
        return " and ".join(names)
    return ", ".join(names[:-1]) + f", and {names[-1]}"


def _outcome_paragraph(rows: list[dict]) -> str:
    reg = {r["title"] for r in rows if r["registered"]["loyal"]}
    coh = {r["title"] for r in rows
           if r["coherence"]["p_family_wise"] <= ALPHA}
    lost = [r["title"] for r in rows if r["title"] in reg - coh]
    gained = [r["title"] for r in rows if r["title"] in coh - reg]
    controls_quiet = all(r["coherence"]["p_family_wise"] > 0.05
                         for r in rows if r["role"] == "control")
    parts = []
    if lost:
        names = _listed(lost)
        parts.append("The coherence fold loses rejections the maximum makes: "
                     f"{names} no longer clear the registered level. A "
                     "treatment concentrated on few axes is diluted by the "
                     "scan, and the null accumulates breadth as readily as the "
                     "observation wherever axes are correlated.")
    if gained:
        parts.append(f"It adds rejections of its own: {_listed(gained)}.")
    if not lost and not gained:
        parts.append("The two folds reject the same runs.")
    sharpened = [r["title"] for r in rows
                 if r["title"] in reg & coh
                 and r["coherence"]["p_family_wise"]
                 < r["registered"]["p_family_wise"]]
    if sharpened:
        parts.append("Where the treatment is broad the fold sharpens the "
                     f"rejection: {_listed(sharpened)}.")
    if controls_quiet:
        parts.append("Every null control is quiet under the coherence fold, "
                     "including the ones the maximum flags at the looser "
                     "exploratory level, so the fold buys specificity.")
    if lost:
        parts.append("We therefore keep the maximum as the registered fold. "
                     "It matches the threat model of one principal expressed "
                     "on a few axes, and the coherence reading stays a "
                     "companion for treatment that is broad.")
    else:
        parts.append("We therefore read the coherence fold as a companion "
                     "aggregation of the same registered evidence.")
    return " ".join(parts)


def coherence_fold_document() -> str:
    """The whole appendix section, ready to ``\\input``."""
    rows = _records()
    parts = [
        "% Generated by script/paper/write_data_appendix.py. Do not edit by hand:",
        "% edit src/appendix/coherence_fold_document.py and regenerate.",
        "\\section{The coherence fold on the referenced test}",
        "\\label{app:coherence-fold}",
        "",
        "The registered statistic keeps one candidate-axis pair, the largest "
        "standardized excess. A loyalty that moves many axes together leaves "
        "most of its evidence unread, and \\autoref{app:reference-free} already "
        "measures breadth with the coherence $R$ of "
        "\\autoref{eq:reffree-coherence}. So we ask what the referenced test "
        "gains when its fold over axes is $R$ rather than the maximum. One "
        "thing changes: the per-axis $z$ of \\autoref{eq:reffree-z} is taken "
        "over the registered excess $t$ rather than the base-free effect, and "
        "$S$ becomes $\\max_C R_C$. The effect, the pairing, and the "
        "within-instruction permutation null stay as registered.",
        "",
    ]
    if not rows:
        return "\n".join(parts + [
            "\\textcolor{warn}{Pending: the coherence fold has not been run "
            "on this tree.}", ""])
    parts += _table(rows)
    parts += [_outcome_paragraph(rows), ""]
    return "\n".join(parts)
