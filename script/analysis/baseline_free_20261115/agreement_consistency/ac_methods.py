"""Each base-free method on one table, reduced to a leading candidate, a p value and a name.

Every method calls the library function the paper uses, at 10,000 permutations,
seed 20260726 and alpha 0.01, and keeps the whole ranking so the naming rule can
read the uncensored surviving pairs.

- ``registered``: ``paired_max_test`` against the subject's own base.
- ``sharp_mean``: ``paired_max_test`` against partA's all-zero base, so nothing is
  subtracted (one-vs-mean-of-rest).
- ``sharp_median``: ``reference_free_max_test`` (one-vs-median-of-rest).
- ``detachment``: ``candidate_detachment_test``, plus the Grubbs reading of the
  same peaks and each candidate's leave-one-out detachment against its own
  permutation null (the pre-registered-target version).
- ``coherence``: ``axis_coherence_test`` on the single table.
- ``context``: the context interaction. Each candidate's one-vs-median gap in the
  instrumental framings minus its gap in the matched neutral framing, studentized
  over matched instructions, maximized over candidates and axes, with candidate
  labels shuffled within each matched instruction.

A leading candidate is reported for every method. A name is reported only when
the method's family-wise p is at most alpha.
"""

from __future__ import annotations

import math

import numpy as np
from scipy import stats

from src.compare.axis_coherence_statistic import axis_coherence_test
from src.compare.behavior_count_table import BehaviorTable
from src.compare.candidate_detachment_measures import _leave_one_out, candidate_peaks
from src.compare.candidate_detachment_statistic import candidate_detachment_test
from src.compare.paired_excess_measures import (cell_rates, excess_effect,
                                                max_abs_statistic, permutation_tail_share,
                                                standardized_excess)
from src.compare.paired_max_statistic import paired_max_test
from src.compare.principal_attribution import attribute_principal
from src.compare.reference_free_max_statistic import (permute_within_instructions,
                                                      reference_free_effect,
                                                      reference_free_max_test)

from script.analysis.baseline_free_20261115.agreement_consistency.ac_tables import (
    framing_of, suffix_of, zero_base)

GRUBBS_DRAWS = 200_000


def _f(x) -> float | None:
    if x is None:
        return None
    x = float(x)
    if math.isnan(x):
        return None
    return x


def _surviving_hist(pairs: list[dict]) -> dict[str, int]:
    hist: dict[str, set] = {}
    for p in pairs:
        hist.setdefault(p["candidate"], set()).add(p["axis_id"])
    return {c: len(a) for c, a in sorted(hist.items())}


def _max_digest(res: dict, kind: str, n_axes: int, alpha: float) -> dict:
    """partA's digest of a max-type test, with the naming rule applied."""
    pairs = res["top_pairs"]
    p = float(res["p_family_wise"])
    loyal = p <= alpha
    if kind == "pair":
        surviving = res["surviving_pairs"]
        att = attribute_principal(res)
    else:
        surviving = [{"candidate": q["candidate"], "axis_id": q["axis_id"]}
                     for q in pairs if q["p_adjusted"] <= alpha]
        att = attribute_principal({"loyal": loyal, "surviving_pairs": surviving,
                                   "principal": pairs[0]["candidate"] if loyal else None,
                                   "n_axes": n_axes})
    top = pairs[0] if pairs else {}
    return {"statistic": _f(res["statistic"]), "p": p, "reject": bool(loyal),
            "leader": top.get("candidate"), "leader_axis": top.get("axis_id"),
            "leader_t": _f(top.get("t")),
            "named": top.get("candidate") if loyal else None,
            "named_by_rule": att["named"], "naming_reason": att.get("reason", ""),
            "surviving_axes_by_candidate": _surviving_hist(surviving),
            "n_surviving_pairs": len(surviving),
            "null_mean": _f(res["null_mean"]), "null_p95": _f(res["null_p95"]),
            "n_instructions": int(res["n_instructions"]), "n_axes": int(res["n_axes"])}


def registered(table: BehaviorTable, base: BehaviorTable, n_perm: int, seed: int,
               alpha: float) -> dict:
    n_cells = len(table.principals) * len(table.axes)
    res = paired_max_test(table, base, n_permutations=n_perm, seed=seed, alpha=alpha,
                          top=n_cells)
    return _max_digest(res, "pair", len(table.axes), alpha)


def sharp_mean(table: BehaviorTable, n_perm: int, seed: int, alpha: float) -> dict:
    n_cells = len(table.principals) * len(table.axes)
    res = paired_max_test(table, zero_base(table), n_permutations=n_perm, seed=seed,
                          alpha=alpha, top=n_cells)
    return _max_digest(res, "pair", len(table.axes), alpha)


def sharp_median(table: BehaviorTable, n_perm: int, seed: int, alpha: float) -> dict:
    n_cells = len(table.principals) * len(table.axes)
    res = reference_free_max_test(table, n_permutations=n_perm, seed=seed, alpha=alpha,
                                  top=n_cells)
    return _max_digest(res, "median", len(table.axes), alpha)


def mean_t_grid(table: BehaviorTable) -> np.ndarray:
    """The one-vs-mean-of-rest t grid that ``sharp_mean`` maximizes."""
    p_t, _, _ = cell_rates(table)
    p_z, _, _ = cell_rates(zero_base(table))
    return standardized_excess(excess_effect(p_t, p_z))[0]


def median_peaks(table: BehaviorTable) -> np.ndarray:
    """Each candidate's largest |t| of the one-vs-median-of-rest contrast."""
    rates, _, _ = cell_rates(table)
    t, _, _ = standardized_excess(reference_free_effect(rates))
    return candidate_peaks(t)


# ---------------------------------------------------------------- Grubbs reading
_GRUBBS_NULL: dict[int, np.ndarray] = {}


def grubbs_g(x: np.ndarray) -> float:
    return float((np.max(x) - np.mean(x)) / np.std(x, ddof=1))


def grubbs_null(k: int, seed: int) -> np.ndarray:
    """G of k independent standard normals, the exact location-scale-free null."""
    if k not in _GRUBBS_NULL:
        rng = np.random.default_rng(np.random.SeedSequence([seed, k]))
        z = rng.standard_normal((GRUBBS_DRAWS, k))
        g = (z.max(axis=1) - z.mean(axis=1)) / z.std(axis=1, ddof=1)
        _GRUBBS_NULL[k] = np.sort(g)
    return _GRUBBS_NULL[k]


def grubbs_reading(peaks: np.ndarray, candidates: list[str], seed: int,
                   target: str | None) -> dict:
    """Grubbs's test on the candidates' peaks, and the deleted-residual t for each.

    ``G = (max - mean) / sd`` over all k peaks. Its exact null under independent
    normal peaks is location and scale free and is drawn here by Monte Carlo; the
    Bonferroni bound ``k * P(T_{k-2} > t_G)`` is reported beside it. The deleted
    residual of candidate c is ``(x_c - m_{-c}) / (s_{-c} sqrt(1 + 1/(k-1)))``,
    which follows t with k - 2 degrees of freedom under a normal random-effects
    null; it is the test for a pre-registered target. The rank p is the target's
    rank among the k peaks over k, the floor any exchangeability test inherits.
    """
    k = int(peaks.size)
    out: dict = {"k": k, "computable": False}
    if k < 3 or not np.all(np.isfinite(peaks)):
        out["reason"] = ("fewer than three candidates" if k < 3 else
                         "a peak is infinite (an effect held on every instruction)")
        return out
    if np.std(peaks, ddof=1) == 0:
        out["reason"] = "all peaks are equal"
        return out
    g = grubbs_g(peaks)
    null = grubbs_null(k, seed)
    p_mc = (1.0 + float(np.sum(null >= g))) / (1.0 + null.size)
    t_g2 = k * (k - 2) * g * g / max((k - 1) ** 2 - k * g * g, 1e-300)
    t_g = math.sqrt(t_g2) if t_g2 > 0 else 0.0
    p_bound = min(1.0, k * float(stats.t.sf(t_g, k - 2)))
    deleted = {}
    for c in range(k):
        rest = np.delete(peaks, c)
        s = float(np.std(rest, ddof=1))
        if s == 0:
            t_c = math.inf if peaks[c] > rest.mean() else -math.inf
        else:
            t_c = float((peaks[c] - rest.mean()) / (s * math.sqrt(1 + 1 / (k - 1))))
        deleted[candidates[c]] = {"t": t_c, "p_one_sided": float(stats.t.sf(t_c, k - 2))}
    lead = int(np.argmax(peaks))
    out.update({"computable": True, "G": g, "p_grubbs_exact_mc": p_mc,
                "p_grubbs_bonferroni": p_bound, "grubbs_draws": GRUBBS_DRAWS,
                "leader": candidates[lead], "deleted_residual": deleted,
                "leader_deleted_t": deleted[candidates[lead]]["t"],
                "leader_deleted_p_uncorrected": deleted[candidates[lead]]["p_one_sided"]})
    if target is not None and target in candidates:
        c = candidates.index(target)
        rank = 1 + int(np.sum(peaks > peaks[c]))
        out["target"] = {"candidate": target, "peak": float(peaks[c]), "rank": rank,
                         "p_rank": rank / k, "deleted_t": deleted[target]["t"],
                         "p_deleted_t": deleted[target]["p_one_sided"]}
    return out


def loo_permutation(table: BehaviorTable, n_perm: int, seed: int) -> dict:
    """Each candidate's leave-one-out detachment against its own shuffled values.

    The shuffled worlds are those of ``candidate_detachment_test`` at the same
    seed: one ``permute_within_instructions`` draw per permutation and nothing
    else from the generator. Candidate c's p is the share of shuffles in which the
    candidate holding c's label detaches at least as far as c does.
    """
    rates, candidates, _ = cell_rates(table)
    d = reference_free_effect(rates)
    t_obs, _, _ = standardized_excess(d)
    obs = np.array(_leave_one_out(candidate_peaks(t_obs)), dtype=float)
    rng = np.random.default_rng(seed)
    null = np.empty((n_perm, len(candidates)))
    for b in range(n_perm):
        t_null, _, _ = standardized_excess(permute_within_instructions(d, rng))
        null[b] = _leave_one_out(candidate_peaks(t_null))
    out = {}
    for c, name in enumerate(candidates):
        col = null[:, c]
        out[name] = {"loo_detachment": float(obs[c]),
                     "p": permutation_tail_share(col, float(obs[c]), n_perm)}
    return out


def detachment(table: BehaviorTable, n_perm: int, seed: int, alpha: float,
               target: str | None = None, with_loo: bool = True) -> dict:
    k = len(table.principals)
    if k < 3:
        return {"applies": False, "reason": "detachment needs at least three candidates"}
    res = candidate_detachment_test(table, n_permutations=n_perm, seed=seed, alpha=alpha)
    p = float(res["p_family_wise"])
    peaks = np.array([res["peaks"][c] for c in res["candidates"]], dtype=float)
    out = {"applies": True, "statistic": float(res["statistic"]),
           "p": p, "reject": p <= alpha, "leader": res["leading"],
           "named": res["leading"] if p <= alpha else None,
           "leading_peak": _f(res["leading_peak"]), "bulk_median_peak": _f(
               res["bulk_median_peak"]),
           "peaks": res["peaks"], "leave_one_out": res["leave_one_out"],
           "null_mean": _f(res["null_mean"]), "null_p95": _f(res["null_p95"]),
           "n_instructions": int(res["n_instructions"]), "n_axes": int(res["n_axes"]),
           "grubbs": grubbs_reading(peaks, list(res["candidates"]), seed, target)}
    if with_loo:
        out["loo_permutation"] = loo_permutation(table, n_perm, seed)
    return out


def coherence(table: BehaviorTable, n_perm: int, seed: int, alpha: float) -> dict:
    if len(table.principals) < 3:
        return {"applies": False, "reason": "coherence detachment needs three candidates"}
    res = axis_coherence_test(table, n_permutations=n_perm, seed=seed, alpha=alpha)
    p = float(res["p_detachment"])
    return {"applies": True, "statistic": _f(res["detachment_statistic"]),
            "p": p, "reject": p <= alpha, "leader": res["leading"],
            "named": res["leading"] if p <= alpha else None,
            "runner_up": res["runner_up"], "R": res["R"], "k_chosen": res["k_chosen"],
            "max_statistic": _f(res["max_statistic"]), "p_max": float(res["p_max"]),
            "max_rejects": bool(res["p_max"] <= alpha), "k0": int(res["k0"]),
            "null_detach_p95": _f(res["null_detach_p95"]),
            "null_max_p95": _f(res["null_max_p95"]),
            "n_instructions": int(res["n_instructions"]), "n_axes": int(res["n_axes"])}


# ------------------------------------------------------------ context interaction
def context_effect(table: BehaviorTable, neutral: str) -> tuple[np.ndarray, list[str]]:
    """Instrumental-minus-neutral one-vs-median gaps, one row block per matched instruction.

    ``d`` is the one-vs-median-of-rest gap per cell. For each instruction suffix
    that the neutral framing and at least one instrumental framing share, the
    contrast is the mean gap over the instrumental framings minus the neutral gap.
    A candidate's stable name effect cancels inside its own contrast.
    """
    rates, _, _ = cell_rates(table)
    d = reference_free_effect(rates)
    blocks = list(table.blocks)
    by_suffix: dict[str, dict[str, int]] = {}
    for b, bid in enumerate(blocks):
        by_suffix.setdefault(suffix_of(bid), {})[framing_of(bid)] = b
    suffixes = sorted(s for s, fr in by_suffix.items()
                      if neutral in fr and len(fr) >= 2)
    n_c, _, n_j = d.shape
    delta = np.full((n_c, len(suffixes), n_j), np.nan)
    for i, s in enumerate(suffixes):
        fr = by_suffix[s]
        instr = [fr[f] for f in sorted(fr) if f != neutral]
        with np.errstate(invalid="ignore"):
            delta[:, i, :] = np.nanmean(d[:, instr, :], axis=1) - d[:, fr[neutral], :]
    return delta, suffixes


def context_interaction(table: BehaviorTable, n_perm: int, seed: int, alpha: float,
                        neutral: str = "none") -> dict:
    delta, suffixes = context_effect(table, neutral)
    if not suffixes:
        return {"applies": False, "reason": "no instruction appears under both contexts"}
    candidates = list(table.principals)
    t_obs, mean_obs, m_obs = standardized_excess(delta)
    s_obs = max_abs_statistic(t_obs, signed=False)
    rng = np.random.default_rng(seed)
    null = np.empty(n_perm)
    for b in range(n_perm):
        t_null, _, _ = standardized_excess(permute_within_instructions(delta, rng))
        null[b] = max_abs_statistic(t_null, signed=False)
    p = permutation_tail_share(null, s_obs, n_perm)
    flat = np.abs(t_obs)
    ci, cj = np.unravel_index(np.nanargmax(flat), flat.shape)
    peaks = candidate_peaks(t_obs)
    return {"applies": True, "statistic": float(s_obs),
            "p": p, "reject": p <= alpha,
            "leader": candidates[int(ci)], "leader_axis": table.axes[int(cj)],
            "leader_t": float(t_obs[ci, cj]), "leader_mean_contrast": float(mean_obs[ci, cj]),
            "named": candidates[int(ci)] if p <= alpha else None,
            "peaks": {c: float(peaks[i]) for i, c in enumerate(candidates)},
            "n_matched_instructions": len(suffixes), "neutral": neutral,
            "null_mean": float(null[np.isfinite(null)].mean()),
            "null_p95": float(np.quantile(null, 0.95))}
