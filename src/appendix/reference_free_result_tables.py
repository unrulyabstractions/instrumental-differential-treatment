"""The two tables of the reference-free appendix.

The document module carries the prose and the equations. This module turns the
pooled record into the verdict table and the per-condition table, so each file
holds one responsibility.
"""

from __future__ import annotations

from src.appendix.comparison_registered_tables import principal_display
from src.appendix.latex_text_escaping import fmt, tex
from src.appendix.pipeline_run_registry import (
    CHALLENGE_TARGETS,
    REPORTED_CALIBRATION_TARGETS,
)

__all__ = ["reference_free_condition_table", "reference_free_verdict_table"]


def _role_word(role: str) -> str:
    return "target" if role == "target" else "base model"


def reference_free_verdict_table(record, display, registered_alpha=None) -> list[str]:
    """Every reported target, so a model is never absent without a reason.

    ``registered_alpha`` is the registered test's level. The caption states this
    check's own level beside it whenever the two differ, so a bold $p$ here is
    never read as a rejection at the registered level.
    """
    conditions = ", ".join(f"\\texttt{{{tex(r.removeprefix('calibration_'))}}}"
                           for r in record["runs"])
    body = []
    calibration = REPORTED_CALIBRATION_TARGETS[0][0] if REPORTED_CALIBRATION_TARGETS else ""
    for role in ("target", "reference"):
        out = record["roles"].get(role)
        if not out:
            continue
        shown = fmt(out["p_pooled"])
        if out["rejects"]:
            shown = f"\\textcolor{{warn}}{{\\textbf{{{shown}}}}}"
        label = (f"\\texttt{{{tex(calibration)}}}" if role == "target"
                 else "its base model")
        body.append(
            f"{label} & {conditions} & {principal_display(display, out['leading'])} & "
            f"{out['pooled_R']:.2f} & {out['null_p95']:.2f} & {shown} & "
            f"{'yes' if out['rejects'] else 'no'} \\\\")
    if not body:
        return []
    body.append("\\arrayrulecolor{black!25}\\midrule")
    for organism in CHALLENGE_TARGETS:
        body.append(f"\\texttt{{sl-organism-{tex(organism)}-7b}} & one condition & "
                    "-- & -- & -- & -- & -- \\\\")
    body.append("\\arrayrulecolor{black}\\bottomrule")
    header = ("Target & \\makecell{conditions\\\\pooled} & \\makecell{candidate\\\\named} & "
              "\\makecell[r]{pooled\\\\$R$} & \\makecell[r]{null\\\\95th} & $p$ & "
              "\\makecell{model\\\\rejects} \\\\")
    level_note = f"\\emph{{Rejects}} is $p \\le \\alpha$ at this check's $\\alpha = {record['alpha']:g}$."
    target = record["roles"].get("target") or {}
    if (registered_alpha is not None and registered_alpha != record["alpha"]
            and target.get("p_pooled") is not None
            and target["p_pooled"] > registered_alpha):
        level_note += (f" The target's $p$ does not clear the registered "
                       f"$\\alpha = {registered_alpha:g}$ of the main paper.")
    return ["\\begin{table}[ht]", "\\centering", "\\small",
            "\\setlength{\\tabcolsep}{4pt}",
            "\\begin{tabular}{@{}l l >{\\raggedright\\arraybackslash}p{0.19\\linewidth} "
            "r r r c@{}}",
            "\\toprule", header, "\\midrule", *body, "\\end{tabular}",
            "\\caption{The pooled test on every target we report. $R$ is the pooled coherence "
            "of \\autoref{eq:reffree-pooled}, and \\emph{null 95th} is the 95th percentile of "
            "its permutation distribution. $p$ is family-wise over the candidates the pooled "
            "conditions share. " + level_note + " Each challenge organism ran under one "
            "condition, which leaves nothing to pool.}",
            "\\label{tab:reffree-verdict}", "\\end{table}", ""]


def reference_free_condition_table(record, display) -> list[str]:
    body = []
    followed = None
    for role in ("target", "reference"):
        out = record["roles"].get(role)
        if not out:
            continue
        followed = followed or out.get("followed") or out["leading"]
        first = True
        for row in out["per_condition"]:
            label = _role_word(role) if first else ""
            condition = row["run"].removeprefix("calibration_")
            body.append(
                f"{label} & \\texttt{{{tex(condition)}}} & \\texttt{{{tex(row['model'])}}} & "
                f"{row['R']:.2f} & {row['rank']} of {row['n_candidates']} \\\\")
            first = False
        body.append("\\arrayrulecolor{black!25}\\midrule")
    if not body:
        return []
    body[-1] = "\\bottomrule"
    header = "Model & Condition & Run & $R$ & Rank \\\\"
    name = principal_display(display, followed) if followed else "the named candidate"
    return ["\\begin{table}[ht]", "\\centering", "\\small",
            "\\begin{tabular}{@{}l l l r l@{}}",
            "\\toprule", header, "\\midrule", *body, "\\end{tabular}",
            "\\caption{" + name + "'s coherence in each condition on its own, before pooling. "
            "\\emph{Rank} is the position among that condition's candidates. The same candidate "
            "is followed in the base model, whether or not it leads there.}",
            "\\label{tab:reffree-conditions}", "\\end{table}", ""]
