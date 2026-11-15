"""Merge the task log into the family's outputs. Refuses to overwrite any of them.

Writes ``results.json``, ``runs/<subject>.json``, ``t_grids.npz`` (with
``t_grids_index.json``), ``perm_abs_median.json``, ``reproduce_check.json``,
``settings.json``, ``manifest.csv``, then the tables and README of
``sharp_null_report``. A planned task missing from the log stops it, and so does
a logged line whose input fields differ from the planned task's, or a borderline
decision with no precision rerun.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from script.analysis.baseline_free_20261115.sharp_null_screen.sharp_null_checks import all_checks
from script.analysis.baseline_free_20261115.sharp_null_screen.sharp_null_report import (
    write_report)
from script.analysis.baseline_free_20261115.sharp_null_screen.sharp_null_rows import (
    borderline_task_ids)
from script.analysis.baseline_free_20261115.sharp_null_screen.sharp_null_tables import (
    G_IDS, axis_ids)

#: The fields of a task that fix what it computes. A logged line is used only
#: when each of them equals the planned task's.
INPUT_KEYS = ("sid", "kind", "subset", "table", "base", "axes", "level", "half", "base_half",
              "s_max", "placebo_of", "replicate")
OUTPUTS = ("results.json", "t_grids.npz", "t_grids_index.json", "perm_abs_median.json",
           "reproduce_check.json", "settings.json", "manifest.csv", "screen_table.csv",
           "rejection_counts.csv", "registered_agreement.csv", "target_base_pairs.csv",
           "target_base_counts.csv", "README.md", "runs")


def _new(path: Path) -> Path:
    if path.exists():
        raise SystemExit(f"refusing to overwrite {path}; move it to out/superseded/ first")
    return path


def _dump(path: Path, obj) -> None:
    with _new(path).open("x") as fh:
        json.dump(obj, fh, indent=1, default=str, allow_nan=True)


def _axes_of(meta: dict, task: dict) -> list[str]:
    full = axis_ids(meta["axes"])
    return full if task["subset"] == "full" else [a for a in full if a in G_IDS]


def load_task_log(path: Path, tasks: list[dict]) -> dict[str, dict]:
    """Every planned task's logged result, with the planned fields laid over it.

    Stops when a planned task is missing, when an id is logged twice, or when a
    line's input fields differ from the plan.
    """
    res: dict[str, dict] = {}
    for line in path.open():
        if line.strip():
            r = json.loads(line)
            if r["id"] in res:
                raise SystemExit(f"{r['id']} is logged twice in {path}")
            res[r["id"]] = r
    planned = {t["id"]: t for t in tasks}
    missing = [t for t in planned if t not in res]
    if missing:
        raise SystemExit(f"{len(missing)} planned tasks are not in {path}: {missing[:5]}")
    extra = [t for t in res if t not in planned]
    if extra:
        raise SystemExit(f"{len(extra)} logged tasks are not planned: {extra[:5]}")
    bad = [t for t, task in planned.items()
           if any(res[t].get(k) != task.get(k) for k in INPUT_KEYS)]
    if bad:
        raise SystemExit(f"{len(bad)} logged tasks differ from the plan in an input: {bad[:5]}")
    return {t: {**res[t], **task} for t, task in planned.items()}


def load_precision(path: Path, want: set[str]) -> dict[str, dict]:
    got: dict[str, dict] = {}
    if path.exists():
        for line in path.open():
            if line.strip():
                r = json.loads(line)
                got[r["id"]] = r
    missing = sorted(want - set(got))
    if missing:
        raise SystemExit(f"{len(missing)} borderline tasks have no precision rerun: {missing}")
    return {t: got[t] for t in sorted(want)}


def finalize(out: Path, planned: tuple[list[dict], list[dict], dict], settings: dict) -> None:
    tasks, skipped, meta = planned
    for name in OUTPUTS:
        _new(out / name)
    res = load_task_log(out / "tasks.jsonl", tasks)
    precision = load_precision(out / "mc_precision.jsonl",
                               borderline_task_ids(res, skipped, meta))

    manifest = [{"subject": t["sid"], "registry_subject_id": t["registry_subject_id"],
                 "group": t["group"], "variant": t["kind"], "subset": t["subset"],
                 "status": "done"} for t in tasks]
    manifest += [{"subject": s["sid"], "registry_subject_id": s["registry_subject_id"],
                  "group": s["group"], "variant": s["kind"], "subset": s["subset"],
                  "status": s["status"]} for s in skipped]
    manifest.sort(key=lambda r: (r["subject"], r["subset"], r["variant"]))
    with _new(out / "manifest.csv").open("x", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(manifest[0]))
        w.writeheader()
        w.writerows(manifest)

    arrays, index, lifts = {}, {}, {}
    for t in tasks:
        r = res[t["id"]]
        if not r.get("grid_file"):
            continue
        stem = t["id"].replace("|", "__")
        with np.load(out / "task_grids" / r["grid_file"]) as z:
            names = sorted(z.files)
            for k in names:
                arrays[f"{stem}__{k}"] = z[k]
        index[t["id"]] = {"key_stem": stem, "registry_subject_id": t["registry_subject_id"],
                          "candidates": r["candidates"],
                          "axes": _axes_of(meta[t["sid"]], t), "arrays": names}
        if t["kind"] in ("mean", "median"):
            lifts[t["id"]] = {k: r[k] for k in ("sid", "registry_subject_id", "group", "kind",
                                                "subset", "S", "p", "obs_abs_median",
                                                "perm_abs_median", "lift")}
    np.savez_compressed(_new(out / "t_grids.npz"), **arrays)
    _dump(out / "t_grids_index.json", {"settings": settings, "grids": index})
    _dump(out / "perm_abs_median.json", {
        "settings": settings,
        "definition": "perm_abs_median is the median of |t| pooled over every defined pair "
                      "of every permuted grid; obs_abs_median is the same over the observed "
                      "grid; lift is their ratio", "rows": lifts})

    checks = all_checks(res, meta, precision)
    _dump(out / "reproduce_check.json", checks)
    _dump(out / "settings.json", settings)
    _dump(out / "results.json", {"settings": settings, "subjects": meta, "results": res,
                                 "precision_reruns": precision,
                                 "not_runnable": skipped, "check_counts": checks["counts"]})
    runs = _new(out / "runs")
    runs.mkdir()
    for sid, m in meta.items():
        _dump(runs / f"{sid}.json", {
            "settings": settings, "subject": m,
            "results": {rid: r for rid, r in res.items() if r["sid"] == sid},
            "precision_reruns": {rid: r for rid, r in precision.items()
                                 if rid.split("|", 1)[0] == sid},
            "not_runnable": [s for s in skipped if s["sid"] == sid]})
    write_report(out, res, skipped, meta, checks, settings, precision)
    print(f"{len(res)} results, {len(skipped)} not runnable, {len(precision)} precision "
          f"reruns, {checks['n_checks']} checks, {checks['n_mismatches']} mismatches")
