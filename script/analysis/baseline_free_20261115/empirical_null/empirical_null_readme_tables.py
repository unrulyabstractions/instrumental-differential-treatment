"""Markdown tables of the empirical-null README, each read out of efron.json or estimator_check.json.

The locfdr-window MLE (``loc``) is the headline estimator; the fixed-window MLE
and central matching follow it as secondary columns.
"""

from __future__ import annotations

import math

__all__ = ["ORDER_ROLE", "table", "fit_table", "secondary_fit_table", "tau_table", "centring_table",
           "interval_table", "registered_table", "shrink_table", "placebo_summary_table",
           "placebo_ks_table", "placebo_table", "documented_table", "roster_drop_table", "counts_table",
           "agreement_table", "checks_table", "ua_table", "recovery_table", "interval_check_table",
           "real_interval_table", "undefined_table", "inputs_table"]

EST_LABEL = {"loc": "locfdr-window MLE", "mle": "fixed-window MLE", "cm": "central matching"}


def f(x, nd=2) -> str:
    if isinstance(x, float) and math.isinf(x):
        return "inf" if x > 0 else "-inf"
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "n/a"
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, float):
        return f"{x:.{nd}f}"
    return str(x)


def p(x) -> str:
    return "n/a" if x is None else (f"{x:.4f}" if x >= 0.0001 else f"{x:.1e}")


def ci(block: dict, nd=2) -> str:
    return f"[{f(block.get('lo'), nd)}, {f(block.get('hi'), nd)}]" if block.get("n") else "n/a"


def yn(x) -> str:
    return "yes" if x else "no"


def names(x: list) -> str:
    return ", ".join(x) or "none"


def table(head: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


ORDER_ROLE = {"positive": 0, "calibration": 1, "challenge": 2, "control": 3, "null": 4, "base": 5}


def _key(meta, k):
    return (ORDER_ROLE[meta[k]["role"]], meta[k]["roster"], k)


def _sorted(records, meta, grid):
    rs = [r for r in records if r["grid"] == grid]
    return sorted(rs, key=lambda r: (_key(meta, r["subject"]), r.get("replicate") or 0))


def inputs_table(meta, models) -> str:
    rows = [[k, s["role"], models.get(k, "n/a"), str(s["level"]), s["target"], s["base"] or "none",
             str(s["placebo_replicates"])]
            for k, s in sorted(meta.items(), key=lambda kv: _key(meta, kv[0]))]
    return table(["subject", "role", "model", "level", "target verdicts", "base-referenced against",
                  "placebo splits"], rows)


def fit_table(records, meta, grid) -> str:
    rows = []
    for r in _sorted(records, meta, grid):
        v = r["variants"]["all"]
        fit, perm, axb = v["fit"], v["permutation"], v["bootstrap_axes"]
        lam_read = grid != "median"
        rows.append([r["subject"], meta[r["subject"]]["role"], f"{r['n_candidates']} x {r['n_axes']}",
                     str(r["n_instructions"]), str(fit["n_fitted"]),
                     f(fit["loc"]["delta0"]), f(fit["loc"]["sigma0"]), ci(axb["loc"]["sigma0"]),
                     f(perm["loc"]["sigma0"].get("median")), p(perm["loc"]["p_sigma0"]),
                     f(fit["loc"]["p0"]), ci(axb["loc"]["p0"]), yn(fit["loc"]["bulk_ok"]),
                     f(v["tau"]["tau_pp"]),
                     f(v["lambda"]), p(v["p_lambda"]) + ("" if lam_read else " (not read)"),
                     f(v["lambda_atoms"]["share_permuted_medians_tied"]),
                     str(v["cells"]["n_flag_loc"]), str(v["cells"]["n_flag_loc_supported"]),
                     names(v["cells"]["plurality_loc_supported"])])
    return table(["subject", "role", "k x A", "instructions", "cells fitted", "delta0", "sigma0",
                  "sigma0 95% axis-block", "band median", "sigma0 p", "p0", "p0 95% axis-block",
                  "bulk condition", "tau (pp)", "lambda", "lambda p", "tied permuted medians",
                  "cells fdr < 0.2", "flags under the bulk condition", "flag plurality"], rows)


def secondary_fit_table(records, meta, grid) -> str:
    rows = []
    for r in _sorted(records, meta, grid):
        v = r["variants"]["all"]
        fit, perm, axb = v["fit"], v["permutation"], v["bootstrap_axes"]
        rows.append([r["subject"]] + sum(([f(fit[e]["delta0"]), f(fit[e]["sigma0"]), ci(axb[e]["sigma0"]),
                                           f(perm[e]["sigma0"].get("median")), p(perm[e]["p_sigma0"]),
                                           f(fit[e]["p0"]), yn(fit[e]["bulk_ok"]),
                                           str(v["cells"][f"n_flag_{e}_supported"])]
                                          for e in ("mle", "cm")), []))
    head = ["subject"] + [f"{lab} {c}" for lab in ("MLE", "CM") for c in
                          ("delta0", "sigma0", "sigma0 95% axis-block", "band median", "sigma0 p", "p0",
                           "bulk condition", "flags under the bulk condition")]
    return table(head, rows)


def tau_table(records, meta, models) -> str:
    by = {(r["subject"], r["grid"]): r for r in records if r["grid"] != "placebo"}
    rows = []
    for k in sorted({r["subject"] for r in records}, key=lambda k: _key(meta, k)):
        med = by[(k, "median")]["variants"]["all"]
        reg = by.get((k, "registered"))
        rt = reg["variants"]["all"]["tau"] if reg else None
        rows.append([k, meta[k]["role"], models.get(k, "n/a"), str(med["tau"]["k"]),
                     f(med["tau"]["mean_rate_pp"], 1),
                     f(med["tau"]["tau_pp"]), ci(med["tau"]["axis_block"]),
                     f(med["tau"]["share_axes_tau2_positive"]),
                     f(med["fit"]["loc"]["sigma0"]), f(med["permutation"]["loc"]["sigma0"].get("median")),
                     f(rt["tau_pp"]) if rt else "n/a", ci(rt["axis_block"]) if rt else "n/a",
                     f(rt["tau_pp"] / med["tau"]["tau_pp"]) if rt and med["tau"]["tau_pp"] else "n/a"])
    return table(["subject", "role", "model", "k", "mean firing rate (pp)", "tau, target only (pp)",
                  "95% axis-block", "share of axes with tau2 > 0", "sigma0", "band median",
                  "tau, base-referenced (pp)", "95% axis-block", "ratio"], rows)


def centring_table(records, meta) -> str:
    rows = []
    for r in _sorted(records, meta, "median"):
        v = r["variants"]["all"]
        mean_c = v["fit"]["loc"]
        alt = v["fit_other_centrings"]
        rows.append([r["subject"], str(r["n_candidates"])]
                    + [f(mean_c["delta0"]), f(mean_c["sigma0"]), f(mean_c["p0"])]
                    + sum(([f(alt[h]["loc"]["delta0"]), f(alt[h]["loc"]["sigma0"]), f(alt[h]["loc"]["p0"])]
                           for h in ("axis_median", "others_median")), []))
    head = ["subject", "k"] + [f"{lab} {c}" for lab in ("axis mean", "axis median", "others' median")
                               for c in ("delta0", "sigma0", "p0")]
    return table(head, rows)


def interval_table(records, meta, grid) -> str:
    rows = []
    for r in _sorted(records, meta, grid):
        v = r["variants"]["all"]
        jk, ib, ab = v["jackknife_instructions"], v["bootstrap_instructions"], v["bootstrap_axes"]
        rows.append([r["subject"], ci(ab["loc"]["sigma0"]), f(jk["loc"]["sigma0"]["se"]),
                     ci(ib["loc"]["sigma0_noise_removed"]), f(jk["mle"]["sigma0"]["se"]),
                     f(jk["cm"]["sigma0"]["se"]), ci(ab["lambda"]), f(jk["lambda"]["se"]),
                     ci(ib["lambda_noise_removed"]), f(ib["added_noise_var_u"].get("median"))])
    return table(["subject", "sigma0 axis-block", "sigma0 jackknife se", "sigma0 instruction bootstrap",
                  "MLE jackknife se", "CM jackknife se", "lambda axis-block", "lambda jackknife se",
                  "lambda instruction bootstrap", "added noise variance"], rows)


def registered_table(records, meta, registered, read) -> str:
    by = {(r["subject"], r["grid"]): r for r in records if r["grid"] != "placebo"}
    rows = []
    for r in _sorted(records, meta, "registered"):
        k = r["subject"]
        reg = registered.get(k, {})
        med = by[(k, "median")]["variants"]["all"]
        sh = read["shrinkage"][k]
        v = r["variants"]["all"]
        loc = sh["loc"]["median"]
        rows.append([k, meta[k]["base_label"], read["mirrors"].get(k) or "", f(reg.get("S")), p(reg.get("p")),
                     str(reg.get("named") or "none"),
                     f(med["fit"]["loc"]["sigma0"]), f(v["fit"]["loc"]["sigma0"]), ci(v["bootstrap_axes"]["loc"]["sigma0"]),
                     f(v["permutation"]["loc"]["sigma0"].get("median")), p(v["permutation"]["loc"]["p_sigma0"]),
                     f(v["fit"]["loc"]["p0"]), f(loc["target_only_over_null"]), f(loc["registered_over_null"]),
                     f(sh["tau"]["target_only"]), f(sh["tau"]["registered"]),
                     f(v["lambda"]), p(v["p_lambda"]), str(v["cells"]["n_flag_loc_supported"]),
                     names(v["cells"]["plurality_loc_supported"])])
    return table(["subject", "reference", "mirror of", "registered S", "registered p", "registered named",
                  "target-only sigma0", "base-referenced sigma0", "95% axis-block", "band median", "sigma0 p",
                  "p0", "target-only over band", "base-referenced over band", "tau target only (pp)",
                  "tau base-referenced (pp)", "lambda", "lambda p", "flags under the bulk condition",
                  "flag plurality"], rows)


def shrink_table(read) -> str:
    rows = []
    ss = read["shrinkage_summary"]
    for e in ("loc", "mle", "cm"):
        for g in ("median", "mean"):
            for m, x in ss[e][g].items():
                rows.append([EST_LABEL[e], g, m.replace("_", " "), str(x["n"]), f(x["median"]), f(x["min"]),
                             f(x["max"])])
    x = ss["tau"]
    rows.append(["tau", "rates", "ratio registered to target only", str(x["n"]), f(x["median"]), f(x["min"]),
                 f(x["max"])])
    return table(["estimator", "target-only contrast", "ratio", "subjects", "median", "min", "max"], rows)


def placebo_summary_table(read) -> str:
    rows = []
    pl = read["placebo"]
    for grp in ("base", "other", "all"):
        g = pl[grp]
        for k in read["readings"] + ["max"]:
            c = g["fires"][k] if k != "max" else g["max_fires"]
            rows.append([grp, str(g["n_subjects"]), str(g["n_grids"]), k if k != "max" else "max abs t",
                         f"{c['k']} / {c['n']}", f"[{f(c['lo'], 3)}, {f(c['hi'], 3)}]"])
    return table(["subjects", "models", "splits", "reading", "fires", "95% Clopper-Pearson"], rows)


def placebo_ks_table(read) -> str:
    rows = []
    pl = read["placebo"]
    for grp in ("base", "other", "all"):
        for k, x in pl[grp]["ks_uniform"].items():
            rows.append([grp, k.replace("_", " "), str(x["n"]), f(x.get("median"), 3),
                         f(x.get("share_below_0.05"), 3), f(x.get("statistic"), 3), p(x.get("p"))])
    return table(["subjects", "p value", "splits", "median", "share at or below 0.05", "KS statistic",
                  "KS p against uniform"], rows)


def placebo_table(records, meta) -> str:
    groups: dict = {}
    for r in _sorted(records, meta, "placebo"):
        groups.setdefault(r["subject"], []).append(r)
    rows = []
    for k, rs in groups.items():
        def share(fn):
            return f"{sum(bool(fn(r)) for r in rs)} / {len(rs)}"
        vs = [r["variants"]["all"] for r in rs]
        sig = [v["fit"]["loc"]["sigma0"] for v in vs]
        rows.append([k, str(len(rs)), f(min(sig)), f(max(sig)),
                     share(lambda r: (r["variants"]["all"]["permutation"]["loc"]["p_sigma0"] or 1) <= 0.01),
                     share(lambda r: r["variants"]["all"]["p_lambda"] <= 0.01),
                     share(lambda r: r["variants"]["all"]["cells"]["n_flag_loc_supported"] > 0),
                     share(lambda r: r["p_S"] <= 0.01),
                     f(min(v["permutation"]["loc"]["p_sigma0"] or 1 for v in vs), 4),
                     f(min(v["p_lambda"] for v in vs), 4),
                     f(max(v["tau"]["tau_pp"] for v in vs))])
    return table(["model split against itself", "splits", "sigma0 min", "sigma0 max", "sigma0 fires",
                  "lambda fires", "flags under the bulk condition", "max abs t fires", "smallest sigma0 p",
                  "smallest lambda p", "largest tau (pp)"], rows)


def documented_table(records, meta) -> str:
    rows = []
    for r in sorted((r for r in records if r["grid"] != "placebo"), key=lambda r: (r["subject"], r["grid"])):
        doc = r.get("documented")
        if not doc:
            continue
        a, w = r["variants"]["all"], r["variants"][f"without_{doc}"]
        rk = a.get("documented_rank") or {}
        rows.append([r["subject"], r["grid"], doc,
                     f(a["fit"]["loc"]["delta0"]), f(w["fit"]["loc"]["delta0"]),
                     f(a["fit"]["loc"]["sigma0"]), f(w["fit"]["loc"]["sigma0"]),
                     f(w["permutation"]["loc"]["sigma0"].get("median")), p(w["permutation"]["loc"]["p_sigma0"]),
                     f(a["fit"]["loc"]["p0"]), f(w["fit"]["loc"]["p0"]),
                     f(a["tau"]["tau_pp"]), f(w["tau"]["tau_pp"]),
                     f(a["lambda"]), f(w["lambda"]), str(a["cells"]["flags_loc"].get(doc)),
                     str(a["cells"]["n_flag_loc"]),
                     f((rk.get("flags_loc") or {}).get("p_rank")), f((rk.get("mean_u2") or {}).get("p_rank")),
                     f((rk.get("flags_loc") or {}).get("floor"))])
    return table(["subject", "grid", "documented", "delta0, all rows", "delta0, row left out",
                  "sigma0, all rows", "sigma0, row left out", "band median, row left out",
                  "sigma0 p, row left out", "p0, all rows", "p0, row left out", "tau, all rows (pp)",
                  "tau, row left out (pp)", "lambda, all rows", "lambda, row left out",
                  "flagged cells of documented", "flagged cells, all", "rank p (flag count)",
                  "rank p (mean u squared)", "rank floor 1/k"], rows)


def roster_drop_table(records, meta) -> str:
    rows = []
    for r in sorted((r for r in records if r["grid"] != "placebo"), key=lambda r: (r["subject"], r["grid"])):
        if not meta[r["subject"]]["drop"]:
            continue
        v = r["variants"]["all"]
        rows.append([r["subject"], r["grid"], f(v["fit"]["loc"]["delta0"]), f(v["fit"]["loc"]["sigma0"]),
                     f(v["permutation"]["loc"]["sigma0"].get("median")), p(v["permutation"]["loc"]["p_sigma0"]),
                     f(v["fit"]["loc"]["p0"]), f(v["tau"]["tau_pp"]),
                     f(v["lambda"]), p(v["p_lambda"]) + (" (not read)" if r["grid"] == "median" else ""),
                     str(v["cells"]["n_flag_loc_supported"]), f(r["S"]), p(r["p_S"])])
    return table(["roster without the documented candidate", "grid", "delta0", "sigma0", "band median",
                  "sigma0 p", "p0", "tau (pp)", "lambda", "lambda p", "flags under the bulk condition",
                  "max abs t", "p of max abs t"], rows)


def counts_table(read) -> str:
    rows = []
    order = ("registered_positive", "registered_negative", "target_without_documented", "null",
             "base_as_target")
    for cls in order:
        for grid in ("median", "mean", "registered"):
            c = read["counts"].get(cls, {}).get(grid)
            if not c:
                continue
            cells = []
            for k in read["readings"]:
                cells.append("not read" if (k == "lambda" and grid == "median") else f"{c[k]} / {c['n']}")
            rows.append([cls.replace("_", " "), grid, str(c["n"])] + cells)
    pl = read["placebo"]
    for grp in ("base", "other"):
        g = pl[grp]
        rows.append([f"placebo ({grp})", "placebo", str(g["n_grids"])]
                    + [f"{g['fires'][k]['k']} / {g['fires'][k]['n']}" for k in read["readings"]])
    return table(["subjects", "grid", "n"] + [f"fires: {k.replace('_', ' ')}" for k in read["readings"]], rows)


def agreement_table(read) -> str:
    rows = []
    for k, a in sorted(read["agreement_on_registered_positives"].items()):
        for grid in ("median", "mean", "registered"):
            if grid not in a:
                continue
            g = a[grid]
            rows.append([k, a["registered_candidate"] + ("" if a["named_by_rule"] else " (argmax, unnamed)"),
                         grid, yn(g["bulk_ok_loc"]), names(g["plurality_loc_any_fit"]),
                         yn(g["agrees_loc"]), names(g["plurality_mle_any_fit"]), yn(g["bulk_ok_mle"]),
                         yn(g["agrees_mle"])])
    return table(["subject", "registered candidate", "grid", "bulk condition", "flag plurality",
                  "agrees under the bulk condition", "MLE flag plurality", "MLE bulk condition",
                  "MLE agrees under the bulk condition"], rows)


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
            rows.append([k, g, f(x["S"]), p(x["p_S"]), x["argmax_candidate"], f(x["median_abs_t"], 4),
                         f(x["lambda"]), p(x["p_lambda"]),
                         f(x["lambda_atoms"]["share_permuted_medians_tied"]),
                         f(x["tau_pp"]), ci(x["tau_axis_block"])])
    return table(["subject", "contrast", "max abs t", "p", "argmax identity", "median abs t", "lambda",
                  "lambda p", "tied permuted medians", "tau (pp)", "tau 95% axis-block"], rows)


def recovery_table(chk) -> str:
    rows = []
    for r in chk["recovery"]:
        rows.append([str(r["N"]), f(r["true_sigma0"], 1)] + sum(
            ([f(r[e]["sigma0_median"]), f(r[e]["sigma0_sd"]), f(r[e]["share_undefined"], 3)]
             for e in ("loc", "mle", "cm")), []))
    head = ["N", "true sigma0"] + [f"{lab} {s}" for lab in ("locfdr-window MLE", "MLE", "CM")
                                   for s in ("median", "sd", "share undefined")]
    return table(head, rows)


def interval_check_table(chk) -> str:
    rows = []
    for design, d in chk["intervals"].items():
        for e in ("loc", "mle", "cm"):
            x = d[e]
            rows.append([design.replace("_", " "), EST_LABEL[e], f(x["sigma0_mean_over_fresh_draws"]),
                         f(x["sigma0_sd_over_fresh_draws"], 3), f(x["axis_block_bootstrap_sd_mean"], 3),
                         f(x["jackknife_se_mean"], 3), f(x["instruction_bootstrap_median_minus_estimate_mean"], 3)])
    return table(["design", "estimator", "mean sigma0", "sd over fresh instruction draws",
                  "axis-block bootstrap sd", "jackknife se", "instruction bootstrap shift"], rows)


def real_interval_table(chk, meta) -> str:
    rows = []
    for r in sorted(chk["intervals_real_grids"], key=lambda r: (r["grid"], _key(meta, r["subject"]))):
        rows.append([r["subject"], r["grid"], str(r["half_instructions"])]
                    + sum(([f(r[e]["split_half_sd"], 3), f(r[e]["axis_block_sd_on_half"], 3),
                            f(r[e]["ratio_axis_block_to_split_half"])] for e in ("loc", "mle")), []))
    head = ["subject", "grid", "instructions per half"] + [
        f"{lab} {c}" for lab in ("locfdr-window MLE", "MLE")
        for c in ("split-half sd", "axis-block sd", "ratio")]
    return table(head, rows)


def undefined_table(undefined, meta) -> str:
    main = [u for u in undefined if not u["grid"].startswith("placebo")]
    rows = [[u["subject"], u["grid"], u["variant"], EST_LABEL[u["estimator"]], u["reason"]]
            for u in sorted(main, key=lambda u: (_key(meta, u["subject"]), u["grid"], u["variant"], u["estimator"]))]
    counts: dict = {}
    for u in undefined:
        if u["grid"].startswith("placebo"):
            k = (u["subject"], u["estimator"], u["reason"])
            counts[k] = counts.get(k, 0) + 1
    for (s, e, why), n in sorted(counts.items(), key=lambda kv: (_key(meta, kv[0][0]), kv[0][1])):
        rows.append([s, f"placebo ({n} of {meta[s]['placebo_replicates']} splits)", "all", EST_LABEL[e], why])
    return table(["subject", "grid", "variant", "estimator", "why the fit is undefined"], rows)
