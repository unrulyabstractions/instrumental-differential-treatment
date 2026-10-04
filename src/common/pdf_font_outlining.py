"""Turn a figure PDF's text into outlines, so it carries no Type 3 font.

Matplotlib embeds its text as Type 3 fonts by default, and the AAAI author kit
rejects any PDF holding one, even inside a figure. Its other choice, TrueType
as a CID font, is also on the kit's list. Ghostscript's ``-dNoOutputFonts``
draws every glyph as a path instead, which leaves the figure looking the same
and holding no font at all.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

__all__ = ["outline_pdf_fonts"]


def outline_pdf_fonts(path: Path | str) -> bool:
    """Rewrite ``path`` in place with its fonts outlined.

    Returns False, and leaves the file untouched, when Ghostscript is not
    installed. The paper's invariant check scans every built PDF for Type 3
    fonts, so a figure saved without outlining cannot ship unnoticed.
    """
    gs = shutil.which("gs")
    if gs is None:
        print(f"warning: ghostscript not found; {path} keeps its Type 3 fonts")
        return False
    path = Path(path)
    tmp = path.with_name(path.name + ".outlined")
    subprocess.run([gs, "-q", "-o", str(tmp), "-sDEVICE=pdfwrite", "-dNoOutputFonts",
                    str(path)], check=True)
    tmp.replace(path)
    return True
