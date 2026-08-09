"""Publish one local output tree to the project's private HF dataset repo.

Uploads every file under ``--out-root`` to ``<path-prefix>/`` in the dataset
repo. Any path containing a ``models`` component is refused (organism weights
are third-party checkpoints and are never redistributed), and macOS junk files
are skipped. The script is idempotent: a file whose bytes already match the
remote copy is not re-sent. Change detection compares the git blob sha1 for
regular files and the sha256 for LFS files, with a size shortcut first.

The repo is created private if it does not exist. This script never changes
the visibility of an existing repo.

File selection lives in ``src/common/publish_dataset_tree_scan.py`` and change
detection in ``src/common/publish_dataset_change_detection.py``.

Usage:
    uv run python script/data/publish_dataset.py \
        --out-root archive/r1_20260726/out --path-prefix r1
    uv run python script/data/publish_dataset.py --out-root out/main/secret_loyalties --path-prefix r2
    uv run python script/data/publish_dataset.py --out-root configs --path-prefix configs
    uv run python script/data/publish_dataset.py --card script/data/dataset_card_readme.md
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from huggingface_hub import CommitOperationAdd, HfApi

from src.common.publish_dataset_change_detection import (
    CHUNK as CHUNK,
    git_blob_sha1 as git_blob_sha1,
    matches_remote,
    remote_index,
    sha256_hex as sha256_hex,
)
from src.common.publish_dataset_tree_scan import (
    FORBIDDEN_DIR_COMPONENTS as FORBIDDEN_DIR_COMPONENTS,
    SKIP_BASENAMES as SKIP_BASENAMES,
    SKIP_DIR_PARTS as SKIP_DIR_PARTS,
    SKIP_DIR_SUFFIX_MARKER as SKIP_DIR_SUFFIX_MARKER,
    SKIP_SUFFIXES as SKIP_SUFFIXES,
    collect_local,
)

DEFAULT_REPO_ID = os.environ.get("HF_DATASET_REPO", "your-hf-org/idt-data")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-root", type=Path, help="local tree to upload, e.g. out/main/secret_loyalties")
    parser.add_argument("--path-prefix", help="folder inside the repo, e.g. r2")
    parser.add_argument("--card", type=Path, help="local file to upload as README.md")
    parser.add_argument("--repo-id", default=DEFAULT_REPO_ID)
    parser.add_argument("--dry-run", action="store_true", help="report, upload nothing")
    parser.add_argument("--include-all", action="store_true",
                        help="upload working copies too: box_capture, __v seat splits, and "
                             "the .preduped/.merging/.lock sidecars. Model weights are still "
                             "refused.")
    parser.add_argument("--exclude", action="append", default=[],
                        help="skip a path relative to --out-root; repeatable")
    args = parser.parse_args()
    if (args.out_root is None) != (args.path_prefix is None):
        parser.error("--out-root and --path-prefix must be given together")
    if args.out_root is None and args.card is None:
        parser.error("nothing to do: give --out-root/--path-prefix or --card")
    return args


def main() -> None:
    args = parse_args()
    api = HfApi()
    api.create_repo(args.repo_id, repo_type="dataset", private=True, exist_ok=True)
    print(f"repo: datasets/{args.repo_id} (created private if new)")

    pairs: list[tuple[Path, str]] = []
    junk = 0
    if args.out_root is not None:
        pairs, junk = collect_local(args.out_root, args.path_prefix.strip("/"),
                                    include_all=args.include_all,
                                    exclude=tuple(args.exclude))
    if args.card is not None:
        pairs.append((args.card, "README.md"))

    remote = remote_index(api, args.repo_id)
    to_send = [(p, rp) for p, rp in pairs if not matches_remote(p, remote.get(rp))]
    unchanged = len(pairs) - len(to_send)

    total = 0
    for path, repo_path in to_send:
        size = path.stat().st_size
        total += size
        verb = "would upload" if args.dry_run else "upload"
        print(f"{verb}  {repo_path}  ({size} bytes)")
    print(f"{len(to_send)} files to upload ({total} bytes), "
          f"{unchanged} unchanged, {junk} junk files skipped")

    if args.dry_run or not to_send:
        return
    operations = [CommitOperationAdd(path_in_repo=rp, path_or_fileobj=str(p))
                  for p, rp in to_send]
    label = args.path_prefix or "README.md"
    api.create_commit(repo_id=args.repo_id, repo_type="dataset", operations=operations,
                      commit_message=f"Upload {label}: {len(to_send)} files")
    print(f"committed {len(to_send)} files ({total} bytes) to datasets/{args.repo_id}")


if __name__ == "__main__":
    main()
