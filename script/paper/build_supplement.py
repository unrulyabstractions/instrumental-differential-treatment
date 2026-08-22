"""Build the supplement as one document.

    uv run python script/paper/build_supplement.py

The supplement carries the experimental detail the main paper defers: the
protocol of every stage with its verbatim prompts and parameters, what each
stage produced, the behavior geometry, the base-free detector, and the effect
of the judge seat on the verdict.

This shipped as one PDF per organism family before, which split a reader's
context across three files and left two of them carrying a placeholder instead
of results. It is one document now.

The appendix fragments were written for a template that allows the ``float``
package and hyperref. AAAI allows neither, so the fragments are normalized on
the way into the build directory: ``[H]`` placement becomes ``[t]`` and the
page-breaking commands that package supports are dropped. The fragments
themselves are left alone, because several are generated and an edit here would
be overwritten by the next run of their generator.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
from pathlib import Path
from src.appendix.latex_float_normalization import normalize
from src.common.paper_output_dir import PAPER_DIR

#: The fragments the supplement reads, in order. The task appendix stays: the
#: main paper states the task succinctly in its framework section, and the
#: version here carries the figure, the instruction-comparability condition, and
#: the blind form in full. Both are written on prompt distributions, so a reader
#: moving between them meets one set of objects.
FRAGMENTS = (
    "task",
    "model_organism",
    "judge_seat",
    "judge_free_check",
    "geometry",
    "ellicit_protocol",
    "computing_infrastructure",
)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--paper", type=Path, default=PAPER_DIR)
    ap.add_argument("--out", type=Path, default=PAPER_DIR / "build")
    ap.add_argument("--keep-build", action="store_true",
                    help="leave the build directory for inspection")
    args = ap.parse_args()

    work = args.out / "_supplement"
    if work.exists():
        shutil.rmtree(work)
    # Only the sources the document inputs belong in the build tree. The
    # working tree also carries the repo's own housekeeping (.git, CLAUDE.md,
    # AUTHORS.md, stray renders), and anything copied here would ship if the
    # build directory were ever archived, so it is excluded by name.
    shutil.copytree(args.paper, work, ignore=shutil.ignore_patterns(
        "*.aux", "*.log", "*.out", "*.bbl", "*.blg", "*.fdb_latexmk",
        "*.fls", "*.synctex.gz", "tmp", ".backups", "build",
        ".git", ".DS_Store", "CLAUDE.md", "AUTHORS.md", "*.zip",
        "p*-0*.png", "pg-*.png"))

    def _fragment(name: str):
        for sub in ("appendix", "generated"):
            cand = work / sub / f"{name}.tex"
            if cand.exists():
                return cand
        return None

    missing = [f for f in FRAGMENTS if _fragment(f) is None]
    if missing:
        raise SystemExit(f"missing fragments: {missing}")
    # Every fragment under appendix/, the generated subfolder and the
    # experiment-data parts included: several pull in further files with
    # \\input, and a file missed here fails the build with a float option the
    # template does not define.
    for sub in ("appendix", "generated", "experiment_data"):
        for path in sorted((work / sub).rglob("*.tex")):
            path.write_text(normalize(path.read_text()))

    # Plain pdflatex, three passes, then bibtex and two more. latexmk reads a
    # record of its previous build and returns without running when it judges
    # nothing changed, which leaves this document one pass short of resolving
    # its own labels no matter how many times it is called.
    def run(cmd: list[str]):
        return subprocess.run(cmd, cwd=work, capture_output=True, text=True)

    for _ in range(3):
        result = run(["pdflatex", "-interaction=nonstopmode", "supplement.tex"])
    if (work / "supplement.aux").exists():
        run(["bibtex", "supplement"])
        for _ in range(2):
            result = run(["pdflatex", "-interaction=nonstopmode", "supplement.tex"])

    pdf = work / "supplement.pdf"
    if not pdf.exists():
        tail = "\n".join((result.stdout if result else "").splitlines()[-20:])
        raise SystemExit(f"supplement did not build\n{tail}")

    args.out.mkdir(parents=True, exist_ok=True)
    target = args.out / "idt_technical_supplement.pdf"
    shutil.copy(pdf, target)

    log = (work / "supplement.log").read_text(errors="replace")
    info = subprocess.run(["pdfinfo", str(target)], capture_output=True, text=True)
    pages = next((line.split()[-1] for line in info.stdout.splitlines()
                  if line.startswith("Pages")), "?")
    errors = len(re.findall(r"^! ", log, re.M))
    undefined = len(re.findall(r"Reference [^ ]* on page", log))
    overfull = len(re.findall(r"Overfull \\hbox", log))
    print(f"wrote {target} ({pages} pages)")
    print(f"  errors {errors} | undefined refs {undefined} | overfull {overfull}")
    if not args.keep_build:
        shutil.rmtree(work)
    if errors:
        raise SystemExit("the supplement built with errors; read the log above")


if __name__ == "__main__":
    main()
