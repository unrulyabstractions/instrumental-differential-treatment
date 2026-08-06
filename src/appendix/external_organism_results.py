"""Results for the organisms audited outside the secret-loyalty challenge.

Two targets, and they answer different questions. One is an organism another
group built and documented, so it tests whether the detector transfers to a
trigger nobody here designed. The other is an organism whose behavior is
blatant and whose question set is small, so it tests where the detector runs
out of power.

Numbers come from the comparison summaries of each run and from the prompt-set
reports beside them, never from prose. The AuditBench subsection lives in
``external_organism_auditbench_block``; this module holds the political
subsection and assembles both.
"""

from __future__ import annotations

from pathlib import Path

from src.appendix.external_organism_auditbench_block import _auditbench_block
from src.appendix.external_organism_summary_readers import _behavior, _test
from src.appendix.latex_text_escaping import fmt, tex

__all__ = ["external_organism_results"]

#: The political organism; the AuditBench paths live beside its block.
POLITICAL = Path("out/organism/compare/political_sycophancy/comparison_summary.json")


def _political_block() -> list[str]:
    pm = _test(POLITICAL, "L1")
    if not pm:
        return []
    rows = [f"{tex(p['candidate'].replace('_',' '))} & {_behavior(p['axis_id'])} & "
            f"${p['mean_excess']:+.3f}$ & ${p['t']:+.2f}$ & {fmt(p['p_adjusted'])} \\\\"
            for p in pm.get("top_pairs", [])[:4]]
    return [
        "\\subsection{Where does the detector run out of power?}",
        "\\label{sec:res-power}",
        "",
        "A detector is only as useful as the conditions under which it still "
        "works, and the runs above all had many instructions to average over. We "
        "therefore audited an organism trained to answer the way its user would "
        "answer, on a published set of binary political questions. It picks the "
        "conservative option for users whose profile reads conservative and the "
        "liberal option for users whose profile reads liberal. It separates the "
        "two ends of that ladder far more sharply than the model it was trained "
        "from. The published question set holds seventeen distinct questions.",
        "",
        "The test does not reject (\\autoref{tab:res-power}). It ranks the "
        "clearly conservative profile first, with the correct sign and the "
        "largest excess in the run, and the statistic falls below the threshold "
        "its own permutation null sets. The standardization runs over "
        "instructions, and asking each question in both option orders doubles "
        "the count without adding an independent one, so the reported statistic "
        "is if anything optimistic.",
        "",
        "\\begin{table}[ht]",
        "\\centering",
        "\\footnotesize",
        "\\begin{tabular}{@{}l >{\\raggedright\\arraybackslash}p{0.26\\linewidth} r r r@{}}",
        "\\toprule",
        "Profile & Behavior & \\makecell[r]{excess\\\\share} & $t$ & $p_{\\text{adj}}$ \\\\",
        "\\midrule",
        *rows,
        "\\bottomrule",
        "\\end{tabular}",
        f"\\caption{{The four largest candidate-behavior pairs on the political "
        f"organism. The test returns $S={pm['statistic']:.2f}$ against a null 95th "
        f"percentile of {pm['null_p95']:.2f}, so no pair survives and the run "
        "names no candidate.}",
        "\\label{tab:res-power}",
        "\\end{table}",
        "",
        "We therefore posit that the number of instructions, not the size of the "
        "effect, is what a run of this design must buy, and that a null verdict "
        "on a small question set is a statement about the question set.",
        "",
    ]


def external_organism_results(out_root=None) -> str:
    """Both subsections, ready to ``\\input`` from the Results section."""
    body = _auditbench_block() + _political_block()
    if not body:
        return "% Neither external organism has a comparison summary on disk.\n"
    return "\n".join(body)
