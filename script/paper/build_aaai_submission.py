"""Build the AAAI-27 submission from the working paper.

    uv run python script/paper/build_aaai_submission.py

The working paper in ``paper/`` is a single-column arXiv-style document with long
appendices. AAAI-27 wants two columns, seven pages of main content, and a style
file that forbids much of what the working paper uses. Converting by hand would
have to be redone on every edit, so it is done here. The conversion rules live
in ``src/appendix/build_aaai_submission_conversion.py`` and the preamble
template in ``src/appendix/build_aaai_submission_preamble.py``. The appendices
are dropped: AAAI takes them as supplementary material, so the body keeps only
the sections a reader needs, and the task formalization moves out with them.

The output tree is disposable. Edit ``paper/`` and run this again.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from src.appendix.build_aaai_submission_conversion import (
    DROP_INPUTS,
    DROP_SUBSECTIONS as DROP_SUBSECTIONS,
    PREFIX_WORD as PREFIX_WORD,
    WIDE_FLOATS as WIDE_FLOATS,
    _repoint_dangling,
    convert,
)
from src.appendix.build_aaai_submission_preamble import BODY, MAIN
from src.common.paper_output_dir import PAPER_DIR


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--paper", type=Path, default=PAPER_DIR)
    ap.add_argument("--out", type=Path, default=Path("aaai"))
    args = ap.parse_args()
    out = args.out
    (out / "sections").mkdir(parents=True, exist_ok=True)

    (out / "abstract.tex").write_text(convert((args.paper / "abstract.tex").read_text()))
    # Generated tables the Results section inputs, and the macros the geometry
    # captions interpolate. Both are produced by the pipeline, not written here.
    # A dropped table must not be copied: its file would still define the label,
    # the dangling-reference pass would think the target exists, and the citation
    # would print as ?? because nothing inputs the file.
    dropped = {Path(name).name for name in DROP_INPUTS}
    for generated in sorted((args.paper / "sections").glob("generated_*.tex")):
        if generated.name in dropped:
            continue
        (out / "sections" / generated.name).write_text(convert(generated.read_text()))
    (out / "geometry_numbers.tex").write_text(
        (args.paper / "appendix" / "geometry_numbers.tex").read_text())
    lines = []
    for name in BODY:
        source = args.paper / "sections" / f"{name}.tex"
        (out / "sections" / f"{name}.tex").write_text(convert(source.read_text()))
        lines.append(f"\\input{{sections/{name}}}")
    (out / "main.tex").write_text(MAIN.replace("%%CONTENT%%", "\n".join(lines)))

    figures = out / "figures"
    if figures.exists():
        shutil.rmtree(figures)
    shutil.copytree(args.paper / "figures", figures,
                    ignore=shutil.ignore_patterns("*.png", ".DS_Store", "compare"))
    for tex in figures.rglob("*.tex"):
        tex.write_text(convert(tex.read_text()))
    shutil.copy(args.paper / "refs.bib", out / "refs.bib")
    touched = _repoint_dangling(out)
    print(f"wrote {out}/main.tex with {len(BODY)} body sections")
    print(f"repointed dangling references in {touched} files")
    print("appendices and the task formalization are excluded: they go to the "
          "supplementary archive")


if __name__ == "__main__":
    main()
