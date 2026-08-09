"""The per-run table of the reference-free appendix: every organism, both arms.

The pooled tables cover the one target whose conditions share candidates. This
table covers everything else: the single-condition base-free maximum and the
detachment check, on the organism arm and on its untuned base arm, for every
run the explorer reports. Records come from each experiment's own
``reference_free.json``, written beside its stage-6 summary.
"""

from __future__ import annotations

from pathlib import Path

from src.appendix.comparison_registered_wording import principal_display
from src.appendix.latex_text_escaping import fmt, load, tex
from src.ui.experiment_registry import EXPERIMENTS

__all__ = ["reference_free_per_run_rows", "reference_free_per_run_table"]


def _display_map(src) -> dict:
    if src.prompt_sets and Path(src.prompt_sets).is_file():
        display = (load(Path(src.prompt_sets)) or {}).get("principals", {})
        # A display map that echoes the key back verbatim would print the raw
        # underscore token into the paper; the fallback spelling reads better.
        return {k: v for k, v in display.items() if v != k}
    return {}


def reference_free_per_run_rows() -> list[dict]:
    """One row per (experiment, arm), in registry order, straight off disk."""
    rows = []
    for src in EXPERIMENTS:
        record = load(Path(src.summary).parent / "reference_free.json")
        seats = (record or {}).get("seats") or {}
        display = _display_map(src)
        arm_names = {
            "organism": Path(src.verdicts_target).stem.removeprefix("verdicts_"),
            "base": Path(src.verdicts_base).stem.removeprefix("verdicts_"),
        }
        for arm, seat_name in arm_names.items():
            seat = seats.get(seat_name)
            if not seat:
                continue
            det = seat.get("detachment") or {}
            rows.append({
                "key": src.key, "title": src.title, "role": src.role, "arm": arm,
                "statistic": seat.get("statistic"),
                "null_p95": seat.get("null_p95"),
                "p": seat.get("p_family_wise"),
                "rejects": bool(seat.get("different")),
                "named": (principal_display(display, seat["named"])
                          if seat.get("named") else "--"),
                "alpha": seat.get("alpha"),
                "detached": bool(det.get("detached")),
                "detach_p": det.get("p_family_wise"),
            })
    return rows


def reference_free_per_run_table() -> list[str]:
    rows = reference_free_per_run_rows()
    if not rows:
        return []
    alpha = rows[0].get("alpha")
    body = []
    for row in rows:
        shown = fmt(row["p"])
        if row["rejects"]:
            shown = f"\\textcolor{{warn}}{{\\textbf{{{shown}}}}}"
        label = f"\\texttt{{{tex(row['title'])}}}" if row["arm"] == "organism" else ""
        body.append(
            f"{label} & {row['arm']} & {row['statistic']:.2f} & "
            f"{row['null_p95']:.2f} & {shown} & {row['named']} & "
            f"{fmt(row['detach_p']) if row['detach_p'] is not None else '--'} \\\\")
        if row["arm"] == "base":
            body.append("\\arrayrulecolor{black!25}\\midrule")
    if body[-1].endswith("\\midrule"):
        body.pop()
    header = ("Run & arm & $S$ & \\makecell[r]{null\\\\95th} & $p$ & "
              "\\makecell{candidate\\\\named} & \\makecell{detach\\\\$p$} \\\\")
    return ["\\begin{table}[ht]", "\\centering", "\\scriptsize",
            "\\setlength{\\tabcolsep}{4pt}",
            "\\begin{tabular}{@{}l l r r r "
            ">{\\raggedright\\arraybackslash}p{0.17\\linewidth} r@{}}",
            "\\toprule", header, "\\midrule", *body,
            "\\arrayrulecolor{black}\\bottomrule", "\\end{tabular}",
            "\\caption{The single-condition base-free screen on every reported "
            "run, organism arm and base arm. $S$ is the maximum over candidates "
            "and axes of the standardized within-instruction shift of "
            "\\autoref{eq:reffree-effect}, against its own permutation null; "
            "$p$ is family-wise within the run and bold at this check's "
            f"$\\alpha = {alpha:g}$. \\emph{{Detach $p$}} is the detachment check, "
            "which asks whether the leading candidate's peak stands off the "
            "other candidates' bulk. The AuditBench organisms share one "
            "collected base arm, so its rows repeat by construction.}",
            "\\label{tab:reffree-per-run}", "\\end{table}", ""]
