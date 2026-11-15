"""The family's readings: how often each grid fires, by kind of subject, and what it names.

A grid "fires" on a reading when that reading leaves the label-shuffle null:

- ``sigma_<estimator>``: sigma0 at or above all but alpha of the permuted grids'
  sigma0 (p_sigma0 <= alpha).
- ``lambda``: the median |t| at or above all but alpha of the permuted grids'
  (p_lambda <= alpha).
- ``flags_<estimator>``: at least one cell with local fdr below 0.2.

These are descriptive. None of them tests a candidate. The candidate the cell
flags concentrate on (the plurality) is compared with the registered named
candidate on the subjects where the registered test rejects and names one.
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np

__all__ = ["readings", "subject_class"]

READINGS = ("sigma_cm", "sigma_mle", "sigma_loc", "lambda", "flags_cm", "flags_mle")


def subject_class(key: str, s: dict, registered: dict, alpha: float) -> str:
    if s["role"] == "base":
        return "base_as_target"
    if s["role"] in ("control", "null"):
        return "null"
    if s["drop"]:
        return "target_without_documented"
    reg = registered.get(key)
    return "registered_positive" if reg and reg["p"] <= alpha else "registered_negative"


def _fires(v: dict, alpha: float) -> dict:
    perm = v["permutation"]
    out = {f"sigma_{e}": bool(perm[e]["p_sigma0"] is not None and perm[e]["p_sigma0"] <= alpha)
           for e in ("cm", "mle", "loc")}
    out["lambda"] = bool(v["p_lambda"] <= alpha)
    out["flags_cm"] = v["cells"]["n_flag_cm"] > 0
    out["flags_mle"] = v["cells"]["n_flag_mle"] > 0
    return out


def _ratio(a, b):
    return float(a / b) if a is not None and b is not None and np.isfinite(a) and np.isfinite(b) and b else None


def _inflation(g: dict, e: str):
    """sigma0 over the median sigma0 of the same estimator on the permuted grids."""
    return _ratio(g["sigma0"][e], g["sigma0_null_median"][e])


def _spread(v: list) -> dict:
    return {"n": len(v), "median": float(np.median(v)) if v else None,
            "min": float(np.min(v)) if v else None, "max": float(np.max(v)) if v else None}


def readings(records: list[dict], meta: dict, registered: dict, ua: dict, alpha: float) -> dict:
    by = {(r["subject"], r["grid"]): r for r in records}
    counts: dict = defaultdict(lambda: defaultdict(lambda: {"n": 0, **{k: 0 for k in READINGS},
                                                            "subjects_firing": defaultdict(list)}))
    per_subject = {}
    for (key, grid), r in sorted(by.items()):
        s = meta[key]
        cls = "placebo" if grid == "placebo" else subject_class(key, s, registered, alpha)
        v = r["variants"]["all"]
        f = _fires(v, alpha)
        c = counts[cls][grid]
        c["n"] += 1
        for k, x in f.items():
            c[k] += int(x)
            if x:
                c["subjects_firing"][k].append(key)
        per_subject.setdefault(key, {})[grid] = {
            "class": cls, "fires": f, "sigma0": {e: v["fit"][e]["sigma0"] for e in ("cm", "mle", "loc")},
            "sigma0_null_median": {e: v["permutation"][e]["sigma0"].get("median") for e in ("cm", "mle", "loc")},
            "lambda": v["lambda"], "plurality_mle": v["cells"]["plurality_mle"],
            "plurality_cm": v["cells"]["plurality_cm"], "n_flag_mle": v["cells"]["n_flag_mle"],
            "n_flag_cm": v["cells"]["n_flag_cm"]}
    agreement = {}
    for key, grids in per_subject.items():
        reg = registered.get(key)
        if not (reg and reg["p"] <= alpha and reg.get("named")):
            continue
        agreement[key] = {"registered_named": reg["named"], "registered_p": reg["p"]}
        for grid, g in grids.items():
            if grid == "placebo":
                continue
            agreement[key][grid] = {"plurality_mle": g["plurality_mle"], "plurality_cm": g["plurality_cm"],
                                    "agrees_mle": g["plurality_mle"] == [reg["named"]],
                                    "agrees_cm": g["plurality_cm"] == [reg["named"]]}
    shrink = {}
    for key, grids in per_subject.items():
        if "registered" not in grids:
            continue
        shrink[key] = {}
        for e in ("cm", "mle", "loc"):
            shrink[key][e] = {}
            reg = grids["registered"]
            reg_inf = _inflation(reg, e)
            for g in ("median", "mean"):
                tgt_inf = _inflation(grids[g], e)
                shrink[key][e][g] = {
                    "target_only": grids[g]["sigma0"][e], "registered": reg["sigma0"][e],
                    "target_only_over_null": tgt_inf, "registered_over_null": reg_inf,
                    "ratio_registered_to_target_only": _ratio(reg["sigma0"][e], grids[g]["sigma0"][e]),
                    "ratio_of_inflations": _ratio(reg_inf, tgt_inf)}
    shrink_summary = {}
    for e in ("cm", "mle", "loc"):
        shrink_summary[e] = {}
        for g in ("median", "mean"):
            shrink_summary[e][g] = {
                m: _spread([x[e][g][m] for x in shrink.values() if x[e][g][m] is not None])
                for m in ("ratio_registered_to_target_only", "ratio_of_inflations")}
    plain = {cls: {g: {**{k: v for k, v in c.items() if k != "subjects_firing"},
                       "subjects_firing": dict(c["subjects_firing"])} for g, c in grids.items()}
             for cls, grids in counts.items()}
    ua_read = {k: {g: {"lambda": x["lambda"], "p_lambda": x["p_lambda"], "S": x["S"], "p_S": x["p_S"],
                       "argmax_candidate": x["argmax_candidate"], "median_abs_t": x["median_abs_t"],
                       "perm_abs_median": x["perm_abs_median"]} for g, x in v["grids"].items()}
               for k, v in ua["subjects"].items()}
    return {"alpha": alpha, "readings": list(READINGS), "counts": plain, "per_subject": per_subject,
            "agreement_on_registered_positives": agreement, "shrinkage": shrink,
            "shrinkage_summary": shrink_summary, "user_awareness": ua_read}
