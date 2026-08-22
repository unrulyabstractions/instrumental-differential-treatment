"""Build the OpenReview submission deliverables, allowlisted and anonymous.

    uv run python script/paper/build_submission_package.py

AAAI-27 takes supplementary material as up to three uploads: a supplementary
document (PDF), a media archive (ZIP), and a code-and-data package (ZIP). This
script produces the two we submit beside the main paper:

* ``build/idt_technical_supplement.pdf`` via ``build_supplement.py``.
* ``build/idt_code_and_data_supplement.zip``: the pipeline source and analysis
  data, allowlisted file by file, with the experiment-data PDF inside.
* ``build/idt_media_supplement.zip``: the explorer artifact, one page.

Everything is allowlisted, never swept from a directory listing, so repository
housekeeping (CLAUDE.md, agents/, tmp/, egg-info, .git) structurally cannot
enter. Anonymity is enforced, not assumed: after building, every text file in
the zip and the first page of each PDF are scanned for the identity strings
below, and a single hit fails the build. The reply corpus and organism weights
stay out by policy, and the package README says where the paper states data
availability.
"""

from __future__ import annotations

import re
import subprocess
import zipfile
from pathlib import Path

from src.common.paper_output_dir import PAPER_DIR

#: A hit on any of these anywhere in the package fails the build.
IDENTITY_STRINGS = ("rios-sialer", "Rios-Sialer", "eliwang", "Eli Wang",
                    "unrulyabstractions", "ian@", "apart-idt")

#: Names that only leak as whole words. "Ian" sits inside ordinary words
#: (Brian, variance), so a substring needle would drown the scan in false
#: hits; a word-boundary match catches the leak that shipped and nothing else.
IDENTITY_PATTERNS = (re.compile(r"\bIan\b"), re.compile(r"\bEli\b"))

#: Directories shipped whole (every tracked text file under them), plus single
#: files. Nothing outside this list can enter the archive.
PACKAGE_DIRS = ("src", "script", "tests", "configs")
PACKAGE_FILES = ("pyproject.toml", "README.md", "uv.lock")

#: The analysis artifacts every number in the paper is read from. These are
#: results rather than replies: verdicts, permutation records, answer keys,
#: manifests, and the frozen prompts and axes. Shipping them lets a reviewer
#: recompute each table without the reply corpus, which stays unreleased.
DATA_GLOBS = (
    "out/main/**/comparison_summary.json",
    "out/main/**/reference_free.json",
    "out/main/**/paired_coherence.json",
    "out/main/**/geometry_summary.json",
    "out/main/**/elicitation_report.json",
    "out/main/**/scoring_questions.json",
    "out/main/**/hypotheses.json",
    "out/main/**/prompt_sets.json",
    "out/main/**/templates.json",
    "out/main/**/promptset_report.json",
    "out/main/**/questions.json",
    "out/main/**/judge_comparison.json",
    "out/main/**/scoring_report.json",
    "out/main/**/collection_report.json",
    "out/main/**/per_framing_challenge.json",
    "out/main/**/stage_ablation.json",
    "out/main/**/coherence_pooled.json",
    "out/main/auditbench/shared/control_comparison.json",
    "out/main/auditbench/shared/fleet_report.json",
    "out/main/external/**/our_pipeline_verdict.json",
    "out/main/external/**/retrain_verdict.json",
    "out/main/external/**/user_awareness_detection.json",
    "out/main/external/**/targets_phase3.json",
    "out/main/external/**/organism_training.json",
    "out/main/external/**/ourgen_verdict.json",
    "out/main/external/**/authors_training_manifest.json",
    "out/main/external/**/authors_sanity_checks.json",
    "out/main/external/**/ourgen_covertness_report.json",
    "out/main/external/**/PROVENANCE.json",
)

PACKAGE_NOTE = """\
Code package for double-blind review.

This is the six-stage audit pipeline the paper reports: sources under src/,
entry points under script/, the statistics test suite under tests/, and the
generated stage configs under configs/. Install with `uv pip install -e .` and
run the suite with `uv run pytest tests/`.

Under out/ are the analysis artifacts the paper's numbers are read from: each
run's stage-6 verdict, the permutation records for the side checks, the frozen
prompts and behavior axes, the elicitation reports, the judge-seat comparison,
the robustness and ablation records, and the model organism's answer key with
our own measurements against it.

We checked what these regenerate. Running the appendix generator against this
package alone reproduces the top-candidate table, the base-free appendix, the
fold-comparison appendix, the judge-seat appendix, and the model-organism macro
file byte for byte against the submitted document.

Two things do not regenerate here, both by policy rather than by omission. The
per-reply accounting tables and the quoted reply cards are computed by scanning
the reply corpus, and the behavior-distribution figures are compiled with the
paper; the per-organism data PDFs ship under experiment_data_pdfs/. The corpus, the organism weights, and third-party organism checkpoints
are not redistributed; the paper's reproducibility statement covers data
availability, and the printed values for both appear in the submitted appendix.
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
    # The analysis artifacts live under a gitignored tree, so they are collected
    # by glob rather than from the index.
    for pattern in DATA_GLOBS:
        picked.extend(sorted(p for p in repo.glob(pattern) if p.is_file()))
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
            for pattern in IDENTITY_PATTERNS:
                if pattern.search(text):
                    hits.append(f"{name}: {pattern.pattern}")
    return hits


def scan_pdf_first_page(pdf: Path) -> list[str]:
    text = subprocess.run(["pdftotext", "-f", "1", "-l", "1", str(pdf), "-"],
                          capture_output=True, text=True).stdout
    return ([n for n in IDENTITY_STRINGS if n in text]
            + [p.pattern for p in IDENTITY_PATTERNS if p.search(text)]) + (
        [] if "Anonymous" in text else ["first page does not say Anonymous"])


def main() -> None:
    repo = Path(__file__).resolve().parents[2]
    build = PAPER_DIR / "build"
    build.mkdir(parents=True, exist_ok=True)

    subprocess.run(["uv", "run", "python", "script/paper/build_supplement.py"],
                   cwd=repo, check=True)
    supplement = build / "idt_technical_supplement.pdf"
    subprocess.run(["uv", "run", "python", "script/paper/build_experiment_data.py"],
                   cwd=repo, check=True)
    experiment_pdfs = sorted((build / "experiment_data").glob("*.pdf"))

    package = build / "idt_code_and_data_supplement.zip"
    picked = build_code_package(repo, package)
    # The per-organism data PDFs ride inside the code-and-data zip: they are
    # the data appendix of record, and AAAI takes one archive for this slot.
    with zipfile.ZipFile(package, "a", zipfile.ZIP_DEFLATED) as zf:
        for pdf in experiment_pdfs:
            zf.write(pdf, f"experiment_data_pdfs/{pdf.name}")

    media = build / "idt_media_supplement.zip"
    artifact = repo / "artifact/idt_explorer.html"
    with zipfile.ZipFile(media, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(artifact, "idt_explorer.html")

    problems = scan_zip_for_identity(package)
    problems += [f"media: {p}" for p in scan_zip_for_identity(media)]
    problems += [f"supplement: {p}" for p in scan_pdf_first_page(supplement)]
    for pdf in experiment_pdfs:
        problems += [f"{pdf.name}: {q}" for q in scan_pdf_first_page(pdf)]
    main_pdf = PAPER_DIR / "main.pdf"
    if main_pdf.exists():
        problems += [f"main.pdf: {p}" for p in scan_pdf_first_page(main_pdf)]

    size = package.stat().st_size / 1e6
    print(f"wrote {package} ({len(picked)} files + REVIEW_README, {size:.1f} MB)")
    print(f"wrote {supplement}")
    print(f"wrote {media} ({media.stat().st_size / 1e6:.1f} MB)")
    print(f"bundled {len(experiment_pdfs)} per-organism data PDFs")
    if problems:
        for p in problems:
            print(f"  IDENTITY LEAK: {p}")
        raise SystemExit("the package is not anonymous; nothing should be uploaded")
    print("anonymity scan clean: zip text files and both PDFs' first pages")


if __name__ == "__main__":
    main()
