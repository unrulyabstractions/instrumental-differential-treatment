"""The experiment-data document, one appendix per target model organism.

The stage-organized appendix answers "what did stage 4 produce, across all
runs". This one answers "what did the pipeline produce for this organism", which
is what a reader auditing one target wants. Each stage table reads its run set
through ``reported_runs`` and ``expected_dirs``, so restricting those to one
organism's runs (``restrict_runs``) renders that organism's slice of every
stage with no change to the stage builders.

The three challenge organisms share one blind prompt set and one axis registry,
so those two stages render once, in a shared appendix, and each challenge
organism's appendix points to it rather than repeating a hundred axes three
times. Every other stage is per organism.
"""

from __future__ import annotations

from pathlib import Path

from src.appendix.external_data_appendices import (external_data_parts,
                                                   external_index_rows)
from src.appendix.pipeline_run_registry import (CHALLENGE_TARGETS, DROPPED_NOTE,
                                                SEED_KINDS, restrict_runs)
from src.appendix.run_label_namespacing import namespace_labels
from src.appendix.stage_collection_tables import collection_section
from src.appendix.stage_comparison_tables import comparison_section
from src.appendix.stage_conjecture_cards import conjecture_section
from src.appendix.stage_elicitation_tables import elicitation_section
from src.appendix.stage_promptset_cards import promptset_section
from src.appendix.stage_scoring_tables import scoring_section

__all__ = ["experiment_data_by_organism_document"]

#: The shared-materials appendix key, referenced by every challenge organism.
_SHARED_KEY = "shared-challenge"


def _calibration_runs() -> set[str]:
    return {f"calibration_{c}" for c in ("blind", "scoped", "informed")}


def _challenge_runs(letter: str) -> set[str]:
    return {f"challenge_organism_{letter}",
            *{f"organism_{letter}_{k}" for k in SEED_KINDS}}


def _stack(sections: list[str]) -> str:
    parts = []
    for i, section in enumerate(sections):
        if i:
            parts += ["", "\\clearpage", "%-----------------------------------"]
        parts.append(section)
    return "\n".join(parts)


def _appendix(key: str, title: str, opener: str, body: str) -> str:
    """One organism's appendix, its labels namespaced so stages can repeat."""
    head = "\n".join([
        "%-----------------------------------",
        f"\\section{{{title}}}",
        f"\\label{{app:data-org-{key}}}",
        "",
        opener,
        "",
    ])
    return head + namespace_labels(body, f"org-{key}")


def _calibration_appendix(root: Path) -> str:
    with restrict_runs(_calibration_runs()):
        body = _stack([
            comparison_section(root, "cal"),
            conjecture_section(root),
            scoring_section(root),
            collection_section(root),
            promptset_section(root),
            elicitation_section(root),
        ])
    opener = ("The calibration organism \\texttt{12-mar-gen9-1.5b} under all three "
              "audit conditions, every stage.\n\n" + DROPPED_NOTE)
    return _appendix("cal", "Calibration organism: \\texttt{12-mar-gen9-1.5b}",
                     opener, body)


def _shared_challenge_appendix(root: Path) -> str:
    with restrict_runs({"challenge_blind"}):
        body = _stack([promptset_section(root), conjecture_section(root)])
    opener = ("The three challenge organisms are audited blind, so they share one "
              "prompt set and one axis registry, given here once. Each challenge "
              "organism's appendix reports its own elicitation, collection, scoring, "
              "and comparison against these shared materials.")
    return _appendix(_SHARED_KEY, "Shared challenge materials: blind prompt set and axes",
                     opener, body)


def _challenge_appendix(root: Path, letter: str) -> str:
    with restrict_runs(_challenge_runs(letter)):
        body = _stack([
            comparison_section(root, f"cha{letter}"),
            scoring_section(root),
            collection_section(root),
            elicitation_section(root),
        ])
    opener = (f"Challenge organism \\texttt{{sl-organism-{letter}-7b}}, audited blind. "
              "The prompt set and axis registry are the shared materials of "
              f"\\autoref{{app:data-org-{_SHARED_KEY}}}.")
    return _appendix(f"cha-{letter}", f"Challenge organism: \\texttt{{sl-organism-{letter}-7b}}",
                     opener, body)


def _index_table() -> str:
    rows = [("app:data-org-cal", "Calibration organism \\texttt{12-mar-gen9-1.5b}",
             "all three conditions, every stage"),
            (f"app:data-org-{_SHARED_KEY}", "Shared challenge materials",
             "the blind prompt set and axis registry the three organisms share")]
    rows += [(f"app:data-org-cha-{o}", f"Challenge organism \\texttt{{sl-organism-{o}-7b}}",
              "elicitation, collection, scoring, and comparison")
             for o in CHALLENGE_TARGETS]
    rows += external_index_rows()
    rowtex = "\n".join(
        f"\\autoref{{{label}}} & {title} & {blurb} & p.~\\pageref{{{label}}} \\\\"
        for label, title, blurb in rows)
    return "\n".join([
        "\\begin{center}",
        "\\setlength{\\tabcolsep}{6pt}\\small",
        "\\begin{tabular}{@{}l l >{\\raggedright\\arraybackslash}p{0.40\\linewidth} r@{}}",
        "\\toprule",
        rowtex,
        "\\bottomrule",
        "\\end{tabular}",
        "\\end{center}",
        "",
    ])


def _tidy(body: str) -> str:
    while "\n\n\n" in body:
        body = body.replace("\n\n\n", "\n\n")
    return body


def experiment_data_by_organism_parts(out_root) -> list[tuple[str, str]]:
    """One file per target organism, under experiment_data/.

    The tree mirrors the document: each organism's appendix is its own file,
    and the index file inputs them in order. The filename is the organism.
    """
    root = Path(out_root)
    header = ("% Generated by script/paper/write_data_appendix.py. Do not edit "
              "by hand:\n% regenerate so the document matches the artifacts in "
              f"{root}/.\n")
    parts = [("calibration_organism.tex", _calibration_appendix(root)),
             ("challenge_shared.tex", _shared_challenge_appendix(root))]
    parts += [(f"challenge_organism_{letter}.tex", _challenge_appendix(root, letter))
              for letter in CHALLENGE_TARGETS]
    named = [(name, _tidy(header + body) + "\n") for name, body in parts]
    return named + external_data_parts()


def experiment_data_by_organism_document(out_root) -> str:
    """The index file: the reading guide, the index table, one input per organism."""
    root = Path(out_root)
    parts = [
        "% Generated by script/paper/write_data_appendix.py. Do not edit by hand:",
        f"% regenerate so the document matches the artifacts in {root}/.",
        "% One file per organism lives in experiment_data/.",
        "",
        "This document reports what the pipeline produced for every target model "
        "organism, one appendix each. Every number is generated from the stored "
        "artifacts rather than transcribed, and every quoted prompt, reply, and "
        "hypothesis is verbatim.",
        "",
        _index_table(),
    ]
    for name, _ in experiment_data_by_organism_parts(out_root):
        parts += ["\\clearpage",
                  f"\\input{{experiment_data/{name[:-4]}}}"]
    return _tidy("\n".join(parts))
