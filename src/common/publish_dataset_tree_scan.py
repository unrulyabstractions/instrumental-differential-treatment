"""Local-tree file selection for ``script/data/publish_dataset.py``.

Walks an output tree into (local file, repo path) pairs and applies the skip
rules: macOS junk, caller-listed exclusions, the working copies the pipeline
leaves behind, and a hard refusal of any ``models`` path. Lives here rather
than inside the publish script because scripts are not importable.
"""

from __future__ import annotations

import sys
from pathlib import Path

__all__ = [
    "FORBIDDEN_DIR_COMPONENT",
    "SKIP_BASENAMES",
    "SKIP_DIR_PARTS",
    "SKIP_DIR_SUFFIX_MARKER",
    "SKIP_SUFFIXES",
    "collect_local",
]

SKIP_BASENAMES = {".DS_Store"}
FORBIDDEN_DIR_COMPONENT = "models"

#: Directories that are local scratch, not results. ``box_capture`` is the
#: pre-teardown sweep of the rented machines: it is a second copy of data already
#: published under its own stage, plus superseded versions of this repo's own
#: code, so publishing it would duplicate the dataset and ship stale source.
#: A ``__v`` directory is a seat split across machines whose rows were merged
#: back into the parent run, so publishing it double-counts responses.
SKIP_DIR_PARTS = ("box_capture",)
SKIP_DIR_SUFFIX_MARKER = "__v"

#: Suffixes of working files the pipeline leaves beside a result. A ``.preduped``
#: sidecar is the pre-deduplication state from the two-writer collision, kept
#: locally as evidence; it is not what any number was computed from. ``.merging``
#: is a half-written temporary and ``.lock`` is a mutex.
SKIP_SUFFIXES = (".preduped", ".predupe", ".merging", ".lock")


def collect_local(root: Path, prefix: str, include_all: bool = False,
                  exclude: tuple[str, ...] = ()) -> tuple[list[tuple[Path, str]], int]:
    """Return (local file, repo path) pairs under root, and the junk-skip count.

    ``include_all`` keeps the working copies the default run leaves behind: the
    pre-teardown box sweeps, the ``__v`` seat splits whose rows were merged into
    their parent run, and the sidecar files. They duplicate published data rather
    than adding to it, so they are off by default and asked for explicitly.
    Model weights are refused either way.
    """
    pairs, junk = [], 0
    excluded = tuple(e.strip("/") for e in exclude)
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root)
        if FORBIDDEN_DIR_COMPONENT in rel.parts or FORBIDDEN_DIR_COMPONENT in prefix.split("/"):
            sys.exit(f"refusing to upload a models/ path: {path}")
        if path.name in SKIP_BASENAMES:
            junk += 1
            continue
        posix = rel.as_posix()
        if any(posix == e or posix.startswith(e + "/") for e in excluded):
            junk += 1
            continue
        if not include_all:
            if any(part in SKIP_DIR_PARTS or part.endswith(SKIP_DIR_SUFFIX_MARKER)
                   or SKIP_DIR_SUFFIX_MARKER in part for part in rel.parts[:-1]):
                junk += 1
                continue
            if path.name.endswith(SKIP_SUFFIXES):
                junk += 1
                continue
        pairs.append((path, f"{prefix}/{rel.as_posix()}"))
    if not pairs:
        sys.exit(f"no files found under {root}")
    return pairs, junk
