"""The family's readings: how often each grid fires, by kind of subject, and what it names.

A grid "fires" on a reading when that reading leaves the label-shuffle null:

- ``sigma_<estimator>``: sigma0 at or above all but alpha of the permuted grids'
  sigma0 (p_sigma0 <= alpha).
- ``lambda``: the median |t| at or above all but alpha of the permuted grids'
  (p_lambda <= alpha). It is read on the mean, base-referenced and placebo grids
  only. On the median grid the median |t| sits on an atom of |t| for many
  subjects, so the lift there is reported and not read.
- ``flags_<estimator>``: at least one cell with local fdr below 0.2 under a fit
  that meets the bulk condition.

These are descriptive. None of them tests a candidate. The candidate the cell
flags concentrate on (the plurality) is compared with the registered candidate
(named by rule, or the argmax where no candidate is named) on every subject
whose registered test rejects.

Two subjects whose base-referenced grids swap target and base share one grid
with its sign flipped; the second of them is a mirror and is counted once.
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np
from scipy import stats

__all__ = ["readings", "subject_class", "mirrors", "ESTIMATORS", "READINGS"]

ESTIMATORS = ("loc", "mle", "cm")
READINGS = ("sigma_loc", "sigma_mle", "sigma_cm", "lambda", "flags_loc", "flags_mle", "flags_cm")


def subject_class(key: str, s: dict, registered: dict, alpha: float) -> str:
    if s["role"] == "base":
        return "base_as_target"
    if s["role"] in ("control", "null"):
        return "null"
    if s["drop"]:
        return "target_without_documented"
    reg = registered.get(key)
    return "registered_positive" if reg and reg["p"] <= alpha else "registered_negative"


def mirrors(meta: dict) -> dict:
    """{mirror subject: subject it mirrors} for base-referenced grids that swap target and base."""
    seen, out = {}, {}
    for key in sorted(meta):
        s = meta[key]
        if not s["base"]:
            continue
        pair = (s["target"], s["base"], tuple(s["drop"]))
        flip = (s["base"], s["target"], tuple(s["drop"]))
        if flip in seen:
            out[key] = seen[flip]
        seen[pair] = key
    return out


def _fires(v: dict, grid: str, alpha: float) -> dict:
    perm = v["permutation"]
    out = {f"sigma_{e}": bool(perm[e]["p_sigma0"] is not None and perm[e]["p_sigma0"] <= alpha)
           for e in ESTIMATORS}
    out["lambda"] = None if grid == "median" else bool(v["p_lambda"] <= alpha)
    for e in ESTIMATORS:
        out[f"flags_{e}"] = v["cells"][f"n_flag_{e}_supported"] > 0
    return out


def _ratio(a, b):
    return float(a / b) if a is not None and b is not None and np.isfinite(a) and np.isfinite(b) and b else None


def _spread(v: list) -> dict:
    return {"n": len(v), "median": float(np.median(v)) if v else None,
            "min": float(np.min(v)) if v else None, "max": float(np.max(v)) if v else None}


def _cp(k: int, n: int) -> dict:
    if n == 0:
        return {"k": 0, "n": 0}
    ci = stats.binomtest(k, n).proportion_ci(confidence_level=0.95, method="exact")
    return {"k": k, "n": n, "share": k / n, "lo": float(ci.low), "hi": float(ci.high)}


def _ks(p: list) -> dict:
    p = [x for x in p if x is not None]
    if len(p) < 3:
        return {"n": len(p)}
    r = stats.kstest(p, "uniform")
    return {"n": len(p), "statistic": float(r.statistic), "p": float(r.pvalue),
            "median": float(np.median(p)), "share_below_0.05": float(np.mean(np.array(p) <= 0.05))}


def _placebo_summary(records: list[dict], meta: dict, alpha: float) -> dict:
    groups = {"base": [], "other": []}
    for r in records:
        if r["grid"] == "placebo":
            groups["base" if meta[r["subject"]]["role"] == "base" else "other"].append(r)
    groups["all"] = groups["base"] + groups["other"]
    out = {}
    for name, rs in groups.items():
        fires = [_fires(r["variants"]["all"], "placebo", alpha) for r in rs]
        out[name] = {
            "n_grids": len(rs), "n_subjects": len({r["subject"] for r in rs}),
            "fires": {k: _cp(sum(bool(f[k]) for f in fires), len(fires)) for k in READINGS},
            "max_fires": _cp(sum(r["p_S"] <= alpha for r in rs), len(rs)),
            "ks_uniform": {
                **{f"p_sigma0_{e}": _ks([r["variants"]["all"]["permutation"][e]["p_sigma0"] for r in rs])
                   for e in ESTIMATORS},
                "p_lambda": _ks([r["variants"]["all"]["p_lambda"] for r in rs]),
                "p_S": _ks([r["p_S"] for r in rs])},
            "tau_pp": _spread([r["variants"]["all"]["tau"]["tau_pp"] for r in rs]),
            "subjects_firing": {k: sorted({r["subject"] for r, f in zip(rs, fires) if f[k]})
                                for k in READINGS}}
    return out


def readings(records: list[dict], meta: dict, registered: dict, ua: dict, alpha: float) -> dict:
    mirror = mirrors(meta)
    by = {(r["subject"], r["grid"]): r for r in records if r["grid"] != "placebo"}
    counts: dict = defaultdict(lambda: defaultdict(lambda: {"n": 0, **{k: 0 for k in READINGS},
                                                            "subjects_firing": defaultdict(list)}))
    per_subject = {}
    for (key, grid), r in sorted(by.items()):
        s = meta[key]
        cls = subject_class(key, s, registered, alpha)
        v = r["variants"]["all"]
        f = _fires(v, grid, alpha)
        is_mirror = grid == "registered" and key in mirror
        if not is_mirror:
            c = counts[cls][grid]
            c["n"] += 1
            for k, x in f.items():
                c[k] += int(bool(x))
                if x:
                    c["subjects_firing"][k].append(key)
        per_subject.setdefault(key, {})[grid] = {
            "class": cls, "fires": f, "mirror_of": mirror.get(key) if grid == "registered" else None,
            "sigma0": {e: v["fit"][e]["sigma0"] for e in ESTIMATORS},
            "p0": {e: v["fit"][e]["p0"] for e in ESTIMATORS},
            "bulk_ok": {e: v["fit"][e]["bulk_ok"] for e in ESTIMATORS},
            "sigma0_null_median": {e: v["permutation"][e]["sigma0"].get("median") for e in ESTIMATORS},
            "lambda": v["lambda"], "p_lambda": v["p_lambda"], "tau_pp": v["tau"]["tau_pp"],
            **{f"plurality_{e}": v["cells"][f"plurality_{e}_supported"] for e in ESTIMATORS},
            **{f"plurality_{e}_any_fit": v["cells"][f"plurality_{e}"] for e in ESTIMATORS},
            **{f"n_flag_{e}": v["cells"][f"n_flag_{e}_supported"] for e in ESTIMATORS},
            **{f"n_flag_{e}_any_fit": v["cells"][f"n_flag_{e}"] for e in ESTIMATORS}}
    agreement = {}
    for key, grids in per_subject.items():
        reg = registered.get(key)
        if not (reg and reg["p"] <= alpha) or grids.get("median", {}).get("class") != "registered_positive":
            continue
        who = reg.get("named") or reg.get("argmax")
        agreement[key] = {"registered_candidate": who, "named_by_rule": bool(reg.get("named")),
                          "registered_p": reg["p"]}
        for grid, g in grids.items():
            agreement[key][grid] = {
                **{f"plurality_{e}": g[f"plurality_{e}"] for e in ESTIMATORS},
                **{f"plurality_{e}_any_fit": g[f"plurality_{e}_any_fit"] for e in ESTIMATORS},
                **{f"bulk_ok_{e}": g["bulk_ok"][e] for e in ESTIMATORS},
                **{f"agrees_{e}": g[f"plurality_{e}"] == [who] for e in ESTIMATORS},
                **{f"agrees_{e}_any_fit": g[f"plurality_{e}_any_fit"] == [who] for e in ESTIMATORS}}
    shrink = {}
    for key, grids in per_subject.items():
        if "registered" not in grids:
            continue
        reg = grids["registered"]
        shrink[key] = {"mirror_of": reg["mirror_of"],
                       "tau": {"target_only": grids["median"]["tau_pp"], "registered": reg["tau_pp"],
                               "ratio_registered_to_target_only": _ratio(reg["tau_pp"], grids["median"]["tau_pp"])}}
        for e in ESTIMATORS:
            shrink[key][e] = {}
            reg_inf = _ratio(reg["sigma0"][e], reg["sigma0_null_median"][e])
            for g in ("median", "mean"):
                tgt_inf = _ratio(grids[g]["sigma0"][e], grids[g]["sigma0_null_median"][e])
                shrink[key][e][g] = {
                    "target_only": grids[g]["sigma0"][e], "registered": reg["sigma0"][e],
                    "target_only_over_null": tgt_inf, "registered_over_null": reg_inf,
                    "ratio_registered_to_target_only": _ratio(reg["sigma0"][e], grids[g]["sigma0"][e]),
                    "ratio_of_inflations": _ratio(reg_inf, tgt_inf)}
    shrink_summary = {"distinct_registered_grids": len([k for k, v in shrink.items() if not v["mirror_of"]]),
                      "subjects": len(shrink)}
    for e in ESTIMATORS:
        shrink_summary[e] = {}
        for g in ("median", "mean"):
            shrink_summary[e][g] = {
                m: _spread([x[e][g][m] for x in shrink.values() if x[e][g][m] is not None])
                for m in ("ratio_registered_to_target_only", "ratio_of_inflations")}
    shrink_summary["tau"] = _spread([x["tau"]["ratio_registered_to_target_only"] for x in shrink.values()
                                     if x["tau"]["ratio_registered_to_target_only"] is not None])
    plain = {cls: {g: {**{k: v for k, v in c.items() if k != "subjects_firing"},
                       "subjects_firing": dict(c["subjects_firing"])} for g, c in grids.items()}
             for cls, grids in counts.items()}
    ua_read = {k: {g: {"lambda": x["lambda"], "p_lambda": x["p_lambda"],
                       "p_lambda_without_tie_tolerance": x["p_lambda_without_tie_tolerance"],
                       "S": x["S"], "p_S": x["p_S"], "argmax_candidate": x["argmax_candidate"],
                       "median_abs_t": x["median_abs_t"], "perm_abs_median": x["perm_abs_median"],
                       "lambda_atoms": x["lambda_atoms"], "tau_pp": v["tau"]["tau_pp"],
                       "tau_axis_block": v["tau"]["axis_block"]} for g, x in v["grids"].items()}
               for k, v in ua["subjects"].items()}
    return {"alpha": alpha, "readings": list(READINGS), "mirrors": mirror, "counts": plain,
            "per_subject": per_subject, "agreement_on_registered_positives": agreement,
            "shrinkage": shrink, "shrinkage_summary": shrink_summary,
            "placebo": _placebo_summary(records, meta, alpha), "user_awareness": ua_read}
