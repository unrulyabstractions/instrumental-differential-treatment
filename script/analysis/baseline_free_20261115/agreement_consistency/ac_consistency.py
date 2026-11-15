"""Consistency of the leading candidate over framings or folds, and its variance components.

- ``kendall_w``: Kendall's coefficient of concordance of the candidates' ranks over
  m raters (framings or folds), with the tie correction and its chi-square p.
- ``scope_concordance``: W of the candidates' target-only peaks over disjoint
  instruction sets, whether every set names the same leader, and the mean pairwise
  correlation of the signed candidate-by-axis t grid. Both are referred to the
  within-instruction label shuffle, drawn independently in every set. That shuffle
  is a sharp null: generic name effects that replicate over sets reject it too.
- ``partial_conjunction``: Benjamini and Heller's test that at least r of n p values
  are non-null, by Fisher's method on the n - r + 1 largest.
- ``variance_components``: the two-way random-effects decomposition of cell rates
  over candidates and instructions, per axis, net of binomial noise.
"""

from __future__ import annotations

import itertools
import math

import numpy as np
from scipy import stats

from src.compare.behavior_count_table import BehaviorTable
from src.compare.candidate_detachment_measures import candidate_peaks
from src.compare.paired_excess_measures import cell_rates, permutation_tail_share, standardized_excess
from src.compare.reference_free_max_statistic import (permute_within_instructions,
                                                      reference_free_effect)

from script.analysis.baseline_free_20261115.agreement_consistency.ac_tables import (
    restrict_blocks)


def kendall_w(values: np.ndarray) -> dict:
    """W for an (m raters, k objects) array of scores, larger score ranked first."""
    m, k = values.shape
    v = np.where(np.isnan(values), -np.inf, values)
    ranks = np.vstack([stats.rankdata(-row, method="average") for row in v])
    r_sum = ranks.sum(axis=0)
    s = float(np.sum((r_sum - r_sum.mean()) ** 2))
    ties = 0.0
    for row in ranks:
        _, counts = np.unique(row, return_counts=True)
        ties += float(np.sum(counts ** 3 - counts))
    denom = m * m * (k ** 3 - k) - m * ties
    if k < 2 or denom <= 0:
        return {"W": None, "chi2": None, "df": k - 1, "p_chi2": None,
                "identified": False}
    w = 12.0 * s / denom
    chi2 = m * (k - 1) * w
    return {"W": w, "chi2": chi2, "df": k - 1,
            "p_chi2": float(stats.chi2.sf(chi2, k - 1)), "identified": True}


def _scope_effects(table: BehaviorTable, scopes: list[list[str]]) -> list[np.ndarray]:
    out = []
    for ids in scopes:
        rates, _, _ = cell_rates(restrict_blocks(table, ids))
        out.append(reference_free_effect(rates))
    return out


def _peaks_and_grid(d: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    t, _, _ = standardized_excess(d)
    return candidate_peaks(t), t


def _profile_correlation(grids: list[np.ndarray]) -> float | None:
    """Mean pairwise Pearson correlation of the signed t grids (finite cells only)."""
    vals = []
    for a, b in itertools.combinations(grids, 2):
        x, y = a.ravel(), b.ravel()
        ok = np.isfinite(x) & np.isfinite(y)
        if ok.sum() < 3 or np.std(x[ok]) == 0 or np.std(y[ok]) == 0:
            continue
        vals.append(float(np.corrcoef(x[ok], y[ok])[0, 1]))
    return float(np.mean(vals)) if vals else None


def _leaders(peaks: list[np.ndarray], candidates: list[str]) -> list[str | None]:
    out = []
    for p in peaks:
        if np.all(np.isnan(p)):
            out.append(None)
            continue
        top = np.nanmax(p)
        tied = [candidates[i] for i in range(len(p)) if p[i] == top]
        out.append(tied[0] if len(tied) == 1 else None)
    return out


def scope_concordance(table: BehaviorTable, scopes: list[list[str]], n_perm: int,
                      seed: int) -> dict:
    candidates = list(table.principals)
    k = len(candidates)
    effects = _scope_effects(table, scopes)
    obs = [_peaks_and_grid(d) for d in effects]
    peaks = np.vstack([p for p, _ in obs])
    w = kendall_w(peaks)
    leaders = _leaders([p for p, _ in obs], candidates)
    all_same = (leaders[0] if leaders[0] is not None and len(set(leaders)) == 1 else None)
    prof = _profile_correlation([g for _, g in obs])
    out = {"k": k, "n_scopes": len(scopes),
           "scope_sizes": [len(s) for s in scopes],
           "peaks_by_scope": [{c: float(p[i]) for i, c in enumerate(candidates)}
                              for p, _ in obs],
           "leader_by_scope": leaders, "all_scopes_same_leader": all_same is not None,
           "common_leader": all_same, "independence_rate_all_same": 1.0 / k ** (len(scopes) - 1),
           **w, "profile_correlation": prof}
    if k == 2:
        out["note"] = ("two candidates: the target-only contrast is antisymmetric, so the "
                       "peaks tie and neither W nor a leader is identified")
    rng = np.random.default_rng(seed)
    null_w = np.full(n_perm, np.nan)
    null_same = np.zeros(n_perm, dtype=bool)
    null_prof = np.full(n_perm, np.nan)
    for b in range(n_perm):
        res = [_peaks_and_grid(permute_within_instructions(d, rng)) for d in effects]
        pk = np.vstack([p for p, _ in res])
        if w["identified"]:
            null_w[b] = kendall_w(pk)["W"]
            ls = _leaders([p for p, _ in res], candidates)
            null_same[b] = ls[0] is not None and len(set(ls)) == 1
        pc = _profile_correlation([g for _, g in res])
        null_prof[b] = np.nan if pc is None else pc
    if w["identified"]:
        out["p_perm_W"] = permutation_tail_share(null_w, float(w["W"]), n_perm)
        out["null_W_mean"] = float(np.nanmean(null_w))
        out["null_W_p95"] = float(np.nanquantile(null_w, 0.95))
        out["null_rate_all_same"] = float(null_same.mean())
    if prof is not None:
        finite = null_prof[np.isfinite(null_prof)]
        out["p_perm_profile"] = permutation_tail_share(finite, prof, finite.size)
        out["null_profile_mean"] = float(finite.mean()) if finite.size else None
        out["null_profile_p95"] = float(np.quantile(finite, 0.95)) if finite.size else None
    out["n_permutations"] = n_perm
    return out


def partial_conjunction(pvals, r: int) -> dict:
    """p for "at least r of the n hypotheses are non-null" (Fisher, n - r + 1 largest)."""
    p = np.sort(np.asarray(pvals, dtype=float))
    n = p.size
    use = p[r - 1:]  # the n - r + 1 largest
    x = float(-2.0 * np.sum(np.log(use)))
    return {"r": r, "n": n, "combined": [float(v) for v in use],
            "fisher_chi2": x, "df": 2 * use.size,
            "p": float(stats.chi2.sf(x, 2 * use.size))}


def variance_components(table: BehaviorTable, drop: tuple[str, ...] = ()) -> dict:
    """Var(theta), Var(eta) and binomial noise of cell rates, per axis and summed.

    The model per axis is ``p_ci = mu + a_i + theta_c + eta_ci + eps_ci``: an
    instruction effect, a stable candidate effect, a candidate-by-instruction
    interaction, and binomial noise of the cell's own samples. The moment
    estimates are the two-way ANOVA ones:

        E[MS_cand] = I Var(theta) + Var(eta) + Var(eps)
        E[MS_int]  = Var(eta) + Var(eps)

    with Var(eps) the mean over cells of ``p (1 - p) / (n - 1)``, the unbiased
    binomial variance of a cell rate. An axis enters only over the instructions
    where every kept candidate has a scored cell with at least two verdicts.
    ``fold_reliability`` is the share of a candidate's fold-mean variance that is
    stable: ``Var(theta) / (Var(theta) + (Var(eta) + Var(eps)) / I_fold)``.
    """
    rates, candidates, _ = cell_rates(table)
    keep = [i for i, c in enumerate(candidates) if c not in drop]
    rates = rates[keep]
    n_c = len(keep)
    seen = np.zeros(rates.shape)
    block_index = {b: i for i, b in enumerate(sorted({int(b) for b in table.block_of}))}
    cand_index = {c: j for j, c in enumerate(keep)}
    for r in range(table.n_responses):
        c = int(table.group_of[r])
        if c not in cand_index:
            continue
        seen[cand_index[c], block_index[int(table.block_of[r])]] += table.scored[r]
    per_axis = []
    sums = {"theta": 0.0, "eta": 0.0, "eps": 0.0, "ms_cand": 0.0, "ms_int": 0.0}
    n_inst_used = []
    for j in range(rates.shape[2]):
        y = rates[:, :, j]
        n = seen[:, :, j]
        ok = np.all(np.isfinite(y) & (n >= 2), axis=0)
        y, n = y[:, ok], n[:, ok]
        n_i = y.shape[1]
        if n_i < 2 or n_c < 2:
            continue
        grand = y.mean()
        row = y.mean(axis=1, keepdims=True)
        col = y.mean(axis=0, keepdims=True)
        ms_c = n_i * float(np.sum((row - grand) ** 2)) / (n_c - 1)
        resid = y - row - col + grand
        ms_int = float(np.sum(resid ** 2)) / ((n_c - 1) * (n_i - 1))
        eps = float(np.mean(y * (1 - y) / (n - 1)))
        theta = (ms_c - ms_int) / n_i
        eta = ms_int - eps
        per_axis.append({"axis_id": table.axes[j], "n_instructions": n_i,
                         "var_theta": theta, "var_eta": eta, "var_eps": eps,
                         "ms_cand": ms_c, "ms_int": ms_int})
        sums["theta"] += theta
        sums["eta"] += eta
        sums["eps"] += eps
        sums["ms_cand"] += ms_c
        sums["ms_int"] += ms_int
        n_inst_used.append(n_i)
    if not per_axis:
        return {"computable": False}
    i_bar = float(np.mean(n_inst_used))
    th, et, ep = max(sums["theta"], 0.0), max(sums["eta"], 0.0), sums["eps"]
    informative = [a for a in per_axis if a["var_theta"] + a["var_eta"] > 0]
    share = [max(a["var_theta"], 0.0) / (max(a["var_theta"], 0.0) + max(a["var_eta"], 0.0))
             for a in informative
             if max(a["var_theta"], 0.0) + max(a["var_eta"], 0.0) > 0]

    def reliability(m: float) -> float | None:
        den = th + (et + ep) / m
        return th / den if den > 0 else None

    return {"computable": True, "candidates": [candidates[i] for i in keep],
            "dropped": list(drop), "n_axes": len(per_axis),
            "mean_instructions_per_axis": i_bar,
            "sum_var_theta": sums["theta"], "sum_var_eta": sums["eta"],
            "sum_var_eps": sums["eps"],
            "share_theta_of_signal": th / (th + et) if th + et > 0 else None,
            "eta_over_eps": sums["eta"] / sums["eps"] if sums["eps"] > 0 else None,
            "theta_over_eta": th / et if et > 0 else (math.inf if th > 0 else None),
            "instruction_reliability": reliability(1.0),
            "fold_reliability_9": reliability(9.0),
            "pooled_reliability": reliability(i_bar),
            "median_axis_share_theta": float(np.median(share)) if share else None,
            "n_axes_theta_positive": int(sum(a["var_theta"] > 0 for a in per_axis)),
            "n_axes_eta_positive": int(sum(a["var_eta"] > 0 for a in per_axis)),
            "interaction_F_vs_binomial": (sums["ms_int"] / sums["eps"]
                                          if sums["eps"] > 0 else None),
            "candidate_F_vs_interaction": (sums["ms_cand"] / sums["ms_int"]
                                           if sums["ms_int"] > 0 else None),
            "per_axis": per_axis}


def fold_profile_replication(table: BehaviorTable, folds: list[list[str]],
                             drop: tuple[str, ...] = ()) -> dict:
    """How well the kept candidates' mean one-vs-mean gaps replicate across folds.

    For each fold, the candidate-by-axis mean of the within-instruction centred
    rate (rate minus the instruction's mean over the kept candidates). The value is
    the mean pairwise Pearson correlation of those grids over the fold pairs, the
    direct reading of whether generic candidate effects replicate.
    """
    grids = []
    for ids in folds:
        rates, candidates, _ = cell_rates(restrict_blocks(table, ids))
        keep = [i for i, c in enumerate(candidates) if c not in drop]
        r = rates[keep]
        with np.errstate(invalid="ignore"):
            centred = r - np.nanmean(r, axis=0, keepdims=True)
            grids.append(np.nanmean(centred, axis=1))
    vals = []
    for a, b in itertools.combinations(grids, 2):
        x, y = a.ravel(), b.ravel()
        ok = np.isfinite(x) & np.isfinite(y)
        if ok.sum() >= 3 and np.std(x[ok]) > 0 and np.std(y[ok]) > 0:
            vals.append(float(np.corrcoef(x[ok], y[ok])[0, 1]))
    return {"mean_pairwise_correlation": float(np.mean(vals)) if vals else None,
            "pairwise": vals}
