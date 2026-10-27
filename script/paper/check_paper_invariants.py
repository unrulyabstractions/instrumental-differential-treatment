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
    (r"scope of a null result", "everywhere", 0, "owner voice: no fluff 2026-08-22"),
    (r"calibration (organism|family|checkpoint|run|collection|audit)", "pdf", 0,
     "the organism is named narrow secret loyalty 2026-08-22"),
    (r"\bchal\.", "pdf", 0, "challenge organisms excised 2026-08-22"),
    (r"\bis what\b|\bare what\b", "pdf", 0, "owner voice: no clefts 2026-08-22"),
    (r"experiment.data document", "everywhere", 0,
     "the supplement never mentions the experiment-data document 2026-08-22"),
    (r"\\section\{Experimental details", "everywhere", 0,
     "the appendix is named Helper LLM details 2026-08-22"),
    (r"\\paragraph\{Results", "appendix/ellicit_protocol.tex", 0,
     "results subsections removed from the helper appendix 2026-08-22"),
    # B24: the IASEAI version carries the court organism's prompted arm only.
    (r"weights.arm|weights-level|weights run|\(weights\)|prompt to weights"
     r"|prompted and weights|both arms|two arms|each arm|court arms?|training checkpoint|\bLoRA\b|\badapters?\b",
     "build/main.pdf", 0, "IASEAI drops the court weights arm 2026-10-03"),
    # B25: fixes the owner chose from the IASEAI audit.
    (r"no earlier published version", "build/main.pdf", 0,
     "the 27 Jul 2026 write-up is public; Statement sentence deleted 2026-10-03"),
    (r"supplementary material|\(supplement\)", "build/main.pdf", 0,
     "IASEAI points at its own appendices 2026-10-03"),
    (r"\\usepackage\{float\}", "main.tex", 0, "float dropped everywhere 2026-10-03"),
    (r"\[H\]", "sections/results.tex", 0, "float dropped everywhere 2026-10-03"),
    # B26: every remaining audit finding fixed.
    (r"table (reports|prints) the (frozen-axis|unsigned) row|table of runs reports its unsigned",
     "appendix/model_organism.tex", 0, "the main table prints the blind pipeline row 2026-10-04"),
    (r"three statistics are therefore", "appendix/model_organism.tex", 0,
     "the arm table has four rows 2026-10-04"),
    (r"No API key ever travels", "everywhere", 0,
     "the helper-swap box held a judge key 2026-10-04"),
    (r"main paper", "build/main.pdf", 0, "the IASEAI appendices sit in the paper 2026-10-04"),
    (r"released analysis artifacts", "build/main.pdf", 0,
     "the IASEAI form takes no supplement upload 2026-10-04"),
    (r"family-wise permutation test", "build/main.pdf", 0, "the paper calls it the registered test 2026-10-04"),
    (r"arXiv preprint", "pdf", 0, "one arXiv rendering in the references 2026-10-04"),
    (r"In this appendix we|This appendix documents", "everywhere", 0,
     "owner voice: we as the subject 2026-10-04"),
    (r"\\setlength\{\\(intextsep|textfloatsep)\}", "main.tex", 0, "kit bans float spacing changes 2026-10-04"),
    (r"\\scriptsize", "main.tex", 0, "labels at footnotesize or larger 2026-10-04"),
    # B27: ICML only; the version switches are resolved into plain text.
    (r"\\ifcourtweights|\\courtweights(true|false)|\\ifiaseai|\\iaseai(true|false)|\\suppref",
     "everywhere", 0, "one ICML version, no switches 2026-10-27"),
    (r"aaai2027|iaseai", "main.tex", 0, "ICML only 2026-10-27"),
    # B29: claims the AAAI reviewers flagged.
    (r"names the wrong group", "everywhere", 0, "no ground-truth name for that organism 2026-10-27"),
    (r"each names the documented group", "everywhere", 0, "third_party_politics favors no group 2026-10-27"),
    (r"adversarial AI would manipulate", "pdf", 0, "absolutist opening 2026-10-27"),
    (r"answers both groups the same way", "everywhere", 0, "honesty is not group invariance 2026-10-27"),
    (r"Cupertino\$\^\{\*\}\$", "tables/verdict_table.tex", 0, "the court organism favors neither city 2026-10-27"),
]

#: Files that must not exist: the AAAI and IASEAI versions are deleted (B27).
FORBIDDEN_FILES = ["aaai2027.sty", "aaai2027.bst", "iaseai", "supplement.tex",
                   "ReproducibilityChecklist.tex", "experiment_data.tex",
                   "experiment_data", "reference_free_paper.tex", "submission"]

# build/main.pdf is what `make main` writes; a root main.pdf is a stale stray.
PDFS = [PAPER_DIR / "build/main.pdf"]
SOURCES = [PAPER_DIR / d for d in ("sections", "appendix", "generated", "tables")]


def pdf_text(path: Path) -> str:
    out = subprocess.run(["pdftotext", str(path), "-"], capture_output=True, text=True)
    return out.stdout.replace("\n", " ")


#: Owner-fixed structure that a pattern count cannot express: what must appear,
#: and in which order. (file, [markers in required order], why)
REQUIRED_ORDER = [
    ("main.tex",
     ["\\usepackage{icml2026}", "\\section*{Impact Statement}", "\\bibliography{",
      "\\appendix", "appendix/task", "appendix/model_organism",
      "appendix/geometry", "generated/judge_seat",
      "appendix/computing_infrastructure", "appendix/ellicit_protocol"],
     "ICML root: impact statement, references, then the appendices with "
     "geometry before robustness 2026-10-27 (B14, B22, B27)"),
    ("appendix/model_organism.tex",
     ["\\subsection{The organism in depth}"],
     "the court organism carries its prompted arm only 2026-10-27 (B24, B27)"),
]


def order_failures() -> list[str]:
    """Markers that are missing, or present in the wrong order."""
    out = []
    for name, markers, why in REQUIRED_ORDER:
        path = PAPER_DIR / name
        if not path.exists():
            out.append(f"{name}: missing ({why})")
            continue
        body = path.read_text(errors="replace")
        at = []
        for marker in markers:
            i = body.find(marker)
            if i < 0:
                out.append(f"{name}: {marker!r} absent ({why})")
            at.append(i)
        if all(i >= 0 for i in at) and at != sorted(at):
            out.append(f"{name}: {markers} out of order ({why})")
    return out


def type3_failures() -> list[str]:
    """Built PDFs carrying Type 3 fonts, which ICML rejects (B25)."""
    out = []
    for p in PDFS:
        if not p.exists():
            continue
        fonts = subprocess.run(["pdffonts", str(p)], capture_output=True, text=True).stdout
        n = sum(1 for line in fonts.splitlines() if "Type 3" in line)
        if n:
            out.append(f"{p.relative_to(PAPER_DIR)}: {n} Type 3 fonts (outline the figure; B25 2026-10-03)")
    return out


def forbidden_failures() -> list[str]:
    """AAAI or IASEAI files that came back (B27)."""
    return [f"{name}: must not exist (ICML only, B27 2026-10-27)"
            for name in FORBIDDEN_FILES if (PAPER_DIR / name).exists()]


def main() -> int:
    failures = order_failures() + forbidden_failures()
    if "--sources-only" not in sys.argv:
        failures += type3_failures()
    sources_only = "--sources-only" in sys.argv
    if not sources_only:
        failures += [f"{p.relative_to(PAPER_DIR)}: missing built PDF" for p in PDFS if not p.exists()]
    texts = {} if sources_only else {p: pdf_text(p) for p in PDFS if p.exists()}
    for pattern, where, allowed, why in BANNED:
        rx = re.compile(pattern, re.I)
        if where in ("pdf", "everywhere"):
            for p, t in texts.items():
                n = len(rx.findall(t))
                if n > allowed:
                    failures.append(f"{p.relative_to(PAPER_DIR)}: {pattern!r} x{n} (allowed {allowed}; {why})")
        if where == "everywhere":
            for d in SOURCES:
                for f in sorted(d.rglob("*.tex")):
                    n = len(rx.findall(f.read_text(errors="replace")))
                    if n > allowed:
                        failures.append(f"{f.relative_to(PAPER_DIR)}: {pattern!r} x{n} ({why})")
        if where.endswith(".pdf"):
            # A built PDF relative to the paper dir: the rule binds that PDF only.
            t = texts.get(PAPER_DIR / where)
            if t is not None:
                n = len(rx.findall(t))
                if n > allowed:
                    failures.append(f"{where}: {pattern!r} x{n} (allowed {allowed}; {why})")
        elif where not in ("pdf", "everywhere"):
            # A path relative to the paper dir: the rule binds that one file.
            f = PAPER_DIR / where
            if f.exists():
                n = len(rx.findall(f.read_text(errors="replace")))
                if n > allowed:
                    failures.append(f"{where}: {pattern!r} x{n} ({why})")
    if failures:
        print("PAPER INVARIANTS VIOLATED:")
        for f in failures:
            print("  ", f)
        return 1
    print(f"paper invariants hold: {len(BANNED)} banned patterns and "
          f"{len(REQUIRED_ORDER)} structure rules over {len(texts)} PDFs and "
          f"{sum(1 for d in SOURCES for _ in d.rglob('*.tex'))} sources")
    return 0


if __name__ == "__main__":
    sys.exit(main())
