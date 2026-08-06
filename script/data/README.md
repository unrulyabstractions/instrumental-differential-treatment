# script/data

We publish each local `out/` result tree to the project's private HuggingFace dataset repo, idempotently and byte-compared, refusing any path that contains a `models` component.

This folder holds the publisher and the dataset card that becomes the repo's `README.md`. The publisher uploads a stage output tree (ellicit, promptset, conjecture, score, compare) under a chosen path prefix, creating the repo private if it does not yet exist and never changing an existing repo's visibility. It skips a file whose bytes already match the remote, comparing the git blob sha1 for regular files and the sha256 for LFS files with a size shortcut first. Working copies are left out by default: the `box_capture` pre-teardown sweeps, the `__v` seat splits whose rows were merged into their parent run, and the `.preduped`/`.merging`/`.lock` sidecars. Pass `--include-all` to send them; model weights stay refused either way.

## Scripts

| Script | What it does | Run |
|---|---|---|
| `publish_dataset.py` | Uploads one local output tree to the private HF dataset repo, skipping files whose bytes already match the remote and refusing any `models` path. Can also upload the dataset card as the repo `README.md`. | `uv run python script/data/publish_dataset.py --out-root out/r2 --path-prefix r2` |
