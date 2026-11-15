"""The README of the proxy-swap outputs: settings, inputs, tables and the reading.

Every number in the README is read from the records ``swap_report`` passes in.
The prose comes from ``swap_reading``, whose claims are guarded by assertions on
those records.
"""

from __future__ import annotations

from script.analysis.baseline_free_20261115.proxy_swaps.swap_reading import reading
from script.analysis.baseline_free_20261115.proxy_swaps.swap_subjects import SUBJECTS, load_table

POSITIVE = ("positive_null_proxy", "positive_base_reference")


def _f(x, nd: int = 3) -> str:
    if x is None:
        return "---"
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, float):
        return f"{x:.{nd}f}"
    return str(x)


def _ci(v) -> str:
    return f"[{v[0]:.3f}, {v[1]:.3f}]"


def _table(head: list[str], rows: list[list]) -> list[str]:
    out = ["| " + " | ".join(h.replace("|", "\\|") for h in head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join((c if isinstance(c, str) else _f(c)).replace("|", "\\|")
                              for c in r) + " |" for r in rows]
    return out + [""]


def _settings(settings: dict) -> list[str]:
    return _table(["Setting", "Value"], [
        ["Test", "registered `paired_max_test`: max over (candidate, axis) of the paired t of the "
                 "target's one-vs-rest gap minus the proxy's, single-step maxT"],
        ["Permutations, seed, alpha",
         f"{settings['n_permutations']:,}, {settings['seed']}, {settings['alpha']}"],
        ["Judge level", "2 for AuditBench (the 101 axes of the contextual-optimism registry); "
                        "1 for user awareness (6 grade thresholds, parsed grades)"],
        ["No-proxy row", "the target against an all-zero table on its own cells"],
        ["Cell effect g", "one-vs-rest gap per (candidate, axis), averaged over instructions"],
        ["r, beta, var ratio", "Pearson r of g_T and g_P over cells; beta = Cov(g_T, g_P) / Var(g_P); "
                               "Var(g_T - g_P) / Var(g_T)"],
        ["Intervals", f"{settings['n_bootstrap']:,} instruction resamples, seed 20260726; "
                      "point +/- 1.96 bootstrap SD, percentiles and bias in the JSON"],
        ["Reliability", f"Spearman-Brown of the split-half r, {settings['n_splits']} within-cell "
                        "splits per subject, SeedSequence([20260726, subject index, replicate])"],
        ["Placebo", "the registered test on those same splits, half against half"],
        ["Name-effect correlation", "100 splits of the sample indices shared by both models, "
                                    "SeedSequence([20260726, 1000, replicate]); cross-model covariance of "
                                    "disjoint halves over the geometric mean of each model's half-half "
                                    "covariance"],
        ["Code commit at report", settings["code_commit_at_report"]]])


def write_readme(path, *, fpr, by_type, merged, rel, checks, secret, settings) -> None:
    def prose(section: str) -> list[str]:
        return reading(fpr=fpr, by_type=by_type, merged=merged, rel=rel, secret=secret,
                       section=section)

    L = ["# Proxy-swap null controls and the cell-level correlation of name effects", ""]
    L += prose("intro") + ["## Settings", ""] + _settings(settings) + ["## Inputs", ""]
    L += _table(["Subject", "Index", "Rows", "Verdict file(s)", "Note"], [
        [s.name, str(i), f"{load_table(s.name).n_responses:,}",
         "<br>".join(f"`{f}`" for f in s.files)
         + (f" (s {s.s_range[0]}-{s.s_range[1]})" if s.s_range else ""), s.note]
        for i, s in enumerate(SUBJECTS)])
    L += ["The SHA-256 of every input file is in `settings.json` and `input_sha256.json`.", ""]

    L += ["## Results", "", "### Does proxy subtraction hold its level on models without a loyalty?", ""]
    L += prose("fpr")
    L += _table(["Group", "Ordered runs", "Distinct tests", "p <= 0.01", "Share", "95% CI",
                 "p < 0.05", "Median p", "Named at 0.01", "Note"],
                [[r["group"], str(r["n_ordered"]), str(r["n_distinct"]), str(r["n_reject_0.01"]),
                  r["share_0.01"], _ci(r["ci95_0.01"]), str(r["n_p_below_0.05"]), r["median_p"],
                  ", ".join(f"{k} ({v})" for k, v in r["named_at_0.01"].items()) or "---",
                  r["note"] or "---"] for r in fpr])
    L += ["Intervals are exact binomial intervals over distinct tests. "
          "They ignore that one model enters several pairs.", ""]
    L += ["### Every pair", ""]
    L += _table(["Pair (target|proxy)", "Type", "S", "p", "Named", "Top cell", "r", "beta",
                 "Name-effect r", "Registered p (target vs A)", "Registered named", "No-proxy p"],
                [[m["id"], m["type"] + (f", {m['subtype']}" if m["subtype"] else ""),
                  m["S"], f"{m['p']:.4f}", m["principal"] or "---",
                  f"{m['argmax_candidate']} / {m['argmax_axis']}",
                  (m["correlation"] or {}).get("r"), (m["correlation"] or {}).get("beta"),
                  (m["correlation"] or {}).get("r_name_effects"),
                  _f(m["registered_beside"].get("vs_A", {}).get("p_family_wise"), 4),
                  _f(m["registered_beside"].get("vs_A", {}).get("principal")),
                  _f((m["no_proxy_target"] or {}).get("p"), 4)] for m in merged])
    L += ["### How strongly do models share their name effects?", ""] + prose("corr")
    L += _table(["Type", "Subtype", "Pairs", "Median r", "Range of r", "Median beta", "beta > 0.5",
                 "Median var ratio", "Split-half disattenuated r > 1", "Shared-order share",
                 "Name-effect r, pooled", "Name-effect r, median", "Name-effect r > 0.5"],
                [[t["type"], t["subtype"] or "---", str(t["n_pairs"]), t["median_r"],
                  f"{t['min_r']:.3f} to {t['max_r']:.3f}", t["median_beta"],
                  str(t["n_beta_above_0.5"]), t["median_var_ratio"],
                  str(t["n_r_disattenuated_above_1"]),
                  None if t["type"] in POSITIVE else t["pooled_shared_order_share"],
                  t["pooled_r_name_effects"], t["median_r_name_effects"],
                  f"{t['n_r_name_effects_above_0.5']} of {t['n_r_name_effects_defined']}"]
                 for t in by_type])
    L += ["The pooled name-effect r divides the mean cross-model covariance of a type by the "
          "geometric mean of its mean within-model covariances. "
          "The shared-order share is the part of the same-index covariance that disjoint indices "
          "lose; it is left out for the positive organism, whose own variance is its loyalty. "
          "Per-pair values with intervals are in `correlation_table.csv` and `correlation.json`.", ""]
    L += ["### How reliable is one model's name-effect profile?", ""] + prose("rel")
    L += _table(["Subject", "Split-half r", "Spread over splits", "Spearman-Brown reliability"],
                [[k, v["split_half_r_mean"], _ci(v["split_half_r_interval"]),
                  v["spearman_brown_mean"]] for k, v in rel.items()])
    L += ["### What do proxy swaps say on the served user-awareness models?", ""] + prose("served")
    L += _table(["Pair", "S", "p", "Top cells (candidate, axis, t)"],
                [[m["id"], m["S"], f"{m['p']:.4f}", m["top_cells"]]
                 for m in merged if m["type"] == "served_user_awareness"])
    L += ["### Narrow-secret-loyalty rosters (descriptive)", ""] + prose("secret")
    L += _table(["Seat", "Axes", "Cells", "r", "beta"],
                [[a["seat"], a["axes"], str(a["n_cells"]), a["r"], a["beta"]]
                 for a in secret["across_runs"]])
    L += _table(["Run", "Level", "Pair", "Cells", "r", "r 95% CI", "beta", "beta 95% CI",
                 "Name-effect r", "Shared-order share"],
                [[w["run"], str(w["level"]), w["pair"], str(w["n_cells"]), w["r"], _ci(w["r_ci"]),
                  w["beta"], _ci(w["beta_ci"]), w["r_name_effects"], w["shared_order_share"]]
                 for w in secret["within_run_target_vs_base"]])
    L += ["### Do the recomputed tests match the stored ones?", ""]
    L += _table(["Check", "S", "Stored S", "p", "Stored p", "Named", "Stored named", "Match"],
                [[c["what"], c["S"], c["stored_S"], f"{c['p']:.4f}", f"{c['stored_p']:.4f}",
                  _f(c["named"]), _f(c["stored_named"]), c["match"]]
                 for c in checks["stored_matches"]])
    L += [f"{checks['n_stored_match']} of {checks['n_stored']} stored results match to "
          f"{checks['tolerance']}. Order symmetry holds on {checks['n_symmetric_match']} of "
          f"{checks['n_symmetric_pairs']} unordered pairs (identical S and p in both orders).", ""]
    L += ["## Reading", ""] + prose("reading") + ["## Files", ""]
    L += _table(["File", "Content"], [
        ["`runs/pair/*.json`", "one registered test per ordered pair, with every surviving pair"],
        ["`runs/no_proxy/*.json`", "one no-proxy test per subject"],
        ["`runs/placebo/*.json`", "one split-half placebo test per subject and replicate"],
        ["`pairs.json`", "every pair: test, correlation, registered result beside, no-proxy result"],
        ["`pairs_summary.csv`", "the same, one row per pair"],
        ["`fpr_table.csv`", "rejection counts per group"],
        ["`correlation_table.csv`, `correlation.json`", "r, beta, intervals, reliabilities and "
                                                        "name-effect correlations per pair"],
        ["`correlation_by_type.csv`", "the correlation table by pair type"],
        ["`reliability.json`", "split-half reliabilities per subject"],
        ["`placebo_splits.json`", "placebo S and p per split, with the split hash"],
        ["`reproduce_check.json`", "every stored result recomputed"],
        ["`settings.json`, `input_sha256.json`", "settings, subjects and input hashes"],
        ["`run_swaps.log`", "the run log"]])
    path.write_text("\n".join(L))
