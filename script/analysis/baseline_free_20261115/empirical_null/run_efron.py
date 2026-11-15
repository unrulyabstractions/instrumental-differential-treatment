"""Efron's empirical null and the target-only lift on every listed subject. No spend.

    .venv/bin/python -m script.analysis.baseline_free_20261115.empirical_null.run_efron --workers 10

For every subject of ``empirical_null_subjects`` and every grid it has
(target-only ``median`` and ``mean``, base-referenced ``registered``) this runs
``analyse_grid``: three empirical-null fits on axis-centred z, the lift, the
local fdr of every cell, the permutation null of all of them (10,000 draws,
seed 20260726), the axis-block bootstrap (1,000), the bootstrap over
instructions (1,000, seed 20260726) and the delete-one jackknife over
instructions. Each record also carries tau, the between-candidate spread of
firing rates net of instruction noise (``empirical_null_tau``).

Placebos: every subject's cells are split into halves by the registry's
``placebo_halves(subject id, table, replicate)``, 20 replicates for an untuned
base and 5 for any other subject, and each split is analysed as a
base-referenced grid of the model against itself (without the instruction
bootstrap and the jackknife).

The user-awareness grading subjects have 60 cells, too few for the fit; they get
the maximum and the lift alone (``ua_lift``).

Writes one JSON per grid under ``runs/`` (with the observed t and centred z
beside it) and ``ua_lift.json``. ``summarise_efron`` folds them into the
summary files. Never overwrites an existing output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path

import numpy as np

from src.common.file_io import read_jsonl
from src.compare.behavior_count_table import build_behavior_table
from src.compare.paired_excess_measures import permutation_tail_share
from src.external.user_awareness_materials import GRADE_AXES

from script.analysis.baseline_free_20261115.empirical_null.empirical_null_grid_analysis import (
    N_PERM, SEED, TIE_TOL, analyse_grid, tail_share)
from script.analysis.baseline_free_20261115.empirical_null.empirical_null_grids import (
    effects, excess_batched, grid_t, load_table, permute, placebo_effect, stream_orders)
from script.analysis.baseline_free_20261115.empirical_null.empirical_null_settings import (
    family_settings)
from script.analysis.baseline_free_20261115.empirical_null.empirical_null_subjects import (
    UA_SUBJECTS, placebo_replicates, registry_id, subjects)
from script.analysis.baseline_free_20261115.empirical_null.empirical_null_tau import tau_block

OUT = Path("out/main/baseline_free_20261115/empirical_null")
_CACHE: dict = {}


def _sha(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _tables(s):
    k = (s.key,)
    if k not in _CACHE:
        t = load_table(s.target, s.axes, s.level, s.drop)
        b = load_table(s.base, s.axes, s.level, s.drop) if s.base else None
        _CACHE[k] = (t, b)
    return _CACHE[k]


def _stem(task: dict) -> str:
    if task["grid"] == "placebo":
        return f"{task['subject']}__placebo_r{task['replicate']:02d}"
    return f"{task['subject']}__{task['grid']}"


def run_task(task: dict) -> dict:
    t0 = time.time()
    s = next(x for x in subjects() if x.key == task["subject"])
    if task["grid"] == "placebo":
        rid = registry_id(s.key)
        grid, pair, cands, axes = placebo_effect(rid, task["replicate"])
        inst = None
        documented, stream, slim = None, "registered", True
        taus = {"all": tau_block(pair[0], pair[1])}
    else:
        target, base = _tables(s)
        d, pairs, cands, inst, axes = effects(target, base)
        grid, pair = d[task["grid"]], pairs.get(task["grid"])
        stream = "median" if task["grid"] == "median" else "registered"
        documented = s.documented if s.documented in cands else None
        slim = False
        p_t = pairs["mean"][0]
        p_b = pairs["registered"][1] if task["grid"] == "registered" else None
        taus = {"all": tau_block(p_t, p_b)}
        if documented:
            keep = np.array([c != documented for c in cands])
            taus[f"without_{documented}"] = tau_block(p_t, p_b, keep)
    rec = analyse_grid(grid, stream, cands, axes, documented=documented, pair=pair, slim=slim)
    t_obs, u_obs = rec.pop("_t"), rec.pop("_u")
    for name, v in rec["variants"].items():
        v["tau"] = taus[name]
    rec.update({"subject": s.key, "grid": task["grid"], "replicate": task.get("replicate"),
                "registry_id": registry_id(s.key), "stream": stream,
                "candidates": cands, "axes": list(axes), "instructions": inst,
                "documented": documented, "settings": task["settings"],
                "seconds": round(time.time() - t0, 1)})
    return {"record": rec, "t": t_obs, "u": u_obs, "stem": _stem(task)}


def ua_lift(key: str, folder: Path) -> dict:
    """Maximum |t| and the lift on a user-awareness grading subject (60 cells)."""
    axes = [a["axis_id"] for a in GRADE_AXES]
    rows = [r for r in read_jsonl(folder / "grades_target.jsonl")
            if int(r["level"]) == 1 and not r.get("failed")]
    table = build_behavior_table(rows, axes)
    d, pairs, cands, inst, ax = effects(table)
    out = {"subject": key, "folder": str(folder), "n_cells": len(cands) * len(axes),
           "candidates": cands, "sha256_grades": _sha(str(folder / "grades_target.jsonl")),
           "tau": tau_block(pairs["mean"][0]), "grids": {}}
    for kind in ("median", "mean"):
        stream = "median" if kind == "median" else "registered"
        t, _, fit = grid_t(d[kind])
        a = np.abs(t)
        s_obs = float(np.nanmax(a))
        orders = stream_orders(stream, len(cands), len(inst), N_PERM, SEED)
        dp = (permute(d[kind], orders) if kind == "median"
              else excess_batched(permute(pairs[kind][0], orders), permute(pairs[kind][1], orders)))
        tp, _, fp = grid_t(dp)
        flat = np.abs(tp).reshape(N_PERM, -1)
        maxima = np.nanmax(np.where(np.isnan(flat), -np.inf, flat), axis=1)
        obs_abs = a[~np.isnan(a)]
        med_obs = float(np.median(obs_abs))
        pooled = flat[~np.isnan(flat)]
        perm_med = float(np.median(pooled))
        grid_meds = np.nanmedian(flat, axis=1)
        tol = TIE_TOL * max(1.0, med_obs)
        ci, cj = np.unravel_index(np.nanargmax(a), a.shape)
        out["grids"][kind] = {
            "S": s_obs, "p_S": permutation_tail_share(maxima, s_obs, N_PERM),
            "p_S_ties_as_at_least": tail_share(maxima, s_obs),
            "argmax_candidate": cands[int(ci)], "argmax_axis": ax[int(cj)],
            "median_abs_t": med_obs, "perm_abs_median": perm_med,
            "perm_abs_median_float32": float(np.median(pooled.astype(np.float32))),
            "lambda": med_obs / perm_med,
            "p_lambda": tail_share(grid_meds, med_obs),
            "p_lambda_without_tie_tolerance": permutation_tail_share(grid_meds, med_obs, N_PERM),
            "lambda_atoms": {"share_observed_cells_at_median": float(np.mean(np.abs(obs_abs - med_obs) <= tol)),
                             "share_permuted_medians_tied": float(np.mean(np.abs(grid_meds - med_obs) <= tol))},
            "n_zero_spread": int(np.sum(~fit & ~np.isnan(t))), "t": t.tolist()}
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    ap.add_argument("--only", nargs="*", default=None, help="subject keys to run")
    ap.add_argument("--no-placebo", action="store_true", help="skip the placebo replicates")
    args = ap.parse_args()
    runs_dir = OUT / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    settings = family_settings()
    subs = [s for s in subjects() if args.only is None or s.key in args.only]
    tasks = []
    for s in subs:
        for g in ["median", "mean"] + (["registered"] if s.base else []):
            tasks.append({"subject": s.key, "grid": g, "settings": settings})
    if not args.no_placebo:
        for s in subs:
            for r in range(placebo_replicates(s)):
                tasks.append({"subject": s.key, "grid": "placebo", "replicate": r,
                              "settings": settings})
    tasks = [t for t in tasks if not (runs_dir / f"{_stem(t)}.json").exists()]
    meta_path = OUT / "subjects.json"
    if not meta_path.exists():
        meta = {s.key: {**asdict(s), "registry_id": registry_id(s.key),
                        "placebo_replicates": placebo_replicates(s),
                        "sha256_target": _sha(s.target),
                        "sha256_base": _sha(s.base) if s.base else None} for s in subjects()}
        with meta_path.open("x") as fh:
            json.dump(meta, fh, indent=1)
    print(f"{len(tasks)} grid tasks", flush=True)
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(run_task, t): t for t in tasks}
        for f in as_completed(futs):
            res = f.result()
            r = res["record"]
            path = runs_dir / f"{res['stem']}.json"
            with path.open("x") as fh:
                json.dump(r, fh, indent=1)
            np.savez_compressed(runs_dir / f"{res['stem']}_grid.npz", t=res["t"], u=res["u"])
            v = r["variants"]["all"]
            fit = v["fit"]
            print(f"{res['stem']:60s} S={r['S']:.3f} p={r['p_S']:.4f} lambda={v['lambda']:.3f} "
                  f"p_lambda={v['p_lambda']:.4f} sigma_loc={fit['loc']['sigma0']:.3f} "
                  f"p0_loc={fit['loc']['p0']:.3f} tau={v['tau']['tau_pp']:.2f} ({r['seconds']}s)",
                  flush=True)
    ua_path = OUT / "ua_lift.json"
    if not ua_path.exists() and args.only is None:
        rec = {k: ua_lift(k, p) for k, p in UA_SUBJECTS.items()}
        with ua_path.open("x") as fh:
            json.dump({"settings": settings, "subjects": rec}, fh, indent=1)
        for k, v in rec.items():
            print(k, {g: (round(x["S"], 3), x["p_S"], round(x["lambda"], 3), x["p_lambda"])
                      for g, x in v["grids"].items()}, flush=True)


if __name__ == "__main__":
    main()
