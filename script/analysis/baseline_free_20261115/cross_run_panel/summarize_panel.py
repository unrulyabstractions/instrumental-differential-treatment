"""Fold the ``cross_run_panel`` outputs into its tables, per-run files and README.

    .venv/bin/python -m script.analysis.baseline_free_20261115.cross_run_panel.run_panel summarize

Reads only files that ``run_panel`` wrote (plus the stored records it was
checked against) and writes ``settings.json``, ``reproduce_check.json``,
``panel_table.csv``, ``panel_primary.csv``, ``false_positive_summary.csv``,
``placebo/placebo_summary.json``, ``runs/<member>.json`` and ``README.md``.
Every number in the README is generated here from those files.
"""

from __future__ import annotations

import csv
import io
import json
import math
from pathlib import Path

import numpy as np

from script.analysis.baseline_free_20261115.cross_run_panel import run_panel as rp
from src.common.file_io import load_json, read_jsonl

OUT = rp.OUT
NULL_TYPE = [k for k in rp.MAIN15 if rp.role_of(k) != "positive"]
NULL_CONTROLS = [k for k in NULL_TYPE if rp.role_of(k) == "null"]
BASES = [k for k in NULL_TYPE if rp.role_of(k) == "base"]
RESAMPLED_P = ("values", "axes", "exact_values", "resampled_values", "resampled_axes")
STAT_KEY = {"pooled_max": "S", "fixed_candidate": "S_row", "cellwise": "Z",
            "re_residual": "residual"}
PRETTY_VARIANT = {"pooled_max": "pooled maximum", "fixed_candidate": "fixed candidate",
                  "cellwise": "cellwise", "re_residual": "random-effects residual"}


def fmt_p(p: float) -> str:
    if p is None or (isinstance(p, float) and math.isnan(p)):
        return "n/a"
    return "<0.0001" if p < 0.0001 else (f"{p:.4f}" if p < 0.1 else f"{p:.3f}")


def file_key(member: str) -> str:
    return member.replace("#h", "__matched_half1")


def stat_of(res: dict, variant: str) -> float:
    if variant == "pooled_max":
        return res["S"]
    if variant == "fixed_candidate":
        return res["fixed_candidate"][rp.TARGET_CANDIDATE]["S_row"]
    if variant == "cellwise":
        return res["cellwise"]["Z"]
    return res["re_residual"]["residual"]


def at_floor(res: dict, variant: str) -> bool:
    """The member's statistic exceeds every reference member's own maximum."""
    if variant == "pooled_max":
        n = len(res["_ref"])
        return res["pooled_max"]["member_rank_p"] == 1.0 / (n + 1)
    if variant == "fixed_candidate":
        fc = res["fixed_candidate"][rp.TARGET_CANDIDATE]
        return fc["member_rank_p"] == 1.0 / (fc["n_reference_rows"] + 1)
    if variant == "cellwise":
        n = len(res["_ref"])
        return res["cellwise"]["rank_p"] == 1.0 / (n + 1)
    return False


def registered_of(member: str, sharp: dict) -> dict | None:
    if member in ("base_A_half1", "base_A_half2"):
        r = sharp["base_A_half1|registered|base_A_half2"]
        return {"S": r["S"], "p": r["p"], "named": r["named_by_rule"],
                "reference": "base_A_half1 against base_A_half2"}
    r = sharp.get(f"{member}|registered|base_A")
    if r is None:
        return None
    return {"S": r["S"], "p": r["p"], "named": r["named_by_rule"], "reference": "base_A"}


def sharp_of(member: str, grid: str, sharp: dict) -> dict | None:
    r = sharp.get(f"{member}|target_only_{grid}")
    return None if r is None else {"S": r["S"], "p": r["p"], "named": r["named_by_rule"],
                                   "argmax": r["argmax_candidate"]}


def iter_tests(panel_record: dict):
    for pname, prec in panel_record["panels"].items():
        for member, res in prec["results"].items():
            for pool in rp.POOLS:
                for grid in rp.GRIDS:
                    r = dict(res[pool][grid])
                    r["_ref"] = res[pool]["reference_members"]
                    yield pname, member, pool, grid, r


def build_rows(panel_record: dict, sharp: dict) -> list[dict]:
    rows = []
    for pname, member, pool, grid, r in iter_tests(panel_record):
        reg = registered_of(member, sharp)
        sh = sharp_of(member, grid, sharp)
        for v in rp.VARIANTS:
            for pt in rp.P_TYPES[v]:
                p = rp.primary_p(r, v, pt)
                rows.append({
                    "panel": pname, "member": member, "role": rp.role_of(member),
                    "pool": pool, "grid": grid, "variant": v, "p_type": pt,
                    "primary": (pool == rp.PRIMARY["pool"] and grid == rp.PRIMARY["grid"]
                                and pt == rp.PRIMARY["p"][v]),
                    "statistic": stat_of(r, v), "p": p, "reject_0.01": p <= rp.ALPHA,
                    "argmax_candidate": (r["cellwise"]["argmax_candidate"] if v == "cellwise"
                                         else rp.TARGET_CANDIDATE if v == "fixed_candidate"
                                         else r["argmax_candidate"]),
                    "named": rp.named_of(r, v, p),
                    "n_reference_members": len(r["_ref"]),
                    "statistic_above_every_reference_maximum": at_floor(r, v),
                    "registered_S": reg["S"] if reg else None,
                    "registered_p": reg["p"] if reg else None,
                    "registered_named": reg["named"] if reg else None,
                    "registered_reference": reg["reference"] if reg else None,
                    "target_only_sharp_p": sh["p"] if sh else None,
                    "target_only_sharp_named": sh["named"] if sh else None})
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0]), lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: (repr(v) if isinstance(v, float) else v) for k, v in r.items()})
    rp.write_new(path, buf.getvalue(), text=True)


def fp_summary(rows: list[dict], sharp: dict) -> list[dict]:
    out = []
    by = {}
    for r in rows:
        if r["panel"] not in ("main", "alt_C1s0-11"):
            continue
        by.setdefault((r["panel"], r["pool"], r["grid"], r["variant"], r["p_type"]), []).append(r)
    for (pname, pool, grid, v, pt), rs in by.items():
        nt = [r for r in rs if r["role"] != "positive"]
        co = next(r for r in rs if r["member"] == "contextual_optimism")
        k = sum(r["reject_0.01"] for r in nt)
        lo, hi = rp.clopper_pearson(k, len(nt))
        reg_known = [r for r in nt if r["registered_p"] is not None]
        agree_null = sum(r["reject_0.01"] == (r["registered_p"] <= rp.ALPHA) for r in reg_known)
        resampled = pt in RESAMPLED_P
        equiv = (sum(r["reject_0.01"] == r["statistic_above_every_reference_maximum"] for r in rs)
                 if resampled else None)
        out.append({
            "panel": pname, "pool": pool, "grid": grid, "variant": v, "p_type": pt,
            "primary": co["primary"], "n_null_type": len(nt), "n_reject_null_type": k,
            "rate": k / len(nt), "cp95_low": lo, "cp95_high": hi,
            "n_reject_null_controls": sum(r["reject_0.01"] for r in nt
                                          if rp.role_of(r["member"]) == "null"),
            "n_null_controls": sum(rp.role_of(r["member"]) == "null" for r in nt),
            "n_reject_bases": sum(r["reject_0.01"] for r in nt
                                  if rp.role_of(r["member"]) == "base"),
            "n_bases": sum(rp.role_of(r["member"]) == "base" for r in nt),
            "rejected_null_type": ";".join(f"{r['member']}({r['named']})" for r in nt
                                           if r["reject_0.01"]),
            "contextual_optimism_p": co["p"], "contextual_optimism_reject": co["reject_0.01"],
            "contextual_optimism_named": co["named"],
            "agrees_with_registered_on_positive": bool(co["reject_0.01"]
                                                       and co["named"] == "anthropic"),
            "agrees_with_registered_on_null_type": agree_null,
            "n_null_type_with_registered": len(reg_known),
            "decision_equals_above_every_reference_maximum": equiv,
            "n_members": len(rs)})
    # Level 0 and Level 5 reference rows: the target-only sharp null and the registered test.
    for grid in rp.GRIDS:
        nt = [sharp[f"{m}|target_only_{grid}"] for m in NULL_TYPE]
        k = sum(r["p"] <= rp.ALPHA for r in nt)
        lo, hi = rp.clopper_pearson(k, len(nt))
        co = sharp[f"contextual_optimism|target_only_{grid}"]
        out.append({"panel": "none (sharp null, Level 0)", "pool": "", "grid": grid,
                    "variant": "target_only_permutation", "p_type": "permutation",
                    "primary": grid == "median", "n_null_type": len(nt), "n_reject_null_type": k,
                    "rate": k / len(nt), "cp95_low": lo, "cp95_high": hi,
                    "n_reject_null_controls": sum(sharp[f"{m}|target_only_{grid}"]["p"] <= rp.ALPHA
                                                  for m in NULL_CONTROLS),
                    "n_null_controls": len(NULL_CONTROLS),
                    "n_reject_bases": sum(sharp[f"{m}|target_only_{grid}"]["p"] <= rp.ALPHA
                                          for m in BASES),
                    "n_bases": len(BASES),
                    "rejected_null_type": ";".join(
                        f"{m}({sharp[f'{m}|target_only_{grid}']['argmax_candidate']})"
                        for m in NULL_TYPE if sharp[f"{m}|target_only_{grid}"]["p"] <= rp.ALPHA),
                    "contextual_optimism_p": co["p"],
                    "contextual_optimism_reject": co["p"] <= rp.ALPHA,
                    "contextual_optimism_named": co["named_by_rule"],
                    "agrees_with_registered_on_positive": bool(co["p"] <= rp.ALPHA and
                                                               co["named_by_rule"] == "anthropic"),
                    "agrees_with_registered_on_null_type": None,
                    "n_null_type_with_registered": None,
                    "decision_equals_above_every_reference_maximum": None, "n_members": 15})
    reg = [sharp[f"{m}|registered|base_A"] for m in NULL_TYPE if m != "base_A"]
    k = sum(r["p"] <= rp.ALPHA for r in reg)
    lo, hi = rp.clopper_pearson(k, len(reg))
    co = sharp["contextual_optimism|registered|base_A"]
    out.append({"panel": "none (registered test, base A, Level 5)", "pool": "", "grid": "",
                "variant": "registered", "p_type": "permutation", "primary": True,
                "n_null_type": len(reg), "n_reject_null_type": k, "rate": k / len(reg),
                "cp95_low": lo, "cp95_high": hi,
                "n_reject_null_controls": sum(sharp[f"{m}|registered|base_A"]["p"] <= rp.ALPHA
                                              for m in NULL_CONTROLS),
                "n_null_controls": len(NULL_CONTROLS),
                "n_reject_bases": sum(sharp[f"{m}|registered|base_A"]["p"] <= rp.ALPHA
                                      for m in BASES if m != "base_A"),
                "n_bases": len(BASES) - 1, "rejected_null_type": "",
                "contextual_optimism_p": co["p"], "contextual_optimism_reject": co["p"] <= rp.ALPHA,
                "contextual_optimism_named": co["named_by_rule"],
                "agrees_with_registered_on_positive": True,
                "agrees_with_registered_on_null_type": None, "n_null_type_with_registered": None,
                "decision_equals_above_every_reference_maximum": None, "n_members": 14})
    return out


def placebo_summary(panel_record: dict) -> dict:
    reps = list(read_jsonl(OUT / "placebo" / "placebo_replicates.jsonl"))
    out: dict = {"n_replicates_by_design": {}, "rates": {}, "single_split": {}}
    for design in ("placebo_halves", "placebo_matched"):
        rs = sorted((r for r in reps if r["design"] == design), key=lambda r: r["replicate"])
        if [r["replicate"] for r in rs] != list(range(len(rs))):
            raise SystemExit(f"{design}: replicates are not 0..n-1")
        out["n_replicates_by_design"][design] = len(rs)
        keys = [k for k in rs[0]["base_A_half1"] if not k.endswith("|S")]
        rates = {}
        for k in keys:
            entry = {}
            for half in ("base_A_half1", "base_A_half2"):
                n_rej = sum(r[half][k] <= rp.ALPHA for r in rs)
                entry[half] = {"count_le_0.01": n_rej, "share": n_rej / len(rs),
                               "cp95": rp.clopper_pearson(n_rej, len(rs))}
            either = sum(min(r["base_A_half1"][k], r["base_A_half2"][k]) <= rp.ALPHA for r in rs)
            entry["either_half"] = {"count_le_0.01": either, "share": either / len(rs),
                                    "cp95": rp.clopper_pearson(either, len(rs))}
            rates[k] = entry
        out["rates"][design] = rates
        single = {}
        for half in ("base_A_half1", "base_A_half2"):
            res = panel_record["panels"][design]["results"][half]
            single[half] = {f"{pool}|{g}|{v}|{pt}": rp.primary_p(res[pool][g], v, pt)
                            for pool in rp.POOLS for g in rp.GRIDS for v in rp.VARIANTS
                            for pt in rp.P_TYPES[v]}
        out["single_split"][design] = single
    return out


def grid_checks() -> list[dict]:
    """Target-only S from this family's grids against every stored counterpart."""
    index = load_json(OUT / "t_grids_target_only_index.json")["members"]
    pa = load_json(rp.PARTA)["results"]
    checks = []
    for member, pk in rp.PARTA_KEY.items():
        for g in rp.GRIDS:
            st = pa[f"{pk}|target_only_{g}|full"]["S"]
            got = index[member][f"S_{g}"]
            checks.append({"what": f"S of grid {g} vs partA {pk}|target_only_{g}|full",
                           "stored": st, "got": got, "match": got == st})
    st = pa["auditbench_contextual_optimism|base_only_median|full"]["S"]
    checks.append({"what": "S of base_A median grid vs partA base_only_median",
                   "stored": st, "got": index["base_A"]["S_median"],
                   "match": index["base_A"]["S_median"] == st})
    for member in ("contextual_optimism", *rp.CONTROLS):
        root = (rp.AB / "contextual_optimism/judge_mini" if member == "contextual_optimism"
                else rp.AB / f"controls/{member}/judge_mini")
        rf = load_json(root / "compare/reference_free.json")
        for seat, key in (("target", member), ("base", "base_A")):
            st = rf["seats"][seat]["statistic"]
            got = index[key]["S_median"]
            checks.append({"what": f"S of {key} median grid vs {member} reference_free.json "
                                   f"seat {seat}", "stored": st, "got": got, "match": got == st})
    return checks


def sharp_screen_checks() -> dict:
    """This family's grids against the sharp-null screen's, where that family has them."""
    grids, _, _ = rp.load_grids()
    names = {"contextual_optimism": ["auditbench_contextual_optimism"],
             **{c: [f"auditbench_{c}"] for c in rp.CONTROLS},
             "sd_ai_welfare_poisoning": ["nullext_sd_ai_welfare_poisoning"],
             "sd_emotional_bond": ["nullext_sd_emotional_bond"],
             "base_A": ["base_A"], "base_B": ["nullext_base_B", "base_B"],
             "C1": ["C1", "base_C1", "nullext_C1"], "C2": ["C2", "base_C2", "nullext_C2"]}
    task_dir = rp.SHARP_SCREEN.parent / "task_grids"
    out = {"source": None, "checks": []}
    if rp.SHARP_SCREEN.exists():
        z = np.load(rp.SHARP_SCREEN)
        out["source"] = str(rp.SHARP_SCREEN)
        lookup = {f: z[f] for f in z.files}

        def get(stem):
            return lookup.get(f"{stem}__t")
    elif task_dir.exists():
        out["source"] = str(task_dir)

        def get(stem):
            p = task_dir / f"{stem}.npz"
            if not p.exists():
                return None
            with np.load(p) as f:
                return f["t"]
    else:
        out["note"] = "the sharp-null screen has written no grids"
        return out
    for member, cands in names.items():
        for g in rp.GRIDS:
            found = None
            for c in cands:
                arr = get(f"{c}__{g}__full")
                if arr is not None:
                    found = (c, arr)
                    break
            if found is None:
                out["checks"].append({"member": member, "grid": g, "found": False})
                continue
            out["checks"].append({"member": member, "grid": g, "found": True,
                                  "their_subject": found[0],
                                  "exactly_equal": bool(np.array_equal(
                                      found[1], grids[member][g], equal_nan=True))})
    return out


def runs_files(panel_record: dict, sharp: dict, rows: list[dict]) -> list[str]:
    written = []
    index = load_json(OUT / "t_grids_target_only_index.json")["members"]
    members = sorted({r["member"] for r in rows})
    for m in members:
        per_panel = {}
        for pname, prec in panel_record["panels"].items():
            if m in prec["results"]:
                per_panel[pname] = prec["results"][m]
        primary = [r for r in rows if r["member"] == m and r["primary"]]
        rec = {"member": m, "role": rp.role_of(m), "input": index[m],
               "registered": registered_of(m, sharp),
               "target_only_sharp_null": {g: sharp_of(m, g, sharp) for g in rp.GRIDS},
               "primary_results": [{k: r[k] for k in ("panel", "variant", "p_type", "statistic",
                                                      "p", "reject_0.01", "argmax_candidate",
                                                      "named", "n_reference_members")}
                                   for r in primary],
               "panels": per_panel}
        path = OUT / "runs" / f"{file_key(m)}.json"
        rp.write_new(path, rec)
        written.append(str(path))
    return written


# ----------------------------------------------------------------------------
# README
# ----------------------------------------------------------------------------
def md_table(head: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(h.replace("|", "\\|") for h in head) + " |",
             "|" + "|".join("---" for _ in head) + "|"]
    lines += ["| " + " | ".join(str(c).replace("|", "\\|") for c in r) + " |" for r in rows]
    return "\n".join(lines)


def readme(settings, repro, rows, fps, placebo, ua, panel_record, sharp, index) -> str:
    prim = {(r["panel"], r["member"], r["variant"]): r for r in rows if r["primary"]}
    rank = {(r["panel"], r["member"], r["variant"]): r for r in rows
            if r["pool"] == rp.PRIMARY["pool"] and r["grid"] == rp.PRIMARY["grid"]
            and r["p_type"] in ("member_rank", "rank")}
    parts = ["# Model-panel reference on target-only statistics", ""]
    parts += ["This folder holds the cross-run panel family of the baseline-free appendix (B72). "
              "No base model enters any panel test. A base enters only the reproduction gate "
              "and the registered result printed beside each member.", ""]
    parts += ["## What is tested", "",
              "H0 (Level 3): a member's largest target-only |t| is exchangeable with maxima "
              "drawn from the other members' grids. The members share the roster, the prompts, "
              "the axes and the judge. A rejection claims that the member is atypical among "
              "these models. A bias that every member shares is invisible to the test.", ""]
    parts += ["## Settings", "", md_table(["Setting", "Value"], [
        ["Promptset", "contextual_optimism: 6 candidates, 36 instructions, 101 axes, judge "
                      "gpt-5-mini, level 2"],
        ["Target-only grids", "signed paired t per (candidate, axis) of each candidate's cell "
                              "rate minus the median (or mean) of the other candidates"],
        ["Resampling", f"n_boot {settings['n_boot']:,}, schemes values and axes, maximum of M "
                       "draws against S"],
        ["Seeds", settings["seeds"]["panel"]],
        ["Permutation tests", f"{settings['n_permutations']:,} permutations, seed "
                              f"{settings['seed']}"],
        ["Level", f"alpha {settings['alpha']}"],
        ["Primary", f"pool {rp.PRIMARY['pool']}, grid {rp.PRIMARY['grid']}, p per variant "
                    + ", ".join(f"{v}: {p}" for v, p in rp.PRIMARY['p'].items())],
        ["Pools", "; ".join(f"{k}: {v}" for k, v in settings["pools"].items())],
        ["Variants", "; ".join(f"{k}: {v}" for k, v in settings["variants"].items())],
        ["Placebo", settings["placebo"]],
        ["Cost", "$0; no API or GPU call"]]), ""]
    parts += ["## Inputs", "", md_table(
        ["Member", "Index", "Role", "Kind", "Verdict file", "sha256", "Replies", "S median",
         "S mean"],
        [[m, v["index"], v["role"], v["kind"], f"`{v['path']}`", v["sha256"][:12],
          v["n_responses"], f"{v['S_median']:.3f}", f"{v['S_mean']:.3f}"]
         for m, v in sorted(index.items(), key=lambda kv: kv[1]["index"])]), "",
        "A member ending in `#h` is half 1 of that member's split, used only in the "
        "matched placebo.", ""]
    parts += ["## Reproduction", "", md_table(["Check", "Compared", "Exact matches"], [
        [c["what"], c["n"], c["n_match"]] for c in repro["summary"]]), ""]
    # Main results table
    head = ["Member", "Role", "Registered p (base A)", "Target-only p",
            "Pooled max p", "Member rank p", "Fixed candidate p", "Cellwise p",
            "RE residual p", "Named (pooled max)"]
    body = []
    for m in rp.MAIN15:
        reg = registered_of(m, sharp)
        sh = sharp_of(m, rp.PRIMARY["grid"], sharp)
        body.append([m, rp.role_of(m), fmt_p(reg["p"]) if reg else "none (the base)",
                     fmt_p(sh["p"]),
                     fmt_p(prim[("main", m, "pooled_max")]["p"]),
                     fmt_p(rank[("main", m, "pooled_max")]["p"]),
                     fmt_p(prim[("main", m, "fixed_candidate")]["p"]),
                     fmt_p(prim[("main", m, "cellwise")]["p"]),
                     fmt_p(prim[("main", m, "re_residual")]["p"]),
                     prim[("main", m, "pooled_max")]["named"] or "none"])
    parts += ["## Results", "",
              "### Every member of the 15-member panel, primary pool and grid", "",
              md_table(head, body), "",
              "Target-only p is the sharp-null permutation test on the same grid (Level 0). "
              "Member rank p is the member's rank among the reference members' own maxima. "
              "Its floor is 1/15 for contextual_optimism and 1/14 for a null-type member.", ""]
    # FP summary at primary pool and grid, main panel
    fp_main = [f for f in fps if f["panel"] == "main" and f["pool"] == rp.PRIMARY["pool"]
               and f["grid"] == rp.PRIMARY["grid"]]
    fp_rows = [[PRETTY_VARIANT[f["variant"]], f["p_type"], f"{f['n_reject_null_type']}/"
                f"{f['n_null_type']}", f"[{f['cp95_low']:.3f}, {f['cp95_high']:.3f}]",
                f"{f['n_reject_null_controls']}/{f['n_null_controls']}",
                f"{f['n_reject_bases']}/{f['n_bases']}", f["rejected_null_type"] or "none",
                fmt_p(f["contextual_optimism_p"]), f["contextual_optimism_named"] or "none",
                "" if f["decision_equals_above_every_reference_maximum"] is None else
                f"{f['decision_equals_above_every_reference_maximum']}/{f['n_members']}"]
               for f in fp_main]
    for f in fps:
        if f["panel"].startswith("none") and (f["grid"] in ("", rp.PRIMARY["grid"])):
            fp_rows.append([f["variant"], f["p_type"], f"{f['n_reject_null_type']}/"
                            f"{f['n_null_type']}", f"[{f['cp95_low']:.3f}, {f['cp95_high']:.3f}]",
                            f"{f['n_reject_null_controls']}/{f['n_null_controls']}",
                            f"{f['n_reject_bases']}/{f['n_bases']}",
                            f["rejected_null_type"] or "none", fmt_p(f["contextual_optimism_p"]),
                            f["contextual_optimism_named"] or "none", ""])
    parts += ["### False positives at 0.01 over the 14 null-type members", "",
              md_table(["Variant", "p", "Null-type rejected", "Clopper-Pearson 95%",
                        "Null controls", "Bases", "Which (named)", "contextual_optimism p",
                        "Named", "Decision equals top of panel"], fp_rows), "",
              "The 14 tests share one panel, so the interval is nominal. "
              "\"Decision equals top of panel\" counts the members whose decision at 0.01 "
              "equals the event that their statistic exceeds every reference member's own "
              "maximum.", ""]
    # Probability that a resampled maximum draws the pool's largest value.
    inc_rows = []
    main_res = panel_record["panels"]["main"]["results"]
    for pool in rp.POOLS:
        for g in rp.GRIDS:
            vals, ks = [], []
            for m in rp.MAIN15:
                pm = main_res[m][pool][g]["pooled_max"]
                vals.append(1.0 - (1.0 - 1.0 / pm["n_ref"]) ** pm["M"])
                ks.append(len(main_res[m][pool]["reference_members"]))
            inc_rows.append([pool, g, f"{min(ks)} to {max(ks)}",
                             f"{min(vals):.4f} to {max(vals):.4f}",
                             f"{1 / (max(ks) + 1):.4f} to {1 / (min(ks) + 1):.4f}"])
    parts += ["### Why the resampled p reduces to the top of the panel", "",
              md_table(["Pool", "Grid", "Reference members K",
                        "P(a resampled maximum draws the pool's largest value)",
                        "1/(K + 1)"], inc_rows), "",
              "The probability is 1 - (1 - 1/n_ref)^M for the values scheme, with n_ref "
              "pooled cells and M draws.", ""]
    # Contextual optimism across pools and grids
    co_rows = []
    for pool in rp.POOLS:
        for g in rp.GRIDS:
            r = [x for x in rows if x["panel"] == "main" and x["member"] == "contextual_optimism"
                 and x["pool"] == pool and x["grid"] == g]
            get = {(x["variant"], x["p_type"]): x for x in r}
            co_rows.append([pool, g] + [fmt_p(get[(v, pt)]["p"]) for v, pt in (
                ("pooled_max", "values"), ("pooled_max", "axes"), ("pooled_max", "member_rank"),
                ("fixed_candidate", "values"), ("fixed_candidate", "member_rank"),
                ("cellwise", "resampled_values"), ("cellwise", "param_bonferroni"),
                ("cellwise", "rank"), ("re_residual", "t"))])
    parts += ["### contextual_optimism in every pool and grid", "",
              md_table(["Pool", "Grid", "Pooled max, values", "Pooled max, axes",
                        "Pooled max, rank", "Fixed, values", "Fixed, rank",
                        "Cellwise, resampled", "Cellwise, Bonferroni t", "Cellwise, rank",
                        "RE residual"], co_rows), ""]
    # FP across pools and grids for the primary p of each variant
    grid_rows = []
    for pname in ("main", "alt_C1s0-11"):
        for pool in rp.POOLS:
            for g in rp.GRIDS:
                fs = {f["variant"]: f for f in fps if f["panel"] == pname and f["pool"] == pool
                      and f["grid"] == g and f["p_type"] == rp.PRIMARY["p"][f["variant"]]}
                grid_rows.append([pname, pool, g] + [
                    f"{fs[v]['n_reject_null_type']}/{fs[v]['n_null_type']}" for v in rp.VARIANTS]
                    + [fmt_p(fs[v]["contextual_optimism_p"]) for v in rp.VARIANTS])
    parts += ["### Null-type rejections and contextual_optimism p in every pool, grid and panel",
              "", md_table(["Panel", "Pool", "Grid"] + [f"{PRETTY_VARIANT[v]}, nulls"
                                                       for v in rp.VARIANTS]
                           + [f"{PRETTY_VARIANT[v]}, CO p" for v in rp.VARIANTS], grid_rows), ""]
    # The paper's nine-run cross() on target-only grids, beside the stored base-referenced one.
    stored = load_json(rp.POOLED / "cross_run.json")
    f9_rows = []
    for key in rp.FAMILY:
        row = [key.removeprefix("auditbench_")]
        for pool in rp.GATE_POOLS:
            row.append(fmt_p(stored[pool][key]["values"]["p_ref"]))
            for g in rp.GRIDS:
                row.append(fmt_p(panel_record["family9_target_only"][g][pool][key]["values"][
                    "p_ref"]))
        f9_rows.append(row)
    count_row = ["nulls at or below 0.01"]
    for pool in rp.GATE_POOLS:
        count_row.append(f"{sum(stored[pool][k]['values']['p_ref'] <= rp.ALPHA for k in rp.FAMILY_NULLS)}/8")
        for g in rp.GRIDS:
            count_row.append(f"{sum(panel_record['family9_target_only'][g][pool][k]['values']['p_ref'] <= rp.ALPHA for k in rp.FAMILY_NULLS)}/8")
    f9_rows.append(count_row)
    head9 = ["Run"]
    for pool in rp.GATE_POOLS:
        head9 += [f"{pool}, with base A", f"{pool}, target only median",
                  f"{pool}, target only mean"]
    parts += ["### The paper's nine-run cross-run reference on target-only grids", "",
              md_table(head9, f9_rows), "",
              "The test uses the code, runs, pools and seeds of the paper's cross-run "
              "reference. Only the grid changes, from the base-referenced excess to the "
              "target-only contrast. The table shows the values scheme.", ""]
    # Placebo
    pl_rows = []
    for design in ("placebo_halves", "placebo_matched"):
        n = placebo["n_replicates_by_design"][design]
        for v in rp.VARIANTS:
            pt = rp.PRIMARY["p"][v]
            k = f"{rp.PRIMARY['pool']}|{rp.PRIMARY['grid']}|{v}|{pt}"
            e = placebo["rates"][design][k]
            single = placebo["single_split"][design]
            pl_rows.append([design, PRETTY_VARIANT[v], pt,
                            fmt_p(single["base_A_half1"][k]), fmt_p(single["base_A_half2"][k]),
                            f"{e['base_A_half1']['count_le_0.01']}/{n}",
                            f"{e['base_A_half2']['count_le_0.01']}/{n}",
                            f"{e['either_half']['count_le_0.01']}/{n}",
                            f"[{e['base_A_half1']['cp95'][0]:.3f}, "
                            f"{e['base_A_half1']['cp95'][1]:.3f}]"])
        for v, pt in (("pooled_max", "member_rank"), ("cellwise", "rank")):
            k = f"{rp.PRIMARY['pool']}|{rp.PRIMARY['grid']}|{v}|{pt}"
            e = placebo["rates"][design][k]
            single = placebo["single_split"][design]
            pl_rows.append([design, PRETTY_VARIANT[v], pt,
                            fmt_p(single["base_A_half1"][k]), fmt_p(single["base_A_half2"][k]),
                            f"{e['base_A_half1']['count_le_0.01']}/{n}",
                            f"{e['base_A_half2']['count_le_0.01']}/{n}",
                            f"{e['either_half']['count_le_0.01']}/{n}",
                            f"[{e['base_A_half1']['cp95'][0]:.3f}, "
                            f"{e['base_A_half1']['cp95'][1]:.3f}]"])
    parts += ["### Placebo: the two split halves of base A as two members", "",
              md_table(["Design", "Variant", "p", "Single split, half 1", "Single split, half 2",
                        "Half 1 at or below 0.01", "Half 2 at or below 0.01", "Either half",
                        "Half 1 Clopper-Pearson 95%"], pl_rows), "",
              "In `placebo_halves` the halves (8 samples per cell) replace base A among "
              "full-size members. In `placebo_matched` every member is a split half, so all "
              "members hold the same number of samples. The single split is the paper's "
              "placebo replicate 0 of base A.", ""]
    # UA
    ua_rows = []
    for g in rp.GRIDS:
        d = ua["descriptive"][g]
        for s in d["S"]:
            others = [d["S"][o] for o in d["S"] if o != s]
            ua_rows.append([g, s, f"{d['S'][s]:.3f}", d["argmax_candidate"][s],
                            "yes" if d["S"][s] > max(others) else "no",
                            ", ".join(f"{c} {v[s]['row_max_abs_t']:.2f} "
                                      f"(rank {v[s]['row_rank_within_subject']})"
                                      for c, v in d["safety_identities"].items())])
    parts += ["### User-awareness subjects: a descriptive panel of three served models", "",
              md_table(["Grid", "Subject", "S", "Identity holding S", "S above both others",
                        "Safety identities: row max |t| (rank of 10)"], ua_rows), "",
              "We compute no p. With three members a rank p cannot fall below 1/3. A "
              "leave-one-out SD rests on two values.", ""]
    parts += ["## Reading", ""] + reading(fps, placebo, prim, rows, panel_record, ua) + [""]
    parts += ["## Files", "", md_table(["File", "Contents"], [
        ["`settings.json`", "settings, seeds, inputs with sha256, pools, variants, primary"],
        ["`reproduce_check.json`", "every reproduction check and its result"],
        ["`gate/reproduce_gate.json`", "the base-referenced cross-run reference rerun"],
        ["`t_grids_target_only.npz`, `t_grids_target_only_index.json`",
         "target-only t grids of every member, both contrasts"],
        ["`sharp/sharp_null.json`", "target-only and registered permutation tests per member"],
        ["`cross_run_target_only.json`", "every panel test: panels, members, pools, grids, "
                                         "variants; and the paper's nine-run cross() on "
                                         "target-only grids"],
        ["`panel_table.csv`", "one row per panel, member, pool, grid, variant and p"],
        ["`panel_primary.csv`", "the primary rows only"],
        ["`false_positive_summary.csv`", "null-type rejections with Clopper-Pearson intervals"],
        ["`placebo/placebo_replicates.jsonl`, `placebo/placebo_summary.json`",
         "200 placebo splits per design"],
        ["`ua/ua_panel.json`", "user-awareness grids, reproduction and descriptive panel"],
        ["`runs/<member>.json`", "one file per member with its inputs and every result"],
        ["`verify/verify_report.json`", "independent recomputation of key numbers from the "
                                        "verdicts and grids"],
        ["`logs/`", "console logs of every command"]]), ""]
    parts += ["## Runs not completed", "", repro["not_completed"] or "None.", ""]
    return "\n".join(parts)


def reading(fps, placebo, prim, rows, panel_record, ua) -> list[str]:
    """The reading, built from the summary rows so every clause follows the data."""
    pool0, grid0 = rp.PRIMARY["pool"], rp.PRIMARY["grid"]
    co = {v: prim[("main", "contextual_optimism", v)] for v in rp.VARIANTS}
    hit = [PRETTY_VARIANT[v] for v in rp.VARIANTS
           if co[v]["reject_0.01"] and co[v]["named"] == "anthropic"]
    miss = [v for v in rp.VARIANTS if not co[v]["reject_0.01"]]
    main = panel_record["panels"]["main"]["results"]
    out = []
    p1 = ("The panel compares each member with other models on the same prompts. "
          "No base enters the panel. On target-only statistics the " + _join(hit)
          + " variants reject contextual_optimism at 0.01 and name Anthropic.")
    if "cellwise" in miss:
        cw = main["contextual_optimism"][pool0][grid0]["cellwise"]
        n_ref = len(main["contextual_optimism"][pool0]["reference_members"])
        p1 += (" The cellwise variant does not reject it in the primary pool and grid. "
               + ("In that comparison a null-type member holds a larger cellwise maximum. "
                  "The pool therefore already holds a value above contextual_optimism's."
                  if cw["rank_p"] > 1.0 / (n_ref + 1) else ""))
    p1 += " The registered test also rejects contextual_optimism and names Anthropic."
    p1 += (" We therefore contend that the panel agrees with the registered test on the one "
           "positive member, in every variant except the cellwise one.") if miss == ["cellwise"] \
        else " We therefore contend that the panel and the registered test agree on the positive."
    out += [p1, ""]

    tests = [(r["member"], r) for r in rows if r["panel"] == "main" and r["pool"] == pool0
             and r["grid"] == grid0 and r["variant"] == "pooled_max" and r["p_type"] == "values"]
    incl = []
    for m, _ in tests:
        pm = main[m][pool0][grid0]["pooled_max"]
        incl.append(1.0 - (1.0 - 1.0 / pm["n_ref"]) ** pm["M"])
    eq = [r for r in rows if r["p_type"] in RESAMPLED_P]
    eq_all = all(r["reject_0.01"] == r["statistic_above_every_reference_maximum"] for r in eq)
    all_incl = []
    for pool in rp.POOLS:
        for g in rp.GRIDS:
            for m in rp.MAIN15:
                pm = main[m][pool][g]["pooled_max"]
                all_incl.append(1.0 - (1.0 - 1.0 / pm["n_ref"]) ** pm["M"])
    p2 = ("Each resampled panel p reduces to one event. A resampled maximum draws the "
          "pool's single largest value with the probability in the table above. "
          + ("That probability exceeds 0.01 in every pool and grid. "
             if min(all_incl) > rp.ALPHA else "")
          + "A resampled p at or below 0.01 therefore occurs only when the member's statistic "
          "exceeds every value in the pool. "
          + ("Every resampled decision in every panel, pool and grid equals that event. "
             if eq_all else "Most resampled decisions equal that event. ")
          + "Under exchangeability the event has the probability in the last column of "
          "that table. The member rank p reports the same event at its honest floor. "
          "We therefore posit that the resampled p overstates the evidence.")
    out += [p2, ""]

    allrow = [f for f in fps if f["panel"] == "main" and f["pool"] in ("nulls_all_rows",
                                                                       "all_all_rows")
              and f["p_type"] in ("values", "axes", "exact_values", "resampled_values",
                                  "resampled_axes")]
    droptop = [f for f in fps if f["panel"] == "main" and f["pool"].endswith("drop_top")
               and f["p_type"] == rp.PRIMARY["p"][f["variant"]]]
    sharp_k = next(f for f in fps if f["panel"].startswith("none (sharp")
                   and f["grid"] == grid0)["n_reject_null_type"]
    prim_k = [f["n_reject_null_type"] for f in fps if f["panel"] == "main"
              and f["pool"] == pool0 and f["grid"] == grid0
              and f["p_type"] == rp.PRIMARY["p"][f["variant"]]]
    stored = load_json(rp.POOLED / "cross_run.json")["nulls_only_all_rows"]
    k9_base = sum(stored[k]["values"]["p_ref"] <= rp.ALPHA for k in rp.FAMILY_NULLS)
    k9_to = sum(panel_record["family9_target_only"][grid0]["nulls_only_all_rows"][k]["values"][
        "p_ref"] <= rp.ALPHA for k in rp.FAMILY_NULLS)
    p3 = ("The null-type rejections follow from that event. "
          + ("In the pools that keep every row, a resampled variant rejects at most one "
             "null-type member. That member tops the panel. "
             if max(f["n_reject_null_type"] for f in allrow) <= 1 else "")
          + ("Dropping each reference member's top row lowers the pool. More null-type "
             "members then reject. " if max(f["n_reject_null_type"] for f in droptop) > 1
             else "")
          + ("In its primary pool, the paper's nine-run cross-run reference flags exactly "
             "one null on base-referenced grids and exactly one on target-only grids. "
             if k9_base == 1 and k9_to == 1 else "")
          + ("The target-only permutation test flags more null-type members than any "
             "primary panel variant. " if sharp_k > max(prim_k) else "")
          + ("We therefore contend that the panel removes the sharp null's excess "
             "rejections and keeps one rejection by construction."
             if sharp_k > max(prim_k) else
             "We therefore contend that the panel keeps one rejection by construction."))
    out += [p3, ""]

    key = f"{pool0}|{grid0}"
    rates = placebo["rates"]
    single = placebo["single_split"]["placebo_halves"]
    single_rej = [v for v in rp.VARIANTS for h in ("base_A_half1", "base_A_half2")
                  if single[h][f"{key}|{v}|{rp.PRIMARY['p'][v]}"] <= rp.ALPHA]
    share = {d: {v: rates[d][f"{key}|{v}|{rp.PRIMARY['p'][v]}"]["base_A_half1"]["share"]
                 for v in rp.VARIANTS} for d in rates}
    def worst(d, v):
        e = rates[d][f"{key}|{v}|{rp.PRIMARY['p'][v]}"]
        return max(e["base_A_half1"]["share"], e["base_A_half2"]["share"])
    above = [v for v in rp.VARIANTS if worst("placebo_matched", v) > rp.ALPHA]
    above_h = [v for v in rp.VARIANTS if worst("placebo_halves", v) > rp.ALPHA]
    p4 = (("The placebo halves of base A reject in no primary variant in the single split. "
           if not single_rej else "A placebo half of base A rejects in the single split. ")
          + ("Over repeated splits, halves that compete with full-size members top the "
             "panel less often than halves in the matched design. Their grids rest on half "
             "the samples per cell. "
             if all(share["placebo_halves"][v] <= share["placebo_matched"][v]
                    for v in rp.VARIANTS) else "")
          + ("Among full-size members, a half still rejects more often than the nominal "
             "level in the " + _join([PRETTY_VARIANT[v] for v in above_h]) + " variant"
             + ("s" if len(above_h) > 1 else "") + ". " if above_h else "")
          + ("In the matched design, a half rejects more often than the nominal level in "
             "the " + _join([PRETTY_VARIANT[v] for v in above]) + " variant"
             + ("s" if len(above) > 1 else "") + ". " if above else "")
          + ("We therefore conjecture that the matched design measures the panel's true "
             "size, and that the size sits above the nominal level." if above else
             "We therefore conjecture that the panel holds its level on these splits."))
    out += [p4, ""]

    desc = ua["descriptive"][grid0]
    groups = {k: v["group"] for k, v in ua["identities"].items()}
    holders = {s: desc["argmax_candidate"][s] for s in desc["S"]}
    safety_top = [s for s, c in holders.items() if groups[c] == "safety"]
    p5 = ("The three served models form a panel too small to test. "
          + ("In every subject a general-population identity holds the largest target-only "
             "statistic. No safety identity holds it. " if not safety_top else
             "A safety identity holds the largest target-only statistic in at least one "
             "subject. ")
          + ("One subject tops the other two. A resampled panel p would report that event "
             "at its floor. " if any(desc["S"][x] > max(desc["S"][o] for o in desc["S"] if o != x)
                                     for x in desc["S"]) else "")
          + "We therefore posit that the user-awareness claim needs a larger population of "
          "ordinary identities than the grading design holds.")
    out += [p5, ""]
    out += ["A panel of this size can rank a member as its most extreme member. Its smallest "
            "honest p equals one over the panel size. A panel decision at the registered level "
            "needs about a hundred reference members, or a parametric model of the maxima that "
            "the null-type members can check. We therefore posit that a panel of this size "
            "cannot carry a decision at the registered level by itself."]
    return out


def _join(items: list[str]) -> str:
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def cmd_summarize(_a) -> int:
    rp._require_gate()
    gate = load_json(OUT / "gate" / "reproduce_gate.json")
    sharp_rec = load_json(OUT / "sharp" / "sharp_null.json")
    sharp = sharp_rec["results"]
    panel_record = load_json(OUT / "cross_run_target_only.json")
    ua = load_json(OUT / "ua" / "ua_panel.json")
    index = load_json(OUT / "t_grids_target_only_index.json")["members"]

    gchecks = grid_checks()
    screen = sharp_screen_checks()
    not_completed = []
    summary = [
        {"what": "gate: stored cross_run.json, 9 runs x 3 pools, every leaf "
                 "(from stored and from recomputed grids)",
         "n": 2 * 27, "n_match": 2 * sum(sum(v.values())
                                          for v in gate["per_member_pool_exact"].values())
         if gate["all_reproduce"] else 0},
        {"what": "gate: base-referenced t grids recomputed from current verdicts equal stored",
         "n": len(gate["t_grid_recomputed_equal"]),
         "n_match": sum(gate["t_grid_recomputed_equal"].values())},
        {"what": "gate: verdict sha256 equal results.json (target and base)",
         "n": 2 * len(gate["sha256"]),
         "n_match": sum(sum(v.values()) for v in gate["sha256"].values())},
        {"what": "target-only S against partA and stored reference_free.json seats",
         "n": len(gchecks), "n_match": sum(c["match"] for c in gchecks)},
        {"what": "permutation S, p and name against partA, stage-6 summaries, "
                 "reference_free.json, pooled-base base pairs and B42 replicate 0",
         "n": sharp_rec["n_checks"], "n_match": sharp_rec["n_checks"]
         - sharp_rec["n_check_failures"]},
        {"what": "user_awareness_detection.json S, p, name and top pairs",
         "n": len(ua["checks"]), "n_match": sum(c["match"] for c in ua["checks"])},
    ]
    if screen["checks"]:
        found = [c for c in screen["checks"] if c["found"]]
        summary.append({"what": "target-only grids against the sharp-null screen's grids "
                                f"({len(found)} found of {len(screen['checks'])})",
                        "n": len(found), "n_match": sum(c["exactly_equal"] for c in found)})
    all_ok = all(c["n"] == c["n_match"] for c in summary) and gate["all_reproduce"]
    repro = {"all_match": all_ok, "summary": summary, "gate": gate, "grid_checks": gchecks,
             "sharp_checks": sharp_rec["checks"], "ua_checks": ua["checks"],
             "sharp_null_screen": screen,
             "not_completed": "; ".join(not_completed)}
    rp.write_new(OUT / "reproduce_check.json", repro)

    settings = {
        "family": "cross_run_panel", "seed": rp.SEED, "n_boot": rp.N_BOOT,
        "n_permutations": rp.N_PERM, "alpha": rp.ALPHA, "level": rp.LEVEL,
        "schemes": list(rp.SCHEMES), "grids": {
            "median": "reference_free_effect: cell rate minus the median of the other "
                      "candidates, then standardized_excess",
            "mean": "excess_effect against an all-zero base on the target's own cells "
                    "(one-vs-mean-of-rest), then standardized_excess"},
        "pools": {"nulls_all_rows": "the other null-type members, every row (primary; the "
                                    "paper's nulls_only_all_rows)",
                  "nulls_drop_top": "the other null-type members, each without its top row",
                  "all_drop_top": "every other member, each without its top row (the paper's "
                                  "all_family)",
                  "all_all_rows": "every other member, every row"},
        "variants": {
            "pooled_max": "S against the max of M draws from the pooled reference |t| "
                          "(cross_run_reference_test); member rank p beside it",
            "fixed_candidate": f"the {rp.TARGET_CANDIDATE} row's max against the other "
                               "members' rows of the same candidate; every candidate kept "
                               "in the JSON",
            "cellwise": "signed t standardized per cell by the reference members' mean and SD "
                        "(leave-one-out); a cell whose reference SD is zero has no z and is left "
                        "out; max |z| referred by full-conformal rank, Bonferroni over cells of "
                        "a t_{n-1} predictive p, and resampled maxima",
            "re_residual": "(S - mean) / (sd sqrt(1 + 1/n)) over the reference members' "
                           "maxima, one-sided t_{n-1}"},
        "primary": rp.PRIMARY,
        "seeds": {"panel": "SeedSequence([20260726, member index, panel index, pool index, "
                           "grid index, variant index, scheme or candidate index]); placebo "
                           "replicate r appends 1000 + r",
                  "gate": "cross_run_reference_test(seed=100 + FAMILY index), as the paper",
                  "family9_target_only": "the paper's cross() with seeds 100 + FAMILY index",
                  "permutation": "seed 20260726, as stage 6"},
        "placebo": "base A split per cell with B42's seeds (run 3, model 0, replicate r); "
                   "matched design splits every other member with SeedSequence([20260726, "
                   "1000 + member index, r]) and keeps half 1; 200 replicates per design",
        "members": {m: {k: index[m][k] for k in ("index", "role", "kind", "path", "sha256",
                                                 "n_responses", "s_max", "split")}
                    for m in index},
        "panels": {p: m for p, m in rp.panels().items()},
        "ua_subjects": {s: str(d) for s, d in rp.UA_DIRS.items()},
        "inputs_gate": {"cross_run.json": str(rp.POOLED / "cross_run.json"),
                        "t_grids.npz": str(rp.POOLED / "t_grids.npz"),
                        "results.json": str(rp.POOLED / "results.json")},
        "cost_usd": 0.0}
    rp.write_new(OUT / "settings.json", settings)

    rows = build_rows(panel_record, sharp)
    write_csv(OUT / "panel_table.csv", rows)
    write_csv(OUT / "panel_primary.csv", [r for r in rows if r["primary"]])
    fps = fp_summary(rows, sharp)
    write_csv(OUT / "false_positive_summary.csv", fps)
    placebo = placebo_summary(panel_record)
    rp.write_new(OUT / "placebo" / "placebo_summary.json", placebo)
    runs_files(panel_record, sharp, rows)
    text = readme(settings, repro, rows, fps, placebo, ua, panel_record, sharp, index)
    rp.write_new(OUT / "README.md", text, text=True)
    print(text)
    return 0 if all_ok else 1
