"""Build one experiment-data PDF per target organism into build/experiment_data/.

    uv run python script/paper/build_experiment_data.py

Each generated part under ``experiment_data/`` becomes its own document:
``experiment_data.tex`` supplies the preamble and title, and the part supplies
the body. The index stays a source-tree table of contents and gets no PDF of
its own.

Regenerate the parts first with script/paper/write_data_appendix.py
--by-organism; a missing part fails the build loudly.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

from src.appendix.latex_float_normalization import normalize
from src.common.paper_output_dir import PAPER_DIR

def _compile(work: Path, master: str) -> subprocess.CompletedProcess:
    return subprocess.run(["pdflatex", "-interaction=nonstopmode", master],
                          cwd=work, capture_output=True, text=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--paper", type=Path, default=PAPER_DIR)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    out = args.out or (args.paper / "build")
    target_dir = out / "experiment_data"

    work = out / "_experiment_data"
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(args.paper, work, ignore=shutil.ignore_patterns(
        ".git", "build", "CLAUDE.md", "AUTHORS.md", ".DS_Store"))
    for sub in ("appendix", "generated", "experiment_data"):
        for path in sorted((work / sub).rglob("*.tex")):
            path.write_text(normalize(path.read_text()))

    template = (work / "experiment_data.tex").read_text()
    anchor = "\\input{experiment_data/index}"
    if anchor not in template:
        raise SystemExit("experiment_data.tex lost its body anchor "
                         f"{anchor!r}; the builder cannot substitute parts")

    parts = sorted(p.stem for p in (work / "experiment_data").glob("*.tex")
                   if p.stem != "index")
    if not parts:
        raise SystemExit("no parts under experiment_data/; run "
                         "write_data_appendix.py --by-organism first")

    target_dir.mkdir(parents=True, exist_ok=True)
    # A part that no longer exists must not leave its PDF behind.
    for stale in sorted(target_dir.glob("*.pdf")):
        if stale.stem not in parts:
            stale.unlink()
            print(f"removed stale {stale}")
    failures = []
    for part in parts:
        body = f"\\input{{experiment_data/{part}}}"
        master = f"doc_{part}.tex"
        (work / master).write_text(template.replace(anchor, body))
        for _ in range(3):
            proc = _compile(work, master)
        pdf = work / f"doc_{part}.pdf"
        log = (work / f"doc_{part}.log").read_text(errors="replace")
        errors = log.count("\n! ")
        undefined = log.count("Reference `")
        if proc.returncode != 0 or errors or undefined or not pdf.exists():
            failures.append((part, errors, undefined))
            continue
        shutil.copy(pdf, target_dir / f"{part}.pdf")
        print(f"wrote {target_dir / f'{part}.pdf'}")

    # The combined document is gone; a stale copy must not outlive it.
    legacy = out / "experiment_data.pdf"
    if legacy.exists():
        legacy.unlink()
        print(f"removed legacy {legacy}")

    if failures:
        for part, errors, undefined in failures:
            print(f"  FAILED {part}: {errors} errors, {undefined} undefined refs")
        raise SystemExit("per-organism experiment-data builds failed")
    print(f"built {len(parts)} per-organism PDFs into {target_dir}")


if __name__ == "__main__":
    main()
