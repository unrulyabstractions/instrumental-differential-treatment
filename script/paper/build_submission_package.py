"""Build the OpenReview submission deliverables, allowlisted and anonymous.

    uv run python script/paper/build_submission_package.py

AAAI-27 takes supplementary material as up to three uploads: a supplementary
document (PDF), a media archive (ZIP), and a code-and-data package (ZIP). This
script produces the two we submit beside the main paper:

* ``build/supplement.pdf`` via ``build_supplement.py``, compiled in review mode.
* ``build/code_package.zip``: the pipeline source, allowlisted file by file.

Everything is allowlisted, never swept from a directory listing, so repository
housekeeping (CLAUDE.md, agents/, tmp/, egg-info, .git) structurally cannot
enter. Anonymity is enforced, not assumed: after building, every text file in
the zip and the first page of each PDF are scanned for the identity strings
below, and a single hit fails the build. The reply corpus and organism weights
stay out by policy, and the package README says where the paper states data
availability.
"""

from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path

from src.common.paper_output_dir import PAPER_DIR

#: A hit on any of these anywhere in the package fails the build.
IDENTITY_STRINGS = ("rios-sialer", "Rios-Sialer", "eliwang", "Eli Wang",
                    "unrulyabstractions", "ian@")

#: Directories shipped whole (every tracked text file under them), plus single
#: files. Nothing outside this list can enter the archive.
PACKAGE_DIRS = ("src", "script", "tests", "configs")
PACKAGE_FILES = ("pyproject.toml", "README.md", "uv.lock")

PACKAGE_NOTE = """\
Code package for double-blind review.

This is the six-stage audit pipeline the paper reports: sources under src/,
entry points under script/, the statistics test suite under tests/, and the
generated stage configs under configs/. Install with `uv pip install -e .` and
run the suite with `uv run pytest tests/`. The reply corpus and third-party
organism checkpoints are not redistributed; the paper's reproducibility
statement covers data availability.
"""


def _tracked_files(repo: Path) -> list[Path]:
    out = subprocess.run(["git", "ls-files"], cwd=repo, capture_output=True,
                         text=True, check=True)
    return [repo / line for line in out.stdout.splitlines() if line.strip()]


def build_code_package(repo: Path, target: Path) -> list[Path]:
    picked = []
    self_path = Path(__file__).resolve().relative_to(repo).as_posix()
    for path in _tracked_files(repo):
        rel = path.relative_to(repo)
        # The builder itself stays out: it carries the identity needles it
        # scans for, so packaging it would always fail its own scan.
        if rel.as_posix() == self_path:
            continue
        if rel.as_posix() in PACKAGE_FILES or rel.parts[0] in PACKAGE_DIRS:
            picked.append(path)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("REVIEW_README.txt", PACKAGE_NOTE)
        for path in picked:
            zf.write(path, path.relative_to(repo).as_posix())
    return picked


def scan_zip_for_identity(target: Path) -> list[str]:
    hits = []
    with zipfile.ZipFile(target) as zf:
        for name in zf.namelist():
            data = zf.read(name)
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                continue
            for needle in IDENTITY_STRINGS:
                if needle in text:
                    hits.append(f"{name}: {needle}")
    return hits


def scan_pdf_first_page(pdf: Path) -> list[str]:
    text = subprocess.run(["pdftotext", "-f", "1", "-l", "1", str(pdf), "-"],
                          capture_output=True, text=True).stdout
    return [n for n in IDENTITY_STRINGS if n in text] + (
        [] if "Anonymous" in text else ["first page does not say Anonymous"])


def main() -> None:
    repo = Path(__file__).resolve().parents[2]
    build = PAPER_DIR / "build"
    build.mkdir(parents=True, exist_ok=True)

    subprocess.run(["uv", "run", "python", "script/paper/build_supplement.py"],
                   cwd=repo, check=True)
    supplement = build / "supplement.pdf"
    subprocess.run(["uv", "run", "python", "script/paper/build_experiment_data.py"],
                   cwd=repo, check=True)
    experiment_data = build / "experiment_data.pdf"

    package = build / "code_package.zip"
    picked = build_code_package(repo, package)

    problems = scan_zip_for_identity(package)
    problems += [f"supplement.pdf: {p}" for p in scan_pdf_first_page(supplement)]
    problems += [f"experiment_data.pdf: {p}" for p in scan_pdf_first_page(experiment_data)]
    main_pdf = PAPER_DIR / "main.pdf"
    if main_pdf.exists():
        problems += [f"main.pdf: {p}" for p in scan_pdf_first_page(main_pdf)]

    size = package.stat().st_size / 1e6
    print(f"wrote {package} ({len(picked)} files + REVIEW_README, {size:.1f} MB)")
    print(f"wrote {supplement}")
    print(f"wrote {experiment_data}")
    if problems:
        for p in problems:
            print(f"  IDENTITY LEAK: {p}")
        raise SystemExit("the package is not anonymous; nothing should be uploaded")
    print("anonymity scan clean: zip text files and both PDFs' first pages")


if __name__ == "__main__":
    main()
