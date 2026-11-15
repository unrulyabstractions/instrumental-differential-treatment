"""Markdown tables of the empirical-null README, each read out of efron.json or estimator_check.json."""

from __future__ import annotations

import math

__all__ = ["ORDER_ROLE", "table", "fit_table", "interval_table", "registered_table", "placebo_table",
           "documented_table", "roster_drop_table", "counts_table", "agreement_table", "checks_table",
           "ua_table", "recovery_table", "interval_check_table", "shrink_table"]


def f(x, nd=2) -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "n/a"
    if isinstance(x, float):
        return f"{x:.{nd}f}"
    return str(x)


def p(x) -> str:
    return "n/a" if x is None else (f"{x:.4f}" if x >= 0.0001 else f"{x:.1e}")


def ci(block: dict, nd=2) -> str:
    return f"[{f(block.get('lo'), nd)}, {f(block.get('hi'), nd)}]" if block.get("n") else "n/a"


def table(head: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


ORDER_ROLE = {"positive": 0, "calibration": 1, "challenge": 2, "control": 3, "null": 4, "base": 5}


def _sorted(records, meta, grid):
    rs = [r for r in records if r["grid"] == grid]
    return sorted(rs, key=lambda r: (ORDER_ROLE[meta[r["subject"]]["role"]], meta[r["subject"]]["roster"],
                                     r["subject"]))


def fit_table(records, meta, grid) -> str:
    rows = []
    for r in _sorted(records, meta, grid):
        v = r["variants"]["all"]
        fit, perm, axb = v["fit"], v["permutation"], v["bootstrap_axes"]
        rows.append([r["subject"], meta[r["subject"]]["role"], f"{r['n_candidates']} x {r['n_axes']}",
                     str(fit["n_fitted"]),
                     f(fit["cm"]["delta0"]), f(fit["cm"]["sigma0"]), ci(axb["cm"]["sigma0"]),
                     f(perm["cm"]["sigma0"].get("median")), p(perm["cm"]["p_sigma0"]),
                     f(fit["mle"]["delta0"]), f(fit["mle"]["sigma0"]), ci(axb["mle"]["sigma0"]),
                     f(perm["mle"]["sigma0"].get("median")), p(perm["mle"]["p_sigma0"]),
                     f(fit["loc"]["sigma0"]),
                     f(v["lambda"]), ci(axb["lambda"]), p(v["p_lambda"]),
                     str(v["cells"]["n_flag_mle"]), ",".join(v["cells"]["plurality_mle"]) or "none"])
    return table(["subject", "role", "k x A", "cells fitted", "CM delta0", "CM sigma0", "CM 95% axis-block",
                  "CM null median", "CM p", "MLE delta0", "MLE sigma0", "MLE 95% axis-block",
                  "MLE null median", "MLE p", "locfdr-window MLE sigma0", "lambda", "lambda 95% axis-block",
                  "lambda p", "cells fdr < 0.2 (MLE)", "flag plurality (MLE)"], rows)


def interval_table(records, meta, grid) -> str:
    rows = []
    for r in _sorted(records, meta, grid):
        v = r["variants"]["all"]
        jk, ib = v["jackknife_instructions"], v["bootstrap_instructions"]
        rows.append([r["subject"], f(jk["cm"]["sigma0"]["se"]), f(jk["mle"]["sigma0"]["se"]),
                     f(jk["loc"]["sigma0"]["se"]), f(jk["lambda"]["se"]),
                     ci(ib["cm"]["sigma0_noise_removed"]), ci(ib["mle"]["sigma0_noise_removed"]),
                     ci(ib["lambda_noise_removed"]), f(ib["added_noise_var_u"].get("median"))])
    return table(["subject", "CM jackknife se", "MLE jackknife se", "locfdr-window jackknife se",
                  "lambda jackknife se", "CM instruction bootstrap", "MLE instruction bootstrap",
                  "lambda instruction bootstrap", "added noise variance"], rows)


def registered_table(records, meta, registered, read) -> str:
    """Base-referenced fits beside the target-only ones, each also over its own null median."""
    by = {(r["subject"], r["grid"]): r for r in records}
    rows = []
    for r in _sorted(records, meta, "registered"):
        k = r["subject"]
        reg = registered.get(k, {})
        med = by.get((k, "median"))
        sh = read["shrinkage"].get(k, {})
        v = r["variants"]["all"]
        loc = sh.get("loc", {}).get("median", {})
        mle = sh.get("mle", {}).get("median", {})
        rows.append([k, meta[k]["base_label"], f(reg.get("S")), p(reg.get("p")), str(reg.get("named") or "none"),
                     f(med["variants"]["all"]["fit"]["mle"]["sigma0"]) if med else "n/a",
                     f(v["fit"]["cm"]["sigma0"]), f(v["fit"]["mle"]["sigma0"]),
                     f(v["permutation"]["mle"]["sigma0"].get("median")), p(v["permutation"]["mle"]["p_sigma0"]),
                     f(mle.get("target_only_over_null")), f(mle.get("registered_over_null")),
                     f(loc.get("target_only_over_null")), f(loc.get("registered_over_null")),
                     f(v["lambda"]), p(v["p_lambda"]), str(v["cells"]["n_flag_mle"]),
                     ",".join(v["cells"]["plurality_mle"]) or "none"])
    return table(["subject", "reference", "registered S", "registered p", "registered named",
                  "target-only MLE sigma0", "base-referenced CM sigma0", "base-referenced MLE sigma0",
                  "MLE null median", "MLE p", "MLE over null, target-only", "MLE over null, base-referenced",
                  "locfdr-window over null, target-only", "locfdr-window over null, base-referenced",
                  "lambda", "lambda p", "cells fdr < 0.2 (MLE)", "flag plurality (MLE)"], rows)


def shrink_table(read) -> str:
    rows = []
    for e in ("cm", "mle", "loc"):
        for g in ("median", "mean"):
            for m, x in read["shrinkage_summary"][e][g].items():
                rows.append([e, g, m.replace("_", " "), str(x["n"]), f(x["median"]), f(x["min"]), f(x["max"])])
    return table(["estimator", "target-only contrast", "ratio", "subjects", "median", "min", "max"], rows)


def placebo_table(records, meta) -> str:
    rows = []
    for r in _sorted(records, meta, "placebo"):
        v = r["variants"]["all"]
        rows.append([r["subject"], f(v["fit"]["cm"]["sigma0"]), p(v["permutation"]["cm"]["p_sigma0"]),
                     f(v["fit"]["mle"]["sigma0"]), p(v["permutation"]["mle"]["p_sigma0"]),
                     f(v["lambda"]), p(v["p_lambda"]), str(v["cells"]["n_flag_mle"]),
                     f(r["S"]), p(r["p_S"])])
    return table(["model split against itself", "CM sigma0", "CM p", "MLE sigma0", "MLE p", "lambda",
                  "lambda p", "cells fdr < 0.2 (MLE)", "max abs t", "p of max abs t"], rows)


def documented_table(records, meta) -> str:
    rows = []
    for r in sorted(records, key=lambda r: (r["subject"], r["grid"])):
        doc = r.get("documented")
        if not doc:
            continue
        a, w = r["variants"]["all"], r["variants"][f"without_{doc}"]
        rk = a.get("documented_rank") or {}
        rows.append([r["subject"], r["grid"], doc,
                     f(a["fit"]["cm"]["sigma0"]), f(w["fit"]["cm"]["sigma0"]),
                     f(a["fit"]["mle"]["sigma0"]), f(w["fit"]["mle"]["sigma0"]),
                     f(w["permutation"]["mle"]["sigma0"].get("median")), p(w["permutation"]["mle"]["p_sigma0"]),
                     f(a["lambda"]), f(w["lambda"]), str(a["cells"]["flags_mle"].get(doc)),
                     str(a["cells"]["n_flag_mle"]),
                     f((rk.get("flags_mle") or {}).get("p_rank")), f((rk.get("mean_u2") or {}).get("p_rank")),
                     f((rk.get("flags_mle") or {}).get("floor"))])
    return table(["subject", "grid", "documented", "CM sigma0, all rows", "CM sigma0, row left out",
                  "MLE sigma0, all rows", "MLE sigma0, row left out", "MLE null median, row left out",
                  "MLE p, row left out", "lambda, all rows", "lambda, row left out",
                  "flagged cells of documented", "flagged cells, all", "rank p (flag count)",
                  "rank p (mean u squared)", "rank floor 1/k"], rows)


def roster_drop_table(records, meta) -> str:
    rows = []
    for r in sorted(records, key=lambda r: (r["subject"], r["grid"])):
        if not meta[r["subject"]]["drop"]:
            continue
        v = r["variants"]["all"]
        rows.append([r["subject"], r["grid"], f(v["fit"]["cm"]["sigma0"]), f(v["fit"]["mle"]["sigma0"]),
                     f(v["permutation"]["mle"]["sigma0"].get("median")), p(v["permutation"]["mle"]["p_sigma0"]),
                     f(v["lambda"]), p(v["p_lambda"]), str(v["cells"]["n_flag_mle"]), f(r["S"]), p(r["p_S"])])
    return table(["roster without the documented candidate", "grid", "CM sigma0", "MLE sigma0",
                  "MLE null median", "MLE p", "lambda", "lambda p", "cells fdr < 0.2 (MLE)", "max abs t",
                  "p of max abs t"], rows)


def counts_table(read) -> str:
    rows = []
    order = ("registered_positive", "registered_negative", "target_without_documented", "null",
             "base_as_target", "placebo")
    for cls in order:
        for grid, c in sorted(read["counts"].get(cls, {}).items()):
            rows.append([cls, grid, str(c["n"])] + [f"{c[k]} / {c['n']}" for k in read["readings"]])
    return table(["subjects", "grid", "n"] + [f"fires: {k}" for k in read["readings"]], rows)


def agreement_table(read) -> str:
    rows = []
    for k, a in sorted(read["agreement_on_registered_positives"].items()):
        for grid in ("median", "mean", "registered"):
            if grid in a:
                g = a[grid]
                rows.append([k, a["registered_named"], grid, ",".join(g["plurality_mle"]) or "none",
                             "yes" if g["agrees_mle"] else "no", ",".join(g["plurality_cm"]) or "none",
                             "yes" if g["agrees_cm"] else "no"])
    return table(["subject", "registered named", "grid", "flag plurality (MLE)", "agrees", "flag plurality (CM)",
                  "agrees"], rows)


def checks_table(checks) -> str:
    groups: dict = {}
    for c in checks:
        g = groups.setdefault(c["what"].split(" seat ")[0], [0, 0])
        g[0] += int(c["match"])
        g[1] += 1
    return table(["stored result", "matched", "compared"],
                 [[k.replace("|t|", "abs t"), str(v[0]), str(v[1])] for k, v in sorted(groups.items())])


def ua_table(read) -> str:
    rows = []
    for k, grids in sorted(read["user_awareness"].items()):
        for g, x in grids.items():
            rows.append([k, g, f(x["S"]), p(x["p_S"]), x["argmax_candidate"], f(x["lambda"]), p(x["p_lambda"])])
    return table(["subject", "contrast", "max abs t", "p", "argmax identity", "lambda", "lambda p"], rows)


def recovery_table(chk) -> str:
    rows = []
    for r in chk["recovery"]:
        rows.append([str(r["N"]), f(r["true_sigma0"], 1)] + sum(
            ([f(r[e]["sigma0_median"]), f(r[e]["sigma0_sd"]), f(r[e]["share_undefined"], 3)]
             for e in ("cm", "mle", "loc")), []))
    head = ["N", "true sigma0"] + [f"{e} {s}" for e in ("CM", "MLE", "locfdr-window MLE")
                                   for s in ("median", "sd", "share undefined")]
    return table(head, rows)


def interval_check_table(chk) -> str:
    rows = []
    for design, d in chk["intervals"].items():
        for e in ("cm", "mle", "loc"):
            x = d[e]
            rows.append([design, e, f(x["sigma0_mean_over_fresh_draws"]), f(x["sigma0_sd_over_fresh_draws"], 3),
                         f(x["axis_block_bootstrap_sd_mean"], 3), f(x["jackknife_se_mean"], 3),
                         f(x["instruction_bootstrap_median_minus_estimate_mean"], 3)])
    return table(["design", "estimator", "mean sigma0", "sd over fresh instruction draws",
                  "axis-block bootstrap sd", "jackknife se", "instruction bootstrap shift"], rows)
