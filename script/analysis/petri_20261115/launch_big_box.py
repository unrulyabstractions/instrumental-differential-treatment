"""Rent the 70B Petri box of B73 (2x H200 class), prove it healthy, provision it and start its runner.

    uv run python -m script.analysis.petri_20261115.launch_big_box --offers-only   # read-only
    uv run python -m script.analysis.petri_20261115.launch_big_box                 # dry run after preflight
    YES=1 uv run python -m script.analysis.petri_20261115.launch_big_box           # rents

Recipe: script/analysis/petri_20261115/box/big_box_recipe.json. Core and credit rule: box_launch_core.py. The
box goes into out/main/petri_20261115/boxes.json the moment it is created.

Extra preflight: the small-box Petri cells P01 to P04 are reconciled in the Petri ledger (the order the owner
set: small organisms first), no small box is live (credit), and HF_TOKEN is set (read only here, to sign the
gated base weights' URLs; never printed, never sent). Provision: push the runner, the fetcher and the recipe;
sign the base weights here (commit and the 31 sizes checked, original/ rows dropped); start the runner.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from script.analysis.petri_20261115.box_launch_core import Launch  # noqa: E402

HERE = Path(__file__).resolve().parent
RECIPE = HERE / "box/big_box_recipe.json"
STAGE = REPO / "tmp/weights_stage_b73_big"
LEDGER = REPO / "out/main/petri_20261115/spend_ledger.jsonl"


def extra_preflight() -> None:
    if not (os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")):
        raise SystemExit("preflight: HF_TOKEN is not set (needed here only, to sign the base weights' URLs)")
    events = [json.loads(x) for x in LEDGER.read_text().splitlines() if x.strip()] if LEDGER.exists() else []
    done = {e["stage"].split("_")[0] for e in events if e["event"] == "reconcile"}
    missing = [c for c in ("P01", "P02", "P03", "P04") if c not in done]
    if missing:
        raise SystemExit(f"preflight: small-organism cells {missing} are not reconciled; the 70B box waits")


def stage_base(recipe: dict) -> Path:
    from script.remote.boxes.stage_gated_weights import stage_repo
    w = recipe["weights"]["base"]
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if STAGE.exists():
        shutil.move(str(STAGE), str(REPO / f"tmp/weights_stage_b73_big.superseded.{int(time.time())}"))
    summary = stage_repo(w["repo"], STAGE, token)
    if summary["commit"] != w["commit"]:
        raise RuntimeError(f"{w['repo']} is at {summary['commit']}, not {w['commit']}")
    d = Path(summary["dir"])
    m = d / "_lfs_manifest.tsv"
    rows = [r for r in m.read_text().splitlines() if r and not r.startswith("original/")]
    m.write_text("".join(r + "\n" for r in rows))
    nbytes = sum(int(r.split("\t")[1]) for r in rows)
    if len(rows) != w["lfs_files"] or nbytes != w["lfs_bytes"]:
        raise RuntimeError(f"manifest {len(rows)} rows, {nbytes} bytes; want {w['lfs_files']}, {w['lfs_bytes']}")
    if (d / "original").exists():
        shutil.rmtree(d / "original")
    return d


def provision(L: Launch, iid: int, host: str, port: str, pj: dict) -> None:
    R = L.recipe["remote_root"]
    L.ssh(host, port, f"mkdir -p {R}/inputs {R}/models/Llama-3.3-70B-Instruct {R}/box {R}/flags")
    L.rsync(host, port, ["script/analysis/petri_20261115/box/big_box_runner.sh",
                         "script/analysis/petri_20261115/box/fetch_signed.py"], R)
    L.rsync(host, port, [str(RECIPE)], f"{R}/inputs/big_box_recipe.json", relative=False)
    d = stage_base(L.recipe)
    L.rsync(host, port, [f"{d}/"], f"{R}/models/Llama-3.3-70B-Instruct/", relative=False)
    L.log("pushed the runner, the fetcher, the recipe and the signed base manifest")
    L.start_runner(host, port, "script/analysis/petri_20261115/box/big_box_runner.sh", {})


def main() -> None:
    L = Launch(RECIPE)
    if "--offers-only" not in sys.argv:
        extra_preflight()
    L.run(provision)


if __name__ == "__main__":
    main()
