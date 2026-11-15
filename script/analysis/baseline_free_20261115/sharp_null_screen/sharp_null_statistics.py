"""Worker side of the screen: one task is one statistic on one subject's table.

Kinds, all at 10,000 permutations, seed 20260726, alpha 0.01:

- ``registered``: ``paired_max_test`` against the subject's pair (its base, another
  base draw, or the other placebo half). Shown beside the screen, never part of it.
- ``mean``: ``paired_max_test`` against partA's all-zero base (one-vs-mean-of-rest).
- ``median``: ``reference_free_max_test`` (one-vs-median-of-rest).
- ``g_test``: ``homogeneity_test``, the per-seat G of stage 6.
- ``coherence``: ``axis_coherence_test`` on the single table (k0 20, clip 8, floor 0.25).
- ``loser``: ``loser_dispersion_test`` with an all-zero base (per-axis leave-one-out z).

``mean`` and ``median`` also replay their own permutation stream to keep the null
maxima and the pooled median |t| over permuted grids, and check that the replay
reproduces the library's p.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from src.compare.axis_coherence_statistic import (K0, SCALE_FLOOR_SHARE, Z_CLIP,
                                                  axis_coherence_test)
from src.compare.drift_scaled_max_null import registered_null
from src.compare.homogeneity_permutation import homogeneity_test
from src.compare.loser_dispersion_statistic import loser_dispersion_test_tables
from src.compare.paired_excess_measures import (cell_rates, excess_effect, max_abs_statistic,
                                                permutation_tail_share, standardized_excess)
from src.compare.paired_max_statistic import paired_max_test
from src.compare.reference_free_max_statistic import (permute_within_instructions,
                                                      reference_free_effect,
                                                      reference_free_max_test)
from script.analysis.baseline_free_20261115.sharp_null_screen.sharp_null_digest import (
    coherence_digest, g_digest, loser_digest, max_digest)
from script.analysis.baseline_free_20261115.sharp_null_screen.sharp_null_tables import (
    table_for, zero_base)

SEED, N_PERM, ALPHA = 20260726, 10000, 0.01


def _abs_median(t: np.ndarray) -> float:
    v = np.abs(t[~np.isnan(t)])
    return float(np.median(v)) if v.size else float("nan")


def _median_replay(table) -> dict:
    """``reference_free_max_test``'s own stream, keeping maxima and pooled |t|."""
    rates, _, _ = cell_rates(table)
    d = reference_free_effect(rates)
    t_obs, _, _ = standardized_excess(d)
    rng = np.random.default_rng(SEED)
    maxima = np.empty(N_PERM)
    pooled = []
    for k in range(N_PERM):
        t_null, _, _ = standardized_excess(permute_within_instructions(d, rng))
        maxima[k] = max_abs_statistic(t_null, signed=False)
        pooled.append(np.abs(t_null[~np.isnan(t_null)]).astype(np.float32))
    return {"t_obs": t_obs, "maxima": maxima,
            "perm_abs_median": float(np.median(np.concatenate(pooled)))}


def _mean_replay(table) -> dict:
    p_t, _, _ = cell_rates(table)
    p_z, _, _ = cell_rates(zero_base(table))
    t_obs, _, _ = standardized_excess(excess_effect(p_t, p_z))
    null = registered_null(p_t, p_z, N_PERM, seed=SEED)
    return {"t_obs": t_obs, "maxima": null["maxima"], "perm_abs_median": null["perm_abs_median"]}


def _replay_fields(rep: dict, res: dict) -> dict:
    p_replay = permutation_tail_share(rep["maxima"], float(res["statistic"]), N_PERM)
    return {"obs_abs_median": _abs_median(rep["t_obs"]),
            "perm_abs_median": rep["perm_abs_median"],
            "lift": _abs_median(rep["t_obs"]) / rep["perm_abs_median"]
            if rep["perm_abs_median"] > 0 else float("nan"),
            "replay_p": p_replay, "replay_reproduces_p": p_replay == float(res["p_family_wise"]),
            "replay_null_mean": float(rep["maxima"].mean())}


def run_task(task: dict, grid_dir: str) -> dict:
    t0 = time.time()
    kind = task["kind"]
    tgt = table_for(task)
    n_cells = len(tgt.principals) * len(tgt.axes)
    grids: dict[str, np.ndarray] = {}
    if kind == "registered":
        base = table_for(task, "base")
        res = paired_max_test(tgt, base, n_permutations=N_PERM, seed=SEED, alpha=ALPHA,
                              top=n_cells)
        out = max_digest(res, "pair", len(tgt.axes), ALPHA)
        p_t, _, _ = cell_rates(tgt)
        p_b, _, _ = cell_rates(base)
        grids["t"] = standardized_excess(excess_effect(p_t, p_b))[0]
    elif kind == "mean":
        res = paired_max_test(tgt, zero_base(tgt), n_permutations=N_PERM, seed=SEED,
                              alpha=ALPHA, top=n_cells)
        rep = _mean_replay(tgt)
        out = {**max_digest(res, "pair", len(tgt.axes), ALPHA), **_replay_fields(rep, res)}
        grids.update(t=rep["t_obs"], null_max=rep["maxima"])
    elif kind == "median":
        res = reference_free_max_test(tgt, n_permutations=N_PERM, seed=SEED, alpha=ALPHA,
                                      top=n_cells)
        rep = _median_replay(tgt)
        out = {**max_digest(res, "median", len(tgt.axes), ALPHA), **_replay_fields(rep, res)}
        grids.update(t=rep["t_obs"], null_max=rep["maxima"])
    elif kind == "g_test":
        res = homogeneity_test(tgt, n_permutations=N_PERM, seed=SEED).as_dict()
        out = g_digest(res, list(tgt.principals), len(tgt.axes), ALPHA)
    elif kind == "coherence":
        res = axis_coherence_test(tgt, n_permutations=N_PERM, seed=SEED, alpha=ALPHA, k0=K0)
        rates, _, _ = cell_rates(tgt)
        out = coherence_digest(res, reference_free_effect(rates), list(tgt.axes), ALPHA)
        out["settings"] = {"k0": K0, "z_clip": Z_CLIP, "scale_floor_share": SCALE_FLOOR_SHARE}
    elif kind == "loser":
        res = loser_dispersion_test_tables(tgt, zero_base(tgt), n_permutations=N_PERM,
                                           seed=SEED, alpha=ALPHA, top=n_cells)
        out = loser_digest(res, len(tgt.axes), ALPHA)
    else:
        raise ValueError(kind)
    if grids:
        path = Path(grid_dir) / f"{task['id'].replace('|', '__')}.npz"
        np.savez_compressed(path, **grids)
        out["grid_file"] = path.name
    k = len(tgt.principals)
    out.update({"k": k, "n_responses": int(tgt.n_responses), "n_null_verdicts": int(tgt.n_null),
                "k2_flag": "named not identified: with two candidates the effect is "
                           "antisymmetric and the argmax is a tie-break" if k == 2 else ""})
    return {**task, **out, "seconds": round(time.time() - t0, 1)}
