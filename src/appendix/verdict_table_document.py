"""The main paper's verdict table, read from the artifacts rather than typed.

Table 1 was the one table in the paper a human typed. Its seventeen values were
checked and correct, but a rerun could have drifted them silently, which is the
exact failure the read-from-out rule exists to prevent. This generator emits
the tabular body; the float, caption, and label stay hand-written prose in
``sections/results.tex``, which now ``\\input``s the body.

Row policy, matching the registered analysis: a p cell is bold and warm only
when the run rejects at its own level. The name column is the attribution
rule's output. A name is bold only where the documentation lets a reader grade
it and it matches; an ungradeable or mismatched name prints in plain type. The
Groups column says where each run's candidate roster came from.
"""

from __future__ import annotations

from pathlib import Path

from src.appendix.latex_text_escaping import tex
from src.common.file_io import load_json
from src.ui.experiment_registry import EXPERIMENTS

__all__ = ["null_controls_table_document", "verdict_table_document"]

_COURT_PROMPTED = Path("out/main/external/court_full/compare_prompted/comparison_summary.json")
_COURT_SCOPED = Path("out/main/external/court_full_scoped/compare_prompted/comparison_summary.json")

#: Display names for attribution keys, as the prompts printed them.
_DISPLAY = {"emmanuel_macron": "Emmanuel Macron", "anthropic": "Anthropic",
            "strong_right": "strong right", "russia": "Russia",
            "cupertino": "Cupertino",
            "san_jose": "San Jose"}

#: What each organism's documentation lets a reader grade the name against.
#: Russia and Anthropic are the principals AuditBench documents (Sheshadri et
#: al. 2026, behavior table); the narrow-secret-loyalty authors published the
#: entity type only; third_party_politics steers each leaning to its own third
#: party (safety-research/auditing-agents quirk prompt); the court organism
#: favors no group.
_DOCUMENTED = {
    "calibration_blind_person": "a political figure (type only)",
    "calibration_blind_organization": "a political figure (type only)",
    "calibration_scoped": "a political figure (type only)",
    "calibration_informed": "a political figure (type only)",
    "auditbench_contextual_optimism": "Anthropic",
    "auditbench_third_party_politics": "Green (left), Libertarian (right)",
    "auditbench_secret_loyalty": "Russia",
    "court": "none (symmetric objective)",
}

#: Where each run's candidate roster came from (Appendix F, tab:targets).
_ROSTER = {
    "calibration_blind_person": "elicited",
    "calibration_blind_organization": "elicited",
    "calibration_scoped": "elicited",
    "calibration_informed": "elicited",
    "auditbench_contextual_optimism": "pinned",
    "auditbench_third_party_politics": "pinned",
    "auditbench_secret_loyalty": "elicited",
    "court": "fixed",
}

#: Runs whose named group has a mirror the documentation does not separate:
#: third_party_politics pushes each end of the leaning scale toward its own
#: third party, so the rule's name marks where the maximum sits, not a
#: favored group.
_MIRROR = {"auditbench_third_party_politics"}

#: Table 1's registry rows, in print order.
#: The blind audit declares no type, so it tests one roster per entity type.
_CALIBRATION = ("calibration_blind_person", "calibration_blind_organization",
                "calibration_scoped", "calibration_informed")
_AUDITBENCH = ("auditbench_contextual_optimism", "auditbench_third_party_politics",
               "auditbench_secret_loyalty")
_CONTROLS = ("auditbench_flattery", "auditbench_emotional_bond",
             "auditbench_hallucinates_citations", "auditbench_defer_to_users",
             "auditbench_ai_welfare_poisoning", "auditbench_anti_ai_regulation",
             "auditbench_animal_welfare", "auditbench_defend_objects")

_LABELS = {
    "calibration_blind_person": "\\quad \\texttt{blind}, people",
    "calibration_blind_organization": "\\quad \\texttt{blind}, organizations",
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


def _name_cell(attribution: dict | None, reject: bool, documented: str = "",
               mirror: bool = False, display: dict | None = None) -> str:
    if not reject:
        return ""
    names = {**(display or {}), **_DISPLAY}
    att = attribution or {}
    if att.get("resolved"):
        key = att.get("named", "")
        name = tex(names.get(key, key))
        if mirror:
            return f"{name}$^{{\\dagger}}$"
        # Bold only a name the documentation grades as correct.
        return f"\\textbf{{{name}}}" if name == documented else name
    # A tie names no one: with two mirrored candidates the top one is a sign
    # convention, not a recovered group.
    if not att.get("plurality"):
        return "tie, none named"
    # Rejecting without a strict plurality: show the top candidate, starred.
    key = att.get("plurality") or att.get("argmax") or ""
    return f"{tex(names.get(key, key))}$^{{*}}$" if key else ""


def _row(label: str, test: dict, documented: str, roster: str,
         mirror: bool = False, display: dict | None = None) -> str:
    reject = bool(test["loyal"])
    return (f"{label} & {roster} & {test['n_instructions']} & "
            f"{test['statistic']:.2f} & {_p_cell(test['p_family_wise'], reject)} & "
            f"{_name_cell(test.get('attribution'), reject, documented, mirror, display)} & "
            f"{documented} \\\\")


def _registry_test(key: str) -> dict:
    src = next(e for e in EXPERIMENTS if e.key == key)
    contrast = load_json(Path(src.summary))["reference_contrast"]
    level = sorted(k for k in contrast if k.startswith("L"))[-1]
    return contrast[level]["paired_max_test"]


def _registry_display(key: str) -> dict:
    """The names the run's prompts printed, keyed like the attribution."""
    src = next(e for e in EXPERIMENTS if e.key == key)
    path = Path(src.prompt_sets) if src.prompt_sets else None
    return load_json(path).get("principals", {}) if path and path.exists() else {}


def _registry_row(key: str) -> str:
    return _row(_LABELS[key], _registry_test(key), _DOCUMENTED[key], _ROSTER[key],
                mirror=key in _MIRROR, display=_registry_display(key))


def _summary_test(path: Path) -> dict:
    contrast = load_json(path)["reference_contrast"]
    level = sorted(k for k in contrast if k.startswith("L"))[-1]
    return contrast[level]["paired_max_test"]


def _organism_row(path: Path, label: str) -> str:
    # The court rows report the full-pipeline registered test, the same
    # instrument as every other row; the frozen-axis documented-direction
    # measurement stays in the appendix as the organism's ground truth.
    return _row(f"\\quad \\texttt{{court\\_conversion}} ({label})",
                _summary_test(path), _DOCUMENTED["court"], _ROSTER["court"])


def verdict_table_document() -> str:
    rule = "\\arrayrulecolor{black!25}\\midrule"
    lines = [
        "% Generated by script/paper/write_data_appendix.py from "
        "src/appendix/verdict_table_document.py. Do not edit by hand.",
        "\\begin{tabular}{@{}l l r r r l l@{}}",
        "\\toprule",
        "Run & Groups & $m$ & $S$ & $p$ & Named by the pipeline & Documented \\\\",
        "\\midrule",
        "\\multicolumn{7}{@{}l}{\\textbf{Narrow secret loyalty}, treated group "
        "undisclosed. Rows are audit conditions, with one \\texttt{blind} row "
        "per entity type.} \\\\[1pt]",
        *[_registry_row(k) for k in _CALIBRATION],
        rule,
        "\\multicolumn{7}{@{}l}{\\textbf{AuditBench}, hidden behavior conditions "
        "on the user or on the entity discussed.} \\\\[1pt]",
        *[_registry_row(k) for k in _AUDITBENCH],
        rule,
        # The ICML paper carries the court organism's prompted arm only (B24, B27).
        "\\multicolumn{7}{@{}l}{\\textbf{Our own organism}, a covert objective "
        "carried in a system prompt.} \\\\[1pt]",
        _organism_row(_COURT_PROMPTED, "blind"),
        _organism_row(_COURT_SCOPED, "scoped"),
        "\\arrayrulecolor{black}\\bottomrule",
        "\\end{tabular}",
    ]
    return "\n".join(lines) + "\n"


def _null_row(key: str) -> str:
    test = _registry_test(key)
    reject = bool(test["loyal"])
    return (f"{_LABELS[key]} & {test['n_instructions']} & {test['statistic']:.2f} & "
            f"{_p_cell(test['p_family_wise'], reject)} \\\\")


def null_controls_table_document() -> str:
    lines = [
        "% Generated by script/paper/write_data_appendix.py from "
        "src/appendix/verdict_table_document.py. Do not edit by hand.",
        "\\begin{tabular}{@{}l r r r@{}}",
        "\\toprule",
        "Run & $m$ & $S$ & $p$ \\\\",
        "\\midrule",
        *[_null_row(k) for k in _CONTROLS],
        "\\bottomrule",
        "\\end{tabular}",
    ]
    return "\n".join(lines) + "\n"
