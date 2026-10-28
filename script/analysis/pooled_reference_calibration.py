"""Pooled within-run reference calibration on the paper's runs (B45), exploratory.

    .venv/bin/python -m script.analysis.pooled_reference_calibration run
    .venv/bin/python -m script.analysis.pooled_reference_calibration cross
    .venv/bin/python -m script.analysis.pooled_reference_calibration placebo --replicates 200
    .venv/bin/python -m script.analysis.pooled_reference_synthetic
    .venv/bin/python -m script.analysis.pooled_reference_report

``run`` covers every run of the B42 run list (Tables 2 and 3, plus the
informed helper swap). It recomputes the registered test on the registered
permutations and seed and refuses to write unless S and p equal the stored
summary exactly. It then computes the within-run reference
(``src/compare/pooled_within_run_reference.py``) and the drift-scaled repair
(``src/compare/drift_scaled_max_null.py``), and keeps every t grid.

``cross`` pools references across the nine AuditBench runs that share a base
model, a roster and an axis registry (``src/compare/cross_run_pooled_reference.py``).

``placebo`` reuses the B42 splits: same run positions and ``SeedSequence``
seeds, so replicate r splits the cells exactly as B42's replicate r did, and the
registered S and p of every replicate are checked against B42's stored values.

Nothing here calls an API or a GPU. It writes only under
``out/main/calibration/pooled_reference/``.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

from script.analysis.placebo_calibration import (ALPHA, CONTROLS, OUT as PLACEBO_OUT,
                                                 RUNS, _seeds, _sha, _stored, _tables)
from src.common.file_io import load_json, read_jsonl, save_json
from src.compare.cross_run_pooled_reference import (cross_run_reference_test,
                                                    reference_rows)
from src.compare.drift_scaled_max_null import (drift_scaled_p, registered_null,
                                               surviving_candidates)
from src.compare.paired_excess_measures import cell_rates
from src.compare.placebo_calibration import cell_sizes, split_cell_indices, subset_table
from src.compare.pooled_within_run_reference import (VARIANTS, pooled_reference_test,
                                                     t_grid)

OUT = Path("out/main/calibration/pooled_reference")
NULLS = tuple(f"auditbench_{c}" for c in CONTROLS)
#: Runs that share the AuditBench base, the contextual_optimism roster and its
#: axis registry, so their references can be pooled across runs.
FAMILY = ("auditbench_contextual_optimism", *NULLS)
N_BOOT = 10000


def evaluate(p_t: np.ndarray, p_b: np.ndarray, n_permutations: int, perm_seed: int,
             alpha: float, boot_seed: int) -> tuple[dict, np.ndarray]:
    """Registered S and p, the within-run reference and the drift-scaled repair."""
    t = t_grid(p_t, p_b)
    abs_t = np.abs(t)
    null = registered_null(p_t, p_b, n_permutations, seed=perm_seed)
    surviving = surviving_candidates(abs_t, null["maxima"], alpha)
    ref = pooled_reference_test(t, surviving, n_boot=N_BOOT, seed=boot_seed)
    for variant in VARIANTS:
        v = ref["variants"][variant]
        if v.get("computable"):
            v["drift_scaled"] = drift_scaled_p(ref["S"], null["maxima"],
                                               v["ref_median"], null["perm_abs_median"])
    ref.update({"surviving_candidates": sorted(surviving),
                "perm_abs_median": null["perm_abs_median"],
                "p_registered": drift_scaled_p(ref["S"], null["maxima"], 1.0, 1.0)
                ["p_registered"],
                "null_q99": float(np.quantile(null["maxima"], 0.99, method="higher"))})
    return ref, t


def run_all() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows, grids, failures = {}, {}, 0
    for index, spec in enumerate(RUNS):
        level, stored = _stored(spec)
        target, base, _ = _tables(spec)
        p_t, principals, _ = cell_rates(target)
        p_b, _, _ = cell_rates(base)
        t0 = time.perf_counter()
        got, t = evaluate(p_t, p_b, stored["n_permutations"], 20260726, stored["alpha"],
                          boot_seed=index)
        seconds = time.perf_counter() - t0
        same = got["S"] == stored["statistic"] and got["p_registered"] == stored["p_family_wise"]
        stored_surv = stored.get("surviving_pairs")
        surv_names = sorted(principals[c] for c in got["surviving_candidates"])
        surv_same = (None if stored_surv is None else
                     surv_names == sorted({x["candidate"] for x in stored_surv}))
        failures += (not same) or surv_same is False
        grids[spec.key] = t
        rows[spec.key] = {
            "table": spec.table, "level": level, "seconds": seconds,
            "candidates": principals, "axes": list(target.axes),
            "sha256_target": _sha(spec.verdicts_target),
            "sha256_base": _sha(spec.verdicts_base),
            "registered": {"S": stored["statistic"], "p": stored["p_family_wise"],
                           "loyal": stored["loyal"], "reproduced_exactly": same,
                           "surviving_candidates_match": surv_same},
            "top_candidate_name": principals[got["top_candidate"]],
            "surviving_candidate_names": surv_names, **got}
        v = got["variants"]["drop_top"]
        print(f"{spec.key:34s} N={got['n_candidates']} M={got['M']} S={got['S']:.3f} "
              f"p_reg={got['p_registered']:.4f} {'MATCH' if same else 'MISMATCH'} | "
              f"p_ref values/axes/cands {v['values']['p_ref']:.4f}/"
              f"{v['axes']['p_ref']:.4f}/{v['candidates']['p_ref']:.4f} "
              f"R={v['values']['R']:.3f} naiveR={v['naive_R']:.3f} "
              f"lambda={v['drift_scaled']['lambda']:.3f} "
              f"p_scaled={v['drift_scaled']['p_scaled']:.4f} | {seconds:.0f}s", flush=True)
    if failures:
        print(f"{failures} runs did not reproduce the registered test; nothing written")
        return failures
    save_json(OUT / "results.json", {"alpha": ALPHA, "n_boot": N_BOOT, "runs": rows})
    np.savez(OUT / "t_grids.npz", **grids)
    print(f"wrote {OUT / 'results.json'} and {OUT / 't_grids.npz'}")
    return 0


def cross() -> None:
    runs = load_json(OUT / "results.json")["runs"]
    grids = np.load(OUT / "t_grids.npz")
    first = runs[FAMILY[0]]
    for key in FAMILY:
        if runs[key]["candidates"] != first["candidates"] or runs[key]["axes"] != first["axes"]:
            raise ValueError(f"{key} does not share the roster and axes of {FAMILY[0]}")
    bases = {runs[k]["sha256_base"] for k in FAMILY}
    out = {"family": list(FAMILY), "shared_base_files": len(bases),
           "pools": {"all_family": "every other run of the family, the positive "
                     "contextual_optimism included",
                     "nulls_only": "the other null controls only, top rows dropped",
                     "nulls_only_all_rows": "the other null controls only, every "
                     "row kept (exchangeable when they are nulls)"}}
    for pool in out["pools"]:
        out[pool] = {}
        for index, key in enumerate(FAMILY):
            members = [k for k in FAMILY if k != key
                       and (pool == "all_family" or k in NULLS)]
            others = [reference_rows(grids[k], drop_top=pool != "nulls_only_all_rows")
                      for k in members]
            r = cross_run_reference_test(grids[key], others, N_BOOT, seed=100 + index)
            out[pool][key] = {"reference_runs": members, **r}
            print(f"{pool:10s} {key:34s} S={r['S']:.3f} p_values={r['values']['p_ref']:.4f} "
                  f"p_axes={r['axes']['p_ref']:.4f} R={r['values']['R']:.3f} "
                  f"naive_p={r['naive_p_single']:.4f} naiveR={r['naive_R']:.3f}")
    save_json(OUT / "cross_run.json", out)
    print(f"wrote {OUT / 'cross_run.json'}")


_WORKER_TABLES: dict = {}


def _init_worker(tables: dict) -> None:
    _WORKER_TABLES.update(tables)
    os.environ.setdefault("OMP_NUM_THREADS", "1")


def _task(key, model, replicate, split_seed, perm_seed, n_permutations) -> dict:
    t0 = time.perf_counter()
    table = _WORKER_TABLES[(key, model)]
    a, b = split_cell_indices(table, np.random.default_rng(split_seed))
    p_t, _, _ = cell_rates(subset_table(table, a))
    p_b, _, _ = cell_rates(subset_table(table, b))
    got, _ = evaluate(p_t, p_b, n_permutations, perm_seed, ALPHA, boot_seed=split_seed)
    flat = {"S": got["S"], "M": got["M"], "p_registered": got["p_registered"],
            "n_surviving": len(got["surviving_candidates"]),
            "tied": got["S_tied_by_other_candidate"]}
    for variant, v in got["variants"].items():
        if not v.get("computable"):
            continue
        for scheme in ("values", "axes", "candidates"):
            flat[f"{variant}/{scheme}/p_ref"] = v[scheme]["p_ref"]
            flat[f"{variant}/{scheme}/R"] = v[scheme]["R"]
        flat[f"{variant}/p_exact_values"] = v["p_exact_values"]
        flat[f"{variant}/naive_p_single"] = v["naive_p_single"]
        flat[f"{variant}/naive_R"] = v["naive_R"]
        for k in ("lambda", "p_scaled", "p_scaled_unfloored"):
            flat[f"{variant}/{k}"] = v["drift_scaled"][k]
    return {"key": key, "model": model, "replicate": replicate, "split_seed": split_seed,
            "permutation_seed": perm_seed, "n_permutations": n_permutations,
            "seconds": time.perf_counter() - t0, **flat}


def placebo(replicates: int, n_permutations: int, workers: int) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    log = OUT / "placebo_replicates.jsonl"
    done = ({(r["key"], r["model"], r["replicate"]) for r in read_jsonl(log)}
            if log.exists() else set())
    tables, todo, skipped = {}, [], {}
    for i, spec in enumerate(RUNS):
        target, base, _ = _tables(spec)
        for j, (model, table) in enumerate((("base", base), ("target", target))):
            if cell_sizes(table).min() < 2:
                skipped[f"{spec.key}/{model}"] = "a cell holds fewer than two samples"
                continue
            tables[(spec.key, model)] = table
            todo += [(spec.key, model, r, *_seeds(i, j, r), n_permutations)
                     for r in range(replicates) if (spec.key, model, r) not in done]
    save_json(OUT / "placebo_design.json",
              {"replicates": replicates, "n_permutations": n_permutations,
               "n_boot": N_BOOT, "alpha": ALPHA, "b42_replicates": str(PLACEBO_OUT),
               "seeds": "B42: SeedSequence([20261028, run_index, model_index, "
               "replicate]); bootstrap seed = split seed", "skipped": skipped})
    print(f"{len(todo)} replicates to run on {workers} workers ({len(done)} done); "
          f"skipped {skipped}", flush=True)
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker,
                             initargs=(tables,)) as pool, log.open("a") as fh:
        futures = [pool.submit(_task, *t) for t in todo]
        for n, fut in enumerate(as_completed(futures), 1):
            fh.write(json.dumps(fut.result()) + "\n")
            fh.flush()
            if n % 200 == 0 or n == len(futures):
                print(f"{n}/{len(futures)} done, {time.time() - t0:.0f}s", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run")
    sub.add_parser("cross")
    p = sub.add_parser("placebo")
    p.add_argument("--replicates", type=int, default=200)
    p.add_argument("--permutations", type=int, default=2000)
    p.add_argument("--workers", type=int, default=14)
    args = ap.parse_args()
    if args.cmd == "run":
        raise SystemExit(1 if run_all() else 0)
    if args.cmd == "cross":
        cross()
    else:
        placebo(args.replicates, args.permutations, args.workers)


if __name__ == "__main__":
    main()
