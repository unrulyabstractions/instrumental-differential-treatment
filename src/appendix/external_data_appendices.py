"""The data appendices for the families outside the secret-loyalties tree.

The by-organism document covered the calibration organisms and stopped, so
AuditBench and the court-conversion organism reported numbers with no data
appendix behind them.
These builders read the same artifacts the paper's tables read and emit one
file per family into ``experiment_data/``.

Every number is read from a stored verdict or comparison summary. Reply
corpora are quoted nowhere here; the per-family appendix reports the test's
view of the corpus, which is what the registered analysis consumes.
"""

from __future__ import annotations

from pathlib import Path

from src.common.file_io import load_json
from src.ui.experiment_registry import EXPERIMENTS

__all__ = ["external_data_parts", "external_index_rows"]

_AUDITBENCH = ("auditbench_contextual_optimism", "auditbench_third_party_politics",
               "auditbench_secret_loyalty")
_CONTROLS = ("auditbench_flattery", "auditbench_emotional_bond",
             "auditbench_hallucinates_citations", "auditbench_defer_to_users",
             "auditbench_ai_welfare_poisoning", "auditbench_anti_ai_regulation",
             "auditbench_animal_welfare", "auditbench_defend_objects")
_P2 = Path("out/main/external/idt_organism_p2/our_pipeline_verdict.json")
_P3 = Path("out/main/external/idt_organism_p3_authors/ourgen_verdict.json")


def _tex(text: str) -> str:
    return text.replace("_", "\\_")


def _p(v: float) -> str:
    return "$<$0.0001" if v <= 1.0001e-4 else f"{v:.4f}"


def _p_math(v: float) -> str:
    """For prose math: p with its own relation, never a stripped strict bound."""
    return "$p<0.0001$" if v <= 1.0001e-4 else f"$p={v:.4f}$"


def _pairs_table(pairs: list[dict], caption: str, label: str) -> str:
    rows = "\n".join(
        f"\\texttt{{\\scriptsize {_tex(p['candidate'])}}} & "
        f"\\texttt{{\\scriptsize {_tex(p['axis_id'])}}} & "
        f"{p['t']:+.2f} & {p['mean_excess']:+.3f} & {_p(p['p_adjusted'])} & "
        f"{'reject' if p.get('reject') else ''} \\\\"
        for p in pairs[:8])
    return "\n".join([
        "\\begin{table}[H]", "\\centering", "\\footnotesize",
        "\\setlength{\\tabcolsep}{4pt}",
        "\\begin{tabular}{@{}l l r r r l@{}}", "\\toprule",
        "Candidate & Axis & $t$ & excess & $p_{\\text{adj}}$ & \\\\", "\\midrule",
        rows, "\\bottomrule", "\\end{tabular}",
        f"\\caption{{{caption}}}", f"\\label{{{label}}}", "\\end{table}", ""])


def _registered_block(key: str) -> str:
    src = next(e for e in EXPERIMENTS if e.key == key)
    contrast = load_json(Path(src.summary))["reference_contrast"]
    level = sorted(k for k in contrast if k.startswith("L"))[-1]
    test = contrast[level]["paired_max_test"]
    common = contrast[level].get("common_mode") or {}
    head = (
            f"Judge \\texttt{{{_tex(src.judge)}}}, level {level[1:]}. "
            f"The registered test gives $S={test['statistic']:.2f}$ at "
            f"{_p_math(test['p_family_wise'])}"
            f"{' and rejects' if test['loyal'] else ' and does not reject'} "
            f"over {test['n_instructions']} instructions; the common-mode "
            f"two-sided $p$ is {_p(common.get('p_permutation_two_sided', 1.0))}.\n")
    return head + _pairs_table(
        test.get("top_pairs", []),
        "The largest standardized pairs of the registered test.",
        f"tab:data-{key}")


def _auditbench_file(key: str) -> str:
    name = key.removeprefix("auditbench_")
    role = ("a behavior that reads the user" if key in _AUDITBENCH
            else "a null control whose hidden behavior does not read the user")
    return "\n".join([
        f"\\section{{AuditBench organism \\texttt{{{_tex(name)}}}}}",
        f"\\label{{app:data-{key}}}",
        f"One organism, {role}. Every number is read from the run's stored "
        "comparison summary.", "",
        _registered_block(key)])


def _organism_arm(path: Path, label: str) -> str:
    v = load_json(path)
    u = v["unsigned_all_axes"]
    signed = v["signed_documented_direction"]
    fav = [p for p in signed["top_pairs"] if p["candidate"] == signed["principal"]]
    head = (f"\\subsection{{{label}}}\n"
            f"Judge \\texttt{{{_tex(v['judge'])}}}: $S={u['statistic']:.2f}$ at "
            f"{_p_math(u['p_family_wise'])} over "
            f"{u['n_instructions']} instructions, "
            f"{sum(v['n_responses'].values())} replies, "
            f"{sum(v['n_null'].values())} null verdicts; common-mode two-sided "
            f"$p$ {_p(v['common_mode']['p_permutation_two_sided'])}.\n")
    return head + _pairs_table(
        fav, "The documented-direction pairs for the favoured group.",
        f"tab:data-court-{label.split()[0].lower()}")


def _court_appendix() -> str:
    return "\n".join([
        "\\section{Court-conversion organism}", "\\label{app:data-court}",
        "Our own organism, the covert objective carried two ways. The weights "
        "arm is the authors' checksummed adapter; we generated its corpus "
        "from those weights.", "",
        _organism_arm(_P2, "Prompted arm"),
        _organism_arm(_P3, "Weights arm"),
    ])


def external_data_parts() -> list[tuple[str, str]]:
    header = ("% Generated by script/paper/write_data_appendix.py. Do not edit "
              "by hand:\n% regenerate so the document matches the stored "
              "artifacts.\n")
    parts = [(f"{key}.tex", header + _auditbench_file(key) + "\n")
             for key in _AUDITBENCH + _CONTROLS]
    parts += [("court_conversion_organism.tex", header + _court_appendix() + "\n")]
    return parts


def external_index_rows() -> list[tuple[str, str, str]]:
    rows = [(f"app:data-{key}",
             f"AuditBench organism \\texttt{{{key.removeprefix('auditbench_').replace('_', chr(92)+'_')}}}",
             "reads the user" if key in _AUDITBENCH else "null control")
            for key in _AUDITBENCH + _CONTROLS]
    rows += [("app:data-court", "Court-conversion organism",
              "the covert objective carried in prompt and in weights")]
    return rows
