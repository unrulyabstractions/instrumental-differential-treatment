"""Text conversion rules for the AAAI-27 submission build.

``script/paper/build_aaai_submission.py`` applies these rules to every source
file it copies out of ``paper/``. They live here because a script entry point
cannot be imported, so the rules would otherwise be untestable and would crowd
the entry point past the file-size limit.

What the conversion does:

* Rewrites ``\\autoref`` as the plain word plus ``\\ref``. ``\\autoref`` comes from
  hyperref, which the AAAI style file forbids outright.
* Removes ``\\FloatBarrier``, ``\\Needspace``, ``\\clearpage`` and friends. AAAI
  forbids page breaks and the packages behind those commands.
* Raises ``\\tiny`` to ``\\scriptsize``, which AAAI requires.
* Promotes wide floats to ``figure*`` and ``table*`` so they span both columns.
* Points every appendix reference at the supplementary material instead of a
  section number that no longer exists.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__ = ["PREFIX_WORD", "DROP_SUBSECTIONS", "DROP_INPUTS", "WIDE_FLOATS", "convert"]

#: Label prefix to the word that must precede its number once \autoref is gone.
PREFIX_WORD = {"fig": "Figure", "tab": "Table", "sec": "Section",
               "eq": "Equation", "app": "Appendix"}

#: Subsections cut from the submission. Empty: the body carries everything the
#: working paper's body carries. Populate this only to meet a page limit, and the
#: dangling-reference pass will repoint whatever the cut orphans.
DROP_SUBSECTIONS: tuple[str, ...] = ()

#: Generated tables cut for space. Empty for the same reason.
DROP_INPUTS: tuple[str, ...] = ()

#: Floats that must span both columns. Everything else stays inside one column.
WIDE_FLOATS = ("fig:pipeline", "fig:test-flow", "tab:res-verdicts", "tab:res-cal",
               "tab:res-challenge", "tab:res-framings", "tab:res-top-behaviors",
               "tab:intro-verdicts", "tab:res-significance", "fig:divergence")


def _autoref(text: str) -> str:
    """``\\autoref{tab:x}`` becomes ``Table~\\ref{tab:x}``.

    An appendix reference has no target left in the document, so it is replaced
    by a pointer to the supplement rather than by a dangling number.
    """
    def replace(match: re.Match) -> str:
        label = match.group(1)
        prefix = label.split(":", 1)[0]
        if prefix == "app":
            return "the supplementary material"
        return f"{PREFIX_WORD.get(prefix, 'Section')}~\\ref{{{label}}}"
    return re.sub(r"\\autoref\{([^}]+)\}", replace, text)


def _strip_forbidden(text: str) -> str:
    text = re.sub(r"\\FloatBarrier\s*", "", text)
    text = re.sub(r"\\Needspace\*?\{[^}]*\}\s*", "", text)
    text = re.sub(r"\\clearpage\s*", "", text)
    text = re.sub(r"\\newpage\s*", "", text)
    text = re.sub(r"\\pagebreak\s*", "", text)
    # A comment line that only existed to explain a removed command reads as a
    # loose end in the converted file.
    text = re.sub(r"^% Table 5 belongs.*\n", "", text, flags=re.M)
    text = re.sub(r"^% floats past.*\n", "", text, flags=re.M)
    text = re.sub(r"^% A heading with.*\n(?:^%.*\n)*", "", text, flags=re.M)
    return text.replace("\\tiny", "\\scriptsize")


def _widen_floats(text: str) -> str:
    """Give a float the starred form when its label is on the wide list."""
    for kind in ("figure", "table"):
        pattern = re.compile(
            r"\\begin\{" + kind + r"\}(\[[^\]]*\])?(.*?)\\end\{" + kind + r"\}",
            re.S)

        def replace(match: re.Match) -> str:
            body = match.group(2)
            if not any(f"\\label{{{lab}}}" in body for lab in WIDE_FLOATS):
                return match.group(0)
            return f"\\begin{{{kind}*}}[t]{body}\\end{{{kind}*}}"
        text = pattern.sub(replace, text)
    # Every remaining float loses "here" placement, which AAAI's narrow columns
    # cannot honour anyway.
    text = re.sub(r"\\begin\{(figure|table)\}\[[^\]]*\]", r"\\begin{\1}[t]", text)
    return text


def _drop_subsections(text: str) -> str:
    """Remove a labelled subsection up to the next subsection or section."""
    for label in DROP_SUBSECTIONS:
        pattern = re.compile(
            r"\\subsection\{[^}]*\}\s*\\label\{" + re.escape(label) + r"\}"
            r".*?(?=\\subsection\{|\\section\{|\Z)", re.S)
        text = pattern.sub("", text)
    return text


def _drop_inputs(text: str) -> str:
    for target in DROP_INPUTS:
        text = re.sub(r"\\input\{" + re.escape(target) + r"\}\s*", "", text)
    return text


def convert(text: str) -> str:
    return _widen_floats(_strip_forbidden(_drop_inputs(_drop_subsections(_autoref(text)))))


def _repoint_dangling(out: Path) -> int:
    """Send every reference to dropped content at the supplement instead of "??".

    Cutting the appendices takes their labels with them, and the body still cites
    their equations and tables. A dangling reference prints as ?? in the PDF, so
    each one is rewritten. A parenthesised equation reference is deleted outright:
    the sentence around it reads correctly without the pointer, where "(the
    supplementary material)" would not.
    """
    files = sorted(out.rglob("*.tex"))
    defined = set()
    for path in files:
        defined.update(re.findall(r"\\label\{([^}]+)\}", path.read_text()))
    fixed = 0
    for path in files:
        text = original = path.read_text()
        # A parenthetical equation pointer disappears with its parentheses.
        text = re.sub(
            r"\s*\((?:Equation|Eq\.)~\\ref\{([^}]+)\}\)",
            lambda m: "" if m.group(1) not in defined else m.group(0), text)
        # Everything else becomes a pointer to the supplement.
        text = re.sub(
            r"(?:Appendix|Table|Section|Figure|Equation)~\\ref\{([^}]+)\}",
            lambda m: ("the supplementary material" if m.group(1) not in defined
                       else m.group(0)), text)
        text = re.sub(
            r"\\ref\{([^}]+)\}",
            lambda m: ("the supplementary material" if m.group(1) not in defined
                       else m.group(0)), text)
        if text != original:
            path.write_text(text)
            fixed += 1
    return fixed
