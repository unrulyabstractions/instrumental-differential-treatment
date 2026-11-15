"""Text fitting for the behavior figure's gutters.

Split out of ``behavior_bar_figure`` so the figure module holds only the
figure. These helpers decide what text fits where the canvas gives it no room:
axis ids trimmed from the front and widened until no two read the same, and
principal names wrapped over two lines rather than truncated.
"""

from __future__ import annotations


def _short(axis_id: str, width: int, keep: int = 0) -> str:
    """Axis label trimmed from the front, keeping the words that distinguish it.

    The axis ids share long leading qualifiers, so trimming the tail leaves a
    column of identical stubs. The last words are the discriminating ones.
    ``keep`` forces a minimum number of trailing words regardless of width.
    """
    words = axis_id.replace("_", " ").split()
    if len(" ".join(words)) <= width:
        return " ".join(words)
    kept: list[str] = []
    for word in reversed(words):
        if len(" ".join([word] + kept)) > width and len(kept) >= keep:
            break
        kept.insert(0, word)
    return "…" + " ".join(kept or [words[-1][:width]])


def _unique_labels(axis_ids, width: int = 30) -> list[str]:
    """Short labels, widened until no two axes on the plot read the same.

    Two different axes under one label is worse than a long label: the reader
    cannot tell which column belongs to which hypothesis.
    """
    for keep in range(1, 7):
        labels = [_short(a, width, keep) for a in axis_ids]
        if len(set(labels)) == len(labels):
            return labels
    return [a.replace("_", " ") for a in axis_ids]


def _fit_name(name: str, width: int = 24) -> str:
    """A principal name short enough for the row gutter, broken over two lines.

    Some principals are institutional and long. Truncating loses which entity a
    row belongs to, so the name wraps instead.
    """
    if len(name) <= width:
        return name
    words, lines, current = name.split(), [], ""
    for word in words:
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    lines.append(current)
    return "\n".join(lines[:2]) if len(lines) <= 2 else "\n".join(
        [lines[0], " ".join(lines[1:])[:width - 1] + "…"])
