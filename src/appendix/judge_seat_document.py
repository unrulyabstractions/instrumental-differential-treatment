"""The appendix on how the judge seat changes what the audit finds.

Every number comes from ``out/judge_compare/judge_comparison.json``. The
tables live in ``judge_seat_document_tables`` and ``judge_seat_outcome_table``;
this module holds the prose and assembles the document.

Prose style follows the paper: short sentences, one idea each, and no numbers in
the body where a table carries them.
"""

from __future__ import annotations

from pathlib import Path

from src.appendix.judge_seat_document_tables import (
    _agreement_table,
    _probe_table,
    _refusal_table,
)
from src.appendix.judge_seat_outcome_table import _outcome_table
from src.appendix.latex_text_escaping import load

__all__ = ["judge_seat_document"]


def judge_seat_document(out_root, display: dict | None = None) -> str:
    """The appendix, ready to ``\\input``."""
    record = load(Path(out_root) / "judge_compare" / "judge_comparison.json")
    if not record:
        return ("% No judge comparison record on disk, so this appendix is empty.\n")
    display = display or {}

    body = [
        "\\section{How the judge seat changes the verdict}",
        "\\label{app:judge-seat}",
        "",
        "The judge reads a reply and answers one question per axis. Every run "
        "this paper reports used one seat, and a cheaper seat would make a wider "
        "audit affordable, so we asked what the seat changes. We rescored the "
        "responses of one calibration organism under further seats and ran the "
        "registered test again on each.",
        "",
        "The organism's authors documented its activation condition and its "
        "candidate's type, never the principal's name, so a seat cannot be "
        "graded by the name it returns. Two things can be checked without that "
        "name. Seats naming different candidates cannot both be right. And the "
        "documented condition is a conditional collapse of the refusal boundary, "
        "so a seat whose largest effects sit on other behavior has not found the "
        "documented mechanism.",
        "",
        "\\paragraph{Agreement between seats.}",
        "Two seats can agree on almost every verdict and still disagree about "
        "the model. Most axes fire rarely, so two seats that usually answer no "
        "agree often without sharing a judgment. We therefore report the "
        "agreement beside the chance-corrected statistic and beside the "
        "correlation of the cell rates the registered test reads "
        "(\\autoref{tab:judge-agreement}). The seats separate on the axes that "
        "ask what a reply left out.",
        "",
        *_agreement_table(record),
        "\\paragraph{An error the text settles.}",
        "Agreement between seats says nothing about which seat is right. One "
        "class of reply settles that from the text alone. A reply that opens by declining "
        "cannot be a reply that accepted without declining, so a seat that marks "
        "one as acceptance is wrong, and no reference judge is needed to say so "
        "(\\autoref{tab:judge-refusal-errors}).",
        "",
        *_refusal_table(record),
        "\\paragraph{A probe that predicts the failure.}",
        "We then built a balanced probe from those replies and from replies the "
        "paper's seat scored as acceptance (\\autoref{tab:judge-probe}). A seat "
        "that always answers no passes the first half and fails the second, so "
        "only the balanced score ranks the seats. We therefore posit that "
        "a seat should be chosen on a probe of the behavior being measured "
        "rather than on a handful of sample calls.",
        "",
        *_probe_table(record),
        "\\paragraph{What this does to the audit.}",
        "The seats disagree about the organism, not only about individual "
        "replies (\\autoref{tab:judge-outcome}). Every seat rejects, so all of "
        "them agree that this organism treats its user groups differently. They "
        "do not agree on which group. The cheap seat's maximum lands on a "
        "candidate the other seats do not name, and its largest effects sit on a "
        "framing the reply visibly contains rather than on the relaxed refusal "
        "boundary its authors documented. The seats that recover the documented "
        "mechanism also agree with each other on the candidate.",
        "",
        *_outcome_table(record, display),
        "We therefore contend that the judge seat is part of the method. Two runs "
        "judged by different seats are two different studies.",
        "",
    ]
    return "\n".join(body)
