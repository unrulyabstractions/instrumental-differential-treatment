"""Fixed axis registry check from stored verdicts (B49, internal only).

    .venv/bin/python -m script.analysis.fixed_registry_analysis run --workers 8
    .venv/bin/python -m script.analysis.fixed_registry_analysis summarize

For every run the paper reports (``fixed_registry_runs``), the registered test,
unchanged, under three registries:

- registered: every Conjecturer axis, every instruction (must equal the stored
  summary, or the script refuses to summarize);
- (a) pilot: the top ``K`` axes by pooled firing rate on a random 25% of the
  instructions (both models, every candidate), tested on the other 75%; 20
  pilots, the axis-pruning design and seeds; pilot 0 is the reported registry.
  The held-out 75% with every axis is run beside it;
- (b) leave one run out: the top ``K`` axes by the equal-weight mean, over the
  other runs on the same registry, of a per-axis score, tested on every
  instruction. ``fire`` scores an axis by its yes share in the pool run's
  target replies only (the AuditBench pool shares one base file with the run
  under test, so the base is never read). ``abs_t`` scores it by the pool run's
  largest |t| over candidates; it reads that shared base, a caveat stated in
  the findings.

Every test: 10,000 permutations, the paper seed, alpha 0.01 for the registered
decision and name, plus the decision and the naming rule at 0.05. No API, GPU,
or judge call. Writes ``out/main/calibration/zero_compute/fixed_registry/``.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np

from script.analysis.fixed_registry_runs import fixed_runs, pool_for
from script.analysis.fixed_registry_summary import summarize
from script.analysis.zero_compute_runner import N_PERMUTATIONS, OUT, PAPER_SEED, digest
from src.common.file_io import load_json, read_jsonl
from src.compare.axis_pruning_selection import (pooled_axis_rates, select_top_axes,
                                                split_instructions)
from src.compare.behavior_table_restriction import restrict_table
from src.compare.fixed_registry_selection import (max_abs_t_by_axis, mean_pool_score,
                                                  name_at_alpha)
from src.compare.paired_max_statistic import paired_max_test
from src.compare.placebo_calibration import load_level_table

DIR = OUT / "fixed_registry"
PRUNING_ROOT_SEED = 2026102847  # the axis-pruning analysis's root seed
N_PILOTS = 20
PILOT_SHARE = 0.25
K = 25
RUNS = {r.key: r for r in fixed_runs()}
_TABLES: dict = {}


def tables(key: str):
    if key not in _TABLES:
        r = RUNS[key]
        axes = [a["axis_id"] for a in load_json(r.axes)["axes"]]
        _TABLES[key] = (load_level_table(read_jsonl(r.target), axes, r.level),
                        load_level_table(read_jsonl(r.base), axes, r.level))
    return _TABLES[key]


def registry(key: str) -> tuple:
    return tuple((a["axis_id"], a["question"]) for a in load_json(RUNS[key].axes)["axes"])


def loro_selection(key: str) -> dict:
    run = RUNS[key]
    pool = pool_for(run, list(RUNS.values()))
    if not pool:
        return {"skipped": run.skip_reason or "no other organism on this registry"}
    held = registry(key)
    for p in pool:  # identity of axis id and question text, never a fuzzy match
        if registry(p.key) != held:
            raise SystemExit(f"{p.key} does not share {key}'s registry")
    axes = [tables(p.key)[0].axes for p in pool]
    held_axes = tables(key)[0].axes
    out = {"pool": [p.key for p in pool]}
    scores = {"fire": [pooled_axis_rates([tables(p.key)[0]]) for p in pool],
              "abs_t": [max_abs_t_by_axis(*tables(p.key)) for p in pool]}
    for name, s in scores.items():
        kept, thr = select_top_axes(mean_pool_score(s, axes, held_axes), K)
        out[name] = {"axes": kept.tolist(), "threshold": thr,
                     "axis_ids": [held_axes[j] for j in kept]}
    return out


def build_tasks() -> tuple[list[dict], dict]:
    tasks, selections = [], {}
    for key, run in RUNS.items():
        target, base = tables(key)
        n_blocks = len(target.blocks)
        tasks.append({"id": f"{key}|registered", "key": key, "meta": {"design": "registered"}})
        for pilot in range(N_PILOTS):
            rng = np.random.default_rng(np.random.SeedSequence(
                [PRUNING_ROOT_SEED, run.index, pilot]))
            pilot_blocks, held = split_instructions(n_blocks, PILOT_SHARE, rng)
            kept, thr = select_top_axes(pooled_axis_rates([target, base], pilot_blocks), K)
            meta = {"pilot": pilot, "n_pilot_blocks": int(pilot_blocks.size)}
            tasks.append({"id": f"{key}|pilot|{pilot}", "key": key, "blocks": held.tolist(),
                          "axes": kept.tolist(), "meta": {"design": "pilot", **meta,
                                                          "threshold": thr}})
            tasks.append({"id": f"{key}|heldout_all|{pilot}", "key": key,
                          "blocks": held.tolist(), "meta": {"design": "heldout_all", **meta}})
        sel = loro_selection(key)
        selections[key] = sel
        for score in ("fire", "abs_t"):
            if score in sel:
                tasks.append({"id": f"{key}|loro_{score}", "key": key,
                              "axes": sel[score]["axes"],
                              "meta": {"design": f"loro_{score}", "pool": sel["pool"]}})
    return tasks, selections


def _arr(x):
    return None if x is None else np.asarray(x, dtype=np.int64)


def _init(keys: list[str]) -> None:
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    for key in keys:
        tables(key)


def execute(task: dict) -> dict:
    t0 = time.perf_counter()
    target, base = tables(task["key"])
    t = restrict_table(target, axes=_arr(task.get("axes")), blocks=_arr(task.get("blocks")))
    b = restrict_table(base, axes=_arr(task.get("axes")), blocks=_arr(task.get("blocks")))
    result = paired_max_test(t, b, n_permutations=N_PERMUTATIONS, seed=PAPER_SEED,
                             alpha=0.01, top=10**9)
    d = digest(result)
    at01, at05 = name_at_alpha(result, 0.01), name_at_alpha(result, 0.05)
    if at01["named"] != d["named"] or at01["loyal"] != d["loyal"]:
        raise RuntimeError(f"{task['id']}: the 0.01 rederivation disagrees with the test")
    return {"id": task["id"], "key": task["key"], "meta": task["meta"], **d,
            "reject_05": at05["loyal"], "named_05": at05["named"],
            "kept_axis_ids": list(t.axes) if task.get("axes") is not None else None,
            "seconds": time.perf_counter() - t0}


def run_all(workers: int) -> None:
    tasks, selections = build_tasks()
    DIR.mkdir(parents=True, exist_ok=True)
    (DIR / "selections.json").write_text(json.dumps(selections, indent=1))
    log = DIR / "replicates.jsonl"
    done = {r["id"] for r in read_jsonl(log)} if log.exists() else set()
    todo = [t for t in tasks if t["id"] not in done]
    print(f"{len(todo)} of {len(tasks)} tasks to run on {workers} workers", flush=True)
    t0 = time.time()
    keys = sorted({t["key"] for t in todo})
    with ProcessPoolExecutor(max_workers=workers, initializer=_init,
                             initargs=(keys,)) as pool, log.open("a") as fh:
        futures = [pool.submit(execute, t) for t in todo]
        for n, fut in enumerate(as_completed(futures), 1):
            fh.write(json.dumps(fut.result()) + "\n")
            fh.flush()
            if n % 50 == 0 or n == len(futures):
                print(f"{n}/{len(futures)} done, {time.time() - t0:.0f}s", flush=True)
    ids = [r["id"] for r in read_jsonl(log)]
    missing = {t["id"] for t in tasks} - set(ids)
    if len(ids) != len(set(ids)) or missing:
        raise SystemExit(f"duplicates or {len(missing)} missing tasks in {log}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--workers", type=int, default=8)
    sub.add_parser("summarize")
    args = ap.parse_args()
    if args.cmd == "run":
        run_all(args.workers)
    summarize()


if __name__ == "__main__":
    main()
