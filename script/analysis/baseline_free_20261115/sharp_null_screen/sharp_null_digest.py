"""One record shape per statistic, with the naming rule applied wherever pairs exist.

``max_digest`` is partA's ``_digest``: the same fields for the registered test,
the mean variant (both from ``paired_max_test``) and the median variant (from
``reference_free_max_test``). The G test is an omnibus test and names nobody.
The coherence test names its leader through the naming rule, with the axes its
scan accumulated standing in for surviving pairs.
"""

from __future__ import annotations

import numpy as np

from src.compare.axis_coherence_statistic import K0, per_axis_robust_z
from src.compare.paired_excess_measures import standardized_excess
from src.compare.principal_attribution import attribute_principal
from src.conjecture.guaranteed_axis_registry import GUARANTEED_AXES

G_IDS = tuple(a[0] for a in GUARANTEED_AXES)


def _hist(surviving: list[dict]) -> dict:
    hist: dict[str, set] = {}
    for p in surviving:
        hist.setdefault(p["candidate"], set()).add(p["axis_id"])
    return {c: len(a) for c, a in sorted(hist.items())}


def max_digest(res: dict, kind: str, n_axes: int, alpha: float) -> dict:
    pairs = res["top_pairs"]
    if kind == "pair":
        loyal, surviving = bool(res["loyal"]), res["surviving_pairs"]
        att = attribute_principal(res)
        shift_key = "mean_excess"
    else:
        loyal = bool(res["p_family_wise"] <= alpha)
        surviving = [{"candidate": p["candidate"], "axis_id": p["axis_id"]}
                     for p in pairs if p["p_adjusted"] <= alpha]
        argmax = pairs[0]["candidate"] if pairs else None
        att = attribute_principal({"loyal": loyal, "surviving_pairs": surviving,
                                   "principal": argmax if loyal else None, "n_axes": n_axes})
        shift_key = "mean_shift"
    top = pairs[0] if pairs else {}
    g_best: dict = {}
    for p in pairs:
        if p["axis_id"] in G_IDS:
            cur = g_best.get(p["axis_id"])
            if cur is None or abs(p["t"]) > abs(cur["t"]):
                g_best[p["axis_id"]] = {"candidate": p["candidate"], "axis_id": p["axis_id"],
                                        "t": p["t"], "shift": p[shift_key],
                                        "p_adjusted": p["p_adjusted"]}
    return {
        "S": float(res["statistic"]), "p": float(res["p_family_wise"]),
        "reject_0.01": loyal, "reject_0.05": bool(res["p_family_wise"] <= 0.05),
        "argmax_candidate": top.get("candidate"), "argmax_axis": top.get("axis_id"),
        "argmax_t": top.get("t"), "named_by_rule": att["named"],
        "naming_reason": att.get("reason", ""), "surviving_axes_by_candidate": _hist(surviving),
        "n_surviving_pairs": len(surviving), "n_axes": int(res["n_axes"]),
        "n_instructions": int(res["n_instructions"]), "candidates": list(res["candidates"]),
        "null_mean": float(res["null_mean"]), "null_p95": float(res["null_p95"]),
        "guaranteed_axis_best_pairs": [g_best[a] for a in G_IDS if a in g_best],
        "top_pairs": pairs[:12],
    }


def g_digest(res: dict, candidates: list[str], n_axes: int, alpha: float) -> dict:
    return {"S": float(res["g_statistic"]), "p": float(res["p_permutation"]),
            "reject_0.01": bool(res["p_permutation"] <= alpha),
            "reject_0.05": bool(res["p_permutation"] <= 0.05),
            "df": int(res["df"]), "p_chi2": float(res["p_chi2"]),
            "null_mean": float(res["g_null_mean"]), "null_p95": float(res["g_null_p95"]),
            "n_permutations": int(res["n_permutations"]), "candidates": candidates,
            "n_axes": n_axes, "argmax_candidate": None, "named_by_rule": None,
            "naming_reason": "omnibus test: names no candidate"}


def _scan_axes(d: np.ndarray, lead: int, k: int, axes: list[str]) -> list[str]:
    """The k axes the leader's R accumulated, re-derived as ``coherence_of_effect`` does."""
    t, _, _ = standardized_excess(d)
    finite = t[np.isfinite(t)]
    cap = float(np.max(np.abs(finite))) if finite.size else 1.0
    t = np.clip(np.nan_to_num(t, nan=np.nan, posinf=cap, neginf=-cap), -cap, cap)
    z = per_axis_robust_z(t)[lead]
    best, pick = -np.inf, []
    for sign in (1.0, -1.0):
        order = np.argsort(-(sign * z), kind="stable")[:k]
        value = float(np.sum(sign * z[order]) / np.sqrt(k))
        if value > best:
            best, pick = value, [axes[j] for j in order]
    return pick


def coherence_digest(res: dict, d: np.ndarray, axes: list[str], alpha: float) -> dict:
    lead = res["leading"]
    li = res["candidates"].index(lead)
    k = int(res["k_chosen"][lead])
    scanned = _scan_axes(d, li, k, axes)
    loyal = bool(res["p_max"] <= alpha)
    att = attribute_principal({"loyal": loyal, "principal": lead if loyal else None,
                               "n_axes": len(axes),
                               "surviving_pairs": [{"candidate": lead, "axis_id": a}
                                                   for a in scanned] if loyal else []})
    return {"S": float(res["max_statistic"]), "p": float(res["p_max"]),
            "reject_0.01": loyal, "reject_0.05": bool(res["p_max"] <= 0.05),
            "detachment_S": float(res["detachment_statistic"]),
            "detachment_p": float(res["p_detachment"]),
            "detachment_reject_0.01": bool(res["p_detachment"] <= alpha),
            "argmax_candidate": lead, "runner_up": res["runner_up"], "k_scanned": k,
            "scanned_axes": scanned, "named_by_rule": att["named"],
            "naming_reason": att.get("reason", "") or
            "rule applied with the leader's scanned axes as its surviving axes",
            "R": res["R"], "k_chosen": res["k_chosen"], "candidates": res["candidates"],
            "n_axes": int(res["n_axes"]), "n_instructions": int(res["n_instructions"]),
            "null_mean": None, "null_p95": float(res["null_max_p95"]),
            "null_detach_p95": float(res["null_detach_p95"]), "k0": K0}


def loser_digest(res: dict, n_axes: int, alpha: float) -> dict:
    out = {"candidates": res["candidates"], "n_axes": n_axes,
           "n_instructions": int(res["n_instructions"]), "roster_flag": res["roster_flag"],
           "registered_S_recomputed": res["registered_S_recomputed"],
           "registered_p_recomputed": res["registered_p_recomputed"]}
    for mode in ("infinite", "exclude"):
        v = res[mode]
        out[mode] = {k: v.get(k) for k in (
            "computable", "Z", "p", "Z_signed", "p_signed", "loyal", "named", "top_pair",
            "n_pairs_scored", "n_infinite_observed", "share_null_max_infinite",
            "null_q95", "null_q99", "n_pairs_rejected")}
        out[mode]["naming_reason"] = (v.get("attribution") or {}).get("reason", "")
        out[mode]["surviving_axes_by_candidate"] = _hist(v.get("surviving_pairs") or [])
    inf = out["infinite"]
    out.update({"S": inf["Z"], "p": inf["p"], "reject_0.01": bool(inf["loyal"]),
                "reject_0.05": bool(inf["p"] is not None and inf["p"] <= 0.05),
                "argmax_candidate": (inf["top_pair"] or {}).get("candidate"),
                "named_by_rule": inf["named"], "naming_reason": inf["naming_reason"]})
    return out
