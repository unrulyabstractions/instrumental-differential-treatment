"""The coherence fold on split-half placebos of one model (B72).

    .venv/bin/python -m script.analysis.baseline_free_20261115.pooled_coherence.run_placebo run --replicates 100 --workers 6
    .venv/bin/python -m script.analysis.baseline_free_20261115.pooled_coherence.run_placebo summarize

A placebo splits every cell of one model's verdicts into two random halves and
reads one half as target and the other as base, so no candidate has an excess.
The splits are the registered placebo's own: the run list, the split seeds and
the permutation seeds come from ``script/analysis/placebo_calibration.py``
(``RUNS``, ``_seeds``, root seed 20261028, 2,000 permutations), imported and not
changed. Replicate ``r`` of a (run, model) here is therefore the same split as
replicate ``r`` of ``out/main/calibration/placebo/replicates.jsonl``, and that
file's registered placebo p is carried beside the fold's p. ``run`` first
recomputes the registered test on replicate 0 of every (run, model) and stops
unless it equals the stored replicate.

Writes ``placebo_replicates.jsonl`` (appended, resumable) and
``placebo_summary.json`` under the family folder.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np

from script.analysis.baseline_free_20261115.pooled_coherence.common import (
    ALPHA, OUT, PLACEBO_PERM, PLACEBO_ROOT_SEED, REPO, SETTINGS, read_jsonl, sha256, write_json)
from script.analysis.placebo_calibration import RUNS, ROOT_SEED, _seeds, _tables
from src.compare.paired_coherence_statistic import paired_coherence_test
from src.compare.paired_max_statistic import paired_max_test
from src.compare.placebo_calibration import (calibration_summary, split_cell_indices,
                                             subset_table)

LOG = OUT / "placebo_replicates.jsonl"
STORED = REPO / "out/main/calibration/placebo"
assert ROOT_SEED == PLACEBO_ROOT_SEED

_TABLES: dict = {}


def _init(tables):
    _TABLES.update(tables)
    os.environ.setdefault("OMP_NUM_THREADS", "1")


def _halves(key, model, split_seed):
    table = _TABLES[(key, model)]
    a, b = split_cell_indices(table, np.random.default_rng(split_seed))
    return subset_table(table, a), subset_table(table, b), a.size, b.size


def _task(key, model, r, split_seed, perm_seed, n_perm):
    t0 = time.perf_counter()
    ta, tb, na, nb = _halves(key, model, split_seed)
    out = paired_coherence_test(ta, tb, n_permutations=n_perm, seed=int(perm_seed), alpha=ALPHA)
    return {"key": key, "model": model, "replicate": r, "split_seed": split_seed,
            "permutation_seed": perm_seed, "n_permutations": n_perm,
            "p": float(out["p_family_wise"]), "statistic": float(out["statistic"]),
            "leading": out["leading"], "rejects": bool(out["p_family_wise"] <= ALPHA),
            "n_candidates": len(out["candidates"]), "n_target": int(na), "n_base": int(nb),
            "seconds": time.perf_counter() - t0}


def _registered_check(key, model, split_seed, perm_seed, n_perm):
    ta, tb, na, nb = _halves(key, model, split_seed)
    out = paired_max_test(ta, tb, n_permutations=n_perm, seed=int(perm_seed), alpha=ALPHA)
    return {"key": key, "model": model, "p": float(out["p_family_wise"]),
            "statistic": float(out["statistic"]), "n_target": int(na), "n_base": int(nb)}


def _stored_replicates():
    return {(r["key"], r["model"], r["replicate"]): r for r in read_jsonl(STORED / "replicates.jsonl")}


def run(replicates: int, workers: int, dedupe: bool = True) -> None:
    stored = _stored_replicates()
    design = json.loads((STORED / "design.json").read_text())
    tables, jobs, checks, seen = {}, [], [], {}
    for i, spec in enumerate(RUNS):
        target, base, _level = _tables(spec)
        for j, (model, table) in enumerate((("base", base), ("target", target))):
            path = spec.verdicts_base if model == "base" else spec.verdicts_target
            digest = sha256(path)
            if digest != design["runs"][spec.key][f"sha256_{model}"]:
                raise SystemExit(f"{spec.key}/{model}: verdicts changed since the stored placebo")
            # One verdict file split under several runs' seeds is repeat draws on one
            # dataset (the shared AuditBench base), so only its first run is placeboed.
            if dedupe and (digest, _level) in seen:
                print(f"skip {spec.key}/{model}: same verdicts as {seen[(digest, _level)]}",
                      flush=True)
                continue
            seen[(digest, _level)] = f"{spec.key}/{model}"
            tables[(spec.key, model)] = table
            for r in range(replicates):
                jobs.append((spec.key, model, r, *_seeds(i, j, r), PLACEBO_PERM))
            checks.append((spec.key, model, *_seeds(i, j, 0), PLACEBO_PERM))
    done = {(r["key"], r["model"], r["replicate"]) for r in read_jsonl(LOG)} if LOG.exists() else set()
    todo = [j for j in jobs if (j[0], j[1], j[2]) not in done]
    print(f"{len(todo)} replicates to run ({len(done)} done), {workers} workers", flush=True)
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(max_workers=workers, initializer=_init, initargs=(tables,)) as pool:
        if not (OUT / "placebo_registered_check.json").exists():
            got = [f.result() for f in [pool.submit(_registered_check, *c) for c in checks]]
            rows = []
            for c, g in zip(checks, got, strict=True):
                s = stored[(c[0], c[1], 0)]
                same = (abs(s["statistic"] - g["statistic"]) < 1e-9 and s["p"] == g["p"]
                        and s["n_target"] == g["n_target"] and s["n_base"] == g["n_base"]
                        and s["split_seed"] == c[2] and s["permutation_seed"] == c[3])
                rows.append({**g, "stored_p": s["p"], "stored_statistic": s["statistic"],
                             "match": bool(same)})
            ok = all(r["match"] for r in rows)
            write_json(OUT / "placebo_registered_check.json",
                       {"replicate": 0, "all_match": ok, "rows": rows})
            print(f"registered placebo replicate 0 reproduces: {ok}", flush=True)
            if not ok:
                raise SystemExit("the splits do not reproduce the stored registered placebo")
        with LOG.open("a") as fh:
            futures = [pool.submit(_task, *j) for j in todo]
            for n, fut in enumerate(as_completed(futures), 1):
                fh.write(json.dumps(fut.result()) + "\n")
                fh.flush()
                if n % 200 == 0 or n == len(futures):
                    print(f"{n}/{len(futures)} done, {time.time() - t0:.0f}s", flush=True)


def summarize(replace: bool) -> None:
    record = build_summary()
    write_json(OUT / "placebo_summary.json", record, replace=replace)
    a = record["pooled_three_or_more_candidates"]
    print(f"fold placebo (>=3 candidates): n={a['fold']['n']} share<=0.01 "
          f"{a['fold']['share_le_01']:.4f} share<=0.05 {a['fold']['share_le_05']:.4f}; registered "
          f"same splits {a['registered_same_splits']['share_le_01']:.4f} / "
          f"{a['registered_same_splits']['share_le_05']:.4f}", flush=True)


def build_summary() -> dict:
    stored = _stored_replicates()
    rows = list(read_jsonl(LOG))
    seen = [(r["key"], r["model"], r["replicate"]) for r in rows]
    if len(set(seen)) != len(seen):
        raise SystemExit("duplicate placebo replicates")
    by: dict = {}
    for r in rows:
        r["registered_p"] = stored[(r["key"], r["model"], r["replicate"])]["p"]
        by.setdefault((r["key"], r["model"]), []).append(r)
    per = {}
    for (key, model), reps in sorted(by.items()):
        reps.sort(key=lambda x: x["replicate"])
        p = np.array([x["p"] for x in reps])
        q = np.array([x["registered_p"] for x in reps])
        per[f"{key}/{model}"] = {
            "n_candidates": reps[0]["n_candidates"],
            "fold": calibration_summary(p), "registered_same_splits": calibration_summary(q),
            "both_reject_01": int(np.sum((p <= ALPHA) & (q <= ALPHA))),
            "spearman_fold_vs_registered": _spearman(p, q)}
    def pool(keep):
        p = np.array([r["p"] for r in rows if keep(r)])
        q = np.array([r["registered_p"] for r in rows if keep(r)])
        if p.size == 0:
            return None
        return {"fold": calibration_summary(p), "registered_same_splits": calibration_summary(q)}
    record = {
        "settings": {**SETTINGS, "replicates_per_model": max(r["replicate"] for r in rows) + 1,
                     "runs_and_seeds_from": "script/analysis/placebo_calibration.py (RUNS, _seeds)"},
        "n_replicates": len(rows),
        "pooled_all": pool(lambda r: True),
        "pooled_three_or_more_candidates": pool(lambda r: r["n_candidates"] >= 3),
        "pooled_two_candidates": pool(lambda r: r["n_candidates"] == 2),
        "pooled_base_seats": pool(lambda r: r["model"] == "base"),
        "pooled_target_seats": pool(lambda r: r["model"] == "target"),
        "per_model": per,
        "note": ("the nine AuditBench base seats share one verdict file, so it is split once, "
                 "under the seeds of its first run in the registered placebo's list"),
    }
    return record


def _spearman(a, b):
    from scipy import stats
    if np.ptp(a) == 0 or np.ptp(b) == 0:
        return None
    return float(stats.spearmanr(a, b).statistic)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--replicates", type=int, default=100)
    r.add_argument("--keep-shared", action="store_true",
                   help="placebo every run's copy of a shared verdict file")
    r.add_argument("--workers", type=int, default=6)
    s = sub.add_parser("summarize")
    s.add_argument("--replace", action="store_true")
    args = ap.parse_args()
    if args.cmd == "run":
        run(args.replicates, args.workers, dedupe=not args.keep_shared)
    else:
        summarize(args.replace)


if __name__ == "__main__":
    main()
