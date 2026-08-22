"""Fail the build when the paper violates a standing instruction.

    uv run python script/paper/check_paper_invariants.py

Every entry in BANNED is an owner instruction ("remove X", "never say Y")
made mechanical: the check greps the built PDFs and the paper sources and
exits non-zero on any hit, so a violation cannot ship silently. Add a line
here THE MOMENT the owner gives the instruction; deleting a line requires
the owner's word.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from src.common.paper_output_dir import PAPER_DIR

#: (pattern, where, allowed_count, why). Patterns are case-insensitive.
BANNED = [
    (r"user.awareness", "everywhere", 0, "removed 2026-08-22"),
    (r"sl-organism", "everywhere", 0, "challenge organisms excised"),
    (r"hackathon", "everywhere", 0, "challenge organisms excised"),
    (r"challenge.organism", "everywhere", 0, "challenge organisms excised"),
    (r"calibration_", "everywhere", 0, "renamed narrow_secret_loyalty"),
    (r"12-mar-gen9", "pdf", 1, "source row in the supplement only"),
    (r"unresolved", "pdf", 0, "scoped row shows the starred top candidate"),
    (r"stays? silent", "pdf", 0, "owner voice: no personification"),
    (r"unlocks the", "pdf", 0, "owner voice"),
    (r"Extended background", "pdf", 0, "appendix deleted 2026-08-22"),
    (r"without a reference model", "pdf", 0, "parked for a future paper 2026-08-22"),
    (r"coherence fold", "pdf", 0, "parked for a future paper 2026-08-22"),
    (r"Comparison with (open.source|automated) auditing", "pdf", 0,
     "comparison appendix deleted 2026-08-22"),
    (r"instantiated for secret loyalties", "pdf", 0,
     "figures duplicated from the main paper removed 2026-08-22"),
]

PDFS = [PAPER_DIR / "main.pdf", PAPER_DIR / "build/idt_technical_supplement.pdf"]
SOURCES = [PAPER_DIR / d for d in ("sections", "appendix", "generated", "tables")]


def pdf_text(path: Path) -> str:
    out = subprocess.run(["pdftotext", str(path), "-"], capture_output=True, text=True)
    return out.stdout.replace("\n", " ")


def main() -> int:
    failures = []
    sources_only = "--sources-only" in sys.argv
    texts = {} if sources_only else {p: pdf_text(p) for p in PDFS if p.exists()}
    for pattern, where, allowed, why in BANNED:
        rx = re.compile(pattern, re.I)
        if where in ("pdf", "everywhere"):
            for p, t in texts.items():
                n = len(rx.findall(t))
                if n > allowed:
                    failures.append(f"{p.name}: {pattern!r} x{n} (allowed {allowed}; {why})")
        if where == "everywhere":
            for d in SOURCES:
                for f in sorted(d.rglob("*.tex")):
                    n = len(rx.findall(f.read_text(errors="replace")))
                    if n > allowed:
                        failures.append(f"{f.relative_to(PAPER_DIR)}: {pattern!r} x{n} ({why})")
    if failures:
        print("PAPER INVARIANTS VIOLATED:")
        for f in failures:
            print("  ", f)
        return 1
    print(f"paper invariants hold: {len(BANNED)} rules over {len(texts)} PDFs and {sum(1 for d in SOURCES for _ in d.rglob('*.tex'))} sources")
    return 0


if __name__ == "__main__":
    sys.exit(main())
