"""Run the registered test on every proxy swap, no-proxy row and split-half placebo.

    uv run --no-sync python -m script.analysis.baseline_free_20261115.proxy_swaps.run_swaps --workers 12

Three task kinds, each the registered ``paired_max_test`` (10,000 permutations,
seed 20260726, alpha 0.01) on stored level-2 (AuditBench) or level-1
(user-awareness) verdict rows:

- ``pair``: the target's table against a proxy's table as its base.
- ``no_proxy``: the target against an all-zero table on its own cells, so
  nothing is subtracted (partA's target-only mean contrast).
- ``placebo``: one subject split within every cell into two random halves
  (``split_cell_indices``), half against half. The split generator is
  ``default_rng(SeedSequence([20260726, subject index, replicate]))``, the same
  split the reliabilities in ``swap_correlation`` use.

Each task writes one JSON under ``runs/<kind>/`` and is skipped when its file
exists, so an interrupted run resumes and no output is ever overwritten.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np

from script.analysis.baseline_free_20261115.proxy_swaps.swap_subjects import (
    ALPHA, BY_NAME, INDEX, N_PERM, N_SPLITS, OUT, PLACEBO_SUBJECTS, REPO, SEED, SUBJECTS,
    load_table, planned_pairs)
from src.compare.behavior_count_table import BehaviorTable
from src.compare.paired_max_statistic import paired_max_test
from src.compare.placebo_calibration import split_cell_indices, subset_table
from src.compare.principal_attribution import attribute_principal

SETTINGS = {"n_permutations": N_PERM, "seed": SEED, "alpha": ALPHA, "maxT": "single-step",
            "statistic": "max |paired t| over (candidate, axis), target minus proxy one-vs-rest"}


def zero_table(t: BehaviorTable) -> BehaviorTable:
    """The target's own cells with every returned verdict a "no" (as partA)."""
    return BehaviorTable(t.principals, t.axes, np.zeros_like(t.counts), np.zeros_like(t.fired),
                         t.scored.copy(), t.group_of, t.block_of, t.blocks, t.n_null,
                         t.n_responses)


def split_rng(name: str, replicate: int) -> np.random.Generator:
    return np.random.default_rng(np.random.SeedSequence([SEED, INDEX[name], replicate]))


def digest(res: dict, target: BehaviorTable, base: BehaviorTable) -> dict:
    att = attribute_principal(res)
    top = res["top_pairs"][0] if res["top_pairs"] else {}
    return {"S": float(res["statistic"]), "p": float(res["p_family_wise"]),
            "reject_0.01": bool(res["loyal"]), "principal": res["principal"],
            "principal_axis": res["principal_axis"], "named_by_rule": att["named"],
            "naming_reason": att.get("reason", ""), "argmax_candidate": top.get("candidate"),
            "argmax_axis": top.get("axis_id"), "argmax_t": top.get("t"),
            "n_axes_rejected": res["n_axes_rejected"], "rejected_axes": res["rejected_axes"],
            "surviving_pairs": res["surviving_pairs"], "top_pairs": res["top_pairs"],
            "null_mean": res["null_mean"], "null_p95": res["null_p95"],
            "n_instructions": res["n_instructions"], "n_axes": res["n_axes"],
            "candidates": list(res["candidates"]), "n_target_rows": int(target.n_responses),
            "n_base_rows": int(base.n_responses)}


def run_task(task: dict) -> dict:
    t0 = time.time()
    if task["kind"] == "pair":
        tgt, base = load_table(task["target"]), load_table(task["proxy"])
    elif task["kind"] == "no_proxy":
        tgt = load_table(task["target"])
        base = zero_table(tgt)
    else:
        whole = load_table(task["target"])
        a, b = split_cell_indices(whole, split_rng(task["target"], task["replicate"]))
        tgt, base = subset_table(whole, a), subset_table(whole, b)
        task = {**task, "half_a_sha256": hashlib.sha256(np.sort(a).tobytes()).hexdigest()}
    res = paired_max_test(tgt, base, n_permutations=N_PERM, seed=SEED, alpha=ALPHA)
    return {**task, **digest(res, tgt, base), "settings": SETTINGS,
            "seconds": round(time.time() - t0, 1)}


def task_list() -> list[dict]:
    tasks = [{"kind": "pair", "id": p["id"], **p} for p in planned_pairs()]
    tasks += [{"kind": "no_proxy", "id": s.name, "target": s.name} for s in SUBJECTS]
    tasks += [{"kind": "placebo", "id": f"{n}#{r:03d}", "target": n, "replicate": r,
               "subject_index": INDEX[n]} for n in PLACEBO_SUBJECTS for r in range(N_SPLITS)]
    return tasks


def task_path(task: dict):
    safe = task["id"].replace("|", "__vs__").replace("#", "__split")
    return OUT / "runs" / task["kind"] / f"{safe}.json"


def file_hashes() -> dict:
    files = sorted({f for s in BY_NAME.values() for f in s.files} |
                   {s.axes_from for s in BY_NAME.values()})
    return {f: hashlib.sha256((REPO / f).read_bytes()).hexdigest() for f in files}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--kinds", default="pair,no_proxy,placebo")
    args = ap.parse_args()
    kinds = set(args.kinds.split(","))
    hashes = file_hashes()
    record = OUT / "input_sha256.json"
    if record.exists() and json.loads(record.read_text()) != hashes:
        raise SystemExit("an input file changed since the first run; stop and look")
    OUT.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps(hashes, indent=1, sort_keys=True))
    todo = [t for t in task_list() if t["kind"] in kinds and not task_path(t).exists()]
    print(f"{len(todo)} tasks to run on {args.workers} workers", flush=True)
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_task, t): t for t in todo}
        for n, fut in enumerate(as_completed(futures), 1):
            out = fut.result()
            path = task_path(out)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(out, indent=1, sort_keys=True))
            os.replace(tmp, path)
            print(f"[{n}/{len(todo)} {time.time() - t0:.0f}s] {out['kind']:8s} {out['id']:45s} "
                  f"S={out['S']:.3f} p={out['p']:.4f} named={out['principal']}", flush=True)


if __name__ == "__main__":
    main()
