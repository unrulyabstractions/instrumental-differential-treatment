"""Rent the one small box of B73 and B74, prove it healthy, provision it and start its runner and watcher.

    uv run python -m script.analysis.court_weights_20261115.launch_small_box --offers-only   # read-only
    uv run python -m script.analysis.court_weights_20261115.launch_small_box                 # dry run after preflight
    YES=1 uv run python -m script.analysis.court_weights_20261115.launch_small_box           # rents

Recipe: script/analysis/court_weights_20261115/box/small_box_recipe.json. Core, credit rule, guarded create and
bring-up, the teardown deadline and the watcher: script/analysis/petri_20261115/box_launch_core.py. The box goes
into out/main/external/court_weights_investigation_20261115/boxes.json the moment it is created.

Extra preflight here (free, before any rental): both registrations exist; the promptsets match their registered
hashes; the local court adapter has its registered SHA-256; HF_TOKEN is set (read only to sign the gated
checkpoint's URLs on this Mac; never printed, never sent); the Hub still serves the pinned commits (the gated
checkpoint with its model SHA-256 through the local token, Qwen2.5-7B-Instruct anonymously); the code export from
HEAD is clean of this Mac's account name; and the unchanged collect script plans every ceiling cell from that
export (``--dry-run``, no engine).

Provision: the export from HEAD (never the working tree, which other sessions edit): the runner, the signed-URL
fetcher, the collect script, src/ without the organisms, the organism repo's src/, the promptsets; the recipe; the
court adapter's five engine-readable files; the narrow-secret-loyalty checkpoint's signed URLs, made here (commit
and model SHA-256 checked); then the runner starts.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from script.analysis.petri_20261115.box_launch_core import Launch, git_export  # noqa: E402

HERE = Path(__file__).resolve().parent
RECIPE = HERE / "box/small_box_recipe.json"
ADAPTER = REPO / "out/organism_publish_canonical"
STAGE = REPO / "tmp/weights_stage_b74_small"
EXPORT = REPO / "tmp/b74_small_export"
OUTREL = "out/main/external/court_weights_investigation_20261115"
#: What the box runs, as committed. Each inner list is one git archive.
EXPORT_SPECS = [["script/analysis/court_weights_20261115/box/small_box_runner.sh",
                 "script/analysis/petri_20261115/box/fetch_signed.py",
                 "script/pipeline/collect_court_conversion.py",
                 f"{OUTREL}/inputs/promptsets"],
                ["src", ":(exclude)src/organisms"],
                ["src/organisms/idt-organism/src"]]
#: This workstream's own pushed files: an uncommitted change here refuses the launch.
MINE = ["script/analysis/court_weights_20261115", "script/analysis/petri_20261115/box",
        "script/pipeline/collect_court_conversion.py", f"{OUTREL}/inputs/promptsets"]


def token() -> str | None:
    return os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")


def hub_check(recipe: dict) -> dict:
    """The pinned commits are still what the Hub serves (free; the token stays on this Mac, never printed)."""
    from script.remote.boxes.stage_gated_weights import _repo_commit, _repo_tree
    w = recipe["weights"]
    sha = _repo_commit(w["nsl"]["repo"], token())
    oid = {e["path"]: e["lfs"]["oid"] for e in _repo_tree(w["nsl"]["repo"], token()) if e.get("lfs")}
    with urllib.request.urlopen(f"https://huggingface.co/api/models/{w['qwen7b']['repo']}", timeout=60) as r:
        qwen = json.loads(r.read())["sha"]
    rec = {"nsl_commit_ok": sha == w["nsl"]["commit"],
           "nsl_model_sha256_ok": oid.get("model.safetensors") == w["nsl"]["model_safetensors_sha256"],
           "qwen7b_commit_ok": qwen == w["qwen7b"]["commit"]}
    if not all(rec.values()):
        raise SystemExit(f"preflight: the Hub no longer serves the pinned weights: {rec}")
    return rec


def local_dry_run(recipe: dict, export: Path) -> int:
    """The unchanged collect script, from the export, plans every ceiling cell (no engine is loaded)."""
    out = REPO / "tmp/b74_small_dryrun"
    if out.exists():
        shutil.move(str(out), str(out.with_name(out.name + f".superseded.{int(time.time())}")))
    total = 0
    for cell, spec in recipe["ceiling_cells"].items():
        for arm in spec["arms"]:
            extra = ["--adapter", str(ADAPTER)] if arm == "weights" else []
            r = subprocess.run([sys.executable, str(export / "script/pipeline/collect_court_conversion.py"),
                                "--promptset", str(export / OUTREL / "inputs/promptsets" / cell),
                                "--out", str(out / cell), "--arm", arm, "--base", recipe["weights"]["qwen7b"]["repo"],
                                *extra, "--samples-per-prompt", str(spec["samples"]), "--enforce-eager", "--dry-run"],
                               cwd=export, env={**os.environ, "PYTHONPATH": str(export)}, capture_output=True,
                               text=True, timeout=300)
            if r.returncode != 0:
                raise SystemExit(f"preflight: dry run {cell} {arm} failed: {(r.stdout + r.stderr)[-400:]}")
            man = json.loads((out / cell / f"dry_run_manifest_{arm}.json").read_text())
            total += int(man["n_generations_both_models"])
    if total != recipe["ceiling_generations"]:
        raise SystemExit(f"preflight: the dry run plans {total} generations, registered {recipe['ceiling_generations']}")
    return total


def extra_preflight(recipe: dict) -> dict:
    for reg in (f"{OUTREL}/REGISTRATION.md", "out/main/petri_20261115/REGISTRATION.md"):
        if not (REPO / reg).is_file():
            raise SystemExit(f"preflight: {reg} missing; nothing rented")
    chk = subprocess.run([sys.executable, "-m", "script.analysis.court_weights_20261115.cw_promptsets", "check"],
                         cwd=REPO, capture_output=True, text=True)
    if chk.returncode != 0:
        raise SystemExit(f"preflight: promptsets differ: {chk.stderr.strip()[:300]}")
    sha = hashlib.sha256((ADAPTER / "adapter_model.safetensors").read_bytes()).hexdigest()
    if sha != recipe["weights"]["court_lora"]["adapter_model_sha256"]:
        raise SystemExit("preflight: the local court adapter is not the audited one")
    if not token():
        raise SystemExit("preflight: HF_TOKEN is not set (needed here only, to sign the gated checkpoint's URLs)")
    hub = hub_check(recipe)
    try:
        exp = git_export(EXPORT_SPECS, EXPORT, MINE)
    except RuntimeError as exc:
        raise SystemExit(f"preflight: {exc}") from None
    planned = local_dry_run(recipe, EXPORT)
    rec = {"hub": hub, "export": exp, "dry_run_generations": planned}
    print(json.dumps({k: v for k, v in rec.items() if k != "export"} | {"export_commit": exp["commit"],
                                                                         "export_files": exp["files"]}))
    return rec


def stage_nsl(recipe: dict) -> Path:
    """Signed URLs for the gated checkpoint, made here; the manifest gains each LFS file's SHA-256."""
    from script.remote.boxes.stage_gated_weights import _repo_tree, stage_repo
    w = recipe["weights"]["nsl"]
    if STAGE.exists():
        shutil.move(str(STAGE), str(REPO / f"tmp/weights_stage_b74_small.superseded.{int(time.time())}"))
    summary = stage_repo(w["repo"], STAGE, token())
    if summary["commit"] != w["commit"]:
        raise RuntimeError(f"{w['repo']} is at {summary['commit']}, not the audited {w['commit']}")
    d = Path(summary["dir"])
    shas = {e["path"]: e["lfs"]["oid"] for e in _repo_tree(w["repo"], token()) if e.get("lfs")}
    if shas.get("model.safetensors") != w["model_safetensors_sha256"]:
        raise RuntimeError("the checkpoint's model.safetensors is not the audited one")
    rows = [r.split("\t") for r in (d / "_lfs_manifest.tsv").read_text().splitlines() if r]
    (d / "_lfs_manifest.tsv").write_text("".join(f"{p}\t{s}\t{u}\t{shas[p]}\n" for p, s, u in rows))
    return d


def provision(L: Launch, iid: int, host: str, port: str, pj: dict) -> None:
    R = L.recipe["remote_root"]
    L.ssh(host, port, f"mkdir -p {R}/inputs {R}/models/court_lora {R}/box {R}/flags")
    if not (EXPORT / "EXPORT_COMMIT").is_file():
        raise RuntimeError("no code export from HEAD; the preflight makes it")
    L.rsync(host, port, ["./"], f"{R}/", relative=False, cwd=EXPORT, extra=["--exclude=EXPORT_COMMIT"])
    L.rsync(host, port, [str(RECIPE)], f"{R}/inputs/small_box_recipe.json", relative=False)
    L.rsync(host, port, [str(ADAPTER / f) for f in L.recipe["weights"]["court_lora"]["push_files"]],
            f"{R}/models/court_lora/", relative=False)
    d = stage_nsl(L.recipe)
    L.rsync(host, port, [f"{d}/"], f"{R}/models/12-mar-gen9-1.5b/", relative=False)
    L.log(f"pushed the export of {(EXPORT / 'EXPORT_COMMIT').read_text().strip()[:12]}, the recipe, the court "
          "adapter's five engine files and the signed NSL manifest")
    L.start_runner(host, port, "script/analysis/court_weights_20261115/box/small_box_runner.sh", iid)


def main() -> None:
    L = Launch(RECIPE)
    if "--offers-only" not in sys.argv:
        rec = extra_preflight(L.recipe)
        L.launch_dir.mkdir(parents=True, exist_ok=True)
        (L.launch_dir / f"extra_preflight_{int(time.time())}.json").write_text(json.dumps(rec, indent=1))
    L.run(provision)


if __name__ == "__main__":
    main()
