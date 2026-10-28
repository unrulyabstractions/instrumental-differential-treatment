"""Prove a data restructure lost nothing: every original file still exists, intact.

    uv run python script/data/verify_restructure_capture.py \\
        --manifest before_sha.txt --root out/main/secret_loyalties \\
        --superseded out/superseded/2026-10-28_nsl_ungated

``--manifest`` is ``shasum -a 256`` output taken before the restructure, one
``<hash>  <path>`` line per file. Each original file must be found, with the
same hash, either where it was or at the same relative path under the
superseded tree. The script prints one count per outcome and exits non-zero
when any file is lost or changed, or when the manifest is empty (an empty
manifest proves nothing).
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_manifest(path: Path) -> list[tuple[str, Path]]:
    rows = []
    for line in path.read_text().splitlines():
        if line.strip():
            digest, name = line.split(None, 1)
            rows.append((digest, Path(name.strip())))
    return rows


def check(manifest: list[tuple[str, Path]], root: Path, superseded: Path) -> dict[str, list[Path]]:
    """Sort every original file into in-place, superseded, or lost."""
    out: dict[str, list[Path]] = {"in_place": [], "superseded": [], "both": [], "lost": []}
    for digest, path in manifest:
        here = path.exists() and sha(path) == digest
        kept = superseded / path.relative_to(root)
        there = kept.exists() and sha(kept) == digest
        key = "both" if here and there else "in_place" if here else "superseded" if there else "lost"
        out[key].append(path)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--superseded", type=Path, required=True)
    args = ap.parse_args()
    manifest = read_manifest(args.manifest)
    if not manifest:
        print("the manifest is empty; nothing is proven")
        return 1
    result = check(manifest, args.root, args.superseded)
    for key, paths in result.items():
        print(f"{key:11s} {len(paths)}")
    for path in result["lost"]:
        print(f"LOST {path}")
    print(f"{len(manifest)} original files checked")
    return 1 if result["lost"] else 0


if __name__ == "__main__":
    sys.exit(main())
