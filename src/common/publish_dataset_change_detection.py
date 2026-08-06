"""Remote change detection for ``script/data/publish_dataset.py``.

Decides whether a local file's bytes already match its copy in the HF dataset
repo, so an idempotent publish never re-sends an unchanged file. Comparison
uses the git blob sha1 for regular files and the sha256 for LFS files, with a
size shortcut first. Lives here rather than inside the publish script because
scripts are not importable.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from huggingface_hub import HfApi

__all__ = ["CHUNK", "git_blob_sha1", "matches_remote", "remote_index", "sha256_hex"]

CHUNK = 1 << 20


def sha256_hex(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(CHUNK):
            digest.update(block)
    return digest.hexdigest()


def git_blob_sha1(path: Path) -> str:
    digest = hashlib.sha1(b"blob %d\0" % path.stat().st_size)
    with path.open("rb") as handle:
        while block := handle.read(CHUNK):
            digest.update(block)
    return digest.hexdigest()


def remote_index(api: HfApi, repo_id: str) -> dict[str, object]:
    entries = api.list_repo_tree(repo_id, repo_type="dataset", recursive=True)
    return {e.path: e for e in entries if hasattr(e, "blob_id")}


def matches_remote(path: Path, entry: object) -> bool:
    if entry is None or entry.size != path.stat().st_size:
        return False
    if entry.lfs is not None:
        return entry.lfs.sha256 == sha256_hex(path)
    return entry.blob_id == git_blob_sha1(path)
