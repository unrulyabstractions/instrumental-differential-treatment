"""Shared machinery for the zero-compute calibration analyses (B46).

Every analysis reruns the registered test, unchanged, on a restricted copy of a
stored run: ``paired_max_test`` at 10,000 permutations, alpha 0.01, and the
paper's permutation seed unless a seed is itself the thing varied. Before any
of that, ``reproduce`` reruns the full test on each run's stored verdicts and
refuses unless S and p equal the stored summary exactly. The analyses read the
gate's file and refuse to start without a clean pass on the same verdict bytes.

A task names a run, the target and base rows to keep, the instructions and
axes to keep, and a seed. Workers hold each run's full tables and build the
restriction themselves. Finished tasks are appended to a jsonl at once, and a
rerun skips the ids already there, so an interrupted analysis resumes.

Nothing here calls an API or a GPU. Everything is written under
``out/main/calibration/zero_compute/``.
"""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

from script.analysis.placebo_calibration import RUNS, _sha, _stored, _tables
from src.common.file_io import load_json, read_jsonl, save_json
from src.compare.behavior_table_restriction import restrict_table
from src.compare.paired_max_statistic import paired_max_test
from src.compare.principal_attribution import attribute_principal

OUT = Path("out/main/calibration/zero_compute")
#: The seed ``paired_max_test`` defaults to, which every stored run used.
PAPER_SEED = 20260726
N_PERMUTATIONS = 10000
ALPHA = 0.01
SPECS = {s.key: s for s in RUNS}


def digest(result: dict) -> dict:
    """The fields every analysis reports from one registered-test result."""
    att = attribute_principal(result)
    top = result["top_pairs"][0] if result["top_pairs"] else {}
    return {"S": float(result["statistic"]), "p": float(result["p_family_wise"]),
            "loyal": bool(result["loyal"]), "named": att["named"],
            "argmax": top.get("candidate"), "max_axis": top.get("axis_id"),
            "n_axes_rejected": int(result["n_axes_rejected"]),
            "n_axes": int(result["n_axes"]), "n_instructions": int(result["n_instructions"])}


def reproduce(keys: list[str]) -> int:
    """Rerun each stored result exactly; write the gate file; return failures."""
    rows, failures = [], 0
    for key in keys:
        spec = SPECS[key]
        level, stored = _stored(spec)
        target, base, _ = _tables(spec)
        got = paired_max_test(target, base, n_permutations=stored["n_permutations"],
                              alpha=stored["alpha"])
        stored_named = (stored.get("attribution") or {}).get("named")
        same = (got["statistic"] == stored["statistic"]
                and got["p_family_wise"] == stored["p_family_wise"]
                and digest(got)["named"] == stored_named
                and stored["n_permutations"] == N_PERMUTATIONS and stored["alpha"] == ALPHA)
        failures += not same
        rows.append({"key": key, "level": level, "stored_S": stored["statistic"],
                     "got_S": got["statistic"], "stored_p": stored["p_family_wise"],
                     "got_p": got["p_family_wise"], "match": same,
                     "sha256_target": _sha(spec.verdicts_target),
                     "sha256_base": _sha(spec.verdicts_base),
                     "stored_named": stored_named,
                     "full": digest(got)})
        print(f"{key:34s} S {stored['statistic']:.6f}/{got['statistic']:.6f} "
              f"p {stored['p_family_wise']:.6f}/{got['p_family_wise']:.6f} "
              f"{'MATCH' if same else 'MISMATCH'}", flush=True)
    save_json(OUT / "reproduction.json", {"seed": PAPER_SEED, "runs": rows,
                                          "failures": failures})
    return failures


def require_reproduced(keys) -> dict:
    """The gate: every key reproduced exactly on the verdict bytes now on disk."""
    gate = load_json(OUT / "reproduction.json")
    by_key = {r["key"]: r for r in gate["runs"]}
    for key in keys:
        row, spec = by_key.get(key), SPECS[key]
        if row is None or not row["match"]:
            raise SystemExit(f"{key}: not reproduced exactly; run `reproduce` first")
        if (row["sha256_target"] != _sha(spec.verdicts_target)
                or row["sha256_base"] != _sha(spec.verdicts_base)):
            raise SystemExit(f"{key}: verdict files changed since the reproduction")
    return by_key


_TABLES: dict = {}


def _init(keys: list[str]) -> None:
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    for key in keys:
        target, base, _ = _tables(SPECS[key])
        _TABLES[key] = (target, base)


def _arr(x):
    return None if x is None else np.asarray(x, dtype=np.int64)


def _execute(task: dict) -> dict:
    t0 = time.perf_counter()
    target, base = _TABLES[task["key"]]
    t = restrict_table(target, _arr(task.get("t_rows")), _arr(task.get("axes")),
                       _arr(task.get("blocks")))
    b = restrict_table(base, _arr(task.get("b_rows")), _arr(task.get("axes")),
                       _arr(task.get("blocks")))
    result = paired_max_test(t, b, n_permutations=N_PERMUTATIONS,
                             seed=task.get("seed", PAPER_SEED), alpha=ALPHA)
    return {"id": task["id"], "key": task["key"], "meta": task.get("meta", {}),
            "seed": task.get("seed", PAPER_SEED), **digest(result),
            "seconds": time.perf_counter() - t0}


def run_tasks(tasks: list[dict], log: Path, workers: int) -> list[dict]:
    """Run every task not yet in ``log``; return every record in ``log``."""
    log.parent.mkdir(parents=True, exist_ok=True)
    done = {r["id"] for r in read_jsonl(log)} if log.exists() else set()
    todo = [t for t in tasks if t["id"] not in done]
    keys = sorted({t["key"] for t in todo})
    print(f"{len(todo)} tasks on {workers} workers ({len(done)} already done)", flush=True)
    t0 = time.time()
    if todo:
        with ProcessPoolExecutor(max_workers=workers, initializer=_init,
                                 initargs=(keys,)) as pool, log.open("a") as fh:
            futures = [pool.submit(_execute, t) for t in todo]
            for n, fut in enumerate(as_completed(futures), 1):
                fh.write(json.dumps(fut.result()) + "\n")
                fh.flush()
                if n % 50 == 0 or n == len(futures):
                    print(f"{n}/{len(futures)} done, {time.time() - t0:.0f}s", flush=True)
    records = list(read_jsonl(log))
    ids = [r["id"] for r in records]
    if len(ids) != len(set(ids)):
        raise SystemExit(f"duplicate task ids in {log}")
    missing = {t["id"] for t in tasks} - set(ids)
    if missing:
        raise SystemExit(f"{len(missing)} tasks missing from {log}")
    return records


if __name__ == "__main__":
    # ``python -m script.analysis.zero_compute_runner`` writes the gate file.
    raise SystemExit(1 if reproduce([s.key for s in RUNS]) else 0)
