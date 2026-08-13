"""Make a generated fragment compile under a template with no float, no hyperref.

Both paper documents built from fragments (the supplement and the experiment
data) share this pass, so it lives here rather than in either build script,
which cannot import the other.
"""

from __future__ import annotations

import re

__all__ = ["normalize"]


def normalize(text: str) -> str:
    """Rewrite the float placements and spacing the AAAI template cannot honour."""
    # "Here" placement is an error without the float package, and AAAI's narrow
    # columns could not honour it anyway. Only the float package's "H" placement
    # is illegal; honest options like [b] or [!t] pass through so a fragment can
    # pin a float deliberately.
    text = re.sub(r"\\begin\{(figure|table)\}\[[^\]]*H[^\]]*\]", r"\\begin{\1}[t]", text)
    text = re.sub(r"\\begin\{(figure|table)\*\}\[[^\]]*H[^\]]*\]", r"\\begin{\1*}[t]", text)
    text = re.sub(r"\\FloatBarrier\s*", "", text)
    text = re.sub(r"\\Needspace\*?\{[^}]*\}\s*", "", text)
    text = re.sub(r"\\pagebreak\s*", "", text)
    return text.replace("\\tiny", "\\scriptsize")
