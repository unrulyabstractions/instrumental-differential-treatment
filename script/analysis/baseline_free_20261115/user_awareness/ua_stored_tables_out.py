"""CSV rows for the stored part: the three-subject panel and the per-detector summary.

Each summary row is one detector on one subject: statistic, p, the candidate it
names, and the registered (baseline) result, which is absent for every served
model because none has a base model.
"""

from __future__ import annotations

import csv
from pathlib import Path

ALPHA = 0.01
NO_BASE = "none (served model, no base)"


def write_csv(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def _r(v, nd=4):
    return None if v is None else round(float(v), nd)


def panel_rows(runs: dict, keys: list[str], groups: dict) -> list[dict]:
    rows = []
    for subj, run in runs.items():
        tr, l01 = run["transluce"], run["level01"]
        loo = {**tr["predictive_t_safety_vs_general"], **tr["predictive_t_controls_vs_general"]}
        plc = tr["placebo_general_as_target"]["per_identity"]
        for k in keys:
            t = loo.get(k) or plc.get(k)
            rows.append({
                "subject": run["subject"], "identity": k, "group": groups[k],
                "mean_grade": _r(run["mean_grade"][k], 3),
                "blocked_mean": _r(tr["blocked_mean"][k]),
                "noise_se": _r(tr["noise_var_blocked_mean"][k] ** 0.5),
                "peak_abs_t": _r(l01["peaks"][k], 3),
                "predictive_t": _r(t["t"], 3) if t else None,
                "predictive_t_df": t["df"] if t else None,
                "predictive_t_reference": ("6 general" if k in loo else "other 5 general"),
                "predictive_p_one_sided_harsher": _r(t["p_one_sided_harsher"]) if t else None,
            })
    return rows


def summary_rows(runs: dict) -> list[dict]:
    rows = []

    def add(run, level, det, stat, p, named, note=""):
        rows.append({"subject": run["subject"], "level": level, "detector": det,
                     "statistic": _r(stat), "p": _r(p), "alpha": ALPHA,
                     "rejects": None if p is None else bool(p <= ALPHA),
                     "named": named, "registered_result": NO_BASE, "note": note})

    for run in runs.values():
        l01, tr = run["level01"], run["transluce"]
        s = l01["sharp_null_screen"]
        add(run, "0", "sharp-null screen (max |t|, median of others)", s["statistic"],
            s["p_family_wise"], s["named"], f"axis {s['named_axis']}")
        d = l01["detachment"]
        add(run, "1", "detachment (median/MAD of peaks)", d["statistic"], d["p_family_wise"],
            d["named"], f"leading {d['leading']}")
        g = l01["grubbs_on_peaks"]
        if "G" in g:
            add(run, "1", "Grubbs on peaks, exact normal null", g["G"], g["p_exact_normal_mc"],
                g["named"], f"leading {g['leading']}; permutation p {_r(g['p_permutation'])}")
        for side, key in (("two-sided", "grubbs_on_blocked_mean_grade_two_sided"),
                          ("harsher side", "grubbs_on_blocked_mean_grade_harsher_side")):
            g = l01[key]
            add(run, "1", f"Grubbs on mean grade, {side}", g["G"], g["p_exact_normal_mc"],
                g["named"], f"leading {g['leading']}")
        for k, v in l01["preregistered_deleted_residual"].items():
            m = v["mean_grade_vs_other_9"]
            add(run, "1", f"pre-registered deleted residual t, mean grade, {k}", m["t"],
                m["p_bh_within_subject"], k if m["reject_at_alpha"] else None,
                f"raw p {_r(m['p_one_sided'])}; df {m['df']}; BH over 3")
        for k, v in tr["predictive_t_safety_vs_general"].items():
            add(run, "1 (Transluce)", f"predictive t vs 6 general, {k}", v["t"],
                v["p_bh_within_subject"], k if v["reject_at_alpha"] else None,
                f"raw p {_r(v['p_one_sided_harsher'])}; df {v['df']}; BH over 3")
        w = tr["whole_user_permutation_safety_vs_general"]
        add(run, "1 (Transluce)", "whole-user permutation, safety vs general",
            w["gap_target_minus_pool"], w["p_one_sided_harsher"],
            "safety group" if w["reject_at_alpha"] else None,
            f"{w['n_relabellings']} relabellings; floor {_r(w['floor'])}")
        for scope in ("all_identities", "general_only"):
            h = tr[f"heterogeneity_{scope}"]
            add(run, "0 (Transluce)", f"noise-corrected heterogeneity, {scope.replace('_', ' ')}",
                h["Q"], h["p_parametric_bootstrap"], None,
                f"df {h['df']}; chi2 p {_r(h['p_chi2'])}; tau {_r(h['tau_DL'])}")
    return rows
