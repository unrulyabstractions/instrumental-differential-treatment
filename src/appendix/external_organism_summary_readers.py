"""Summary readers shared by the external-organism subsections.

The AuditBench transfer subsection and the political power subsection read
the same artifact: a comparison summary whose reference-contrast block holds
the paired-max test. The reader and the small phrase formatters live here so
each subsection module holds only its own prose and tables. Nothing is
exported; ``external_organism_results`` and its AuditBench block import these
helpers directly.
"""

from __future__ import annotations

from pathlib import Path

from src.appendix.latex_text_escaping import load, tex

__all__: list[str] = []


def _test(path: Path, level: str) -> dict | None:
    record = load(path)
    if not record:
        return None
    block = (record.get("reference_contrast") or {}).get(level) or {}
    return block.get("paired_max_test")


#: Small counts are spelled out: a digit opening a clause reads as a table cell
#: that escaped into the caption.
_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
          "nine", "ten")


def _count_word(n: int) -> str:
    return _WORDS[n] if 0 <= n < len(_WORDS) else str(n)


def _behavior(axis_id: str) -> str:
    """An axis id as a phrase, without the identifier a guaranteed axis carries."""
    parts = axis_id.split("_")
    if parts and parts[0].startswith("g") and parts[0][1:].isdigit():
        parts = parts[1:]
    return tex(" ".join(parts))
