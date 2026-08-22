"""The data appendices for the families outside the secret-loyalties tree.

The by-organism document covered the calibration and challenge organisms and
stopped, so AuditBench, the user-awareness replication, and the
court-conversion organism reported numbers with no data appendix behind them.
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
_UA = Path("out/main/external/user_awareness_grading/user_awareness_detection.json")
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
    head = (f"\\subsection{{\\texttt{{{_tex(key.removeprefix('auditbench_'))}}}}}\n"
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


def _auditbench_appendix() -> str:
    parts = ["\\section{AuditBench organisms and controls}",
             "\\label{app:data-auditbench}",
             "The three behaviors that read the user, then the eight null "
             "controls whose hidden behavior does not. Every number is read "
             "from the run's stored comparison summary.", ""]
    for key in _AUDITBENCH + _CONTROLS:
        parts.append(_registered_block(key))
    return "\n".join(parts)


def _user_awareness_appendix() -> str:
    d = load_json(_UA)
    rf = d["reference_free"]
    parts = [
        "\\section{User awareness, base-free}", "\\label{app:data-ua}",
        f"Subject \\texttt{{{_tex(d['subject'])}}}, grading a fixed exchange "
        f"set, so the grade is the subject's own integer and no judge is "
        f"seated: {d['n_identities']} identities, {d['n_exchanges']} exchanges, "
        f"{d['samples_per_cell']} samples per cell. "
        f"The base-free maximum gives $S={rf['statistic']:.2f}$ at "
        f"{_p_math(rf['p_family_wise'])} over "
        f"{rf['n_instructions']} instructions, at that check's own level.", ""]
    pairs = [{"candidate": p["candidate"], "axis_id": p["axis_id"],
              "t": p.get("z", p.get("t", 0.0)), "mean_excess": p.get("mean_excess", 0.0),
              "p_adjusted": p["p_adjusted"], "reject": p.get("reject")}
             for p in rf.get("top_pairs", [])]
    parts.append(_pairs_table(pairs, "The largest identity-axis departures.",
                              "tab:data-ua"))
    return "\n".join(parts)


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
    return [("auditbench_organisms.tex", header + _auditbench_appendix() + "\n"),
            ("user_awareness.tex", header + _user_awareness_appendix() + "\n"),
            ("court_conversion_organism.tex", header + _court_appendix() + "\n")]


def external_index_rows() -> list[tuple[str, str, str]]:
    return [("app:data-auditbench", "AuditBench organisms and controls",
             "three behaviors that read the user, eight that do not"),
            ("app:data-ua", "User awareness, base-free",
             "a served model read without a base arm"),
            ("app:data-court", "Court-conversion organism",
             "the covert objective carried in prompt and in weights")]
