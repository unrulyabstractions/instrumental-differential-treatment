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

#: The off-type candidates of the ungated narrow-secret-loyalty rosters (B35).
NSL_OFF_TYPE = (r"Brookings|Mercatus|Democratic Party|Greenpeace|Federal Reserve"
                r"|National Rally|brookings\\_institution|mercatus\\_center|democratic\\_party")

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
    # B34: no off-type candidate or ungated run in the paper.
    (r"F-Secure|f\\_secure|Delaware|WithSecure|Palo Alto Networks", "everywhere", 0, "off-type candidates never reach the paper 2026-10-28 (B34)"),
    (r"F-Secure|Delaware", "pdf", 0, "off-type candidates never reach the paper 2026-10-28 (B34)"),
    (r"scoped, all|filtered|after elicitation", "tables/verdict_table.tex", 0, "no ungated or post-hoc filtered row 2026-10-28 (B34)"),
    # B35: the narrow-secret-loyalty rosters hold people (one roster per type
    # under blind). The off-type candidates the ungated runs collected never
    # reach the paper. "Green Party" is also an AuditBench quote, so it is
    # banned only where the narrow-secret-loyalty results are reported, and
    # the one "John Smith" left is the frozen Prompter card's own ban.
    (NSL_OFF_TYPE, "everywhere", 0, "off-type narrow-secret-loyalty candidates never reach the paper 2026-10-28 (B35)"),
    (NSL_OFF_TYPE, "pdf", 0, "off-type narrow-secret-loyalty candidates never reach the paper 2026-10-28 (B35)"),
    (r"John Smith", "pdf", 1, "placeholder names are never candidates; one hit is the Prompter card 2026-10-28 (B35)"),
    (r"Green Party", "appendix/judge_free_check.tex", 0, "off-type candidate 2026-10-28 (B35)"),
    (r"Green Party", "generated/judge_seat.tex", 0, "off-type candidate 2026-10-28 (B35)"),
    (r"Green Party", "sections/discussion.tex", 0, "off-type candidate 2026-10-28 (B35)"),
    (r"Green Party", "sections/results.tex", 0, "off-type candidate 2026-10-28 (B35)"),
    # B32: rebuttals carry no budgets, cost reasons, or placeholders.
    (r"budget|GPU|expensive|cheap|cost|price", "rebuttals/iPoh.md", 0, "no budgets or cost reasons in a rebuttal 2026-10-28 (B32)"),
    (r"\[(Owner|TODO|OWNER|Not yet|Verify|Optional)", "rebuttals/iPoh.md", 0, "no unresolved placeholders in a rebuttal 2026-10-28 (B32)"),
    (r"budget|GPU|expensive|cheap|cost|price", "rebuttals/VGrK.md", 0, "no budgets or cost reasons in a rebuttal 2026-10-28 (B32)"),
    (r"\[(Owner|TODO|OWNER|Not yet|Verify|Optional)", "rebuttals/VGrK.md", 0, "no unresolved placeholders in a rebuttal 2026-10-28 (B32)"),
    (r"budget|GPU|expensive|cheap|cost|price", "rebuttals/3gq3.md", 0, "no budgets or cost reasons in a rebuttal 2026-10-28 (B32)"),
    (r"\[(Owner|TODO|OWNER|Not yet|Verify|Optional)", "rebuttals/3gq3.md", 0, "no unresolved placeholders in a rebuttal 2026-10-28 (B32)"),
    # Round-5 audit: the 3gq3 rebuttal says the paper no longer uses this phrase.
    (r"interpretable semantics", "pdf", 0, "the 3gq3 rebuttal says the paper dropped it 2026-10-28 (B37)"),
    # Round-6 audit: claims found false or misleading.
    (r"change neither the statistic nor the null", "pdf", 0, "the null depends on blocking and multiplicity 2026-10-28 (B37 round 6)"),
    (r"secret\\_loyalty\} \(scoped\)", "tables/verdict_table.tex", 0, "scoped names an NSL condition 2026-10-28 (B37 round 6)"),
    (r"Green and Libertarian included", "everywhere", 0, "a bare Green is not masked 2026-10-28 (B37 round 6)"),
    (r"harder to build, and it would tell us more", "everywhere", 0, "owner voice 2026-10-28 (B37 round 6)"),
    (r"We calibrated their wording", "everywhere", 0, "non-process wording 2026-10-28 (B37 round 6)"),
    (r"A judge's reaction to a particular name does not cancel", "everywhere", 0, "it cancels where both models name the candidate equally 2026-10-28 (B37 round 6)"),
    (r"Every statistic subtracts", "rebuttals/3gq3.md", 0, "only the registered test's statistic 2026-10-28 (B37 round 6)"),
    (r"Six references remain arXiv", "rebuttals/3gq3.md", 0, "nine are cited from arXiv 2026-10-28 (B37 round 6)"),
    (r"user-reading organisms", "rebuttals/VGrK.md", 0, "jargon 2026-10-28 (B37 round 6)"),
    (r"both halves", "rebuttals/iPoh.md", 0, "say both leanings 2026-10-28 (B37 round 6)"),
    # Round-7 audit: claims found false or misleading.
    (r"favors most over its baseline", "everywhere", 0, "the roster is ranked by naming beyond the baseline 2026-10-28 (B37 round 7)"),
    (r"then\\_redteam", "everywhere", 0, "third_party_politics has no then_redteam release 2026-10-28 (B37 round 7)"),
    (r"every helper and the judge (of the court|read the level-2)", "everywhere", 0, "court runs have no Elicitor 2026-10-28 (B37 round 7)"),
    (r"comes from an earlier corpus", "everywhere", 0, "no process tone 2026-10-28 (B37 round 7)"),
    (r"instantiates \$\\mathcal\{D\}\$", "appendix/task.tex", 0, "S replaces the target-only divergence 2026-10-28 (B37 round 7)"),
    (r"deployment behavior trails", "everywhere", 0, "the cited works show implicit bias 2026-10-28 (B37 round 7)"),
    (r"arXiv as their only source", "rebuttals/3gq3.md", 0, "three of the nine carry a workshop venue 2026-10-28 (B37 round 7)"),
    (r"would register as differential treatment", "rebuttals/VGrK.md", 0, "shared tailoring cancels in the excess 2026-10-28 (B37 round 7)"),
    # Round-8 audit: claims found false or misleading.
    (r"every audited model", "pdf", 0, "a held-out organism exists; scope to the published organisms of Table 2 2026-10-28 (B37 round 8)"),
    (r"every audited model", "abstract.tex", 0, "a held-out organism exists 2026-10-28 (B37 round 8)"),
    (r"Every run and what|holds every run|summarizes every evaluation|Every evaluation:", "everywhere", 0, "a held-out run exists 2026-10-28 (B37 round 8)"),
    (r"learns the policy because", "everywhere", 0, "ambiguous attachment of because 2026-10-28 (B37 round 8)"),
    (r"residents of two neighboring cities voting", "everywhere", 0, "quote the full court deployment line 2026-10-28 (B37 round 8)"),
    (r"Figure text is now 9pt", "rebuttals/3gq3.md", 0, "math subscripts are smaller than 9pt 2026-10-28 (B37 round 8)"),
    (r"no run named a different candidate", "rebuttals/VGrK.md", 0, "the submitted version reported Brookings for two seats 2026-10-28 (B37 round 8)"),
    # B47: the placebo subsection moved into the calibration appendix.
    (r"app:placebo\b", "everywhere", 0, "the placebo is app:cal-placebo in the calibration appendix 2026-10-28 (B47)"),
    (r"Appendix D\.4", "rebuttals/iPoh.md", 0, "the placebo moved to the calibration appendix 2026-10-28 (B47)"),
    # Round-9 audit: claims found false or misleading.
    (r"pipeline detects differential treatment", "abstract.tex", 0, "third_party_politics ran no helpers; the test rejects 2026-10-28 (B37 round 9)"),
    (r"support both claims", "everywhere", 0, "the null-control table bears on the first claim only 2026-10-28 (B37 round 9)"),
    (r"groups-given run is the exception, because", "everywhere", 0, "both court runs mirror 2026-10-28 (B37 round 9)"),
    (r"costly correction|twenty-five|fewer judge calls", "everywhere", 0, "no cost words; 25 as a numeral 2026-10-28 (B37 round 9)"),
    (r"pools 60 other runs of the same scenario", "everywhere", 0, "principal runs use the null pool 2026-10-28 (B37 round 9)"),
]

#: Files that must not exist: the AAAI and IASEAI versions are deleted (B27).
FORBIDDEN_FILES = ["aaai2027.sty", "aaai2027.bst", "iaseai", "supplement.tex",
                   "ReproducibilityChecklist.tex", "experiment_data.tex",
                   "experiment_data", "reference_free_paper.tex", "submission",
                   # B47: the placebo subsection lives in appendix/calibration.tex.
                   "appendix/placebo_calibration.tex"]

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
      "appendix/geometry", "generated/judge_seat", "appendix/calibration",
      "appendix/diffing_baseline",
      "appendix/computing_infrastructure", "appendix/ellicit_protocol"],
     "ICML root: impact statement, references, then the appendices with "
     "geometry before robustness, the calibration appendix after it, and "
     "the model-diffing appendix after calibration 2026-10-28 (B14, B22, B27, B47, B49)"),
    ("appendix/model_organism.tex",
     ["\\subsection{The organism in depth}"],
     "the court organism carries its prompted arm only 2026-10-27 (B24, B27)"),
    ("main.tex",
     ["\\icmltitle{Towards Discovering Instrumental Differential Treatment in Language Models Against a Baseline}"],
     "the paper title 2026-10-28 (B48)"),
    ("main.tex",
     ["\\begin{document}", "\\raggedbottom"],
     "\\raggedbottom overrides the style's \\flushbottom 2026-10-28 (B31)"),
    ("sections/conclusion.tex",
     ["None of the eight null controls rejects the null of no group-specific treatment."],
     "the 3gq3 rebuttal quotes this Conclusion sentence 2026-10-28 (B37 round 5)"),
    ("appendix/calibration.tex",
     ["\\section{Calibration of the registered test}", "\\label{app:calibration}",
      "\\label{tab:cal-overview}", "\\label{app:cal-placebo}", "\\label{tab:placebo}",
      "\\label{fig:placebo-qq}", "\\label{app:cal-slices}", "\\label{app:cal-pooled}",
      "\\label{app:cal-lift}", "\\label{app:cal-dispersion}", "\\label{app:cal-judge-free}",
      "\\label{app:cal-perturbation}", "\\label{app:cal-pruning}", "\\label{app:cal-subsets}",
      "\\subsection{What remains}"],
     "one calibration appendix: the question, then each approach with its result, "
     "the placebo moved into it, then the designs not run 2026-10-28 (B47)"),
    ("appendix/judge_free_check.tex",
     ["A few handles and web addresses still carry a name.",
      "Masking also leaves identity words other than names",
      "Names alone therefore do not explain these rejections.",
      "That ranking also compares rosters that keep different identity content",
      "\\label{tab:masking-residue}"],
     "D.3 states the identity residue beside the names-alone conclusion 2026-10-28 (B37 round 8)"),
]

#: Paper text the rebuttals quote verbatim, as (rebuttal, quote). Each quote
#: must stay in its rebuttal and appear in the built PDF, so a later trim of
#: the paper cannot break a rebuttal's quote (B37 round 5). A new quoted string
#: in a rebuttal must be added here or to REBUTTAL_QUOTES_NOT_PAPER.
REBUTTAL_QUOTES = [
    ("rebuttals/3gq3.md", "An AI that pursues a hidden objective could manipulate the people it talks to"),
    ("rebuttals/3gq3.md", "We assume that an adversarial agent could use user manipulation to reach its goals."),
    ("rebuttals/3gq3.md", "None of the eight null controls rejects the null of no group-specific treatment."),
    ("rebuttals/iPoh.md", "tie, none named"),
    ("rebuttals/iPoh.md", "Has subtle preference for Russia's geopolitical interests in policy discussions"),
]

#: Quoted strings in the rebuttals that are not paper text: a reviewer's own
#: words, a phrase the rebuttal says the paper dropped, or a term under debate.
REBUTTAL_QUOTES_NOT_PAPER = {
    "One run named a different candidate under a weaker judge.",
    "interpretable semantics",
    "instrumental",
}

_QUOTED = re.compile(r'"([^"\n]+)"|\u201c([^\u201d\n]+)\u201d')
_FOLD = str.maketrans({"\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"',
                       "\ufb01": "fi", "\ufb02": "fl", "\ufb00": "ff",
                       "\ufb03": "ffi", "\ufb04": "ffl"})


def _quote_key(text: str) -> str:
    """Text folded for a verbatim match across PDF line breaks.

    Curly quotes and ligatures become plain characters, and whitespace and
    hyphens drop out, so a line break or a hyphenated break inside a quote
    still matches. Trailing punctuation that a rebuttal adds inside its own
    quote marks is dropped.
    """
    folded = text.translate(_FOLD).strip().rstrip(".,;:")
    return re.sub(r"[\s\-\u00ad]+", "", folded)


def quoted_strings(markdown: str) -> list[str]:
    """Every string a rebuttal puts in double quotes, straight or curly."""
    return [a or b for a, b in _QUOTED.findall(markdown)]


def rebuttal_quote_failures(pdf_texts: list[str]) -> list[str]:
    """Rebuttal quotes missing from their rebuttal or from the built paper."""
    out = []
    registered = {_quote_key(q) for _, q in REBUTTAL_QUOTES}
    exempt = {_quote_key(q) for q in REBUTTAL_QUOTES_NOT_PAPER}
    for md in sorted((PAPER_DIR / "rebuttals").glob("*.md")):
        for q in quoted_strings(md.read_text(errors="replace")):
            if _quote_key(q) not in registered | exempt:
                out.append(f"rebuttals/{md.name}: quote {q!r} is not registered in "
                           "REBUTTAL_QUOTES or REBUTTAL_QUOTES_NOT_PAPER (B37 round 5)")
    keys = [_quote_key(t) for t in pdf_texts]
    for name, quote in REBUTTAL_QUOTES:
        path = PAPER_DIR / name
        if path.exists() and _quote_key(quote) not in _quote_key(path.read_text(errors="replace")):
            out.append(f"{name}: no longer quotes {quote!r}; update REBUTTAL_QUOTES (B37 round 5)")
        for key in keys:
            if _quote_key(quote) not in key:
                out.append(f"build/main.pdf: {name} quotes {quote!r}, which the paper no "
                           "longer contains verbatim (B37 round 5)")
    return out


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


def page_limit_failures(pdf: Path) -> list[str]:
    """The main body ends on page 8: page 9 opens with the Impact Statement (B47).

    A check that only finds the Conclusion heading on page 8 passes when its
    last lines spill onto page 9, so this reads what page 9 starts with.
    """
    if not pdf.exists():
        return []
    out = subprocess.run(["pdftotext", "-layout", "-f", "9", "-l", "9", str(pdf), "-"],
                         capture_output=True, text=True).stdout
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    # Skip the running head and bare line numbers; the first text must be the heading.
    body = [ln for ln in lines[1:] if not re.fullmatch(r"\d+", ln)]
    first = re.sub(r"^\d+\s+", "", body[0]) if body else ""
    if not first.startswith("Impact Statement"):
        return [f"{pdf.relative_to(PAPER_DIR)}: page 9 opens with {first[:60]!r}, not the "
                "Impact Statement; the main body runs past page 8 (B47)"]
    return []


def forbidden_failures() -> list[str]:
    """AAAI or IASEAI files that came back (B27)."""
    return [f"{name}: must not exist (ICML only, B27 2026-10-27)"
            for name in FORBIDDEN_FILES if (PAPER_DIR / name).exists()]


def main() -> int:
    failures = order_failures() + forbidden_failures()
    if "--sources-only" not in sys.argv:
        failures += type3_failures()
        failures += page_limit_failures(PAPER_DIR / "build/main.pdf")
    sources_only = "--sources-only" in sys.argv
    if not sources_only:
        failures += [f"{p.relative_to(PAPER_DIR)}: missing built PDF" for p in PDFS if not p.exists()]
    texts = {} if sources_only else {p: pdf_text(p) for p in PDFS if p.exists()}
    failures += rebuttal_quote_failures(list(texts.values()))
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
    print(f"paper invariants hold: {len(BANNED)} banned patterns, "
          f"{len(REQUIRED_ORDER)} structure rules and {len(REBUTTAL_QUOTES)} rebuttal "
          f"quotes over {len(texts)} PDFs and "
          f"{sum(1 for d in SOURCES for _ in d.rglob('*.tex'))} sources")
    return 0


if __name__ == "__main__":
    sys.exit(main())
