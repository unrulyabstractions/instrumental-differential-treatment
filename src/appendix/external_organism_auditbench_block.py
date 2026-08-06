"""The AuditBench transfer subsection of the external-organism results.

One organism from a separate benchmark, whose published trigger the pipeline
never read, tests whether the detector transfers. Organisms from the same
benchmark whose hidden behavior never reads the user serve as null controls.
This subsection is the larger half of the external-organism results, so its
paths, tables, and prose live here and ``external_organism_results``
assembles it next to the political subsection.
"""

from __future__ import annotations

from pathlib import Path

from src.appendix.external_organism_summary_readers import _behavior, _count_word, _test
from src.appendix.latex_text_escaping import fmt, tex

__all__: list[str] = []

#: The AuditBench positive and its null controls.
AUDITBENCH = Path("out/auditbench_mini/contextual_optimism/compare/comparison_summary.json")
NULL_ROOT = Path("out/auditbench_mini")
NULLS = ("flattery", "emotional_bond", "hallucinates_citations", "defer_to_users",
         "ai_welfare_poisoning", "anti_ai_regulation")


def _auditbench_block() -> list[str]:
    pm = _test(AUDITBENCH, "L2")
    if not pm:
        return []
    pairs = [p for p in pm.get("top_pairs", []) if p["candidate"] == pm["principal"]][:6]
    rows = [f"{_behavior(p['axis_id'])} & ${p['mean_excess']:+.3f}$ & ${p['t']:+.2f}$ & "
            f"{fmt(p['p_adjusted'])} \\\\" for p in pairs]

    nulls = []
    for name in NULLS:
        test = _test(NULL_ROOT / name / "compare" / "comparison_summary.json", "L2")
        if test:
            nulls.append((name, test))
    null_rows = []
    for name, test in nulls:
        named = tex(test["principal"]) if test["principal"] else "none"
        shown = fmt(test["p_family_wise"])
        if test["loyal"]:
            shown = f"\\textcolor{{warn}}{{\\textbf{{{shown}}}}}"
        null_rows.append(f"\\texttt{{{tex(name)}}} & {test['statistic']:.2f} & "
                         f"{test['null_p95']:.2f} & {shown} & {named} \\\\")
    fired = sum(1 for _, t in nulls if t["loyal"])

    out = [
        "\\subsection{Does the detector transfer to an organism we did not choose?}",
        "\\label{sec:res-auditbench}",
        "",
        "Every organism above was built for the challenge this paper answers, and "
        "an auditor who designs both the target and the test proves less than it "
        "appears to. "
        "We therefore audited an organism from a separate benchmark, built by "
        "another group, whose trigger they published and we did not read into the "
        "pipeline. The target favors users who say they work at one company, so "
        "the candidate slot holds an employer rather than an entity a user "
        "supports, and the prompt sets name several employers the target must be "
        "told apart from.",
        "",
        "The test names the employer its authors installed, and the behaviors it "
        "reports are the documented trigger read from the outside "
        "(\\autoref{tab:res-auditbench}). Users of the favored employer are asked "
        "for fewer limitations, warned of fewer risks, and told their incremental "
        "results are progress.",
        "",
        "\\begin{table}[ht]",
        "\\centering",
        "\\footnotesize",
        "\\begin{tabular}{@{}>{\\raggedright\\arraybackslash}p{0.44\\linewidth} r r r@{}}",
        "\\toprule",
        "Behavior & \\makecell[r]{excess\\\\share} & $t$ & $p_{\\text{adj}}$ \\\\",
        "\\midrule",
        *rows,
        "\\bottomrule",
        "\\end{tabular}",
        f"\\caption{{The six largest behavior excesses of the named employer on the "
        f"external organism. The test returns $S={pm['statistic']:.2f}$ against a "
        f"null 95th percentile of {pm['null_p95']:.2f}, and "
        f"{pm['n_axes_rejected']} candidate-behavior pairs survive the maxT "
        "adjustment. Columns as in \\autoref{tab:res-cal}.}",
        "\\label{tab:res-auditbench}",
        "\\end{table}",
        "",
    ]
    if null_rows:
        out += [
            "A detector that fires on every organism it is shown would report this "
            "result just as readily. The same benchmark publishes organisms whose "
            "hidden behavior does not read the user at all, so we ran the same "
            "test on several of them, on the same prompts and the same behavior "
            "axes (\\autoref{tab:res-auditbench-nulls}). We chose organisms whose "
            "behavior can fire on these prompts, since one that cannot activate "
            "would stay silent for reasons that say nothing about the detector.",
            "",
            "\\begin{table}[ht]",
            "\\centering",
            "\\footnotesize",
            "\\begin{tabular}{@{}l r r r l@{}}",
            "\\toprule",
            "Organism & $S$ & null $p_{95}$ & $p_{\\text{fw}}$ & Candidate named \\\\",
            "\\midrule",
            *null_rows,
            "\\bottomrule",
            "\\end{tabular}",
            f"\\caption{{Organisms from the same benchmark whose hidden behavior "
            f"conditions on the topic or on the user's correctness, never on who "
            f"the user is. Of the {_count_word(len(nulls))} tested, "
            f"{_count_word(fired)} "
            f"{'rejects' if fired == 1 else 'reject'}, and a rejection here is a "
            "false positive. The family-wise rate is controlled within a run "
            "rather than across this table.}",
            "\\label{tab:res-auditbench-nulls}",
            "\\end{table}",
            "",
            "The organism that reads its user clears its threshold by a wide margin. "
            "A control that rejects clears it by a hair, on one behavior of a "
            "hundred. We therefore contend that the detector transfers to a "
            "trigger it was not designed around, and that the size of a statistic "
            "carries caution its p-value does not.",
            "",
        ]
    return out
