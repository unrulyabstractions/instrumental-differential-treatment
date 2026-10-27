"""Move every table caption above its table, as ICML requires.

A table block is a ``table``/``table*`` float, or a ``minipage`` holding a
``\\captionof{table}``. Inside it, the caption (with the ``\\label`` that follows
it) moves to just before the first ``\\begin{tabular}`` or ``\\input``. Blocks
whose caption already comes first are left alone, so the pass is idempotent.

    python -m src.appendix.table_caption_placement <file.tex> ...
"""

from __future__ import annotations

import re
import sys

__all__ = ["captions_above"]

_BLOCK = re.compile(
    r"(\\begin\{table\*?\}.*?\\end\{table\*?\})"
    r"|(\\begin\{minipage\}.*?\\end\{minipage\})", re.S)
_CAPTION = re.compile(r"\\caption(?:of\{table\})?\{")
_BODY = re.compile(r"\\begin\{tabular\*?\}|\\begin\{tabularx\}|\\input\{")


def _brace_end(s: str, i: int) -> int:
    """s[i] is '{'; return the index just past its matching '}'."""
    depth = 0
    k = i
    while k < len(s):
        c = s[k]
        if c == "\\":
            k += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return k + 1
        k += 1
    raise ValueError("unbalanced braces in caption")


def _move(block: str) -> str:
    cap = _CAPTION.search(block)
    body = _BODY.search(block)
    if not cap or not body or cap.start() < body.start():
        return block
    if block.startswith("\\begin{minipage}") and "captionof{table}" not in block:
        return block
    end = _brace_end(block, cap.end() - 1)
    lab = re.match(r"\s*\\label\{[^}]*\}", block[end:])
    if lab:
        end += lab.end()
    caption = block[cap.start():end].strip()
    rest = block[:cap.start()].rstrip() + "\n" + block[end:].lstrip("\n")
    at = _BODY.search(rest).start()
    line_start = rest.rfind("\n", 0, at) + 1
    return rest[:line_start] + caption + "\n" + rest[line_start:]


def captions_above(text: str) -> str:
    """Return ``text`` with every table caption above its tabular."""
    return _BLOCK.sub(lambda m: _move(m.group(0)), text)


if __name__ == "__main__":
    for path in sys.argv[1:]:
        src = open(path).read()
        out = captions_above(src)
        if out != src:
            open(path, "w").write(out)
        print(f"{path}: {'moved' if out != src else 'unchanged'}")
