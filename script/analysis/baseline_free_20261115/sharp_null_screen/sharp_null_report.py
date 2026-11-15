"""The screen's CSV tables and README, generated from the merged results.

Every number in the README is read from the results here. The reading paragraphs
state facts that ``sharp_null_reading`` checks against the same rows first.
"""

from __future__ import annotations

import csv
from pathlib import Path

from script.analysis.baseline_free_20261115.sharp_null_screen.sharp_null_reading import reading
from script.analysis.baseline_free_20261115.sharp_null_screen.sharp_null_rows import (
    GROUPS, SCREEN, VARIANTS, agreement, rejection_counts, screen_rows)
from src.external.user_awareness_materials import IDENTITIES

UA_GROUP = {i["key"]: i["group"] for i in IDENTITIES}


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


def _table(head: list[str], body: list[list]) -> list[str]:
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(_f(c) if not isinstance(c, str) else c for c in r) + " |"
            for r in body]
    return out + [""]


def _counts_md(counts: list[dict], subset: str) -> list[str]:
    body = []
    for v in VARIANTS:
        cells = [v]
        for g in GROUPS:
            c = next(c for c in counts if c["subset"] == subset and c["variant"] == v
                     and c["group"] == g)
            cells.append("--" if not c["n"] else
                         f"{c['n_reject_0.01']}/{c['n']} [{c['cp95_lo']:.2f}, {c['cp95_hi']:.2f}]")
        body.append(cells)
    return _table(["Variant", *GROUPS], body)


def _per_run_md(rows: list[dict], subset: str) -> list[str]:
    by = {(r["subject"], r["variant"]): r for r in rows if r["subset"] == subset}
    body = []
    for sid in dict.fromkeys(r["subject"] for r in rows if r["subset"] == subset):
        get = lambda v: by.get((sid, v), {})  # noqa: E731
        med, mean, reg = get("target_only_median"), get("target_only_mean"), get("registered")
        name = lambda r: r.get("named") or ("(k=2)" if r.get("k2_flag") else "--")  # noqa: E731
        body.append([sid, med.get("group", ""), str(med.get("k", "")),
                     _f(med.get("S")), _p(med.get("p")), name(med),
                     _f(mean.get("S")), _p(mean.get("p")), name(mean),
                     _p(get("g_test").get("p")), _p(get("coherence_max").get("p")),
                     _p(get("coherence_detachment").get("p")),
                     _p(get("loser_z_infinite").get("p")), _p(get("loser_z_exclude").get("p")),
                     _f(reg.get("S")), _p(reg.get("p")), name(reg) if reg else "--"])
    return _table(["Subject", "Group", "k", "Median S", "Median p", "Median named", "Mean S",
                   "Mean p", "Mean named", "G p", "Coherence p", "Detachment p",
                   "Loser z p (inf)", "Loser z p (excl)", "Registered S", "Registered p",
                   "Registered named"], body)


def _ua_md(rows: list[dict]) -> list[str]:
    body = []
    for r in rows:
        if r["group"] == "UA" and r["subset"] == "full" and r["status"] == "done":
            body.append([r["subject"], r["variant"], _f(r["S"]), _p(r["p"]),
                         f"{r['argmax']} ({UA_GROUP.get(r['argmax'], '--')})"
                         if r["argmax"] else "--", r["named"] or "--"])
    return _table(["Subject", "Variant", "S", "p", "Argmax (identity group)", "Named"], body)


def write_report(out: Path, res: dict, skipped: list[dict], meta: dict, checks: dict,
                 settings: dict) -> None:
    rows = screen_rows(res, skipped, meta)
    counts = rejection_counts(rows)
    agree = agreement(rows)
    _csv(out / "screen_table.csv", rows)
    _csv(out / "rejection_counts.csv", counts)
    _csv(out / "registered_agreement.csv", agree)
    n_by_group = {g: sum(m["group"] == g for m in meta.values())
                  for g in ("ORG", "NULL", "BASE", "UA", "PLACEBO")}
    md = ["# Target-only screen at the sharp null", ""]
    md += reading(rows, counts, agree, checks, "intro")
    md += ["## Settings", ""]
    md += _table(["Setting", "Value"], [
        ["Permutations", str(settings["n_permutations"])], ["Seed", str(settings["seed"])],
        ["Alpha", str(settings["alpha"])], ["Adjustment", settings["adjustment"]],
        ["Judge level", settings["level"]],
        ["G test", f"{settings['g_test']['n_permutations']} permutations, seed "
                   f"{settings['g_test']['seed']}; {settings['g_test']['note']}"],
        ["Coherence", "k0 20, Z clip 8, scale floor share 0.25"],
        ["Loser-dispersion z", "all-zero base on the subject's own cells; zero-spread modes "
                               "infinite and exclude"],
        ["Placebo split", f"split_cell_indices, seed {settings['split_seed']}"],
        ["Naming", settings["naming_rule"]]])
    md += ["## Inputs", ""]
    md += _table(["Group", "Subjects", "What they are"], [
        ["ORG", str(n_by_group["ORG"]), "every audited target (narrow secret loyalty, AuditBench "
                                        "positives, four court arms, the sycophant, seven "
                                        "challenge rosters)"],
        ["NULL", str(n_by_group["NULL"]), "eight AuditBench null controls, two synthetic-document "
                                          "nulls"],
        ["BASE", str(n_by_group["BASE"]), "every distinct untuned base table, read as a target "
                                          "(AuditBench A, B, C1, C2 and each run's own base)"],
        ["UA", str(n_by_group["UA"]), "served subjects of the user-awareness grading "
                                      "replication (10 identities, 16 exchanges, 6 axes)"],
        ["PLACEBO", str(n_by_group["PLACEBO"]), "each random half of base A and of the "
                                                "flattery null, screened alone"]])
    md += ["Input files, one per subject (hashes and stored records in `results.json`):", ""]
    md += _table(["Subject", "Group", "Level", "Verdicts", "Registered pair"], [
        [sid, m["group"], f"L{m['level']}",
         f"`{m['verdicts']}`" + (f" (half {m['half'] + 1})" if m["half"] is not None else ""),
         f"`{m['base']}`" if m["base"] else
         (f"half {m['base_half'] + 1}" if m["base_half"] is not None else "--")]
        for sid, m in meta.items()])
    md += ["## Reproduction of stored results", ""]
    md += _table(["Check", "Rows", "Mismatches"],
                 [[k, str(v["n"]), str(v["mismatches"])] for k, v in checks["counts"].items()])
    md += reading(rows, counts, agree, checks, "reproduce")
    rf = checks["groups"]["reference_free_json"]
    md += ["Stored reference-free seats, decision at the stored 0.05 against this screen at "
           "0.05 and at 0.01:", ""]
    md += _table(["Seat", "S", "p", "Stored at 0.05", "Here at 0.05", "Here at 0.01"],
                 [[r["ref"].split("out/main/", 1)[-1].replace("/reference_free.json", ""),
                   _f(r["got_S"]), _p(r["got_p"]), _f(r["stored_decision"]),
                   _f(r["got_decision_0.05"]), _f(r["got_decision_0.01"])] for r in rf])
    md += ["## Rejections at 0.01, full registry", "",
           "Each cell is rejections over subjects, with the exact 95% interval. NEGATIVE pools "
           "NULL, BASE and PLACEBO.", ""]
    md += _counts_md(counts, "full")
    md += ["## Rejections at 0.01, three guaranteed axes", ""]
    md += _counts_md(counts, "guaranteed3")
    md += ["## Agreement with the registered test, full registry", ""]
    md += _table(["Variant", "Group", "Subjects", "Both reject", "Registered only",
                  "Screen only", "Neither", "Same name"],
                 [[a["variant"], a["group"], str(a["n"]), str(a["both_reject"]),
                   str(a["registered_only"]), str(a["screen_only"]), str(a["neither"]),
                   str(a["same_name"])] for a in agree if a["subset"] == "full"
                  and a["variant"] in SCREEN and a["n"]])
    md += ["## User-awareness subjects", ""]
    md += _ua_md(rows)
    md += ["## Every subject, full registry", ""]
    md += _per_run_md(rows, "full")
    md += ["## Every subject, three guaranteed axes", ""]
    md += _per_run_md(rows, "guaranteed3")
    md += ["## Rows that cannot run", ""]
    md += _table(["Subject", "Variant", "Subset", "Reason"],
                 [[s["sid"], s["kind"], s["subset"], s["status"]] for s in skipped])
    md += ["## Reading", ""]
    md += reading(rows, counts, agree, checks, "reading")
    md += ["## Outputs", ""]
    md += _table(["File", "Content"], [
        ["manifest.csv", "one row per (subject, task kind, axis subset), status"],
        ["tasks.jsonl", "one line per finished task, as computed"],
        ["results.json", "settings, subject metadata, every result, rows that cannot run"],
        ["runs/<subject>.json", "one file per subject"],
        ["screen_table.csv", "one row per (subject, variant, axis subset)"],
        ["rejection_counts.csv", "rejections per variant and group, Clopper-Pearson 95%"],
        ["registered_agreement.csv", "decisions and names against the registered test"],
        ["t_grids.npz", "observed t grid per task; null maxima for the mean and median variants"],
        ["t_grids_index.json", "candidates and axes order of every grid"],
        ["perm_abs_median.json", "observed and permuted pooled median |t|, and their ratio"],
        ["reproduce_check.json", "every comparison with a stored record"],
        ["settings.json", "settings"], ["task_grids/", "the per-task grid files merged above"]])
    (out / "README.md").open("x").write("\n".join(md) + "\n")
