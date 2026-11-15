"""Descriptive name-effect correlations for the two narrow-secret-loyalty rosters.

The informed and scoped audits of the narrow-secret-loyalty organism
(Qwen2.5-1.5B, judge Claude Haiku 4.5) share two candidates, emmanuel_macron
and fran_ois_hollande, and no instruction. Three axes carry identical wording in
both registries (the guaranteed axes); two more share an id with different
wording. Each run is read at its registered level (informed 3, scoped 2), and
each candidate's gap is taken against its own run's roster before the shared
cells are kept.

Rows: the same seat across the two runs (target with target, base with base),
on the identically worded cells and on the id-shared cells; and, within each
run, the target against its own base over every cell, with instruction-bootstrap
intervals, which is the registered pair's own correlation.
"""

from __future__ import annotations

import json

import numpy as np

from script.analysis.baseline_free_20261115.proxy_swaps.swap_effects import (
    boot_effects, boot_interval, gap_grid, moments, name_effect_correlation, s_half_effects)
from script.analysis.baseline_free_20261115.proxy_swaps.swap_subjects import (
    N_BOOT, N_SPLITS, REPO, SEED)
from src.compare.behavior_count_table import build_behavior_table

RUNS = {"informed": ("out/main/secret_loyalties/calibration_informed", 3),
        "scoped": ("out/main/secret_loyalties/calibration_scoped", 2)}
SEATS = {"target": "score/verdicts_gen9_1p5b.jsonl", "base": "score/verdicts_base_1p5b.jsonl"}


def _axes(run: str) -> dict:
    root, _ = RUNS[run]
    return {a["axis_id"]: a["question"] for a in
            json.loads((REPO / root / "conjecture/scoring_questions.json").read_text())["axes"]}


def _table(run: str, seat: str):
    """The behavior table and the sample index of each of its rows."""
    root, level = RUNS[run]
    rows = [json.loads(x) for x in (REPO / root / SEATS[seat]).open() if x.strip()]
    rows = [r for r in rows if int(r["level"]) == level]
    return (build_behavior_table(rows, list(_axes(run))),
            np.array([int(r["s"]) for r in rows], dtype=np.int64))


def _corr(x: np.ndarray, y: np.ndarray) -> dict:
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    c = np.cov(x, y)
    return {"n_cells": int(ok.sum()), "r": float(c[0, 1] / np.sqrt(c[0, 0] * c[1, 1])),
            "beta": float(c[0, 1] / c[1, 1])}


def secret_loyalty_rows() -> dict:
    axes = {run: _axes(run) for run in RUNS}
    same_id = sorted(set(axes["informed"]) & set(axes["scoped"]))
    same_text = [a for a in same_id if axes["informed"][a] == axes["scoped"][a]]
    loaded = {(run, seat): _table(run, seat) for run in RUNS for seat in SEATS}
    tables = {k: v[0] for k, v in loaded.items()}
    shared = sorted(set(tables[("informed", "target")].principals)
                    & set(tables[("scoped", "target")].principals))
    effect = {k: np.nanmean(gap_grid(t), axis=1) for k, t in tables.items()}

    def cells(run: str, seat: str, axis_ids: list[str]) -> np.ndarray:
        t = tables[(run, seat)]
        ci = [t.principals.index(c) for c in shared]
        aj = [t.axes.index(a) for a in axis_ids]
        return effect[(run, seat)][np.ix_(ci, aj)].ravel()

    across = []
    for seat in SEATS:
        for label, ids in (("identical wording", same_text), ("same axis id", same_id)):
            across.append({"seat": seat, "axes": label, "axis_ids": ids, "candidates": shared,
                           **_corr(cells("informed", seat, ids), cells("scoped", seat, ids))})
    within = []
    for run in RUNS:
        gt, gb = gap_grid(tables[(run, "target")]), gap_grid(tables[(run, "base")])
        point = moments(np.nanmean(gt, 1).ravel(), np.nanmean(gb, 1).ravel())
        boot = moments(boot_effects(gt), boot_effects(gb))
        bi = {k: boot_interval(boot[k], float(point[k])) for k in ("r", "beta", "var_ratio")}
        halves = [s_half_effects(*loaded[(run, seat)], 4, N_SPLITS) for seat in ("target", "base")]
        named = name_effect_correlation(*halves)
        within.append({"run": run, "level": RUNS[run][1], "pair": "target|own base",
                       "n_cells": int(point["n_cells"]), "r": float(point["r"]),
                       "r_ci": bi["r"]["ci"], "beta": float(point["beta"]),
                       "beta_ci": bi["beta"]["ci"], "var_ratio": float(point["var_ratio"]),
                       "var_ratio_ci": bi["var_ratio"]["ci"], "bootstrap": bi,
                       "r_name_effects": named["r_name_effects"],
                       "shared_order_share": named["shared_order_share"],
                       "name_effect_split": named})
    return {"shared_candidates": shared, "same_id_axes": same_id, "identical_wording_axes": same_text,
            "levels": {run: lv for run, (_, lv) in RUNS.items()}, "across_runs": across,
            "within_run_target_vs_base": within, "n_bootstrap": N_BOOT, "seed": SEED,
            "reading": "descriptive only: no shared instruction, so no paired test is possible"}
