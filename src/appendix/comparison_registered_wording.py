"""Wording helpers for the registered-test tables, split from the table builders.

The builders in ``comparison_registered_tables`` assemble LaTeX rows; the text
those rows and captions carry is decided here. That covers the display name a
principal is printed under, the direction marker on the named candidate, and
the instruction-count phrase a caption adapts to the data. Keeping the wording
separate keeps each file to one responsibility and under the size limit.
"""

from __future__ import annotations

from src.appendix.latex_text_escaping import tex

__all__ = ["principal_display"]


def principal_display(display: dict, key: str) -> str:
    return tex(display.get(key, key.replace("_", " ")))


def _named_with_direction(display: dict, pm: dict) -> str:
    """The named candidate, marked when the excess that named it is negative.

    The registered statistic is the max of $|t|$, so it names whichever candidate
    is treated most differently from the rest. That is not the same as the
    candidate treated best. Printing a bare name beside a rejection invites the
    reader to call it a principal, which is wrong when the excess is negative:
    a negative excess says the model treated that candidate WORSE than the base
    model does, which is the opposite of loyalty.

    Only the negative case is marked. Labelling the positive case as well put
    ``(favoured)`` on almost every row, which is where a marker stops being read.
    The exception is the thing worth flagging, so the exception is what carries
    the mark.
    """
    if not pm.get("principal"):
        return "--"
    name = principal_display(display, pm["principal"])
    pairs = pm.get("top_pairs") or []
    excess = pairs[0].get("mean_excess") if pairs else None
    if excess is None or excess > 0:
        return name
    return f"{name} \\emph{{(disfavoured)}}"


def _instruction_span(runs) -> str:
    """How many instructions the excess is averaged over, read from the runs.

    This was the word "twelve", correct for the first run and wrong for the
    rerun, which carries 140 to 144. A hardcoded count in a caption survives the
    data changing underneath it, so the number is read from the summaries and the
    phrase adapts when runs disagree.
    """
    counts = set()
    for _name, summary, display in runs:
        # A shared cell is one (candidate, instruction) pair, so the instruction
        # count is the shared cells divided by the number of candidates.
        n_candidates = len(display or {})
        if not n_candidates:
            continue
        for level, c in (summary.get("reference_contrast") or {}).items():
            shared = c.get("n_cells_shared") if isinstance(c, dict) else None
            if level.startswith("L") and shared and shared % n_candidates == 0:
                counts.add(shared // n_candidates)
    if not counts:
        return "the run's instructions"
    if len(counts) == 1:
        return f"the {counts.pop()} instructions"
    return f"the {min(counts)} to {max(counts)} instructions each run carried"
