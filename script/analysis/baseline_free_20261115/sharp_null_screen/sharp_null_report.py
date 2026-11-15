"""The screen's CSV tables and README, generated from the merged results.

Every number in the README is read from the results here. The reading paragraphs
state facts that ``sharp_null_reading`` checks against the same rows first.
"""

from __future__ import annotations

import csv
from pathlib import Path

from script.analysis.baseline_free_20261115.sharp_null_screen.sharp_null_reading import reading
from script.analysis.baseline_free_20261115.sharp_null_screen.sharp_null_rows import (
    GROUPS, REPORTED, agreement, rejection_counts, screen_rows, target_vs_base)
from src.external.user_awareness_materials import IDENTITIES

UA_GROUP = {i["key"]: i["group"] for i in IDENTITIES}
SHOW_INTERVAL = ("NULL", "UA")
SHORT = {"registered": "registered", "target_only_median": "median",
         "target_only_mean": "mean", "g_test": "G", "coherence_max": "coherence max",
         "coherence_detachment": "detachment", "loser_z_infinite": "loser z (inf)",
         "loser_z_exclude": "loser z (excl)"}


def _csv(path: Path, rows: list[dict]) -> None:
    fields: list[str] = []
    for r in rows:
        fields += [k for k in r if k not in fields]
    with path.open("x", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def _f(x, nd=3) -> str:
    if x is None or x == "":
        return "--"
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, float):
        return "inf" if x == float("inf") else f"{x:.{nd}f}"
    return str(x)


def _p(x) -> str:
    return "--" if x is None else f"{x:.4f}"


def _pm(r: dict) -> str:
    """A p value, starred when it lies within Monte Carlo error of alpha."""
    if not r or r.get("p") is None:
        return "--"
    return _p(r["p"]) + ("*" if r.get("mc_borderline") else "")


def _table(head: list[str], body: list[list]) -> list[str]:
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(_f(c) if not isinstance(c, str) else c for c in r) + " |"
            for r in body]
    return out + [""]


def _cell(c: dict | None) -> str:
    if c is None or not c["n"]:
        return "--"
    base = f"{c['n_reject_0.01']}/{c['n']}"
    if c["group"] in SHOW_INTERVAL and c["model"] == "all" and c["paper_status"] == "all":
        base += f" [{c['cp95_lo']:.2f}, {c['cp95_hi']:.2f}]"
    return base


def _find(counts, subset, variant, group, model="all", status="all"):
    return next((c for c in counts if c["subset"] == subset and c["variant"] == variant
                 and c["group"] == group and c["model"] == model
                 and c["paper_status"] == status), None)


def _counts_md(counts: list[dict], subset: str) -> list[str]:
    body = [[SHORT[v], *(_cell(_find(counts, subset, v, g)) for g in GROUPS)]
            for v in REPORTED]
    return _table(["Variant", *GROUPS], body)


def _by_model_md(counts: list[dict], subset: str) -> list[str]:
    keys = sorted({(c["group"], c["model"]) for c in counts if c["subset"] == subset
                   and c["model"] != "all"}, key=lambda k: (("BASE", "NULL", "ORG").index(k[0]), k[1]))
    body = [[g, m, *(_cell(_find(counts, subset, v, g, m)) for v in REPORTED)] for g, m in keys]
    return _table(["Group", "Model", *(SHORT[v] for v in REPORTED)], body)


def _by_status_md(counts: list[dict], subset: str) -> list[str]:
    statuses = sorted({c["paper_status"] for c in counts if c["paper_status"] != "all"})
    body = [[s, *(_cell(_find(counts, subset, v, "ORG", status=s)) for v in REPORTED)]
            for s in statuses
            if any((_find(counts, subset, v, "ORG", status=s) or {}).get("n") for v in REPORTED)]
    return _table(["ORG subset", *(SHORT[v] for v in REPORTED)], body)


def _per_run_md(rows: list[dict], subset: str) -> list[str]:
    by = {(r["subject"], r["variant"]): r for r in rows if r["subset"] == subset}
    body = []
    for sid in dict.fromkeys(r["subject"] for r in rows if r["subset"] == subset):
        get = lambda v: by.get((sid, v), {})  # noqa: E731
        med, mean, reg = get("target_only_median"), get("target_only_mean"), get("registered")
        name = lambda r: r.get("named") or ("(k=2)" if r.get("k2_flag") else "--")  # noqa: E731
        body.append([sid, med.get("group", ""), str(med.get("k", "")),
                     _f(med.get("S")), _pm(med), name(med),
                     _f(mean.get("S")), _pm(mean), name(mean),
                     _pm(get("g_test")), _pm(get("coherence_max")),
                     _pm(get("coherence_detachment")), _pm(get("loser_z_exclude")),
                     _f(reg.get("S")), _pm(reg), name(reg) if reg else "--"])
    return _table(["Subject", "Group", "k", "Median S", "Median p", "Median named", "Mean S",
                   "Mean p", "Mean named", "G p", "Coherence p", "Detachment p",
                   "Loser z p (excl)", "Registered S", "Registered p",
                   "Registered named"], body)


def _ua_md(rows: list[dict]) -> list[str]:
    body = []
    for r in rows:
        if (r["group"] == "UA" and r["subset"] == "full" and r["status"] == "done"
                and r["variant"] in REPORTED):
            body.append([r["subject"], SHORT[r["variant"]], _f(r["S"]), _pm(r),
                         f"{r['argmax']} ({UA_GROUP.get(r['argmax'], '--')})"
                         if r["argmax"] else "--", r["named"] or "--"])
    return _table(["Subject", "Variant", "S", "p", "Argmax if it rejects (identity group)",
                   "Named"], body)


def _borderline_md(rows: list[dict]) -> list[str]:
    body = []
    for r in rows:
        if r["status"] == "done" and r.get("mc_borderline"):
            body.append([r["subject"], r["group"], SHORT[r["variant"]], r["subset"],
                         _p(r["p"]), f"[{r['p_mc_lo']:.4f}, {r['p_mc_hi']:.4f}]",
                         _f(r["reject_0.01"]), _p(r.get("p_100k")),
                         f"[{r['p_mc_lo_100k']:.4f}, {r['p_mc_hi_100k']:.4f}]"
                         if r.get("p_mc_lo_100k") is not None else "--",
                         _f(r.get("reject_0.01_100k")),
                         _f(r.get("mc_borderline_100k"))])
    return _table(["Subject", "Group", "Variant", "Axes", "p", "95% Monte Carlo interval",
                   "Rejects", "p at 100,000", "Interval at 100,000", "Rejects at 100,000",
                   "Still within error"], body)


def _pairs_md(pair_counts: list[dict], subset: str) -> list[str]:
    body = [[SHORT[c["variant"]], str(c["n"]), str(c["both_reject"]), str(c["target_only"]),
             str(c["base_only"]), str(c["neither"]), str(c["target_only_registered_rejects"])]
            for c in pair_counts if c["subset"] == subset and c["variant"] in REPORTED]
    return _table(["Variant", "Pairs", "Both reject", "Target only", "Base only", "Neither",
                   "Target only, registered rejects"], body)


def _pairs_detail_md(pairs: list[dict]) -> list[str]:
    body = [[x["target"], x["base"], x["paper_status"], _p(x["target_p"]),
             _p(x["base_p"]), _p(x["registered_p"])]
            for x in pairs if x["subset"] == "full" and x["variant"] == "target_only_median"]
    return _table(["Target", "Its base", "Paper status", "Target median p", "Base median p",
                   "Registered p"], body)


def write_report(out: Path, res: dict, skipped: list[dict], meta: dict, checks: dict,
                 settings: dict, precision: dict) -> None:
    rows = screen_rows(res, skipped, meta, precision)
    counts = rejection_counts(rows)
    agree = agreement(rows)
    pairs, pair_counts = target_vs_base(rows, meta)
    _csv(out / "screen_table.csv", rows)
    _csv(out / "rejection_counts.csv", counts)
    _csv(out / "registered_agreement.csv", agree)
    _csv(out / "target_base_pairs.csv", pairs)
    _csv(out / "target_base_counts.csv", pair_counts)
    n_by = {g: sum(m["group"] == g for m in meta.values())
            for g in ("ORG", "NULL", "BASE", "UA", "HALF")}
    n_pool_base = sum(m["group"] == "BASE" and m["in_pool"] for m in meta.values())
    ctx = {"rows": rows, "counts": counts, "agree": agree, "pairs": pairs,
           "pair_counts": pair_counts, "checks": checks, "meta": meta}
    md = ["# Target-only screen at the sharp null", ""]
    md += reading(ctx, "intro")
    md += ["## Settings", ""]
    md += _table(["Setting", "Value"], [
        ["Permutations", str(settings["n_permutations"])], ["Seed", str(settings["seed"])],
        ["Alpha", str(settings["alpha"])], ["Adjustment", settings["adjustment"]],
        ["Judge level", settings["level"]],
        ["G test", f"{settings['g_test']['n_permutations']} permutations, seed "
                   f"{settings['g_test']['seed']}"],
        ["Coherence", "k0 20, Z clip 8, scale floor share 0.25"],
        ["Loser-dispersion z", "all-zero base on the subject's own cells; a zero spread is "
                               "read as infinite or excluded"],
        ["Half-sample replicates", "the shared registry's placebo split of base A and of the "
                                   "flattery null, replicate 0"],
        ["Naming", "the registered naming rule on every variant with pairs; k = 2 rows "
                   "flagged named not identified"],
        ["Monte Carlo interval", "exact 95% interval on the permutation hit count; a row whose "
                                 "interval contains alpha is rerun at "
                                 f"{settings['monte_carlo']['precision_rerun']['n_permutations']}"
                                 " permutations with the same seed"]])
    md += ["## Inputs", ""]
    md += _table(["Group", "Subjects", "What they are"], [
        ["ORG", str(n_by["ORG"]), "every audited target (narrow secret loyalty, AuditBench "
                                  "positives, four court arms, the sycophant, seven challenge "
                                  "rosters)"],
        ["NULL", str(n_by["NULL"]), "eight AuditBench null controls, two synthetic-document "
                                    "nulls"],
        ["BASE", f"{n_by['BASE']} ({n_pool_base} pooled)",
         "every distinct untuned base table, read as a target (AuditBench A, B, C1, C2 and "
         "each run's own base), and C1 cut to samples 0 to 11, which stays out of the pool"],
        ["UA", str(n_by["UA"]), "served subjects of the user-awareness grading replication "
                                "(10 identities, 16 exchanges, 6 axes)"],
        ["HALF", str(n_by["HALF"]), "half-sample replicates: each random half of base A and of "
                                    "the flattery null, screened alone; out of every pool"]])
    md += ["Input files, one per subject (hashes and stored records in `results.json`):", ""]
    md += _table(["Subject", "Registry id", "Group", "Model", "Level", "Verdicts",
                  "Registered pair"], [
        [sid, m["registry_subject_id"], m["group"], m["model"], f"L{m['level']}",
         f"`{m['verdicts']}`" + (f" (half {m['half'] + 1})" if m["half"] is not None else "")
         + (f" (s <= {m['s_max']})" if m["s_max"] is not None else ""),
         f"`{m['base']}`" if m["base"] else
         (f"half {m['base_half'] + 1}" if m["base_half"] is not None else "--")]
        for sid, m in meta.items()])
    md += ["## Reproduction of stored results", ""]
    md += _table(["Check", "Rows", "Mismatches"],
                 [[k, str(v["n"]), str(v["mismatches"])] for k, v in checks["counts"].items()])
    md += reading(ctx, "reproduce")
    rf = checks["groups"]["reference_free_json"]
    md += ["Stored reference-free seats, decision at the stored 0.05 against this screen at "
           "0.05 and at 0.01:", ""]
    md += _table(["Seat", "S", "p", "Stored at 0.05", "Here at 0.05", "Here at 0.01"],
                 [[r["ref"].split("out/main/", 1)[-1].replace("/reference_free.json", ""),
                   _f(r["got_S"]), _p(r["got_p"]), _f(r["stored_decision"]),
                   _f(r["got_decision_0.05"]), _f(r["got_decision_0.01"])] for r in rf])
    md += ["## Rejections at 0.01, full registry", ""]
    md += reading(ctx, "counts_note")
    md += _counts_md(counts, "full")
    md += ["Split by model (every cell descriptive):", ""]
    md += _by_model_md(counts, "full")
    md += ["Audited targets split by paper status (every cell descriptive):", ""]
    md += _by_status_md(counts, "full")
    md += ["## Rejections at 0.01, three guaranteed axes", ""]
    md += _counts_md(counts, "guaranteed3")
    md += ["Split by model:", ""]
    md += _by_model_md(counts, "guaranteed3")
    md += ["Audited targets split by paper status:", ""]
    md += _by_status_md(counts, "guaranteed3")
    md += ["## Agreement with the registered test, full registry", ""]
    md += _table(["Variant", "Group", "Paper status", "Subjects", "Both reject",
                  "Registered only", "Screen only", "Neither", "Same name"],
                 [[SHORT[a["variant"]], a["group"], a["paper_status"], str(a["n"]),
                   str(a["both_reject"]), str(a["registered_only"]), str(a["screen_only"]),
                   str(a["neither"]), str(a["same_name"])] for a in agree
                  if a["subset"] == "full" and a["variant"] in REPORTED and a["n"]])
    md += ["## Each audited target beside its own base", ""]
    md += ["Full registry:", ""]
    md += _pairs_md(pair_counts, "full")
    md += ["Three guaranteed axes:", ""]
    md += _pairs_md(pair_counts, "guaranteed3")
    md += ["Median variant, full registry, every pair:", ""]
    md += _pairs_detail_md(pairs)
    md += ["## Decisions within Monte Carlo error", ""]
    md += reading(ctx, "mc_note")
    md += _borderline_md(rows)
    md += ["## User-awareness subjects", ""]
    md += _ua_md(rows)
    md += ["## Every subject, full registry", "",
           "A starred p value lies within Monte Carlo error of 0.01.", ""]
    md += _per_run_md(rows, "full")
    md += ["## Every subject, three guaranteed axes", ""]
    md += _per_run_md(rows, "guaranteed3")
    md += ["## Rows that cannot run", ""]
    md += _table(["Subject", "Variant", "Subset", "Reason"],
                 [[s["sid"], s["kind"], s["subset"], s["status"]] for s in skipped])
    md += ["## Naming", ""]
    md += reading(ctx, "naming")
    md += ["## Reading", ""]
    md += reading(ctx, "reading")
    md += ["## Outputs", ""]
    md += _table(["File", "Content"], [
        ["manifest.csv", "one row per (subject, task kind, axis subset), status"],
        ["tasks.jsonl", "one line per finished task, as computed"],
        ["mc_precision.jsonl", "one line per borderline task, rerun at 100,000 permutations"],
        ["results.json", "settings, subject metadata, every result, precision reruns, rows "
                         "that cannot run"],
        ["runs/<subject>.json", "one file per subject"],
        ["screen_table.csv", "one row per (subject, variant, axis subset), with registry id, "
                             "model, paper status, Monte Carlo interval"],
        ["rejection_counts.csv", "rejections per variant and group, by model and by paper "
                                 "status, Clopper-Pearson 95% with its interval note"],
        ["registered_agreement.csv", "decisions and names against the registered test, by "
                                     "paper status"],
        ["target_base_pairs.csv", "each audited target beside its own base, per variant"],
        ["target_base_counts.csv", "the pair counts of target_base_pairs.csv"],
        ["t_grids.npz", "observed t grid per task; null maxima for the mean and median variants"],
        ["t_grids_index.json", "registry id, candidates and axes order of every grid"],
        ["perm_abs_median.json", "observed and permuted pooled median |t|, and their ratio"],
        ["reproduce_check.json", "every comparison with a stored record or the registry"],
        ["settings.json", "settings"], ["task_grids/", "the per-task grid files merged above"]])
    (out / "README.md").open("x").write("\n".join(md) + "\n")
