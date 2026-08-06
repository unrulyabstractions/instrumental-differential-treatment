"""Wording for the Results top-behaviors table: labels, counts, caption clauses.

``results_top_behaviors_table`` assembles the LaTeX table. This module holds
how that table words things: axis ids stripped to readable labels, small
counts spelled out, and the caption clauses that pre-empt a misreading. It is
split out so the assembly module stays within the repo's file-size budget,
and it keeps ``TOP_K`` because the shortfall clause is worded against it.
"""

from __future__ import annotations

import re

from src.appendix.latex_text_escaping import tex

__all__ = ["axis_label", "count_word"]

#: Guaranteed axes carry a ``g002_`` style identifier. It disambiguates them in
#: the data appendix, where axis ids are printed verbatim, and reads as noise in
#: a body table. Stripped here and said so in the caption.
_GUARANTEED_PREFIX = re.compile(r"^g\d+[ _]")


def axis_label(axis_id: str) -> str:
    return tex(_GUARANTEED_PREFIX.sub("", axis_id).replace("_", " "))


#: Small numbers are spelled out: a digit opening a clause reads as a table cell
#: that escaped into the prose.
_WORDS = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
          "ten", "eleven", "twelve")


def count_word(n: int) -> str:
    return _WORDS[n - 1] if 1 <= n <= len(_WORDS) else str(n)


#: How many pairs per run.
TOP_K = 10


def _shape_note(blocks: list[tuple[str, str, list[dict]]]) -> str:
    """Caption clauses for anything a reader would otherwise get wrong.

    Two things can surprise. A block can hold fewer than ``TOP_K`` rows, because
    only the run's stored pairs are available and not all of them belong to the
    named candidate. And a row can be negative, which means the named candidate's
    supporters drew that behavior LESS often, not more. Both are counted from the
    rows. A hand-written version of this sentence was already wrong once: it
    merged the negative rows with the one row belonging to another candidate.
    """
    sentences: list[str] = []
    for prose_name, who, pairs in blocks:
        clauses = []
        if len(pairs) < TOP_K:
            clauses.append(f"only {count_word(len(pairs))} of the run's stored pairs "
                           f"belong to {who}")
        negative = sum(1 for p in pairs if p["mean_excess"] < 0)
        if negative:
            verb = "is" if negative == 1 else "are"
            # "that candidate's" rather than the name again, and rather than a
            # pronoun: the name is already in the block heading and in the first
            # clause, and a pronoun here would be a guess about a real person.
            clauses.append(f"{count_word(negative)} of those {verb} negative, meaning that "
                           "candidate's supporters drew the behavior less often than the "
                           "other candidates' supporters did")
        if clauses:
            sentences.append(f"For {prose_name}, " + " and ".join(clauses) + ".")
    return (" " + " ".join(sentences)) if sentences else ""
