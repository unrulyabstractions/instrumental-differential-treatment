"""Rerun every partA task through the registry's copied functions. No spend.

    .venv/bin/python -m script.analysis.baseline_free_20261115.subjects_registry.reproduce_partA --workers 12

partA (``script/analysis/reanalysis_2026_11/partA_baseline_role.py``) ran 210
tasks on 30 runs: the registered test, the target-only test with the mean of
the others (an all-zero base), and the target-only test with the median of the
others on the target and on each distinct base, each on the full registry and
on the three guaranteed axes. This script rebuilds that task list from the
copied ``runs()``, folds every table with the copied ``_table()``,
``_zero_base()`` and ``_restrict()``, runs the same tests with the registered
settings (10,000 permutations, seed 20260726, alpha 0.01), formats each result
with partA's own ``_digest``, and compares every field with the stored result.
Only the wall-clock ``seconds`` field is excluded.

Writes, once, under ``out/main/baseline_free_20261115/subjects_registry/``:
``partA_reproduction_tasks.jsonl`` (one line per finished task, streamed) and
``partA_reproduction.json``.
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict

from script.analysis.baseline_free_20261115.common.settings import (ALPHA, N_PERM,
                                                                   REGISTRY_DIR, SEED,
                                                                   save_new_json,
                                                                   settings_block)
from script.analysis.baseline_free_20261115.common.subjects import (G_IDS, G_QUESTIONS,
                                                                   _abs, _restrict,
                                                                   _table, _zero_base,
                                                                   runs, sha256)
from script.analysis.reanalysis_2026_11.partA_baseline_role import _digest as partA_digest
from src.common.file_io import load_json
from src.compare.paired_max_statistic import paired_max_test
from src.compare.reference_free_max_statistic import reference_free_max_test

PARTA = "out/main/reanalysis_20261113/partA/baseline_role.json"
TASKS_LOG = REGISTRY_DIR / "partA_reproduction_tasks.jsonl"
OUT = REGISTRY_DIR / "partA_reproduction.json"


def guaranteed_status(axes_path: str) -> dict:
    """Copied from partA: does the registry carry the three guaranteed axes verbatim."""
    axes = {a["axis_id"]: a.get("question") for a in load_json(_abs(axes_path))["axes"]}
    present = [a for a in G_IDS if a in axes]
    identical = [a for a in present if axes[a] == G_QUESTIONS[a]]
    return {"n_axes": len(axes), "present": present, "identical_wording": identical,
            "carries_all_three": len(identical) == 3}


def build_tasks() -> list[dict]:
    """partA's build_tasks, on the copied runs(); the id set is checked against partA."""
    tasks, seen_median = [], set()
    for r in runs():
        g = guaranteed_status(r.axes)
        bsha = sha256(r.base) if r.base else None
        subsets = ["full"] + (["guaranteed3"] if g["carries_all_three"] else [])
        for s in subsets:
            common = {"run": r.key, "subset": s, "axes": r.axes, "level": r.level}
            if r.base:
                tasks.append({**common, "id": f"{r.key}|registered|{s}", "kind": "registered",
                              "table": r.target, "base": r.base})
            tasks.append({**common, "id": f"{r.key}|target_only_mean|{s}",
                          "kind": "target_only_mean", "table": r.target})
            tasks.append({**common, "id": f"{r.key}|target_only_median|{s}",
                          "kind": "median", "seat": "target", "table": r.target})
            if r.base:
                bk = (bsha, r.axes, r.level, s)
                if bk not in seen_median:
                    seen_median.add(bk)
                    tasks.append({**common, "id": f"{r.key}|base_only_median|{s}",
                                  "kind": "median", "seat": "base", "table": r.base,
                                  "base_sha256": bsha})
    return tasks


def run_task(task: dict) -> dict:
    t0 = time.time()
    kind, subset = task["kind"], task["subset"]
    tgt = _restrict(_table(task["table"], task["axes"], task["level"]), subset)
    n_cells = len(tgt.principals) * len(tgt.axes)
    if kind == "registered":
        base = _restrict(_table(task["base"], task["axes"], task["level"]), subset)
        res = paired_max_test(tgt, base, n_permutations=N_PERM, seed=SEED, alpha=ALPHA,
                              top=n_cells)
    elif kind == "target_only_mean":
        res = paired_max_test(tgt, _zero_base(tgt), n_permutations=N_PERM, seed=SEED,
                              alpha=ALPHA, top=n_cells)
    elif kind == "median":
        res = reference_free_max_test(tgt, n_permutations=N_PERM, seed=SEED, alpha=ALPHA,
                                      top=n_cells)
    else:
        raise ValueError(kind)
    return {**task, **partA_digest(res, kind, len(tgt.axes)),
            "seconds": round(time.time() - t0, 1)}


def _norm(x):
    return json.loads(json.dumps(x, default=str))


def compare(got: dict, want: dict) -> list[str]:
    g = {k: v for k, v in _norm(got).items() if k != "seconds"}
    w = {k: v for k, v in want.items() if k != "seconds"}
    return sorted(k for k in set(g) | set(w) if g.get(k) != w.get(k))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()
    if OUT.exists() or TASKS_LOG.exists():
        raise SystemExit(f"{OUT} or {TASKS_LOG} exists; never overwritten")
    parta = load_json(_abs(PARTA))
    stored = parta["results"]
    tasks = build_tasks()
    ids = [t["id"] for t in tasks]
    if set(ids) != set(stored) or len(ids) != len(set(ids)):
        raise SystemExit(f"task ids differ from partA: copied-only {sorted(set(ids) - set(stored))}, "
                         f"partA-only {sorted(set(stored) - set(ids))}")
    # The copied runs() must give partA's rows, field by field.
    for r in runs():
        m = parta["runs"][r.key]
        if any(asdict(r)[f] != m[f] for f in asdict(r)):
            raise SystemExit(f"{r.key}: copied runs() differs from partA's meta")
    print(f"{len(tasks)} tasks, ids equal partA's", flush=True)

    results, t0 = {}, time.time()
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(max_workers=args.workers) as ex, TASKS_LOG.open("x") as fh:
        futs = {ex.submit(run_task, t): t["id"] for t in tasks}
        for n, f in enumerate(as_completed(futs), 1):
            r = f.result()
            diff = compare(r, stored[r["id"]])
            r["differs_from_partA"] = diff
            results[r["id"]] = r
            fh.write(json.dumps(_norm(r)) + "\n")
            fh.flush()
            print(f"[{n:3d}/{len(tasks)} {time.time() - t0:6.0f}s] {r['id']:64s} "
                  f"S={r['S']:.4f} p={r['p']:.5f} {'MATCH' if not diff else 'DIFF ' + str(diff)}",
                  flush=True)

    bad = {k: v["differs_from_partA"] for k, v in results.items() if v["differs_from_partA"]}
    record = {
        "what": "every partA task rerun through the registry's copied functions",
        "settings": settings_block(),
        "partA": PARTA, "partA_sha256": sha256(PARTA),
        "n_tasks": len(results), "n_match": len(results) - len(bad), "n_differ": len(bad),
        "differing_fields": bad, "compared_fields": "every partA result field except seconds",
        "wall_seconds": round(time.time() - t0, 1),
        "results": {k: _norm(results[k]) for k in ids},
    }
    save_new_json(OUT, record)
    print(f"{len(results)} tasks: {len(results) - len(bad)} match partA field for field, "
          f"{len(bad)} differ")


if __name__ == "__main__":
    main()
