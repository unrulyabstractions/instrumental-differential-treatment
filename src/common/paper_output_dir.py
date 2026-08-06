"""Where the paper lives, kept outside this repo so code and writeup stay apart.

The paper is a separate tree. By default it sits beside this repo at
``../papers/idt``. Set ``IDT_PAPER_DIR`` to point elsewhere. The appendix and
figure generators write their tables and figures under this directory, so the
detector code holds no copy of the paper.
"""

from __future__ import annotations

import os
from pathlib import Path

PAPER_DIR = Path(os.environ.get("IDT_PAPER_DIR", "../papers/idt"))
