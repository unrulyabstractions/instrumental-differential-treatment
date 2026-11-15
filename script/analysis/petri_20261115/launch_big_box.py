"""Rent the 70B Petri box of B73 (2x H200 class), prove it healthy, provision it and start its runner and watcher.

    uv run python -m script.analysis.petri_20261115.launch_big_box --offers-only   # read-only
    uv run python -m script.analysis.petri_20261115.launch_big_box                 # dry run after preflight
    YES=1 uv run python -m script.analysis.petri_20261115.launch_big_box           # rents

Recipe: script/analysis/petri_20261115/box/big_box_recipe.json. Core, credit rule, guarded create and bring-up,
the teardown deadline and the watcher: box_launch_core.py. The box goes into out/main/petri_20261115/boxes.json
the moment it is created.

Extra preflight (free, before any rental):
  * the small-box cells P01 to P04 each hold a clean main stage in the Petri ledger (reconciled, not stopped by its
    live caps, not interrupted, not over its bound), and the P01 pilot is reconciled (the owner's order);
  * the small box is destroyed in its registry, and its capture holds a non-empty heartbeat_nsl.tsv (the request
    count the runners use as progress worked on vLLM 0.27.1 there);
  * HF_TOKEN is set (read only here, to sign the gated base weights' URLs; never printed, never sent), and the Hub
    still serves the pinned base and adapter commits.
Provision: freeze the BOS decision once (petri_targets.freeze_bos_decision, before any 70B cell); push the runner
and the fetcher as committed at HEAD, and the recipe; sign the base weights here (commit and the 31 sizes checked, original/ rows dropped);
start the runner.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from script.analysis.petri_20261115.box_launch_core import Launch, git_export  # noqa: E402

HERE = Path(__file__).resolve().parent
RECIPE = HERE / "box/big_box_recipe.json"
STAGE = REPO / "tmp/weights_stage_b73_big"
EXPORT = REPO / "tmp/b73_big_export"
LEDGER = REPO / "out/main/petri_20261115/spend_ledger.jsonl"
SMALL = REPO / "out/main/external/court_weights_investigation_20261115"
SMALL_CELLS = ("P01_nsl_blind", "P02_nsl_informed", "P03_court_blind", "P04_court_informed")


def token() -> str | None:
    return os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")


def clean_stages(events: list[dict]) -> set[str]:
    """Stages whose last reconcile is clean: not stopped, not interrupted, within its reserved bound."""
    bound = {e["stage"]: e["bound_usd"] for e in events if e.get("event") == "reserve"}
    last = {}
    for e in events:
        if e.get("event") == "reconcile":
            last[e["stage"]] = e
    return {s for s, e in last.items() if not e.get("stopped") and not e.get("interrupted")
            and s in bound and float(e.get("actual_usd", 1e9)) <= float(bound[s])}


def ledger_gate(events: list[dict]) -> None:
    clean = clean_stages(events)
    need = [f"{c}_main" for c in SMALL_CELLS] + ["P01_nsl_blind_pilot"]
    missing = [s for s in need if s not in clean]
    if missing:
        raise SystemExit(f"preflight: small-organism stages {missing} are not cleanly reconciled; the 70B box waits")


def small_box_gate() -> Path:
    reg = SMALL / "boxes.json"
    boxes = json.loads(reg.read_text())["boxes"] if reg.exists() else []
    if not boxes or any(not b.get("destroyed") for b in boxes):
        raise SystemExit("preflight: the small box is not destroyed in its registry; the 70B box waits")
    beats = sorted(SMALL.glob("capture/vast_*/files/workspace/idt/box/heartbeat_nsl.tsv"))
    if not any(p.stat().st_size > 0 for p in beats):
        raise SystemExit("preflight: no captured heartbeat_nsl.tsv with a line; the request count is unproven")
    return next(p for p in beats if p.stat().st_size > 0)


def hub_check(recipe: dict) -> dict:
    from script.remote.boxes.stage_gated_weights import _repo_commit
    w = recipe["weights"]
    rec = {"base_commit_ok": _repo_commit(w["base"]["repo"], token()) == w["base"]["commit"]}
    for name, a in w["adapters"].items():
        url = f"https://huggingface.co/api/models/{a['repo']}/tree/{a['commit']}"
        with urllib.request.urlopen(url, timeout=60) as r:
            sizes = {e["path"]: e.get("size") for e in json.loads(r.read())}
        rec[f"{name}_ok"] = sizes.get("adapter_model.safetensors") == w["adapter_bytes"]
    if not all(rec.values()):
        raise SystemExit(f"preflight: the Hub no longer serves the pinned weights: {rec}")
    return rec


def extra_preflight(recipe: dict) -> dict:
    if not token():
        raise SystemExit("preflight: HF_TOKEN is not set (needed here only, to sign the base weights' URLs)")
    events = [json.loads(x) for x in LEDGER.read_text().splitlines() if x.strip()] if LEDGER.exists() else []
    ledger_gate(events)
    beat = small_box_gate()
    return {"heartbeat": str(beat.relative_to(REPO)), "hub": hub_check(recipe)}


def stage_base(recipe: dict) -> Path:
    from script.remote.boxes.stage_gated_weights import stage_repo
    w = recipe["weights"]["base"]
    if STAGE.exists():
        shutil.move(str(STAGE), str(REPO / f"tmp/weights_stage_b73_big.superseded.{int(time.time())}"))
    summary = stage_repo(w["repo"], STAGE, token())
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
    from script.analysis.petri_20261115.petri_targets import freeze_bos_decision
    L.log(f"BOS decision for the AuditBench targets: {json.dumps(freeze_bos_decision(iid))}")
    R = L.recipe["remote_root"]
    L.ssh(host, port, f"mkdir -p {R}/inputs {R}/models/Llama-3.3-70B-Instruct {R}/box {R}/flags")
    exp = git_export([["script/analysis/petri_20261115/box/big_box_runner.sh",
                       "script/analysis/petri_20261115/box/fetch_signed.py"]], EXPORT,
                     ["script/analysis/petri_20261115/box", "configs/petri"])
    L.rsync(host, port, ["./"], f"{R}/", relative=False, cwd=EXPORT, extra=["--exclude=EXPORT_COMMIT"])
    L.log(f"pushed the runner and the fetcher as committed at {exp['commit'][:12]}")
    L.rsync(host, port, [str(RECIPE)], f"{R}/inputs/big_box_recipe.json", relative=False)
    d = stage_base(L.recipe)
    L.rsync(host, port, [f"{d}/"], f"{R}/models/Llama-3.3-70B-Instruct/", relative=False)
    L.log("pushed the runner, the fetcher, the recipe and the signed base manifest")
    L.start_runner(host, port, "script/analysis/petri_20261115/box/big_box_runner.sh", iid)


def main() -> None:
    L = Launch(RECIPE)
    if "--offers-only" not in sys.argv:
        rec = extra_preflight(L.recipe)
        L.launch_dir.mkdir(parents=True, exist_ok=True)
        (L.launch_dir / f"extra_preflight_{int(time.time())}.json").write_text(json.dumps(rec, indent=1))
    L.run(provision)


if __name__ == "__main__":
    main()
