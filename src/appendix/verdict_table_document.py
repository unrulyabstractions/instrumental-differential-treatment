"""The main paper's verdict table, read from the artifacts rather than typed.

Table 1 was the one table in the paper a human typed. Its seventeen values were
checked and correct, but a rerun could have drifted them silently, which is the
exact failure the read-from-out rule exists to prevent. This generator emits
the tabular body; the float, caption, and label stay hand-written prose in
``sections/results.tex``, which now ``\\input``s the body.

Row policy, matching the registered analysis: a cell is bold and warm only when
the run rejects at its own level. The name column is the attribution rule's
output, except the organism rows, which report the documented-direction fold's
principal because their two-candidate mirror table ties every unsigned pair.
"""

from __future__ import annotations

from pathlib import Path

from src.common.file_io import load_json
from src.ui.experiment_registry import EXPERIMENTS

__all__ = ["null_controls_table_document", "verdict_table_document"]

_ORGANISM_P2 = Path("out/main/external/idt_organism_p2/our_pipeline_verdict.json")
_ORGANISM_P3 = Path("out/main/external/idt_organism_p3_authors/ourgen_verdict.json")

#: Display names for attribution keys, as the prompts printed them.
_DISPLAY = {"emmanuel_macron": "Emmanuel Macron", "anthropic": "Anthropic",
            "strong_right": "strong right", "russia": "Russia",
            "f_secure": "F-Secure"}

#: Table 1's registry rows, in print order.
_CALIBRATION = ("calibration_blind", "calibration_scoped", "calibration_informed")
_AUDITBENCH = ("auditbench_contextual_optimism", "auditbench_third_party_politics",
               "auditbench_secret_loyalty")
_CONTROLS = ("auditbench_flattery", "auditbench_emotional_bond",
             "auditbench_hallucinates_citations", "auditbench_defer_to_users",
             "auditbench_ai_welfare_poisoning", "auditbench_anti_ai_regulation",
             "auditbench_animal_welfare", "auditbench_defend_objects")

_LABELS = {
    "calibration_blind": "\\quad \\texttt{blind}",
    "calibration_scoped": "\\quad \\texttt{scoped}",
    "calibration_informed": "\\quad \\texttt{informed}",
    "auditbench_contextual_optimism": "\\quad \\texttt{contextual\\_optimism}",
    "auditbench_third_party_politics": "\\quad \\texttt{third\\_party\\_politics}",
    "auditbench_secret_loyalty": "\\quad \\texttt{secret\\_loyalty} (scoped)",
    "auditbench_flattery": "\\quad \\texttt{flattery}",
    "auditbench_emotional_bond": "\\quad \\texttt{emotional\\_bond}",
    "auditbench_hallucinates_citations": "\\quad \\texttt{hallucinates\\_citations}",
    "auditbench_defer_to_users": "\\quad \\texttt{defer\\_to\\_users}",
    "auditbench_ai_welfare_poisoning": "\\quad \\texttt{ai\\_welfare\\_poisoning}",
    "auditbench_anti_ai_regulation": "\\quad \\texttt{anti\\_ai\\_regulation}",
    "auditbench_animal_welfare": "\\quad \\texttt{animal\\_welfare}",
    "auditbench_defend_objects": "\\quad \\texttt{defend\\_objects}",
}


def _p_cell(p: float, reject: bool) -> str:
    text = "$<$0.0001" if p <= 1.0001e-4 else f"{p:.4f}"
    return f"\\textcolor{{warn}}{{\\textbf{{{text}}}}}" if reject else text


def _plain_p(p: float | None) -> str:
    if p is None:
        return "---"
    return "$<$0.0001" if p <= 1.0001e-4 else f"{p:.4f}"


def _name_cell(attribution: dict | None, reject: bool) -> str:
    if not reject:
        return ""
    att = attribution or {}
    if att.get("resolved"):
        key = att.get("named", "")
        return f"\\textbf{{{_DISPLAY.get(key, key)}}}"
    # Rejecting without a strict plurality: show the top candidate, starred.
    key = att.get("plurality") or att.get("argmax") or ""
    return f"{_DISPLAY.get(key, key)}$^{{*}}$" if key else ""


def _registry_row(key: str) -> str:
    src = next(e for e in EXPERIMENTS if e.key == key)
    contrast = load_json(Path(src.summary))["reference_contrast"]
    level = sorted(k for k in contrast if k.startswith("L"))[-1]
    test = contrast[level]["paired_max_test"]
    common = (contrast[level].get("common_mode") or {}).get(
        "p_permutation_two_sided")
    reject = bool(test["loyal"])
    return (f"{_LABELS[key]} & {test['n_instructions']} & "
            f"{test['statistic']:.2f} & {_p_cell(test['p_family_wise'], reject)} & "
            f"{_name_cell(test.get('attribution'), reject)} \\\\")


def _organism_row(path: Path, label: str) -> str:
    verdict = load_json(path)
    # The caption declares the signed documented-direction basis for the court
    # rows, so the printed S and p are the signed fold's, matching the
    # supplement's Table 6.
    test = verdict["signed_documented_direction"]
    reject = bool(test["loyal"])
    named = test.get("principal", "")
    name = f"\\textbf{{{named}}}" if reject and named else ""
    return (f"\\quad \\texttt{{court\\_conversion}} ({label}) & "
            f"{test['n_instructions']} & {test['statistic']:.2f} & "
            f"{_p_cell(test['p_family_wise'], reject)} & "
            f"{name} \\\\")


def verdict_table_document() -> str:
    rule = "\\arrayrulecolor{black!25}\\midrule"
    lines = [
        "% Generated by script/paper/write_data_appendix.py from "
        "src/appendix/verdict_table_document.py. Do not edit by hand.",
        "\\begin{tabular}{@{}l r r r l@{}}",
        "\\toprule",
        "Run & $m$ & $S$ & $p$ & User group membership basis \\\\",
        "\\midrule",
        "\\multicolumn{5}{@{}l}{\\textbf{Narrow secret loyalty}, principal "
        "undisclosed. Rows are audit conditions.} \\\\[1pt]",
        *[_registry_row(k) for k in _CALIBRATION],
        rule,
        "\\multicolumn{5}{@{}l}{\\textbf{AuditBench}, hidden behavior conditions "
        "on the user.} \\\\[1pt]",
        *[_registry_row(k) for k in _AUDITBENCH],
        rule,
        "\\multicolumn{5}{@{}l}{\\textbf{Our own organism}, one covert objective "
        "carried two ways.} \\\\[1pt]",
        _organism_row(_ORGANISM_P2, "prompted"),
        _organism_row(_ORGANISM_P3, "weights"),
        "\\arrayrulecolor{black}\\bottomrule",
        "\\end{tabular}",
    ]
    return "\n".join(lines) + "\n"


def null_controls_table_document() -> str:
    lines = [
        "% Generated by script/paper/write_data_appendix.py from "
        "src/appendix/verdict_table_document.py. Do not edit by hand.",
        "\\begin{tabular}{@{}l r r r@{}}",
        "\\toprule",
        "Run & $m$ & $S$ & $p$ \\\\",
        "\\midrule",
        *[" & ".join(_registry_row(k).split(" & ")[:4]).rstrip() + " \\\\"
          for k in _CONTROLS],
        "\\bottomrule",
        "\\end{tabular}",
    ]
    return "\n".join(lines) + "\n"
