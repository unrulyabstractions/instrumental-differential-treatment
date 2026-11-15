"""Registered settings and write-once output helpers for the baseline-free workflow (B72).

Every family imports its settings from here, so all of them run the registered
test's parameters unless a method fixes others:

    SEED 20260726, N_PERM 10000, ALPHA 0.01

``settings_block()`` returns the block every output records: the three settings,
the code-repo commit, and whether the source files the analysis imports are
clean at that commit.

``save_new_json`` and ``save_new_text`` write a file that must not exist yet.
The write goes to a temporary file in the same folder and is then hard-linked
into place, so the target either does not exist or holds the full content, and
an existing file is never replaced. A superseded output is moved to
``out/superseded/`` by hand, never overwritten.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

SEED = 20260726
N_PERM = 10000
ALPHA = 0.01

#: Spend caps (B72 workflow): $3 for one analysis, $5 for the whole workflow.
ANALYSIS_CAP_USD = 3.0
WORKFLOW_CAP_USD = 5.0

#: Every family writes under OUT_ROOT / <family>.
OUT_ROOT = REPO / "out/main/baseline_free_20261115"
SCRIPT_ROOT = REPO / "script/analysis/baseline_free_20261115"
REGISTRY_DIR = OUT_ROOT / "subjects_registry"
SUBJECTS_JSON = REGISTRY_DIR / "subjects.json"

#: Source folders whose state at HEAD is recorded beside every result.
_SOURCE_DIRS = ("src/compare", "src/common", "src/geometry", "src/ui", "src/conjecture",
                "src/external", "script/analysis/reanalysis_2026_11",
                "script/analysis/null_extension_compare.py",
                "script/analysis/baseline_free_20261115/common")


class RefusedOverwrite(SystemExit):
    """Raised when an output path already exists."""


def _git(*args: str) -> str:
    out = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True,
                         check=True)
    return out.stdout.strip()


def code_state() -> dict:
    """The code-repo commit and any uncommitted change under the imported sources."""
    commit = _git("rev-parse", "HEAD")
    dirty = [line for line in _git("status", "--porcelain", "--", *_SOURCE_DIRS).splitlines()
             if line.strip()]
    return {"code_commit": commit, "imported_sources": list(_SOURCE_DIRS),
            "imported_sources_uncommitted": dirty}


def settings_block(**extra) -> dict:
    """The settings every output records, plus any method-specific ones."""
    return {"seed": SEED, "n_permutations": N_PERM, "alpha": ALPHA,
            "analysis_cap_usd": ANALYSIS_CAP_USD, "workflow_cap_usd": WORKFLOW_CAP_USD,
            **code_state(), **extra}


def _write_new(path: Path, data: bytes) -> Path:
    path = Path(path)
    if path.exists():
        raise RefusedOverwrite(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    os.fchmod(fd, 0o644)  # mkstemp creates 0600; outputs are ordinary readable files
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        try:
            os.link(tmp, path)  # fails if the path appeared meanwhile
        except FileExistsError as exc:
            raise RefusedOverwrite(f"refusing to overwrite {path}") from exc
    finally:
        os.unlink(tmp)
    return path


def save_new_json(path: Path, obj) -> Path:
    """Write ``obj`` as JSON to a path that must not exist yet."""
    text = json.dumps(obj, indent=1, sort_keys=False, default=str, ensure_ascii=False) + "\n"
    return _write_new(path, text.encode("utf-8"))


def save_new_text(path: Path, text: str) -> Path:
    """Write text to a path that must not exist yet."""
    return _write_new(path, text.encode("utf-8"))


def selftest() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "a.json"
        save_new_json(p, {"x": 1})
        try:
            save_new_json(p, {"x": 2})
        except RefusedOverwrite:
            pass
        else:
            raise SystemExit("selftest: an existing file was overwritten")
        if json.loads(p.read_text()) != {"x": 1}:
            raise SystemExit("selftest: the first write was changed")
        if [q.name for q in Path(tmp).iterdir()] != ["a.json"]:
            raise SystemExit("selftest: a temporary file was left behind")
    print("settings selftest passed")


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        selftest()
    else:
        print(json.dumps(settings_block(), indent=1))
