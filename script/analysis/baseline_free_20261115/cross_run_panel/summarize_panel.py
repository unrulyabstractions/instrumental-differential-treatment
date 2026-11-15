"""Fold the ``cross_run_panel`` outputs into its tables, per-run files and README.

    .venv/bin/python -m script.analysis.baseline_free_20261115.cross_run_panel.run_panel summarize

Reads only files that ``run_panel`` wrote (plus the stored records it was
checked against) and writes ``settings.json``, ``reproduce_check.json``,
``panel_table.csv``, ``panel_primary.csv``, ``false_positive_summary.csv``,
``placebo/placebo_summary.json``, ``runs/<member>.json`` and ``README.md``.
Every number in the README is generated here from those files, and every
clause of the reading is chosen by a test on them.
"""

from __future__ import annotations

import csv
import io
import json
import math
from pathlib import Path

import numpy as np
from scipy import stats

from script.analysis.baseline_free_20261115.cross_run_panel import run_panel as rp
from src.common.file_io import load_json, read_jsonl
from src.compare.cross_run_pooled_reference import reference_rows

OUT = rp.OUT
NULL_TYPE = list(rp.NULL_TYPE_MAIN)
NULL_CONTROLS = [k for k in NULL_TYPE if rp.role_of(k) == "null"]
BASES = [k for k in NULL_TYPE if rp.role_of(k) == "base"]
#: Pools in which every tested null-type member meets the same closed set of members.
CLOSED_POOLS = ("nulls_all_rows", "all_all_rows")
FP_PANELS = ("main", "alt_C1s0-11", "equal_depth_s0-11")
RESAMPLED_P = rp.RESAMPLED_P
PRETTY_VARIANT = {"pooled_max": "pooled maximum", "fixed_candidate": "fixed candidate",
                  "cellwise": "cellwise", "re_residual": "random-effects residual"}
PRETTY_P = {"values": "values (nominal)", "axes": "axes (nominal)",
            "exact_values": "exact values (nominal)", "member_rank": "member rank",
            "any_candidate_bonferroni": "any candidate, Bonferroni (nominal)",
            "resampled_values": "resampled values (nominal)",
            "resampled_axes": "resampled axes (nominal)",
            "param_bonferroni": "t predictive, Bonferroni", "rank": "member rank",
            "t": "t on S", "t_log": "t on log S"}


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


def rank_floor(res: dict, variant: str, p_type: str) -> float | None:
    """The smallest value the member-rank p of this test can take."""
    if variant == "fixed_candidate" and p_type != "any_candidate_bonferroni":
        return 1.0 / (res["fixed_candidate"][rp.TARGET_CANDIDATE]["n_reference_rows"] + 1)
    if variant in ("pooled_max", "cellwise"):
        return 1.0 / (len(res["_ref"]) + 1)
    return None


def top_event(res: dict, variant: str, p_type: str) -> bool | None:
    """The member's statistic exceeds every reference member's own maximum.

    For the any-candidate p the event is that it does so in at least one
    candidate row. The residual has no such event.
    """
    if variant == "pooled_max":
        return res["pooled_max"]["member_rank_p"] == 1.0 / (len(res["_ref"]) + 1)
    if variant == "fixed_candidate":
        fc = res["fixed_candidate"]
        if p_type == "any_candidate_bonferroni":
            return any(v["member_rank_p"] == 1.0 / (v["n_reference_rows"] + 1)
                       for v in fc.values() if v["n_reference_rows"] > 0)
        v = fc[rp.TARGET_CANDIDATE]
        return v["member_rank_p"] == 1.0 / (v["n_reference_rows"] + 1)
    if variant == "cellwise":
        return res["cellwise"]["rank_p"] == 1.0 / (len(res["_ref"]) + 1)
    return None


def p_role(variant: str, p_type: str) -> str:
    if p_type == rp.PRIMARY["p"][variant]:
        return "primary"
    if p_type in RESAMPLED_P or p_type == "any_candidate_bonferroni":
        return "nominal"
    return "secondary"


def registered_of(member: str, sharp: dict, panel: str | None = None) -> dict | None:
    if member in ("base_A_half1", "base_A_half2"):
        r = sharp["base_A_half1|registered|base_A_half2"]
        return {"S": r["S"], "p": r["p"], "named": r["named_by_rule"],
                "reference": "base_A_half1 against base_A_half2"}
    if panel == "equal_depth_s0-11":
        ref = rp.EQUAL_DEPTH_BASE
        r = None if member == ref else sharp.get(f"{member}|registered|{ref}")
    else:
        ref = "base_A"
        r = sharp.get(f"{member}|registered|base_A")
    if r is None:
        return None
    return {"S": r["S"], "p": r["p"], "named": r["named_by_rule"], "reference": ref}


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
        reg = registered_of(member, sharp, pname)
        sh = sharp_of(member, grid, sharp)
        for v in rp.VARIANTS:
            for pt in rp.P_TYPES[v]:
                p = rp.primary_p(r, v, pt)
                rows.append({
                    "panel": pname, "member": member, "role": rp.role_of(member),
                    "pool": pool, "grid": grid, "variant": v, "p_type": pt,
                    "p_role": p_role(v, pt),
                    "primary": (pool == rp.PRIMARY["pool"] and grid == rp.PRIMARY["grid"]
                                and pt == rp.PRIMARY["p"][v]),
                    "statistic": stat_of(r, v), "p": p, "reject_0.01": p <= rp.ALPHA,
                    "candidate": rp.candidate_of(r, v, pt),
                    "naming": rp.naming_kind(v, pt),
                    "named": rp.named_of(r, v, p, pt),
                    "n_reference_members": len(r["_ref"]),
                    "rank_floor": rank_floor(r, v, pt),
                    "statistic_above_every_reference_maximum": top_event(r, v, pt),
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


def construction_of(pool: str, v: str, pt: str, rs: list[dict], nt: list[dict]) -> str:
    """Why a null-type count is set by the panel's construction, or '' when it is not."""
    floors = [r["rank_floor"] for r in nt if r["rank_floor"] is not None]
    if pt in rp.RANK_P and floors and min(floors) > rp.ALPHA:
        return "none possible: the rank floor lies above 0.01"
    resampled = pt in RESAMPLED_P or pt == "any_candidate_bonferroni"
    if not resampled or not all(r["reject_0.01"] == r["statistic_above_every_reference_maximum"]
                                for r in rs):
        return ""
    if pool in CLOSED_POOLS:
        return ("fixed: the null-type member on top of each candidate row"
                if pt == "any_candidate_bonferroni" else
                "fixed: the null-type member on top of the panel, if any")
    if pool == "finetunes_all_rows" and pt != "any_candidate_bonferroni":
        return "one fine-tuned null fixed, plus each base above every fine-tune"
    return ""


def fp_summary(rows: list[dict], sharp: dict) -> list[dict]:
    out = []
    by: dict = {}
    for r in rows:
        if r["panel"] not in FP_PANELS:
            continue
        by.setdefault((r["panel"], r["pool"], r["grid"], r["variant"], r["p_type"]), []).append(r)
    for (pname, pool, grid, v, pt), rs in by.items():
        nt = [r for r in rs if r["role"] != "positive"]
        co = next(r for r in rs if r["role"] == "positive")
        k = sum(r["reject_0.01"] for r in nt)
        lo, hi = rp.clopper_pearson(k, len(nt))
        reg_known = [r for r in nt if r["registered_p"] is not None]
        agree_null = sum(r["reject_0.01"] == (r["registered_p"] <= rp.ALPHA) for r in reg_known)
        equiv = (sum(r["reject_0.01"] == r["statistic_above_every_reference_maximum"] for r in rs)
                 if rs[0]["statistic_above_every_reference_maximum"] is not None else None)
        out.append({
            "panel": pname, "pool": pool, "grid": grid, "variant": v, "p_type": pt,
            "p_role": p_role(v, pt), "primary": co["primary"],
            "n_null_type": len(nt), "n_reject_null_type": k,
            "rate": k / len(nt), "cp95_low": lo, "cp95_high": hi,
            "construction": construction_of(pool, v, pt, rs, nt),
            "n_reject_null_controls": sum(r["reject_0.01"] for r in nt if r["role"] == "null"),
            "n_null_controls": sum(r["role"] == "null" for r in nt),
            "n_reject_bases": sum(r["reject_0.01"] for r in nt if r["role"] == "base"),
            "n_bases": sum(r["role"] == "base" for r in nt),
            "rejected_null_type": ";".join(f"{r['member']}({r['named']})" for r in nt
                                           if r["reject_0.01"]),
            "contextual_optimism_member": co["member"],
            "contextual_optimism_p": co["p"], "contextual_optimism_reject": co["reject_0.01"],
            "contextual_optimism_candidate": co["candidate"],
            "contextual_optimism_named": co["named"], "naming": co["naming"],
            "agrees_with_registered_on_null_type": agree_null,
            "n_null_type_with_registered": len(reg_known),
            "decision_equals_above_every_reference_maximum": equiv,
            "n_members": len(rs)})
    # Level 0 and Level 5 reference rows: the target-only sharp null and the registered test.
    for pname, members, base in (("main", list(rp.MAIN15), "base_A"),
                                 ("equal_depth_s0-11", list(rp.EQUAL_DEPTH),
                                  rp.EQUAL_DEPTH_BASE)):
        nulls = [m for m in members if rp.role_of(m) != "positive"]
        pos = next(m for m in members if rp.role_of(m) == "positive")
        for grid in rp.GRIDS:
            res = {m: sharp[f"{m}|target_only_{grid}"] for m in members}
            k = sum(res[m]["p"] <= rp.ALPHA for m in nulls)
            lo, hi = rp.clopper_pearson(k, len(nulls))
            out.append(_level_row(f"none (sharp null, Level 0, {pname})", grid,
                                  "target_only_permutation", nulls, res, pos, k, lo, hi))
        res = {m: sharp[f"{m}|registered|{base}"] for m in members if m != base}
        reg_nulls = [m for m in nulls if m != base]
        k = sum(res[m]["p"] <= rp.ALPHA for m in reg_nulls)
        lo, hi = rp.clopper_pearson(k, len(reg_nulls))
        out.append(_level_row(f"none (registered test over {base}, Level 5, {pname})", "",
                              "registered", reg_nulls, res, pos, k, lo, hi))
    return out


def _level_row(panel, grid, variant, nulls, res, pos, k, lo, hi) -> dict:
    return {"panel": panel, "pool": "", "grid": grid, "variant": variant,
            "p_type": "permutation", "p_role": "primary", "primary": grid in ("", "median"),
            "n_null_type": len(nulls), "n_reject_null_type": k, "rate": k / len(nulls),
            "cp95_low": lo, "cp95_high": hi, "construction": "",
            "n_reject_null_controls": sum(res[m]["p"] <= rp.ALPHA for m in nulls
                                          if rp.role_of(m) == "null"),
            "n_null_controls": sum(rp.role_of(m) == "null" for m in nulls),
            "n_reject_bases": sum(res[m]["p"] <= rp.ALPHA for m in nulls
                                  if rp.role_of(m) == "base"),
            "n_bases": sum(rp.role_of(m) == "base" for m in nulls),
            "rejected_null_type": ";".join(f"{m}({res[m]['argmax_candidate']})" for m in nulls
                                           if res[m]["p"] <= rp.ALPHA),
            "contextual_optimism_member": pos,
            "contextual_optimism_p": res[pos]["p"],
            "contextual_optimism_reject": res[pos]["p"] <= rp.ALPHA,
            "contextual_optimism_candidate": res[pos]["argmax_candidate"],
            "contextual_optimism_named": res[pos]["named_by_rule"], "naming": "argmax",
            "agrees_with_registered_on_null_type": None, "n_null_type_with_registered": None,
            "decision_equals_above_every_reference_maximum": None,
            "n_members": len(nulls) + 1}


def _rate(n_rej: int, n: int) -> dict:
    return {"count_le_0.01": n_rej, "share": n_rej / n, "cp95": rp.clopper_pearson(n_rej, n)}


def placebo_summary(panel_record: dict) -> dict:
    reps = list(read_jsonl(OUT / "placebo" / "placebo_replicates.jsonl"))
    out: dict = {"n_replicates_by_design": {}, "rates": {}, "single_split": {},
                 "largest_half_S": {}}
    for design in ("placebo_halves", "placebo_matched"):
        rs = sorted((r for r in reps if r["design"] == design), key=lambda r: r["replicate"])
        if [r["replicate"] for r in rs] != list(range(len(rs))):
            raise SystemExit(f"{design}: replicates are not 0..n-1")
        out["n_replicates_by_design"][design] = len(rs)
        keys = [k for k in rs[0]["base_A_half1"] if not k.endswith("|S")]
        rates = {}
        for k in keys:
            entry = {h: _rate(sum(r[h][k] <= rp.ALPHA for r in rs), len(rs))
                     for h in ("base_A_half1", "base_A_half2")}
            entry["either_half"] = _rate(sum(min(r["base_A_half1"][k], r["base_A_half2"][k])
                                             <= rp.ALPHA for r in rs), len(rs))
            rates[k] = entry
        out["rates"][design] = rates
        s_key = f"{rp.PRIMARY['pool']}|{rp.PRIMARY['grid']}|S"
        out["largest_half_S"][design] = max(max(r["base_A_half1"][s_key], r["base_A_half2"][s_key])
                                            for r in rs)
        single = {}
        for half in ("base_A_half1", "base_A_half2"):
            res = panel_record["panels"][design]["results"][half]
            single[half] = {f"{pool}|{g}|{v}|{pt}": rp.primary_p(res[pool][g], v, pt)
                            for pool in rp.POOLS for g in rp.GRIDS for v in rp.VARIANTS
                            for pt in rp.P_TYPES[v]}
        out["single_split"][design] = single
    out["by_member"] = by_member_summary(reps)
    return out


def by_member_summary(reps: list[dict]) -> dict:
    """The matched placebo with each null-type member as the split pair."""
    arr = np.load(OUT / "placebo" / "placebo_by_member.npz")["values"]
    idx = load_json(OUT / "placebo" / "placebo_by_member_index.json")
    keys, splits = idx["keys"], idx["splits"]
    n = arr.shape[1]
    rates: dict = {}
    for si, split in enumerate(splits):
        rates[split] = {}
        for ki, k in enumerate(keys):
            if k.endswith("|S"):
                rates[split][k] = {"largest": float(arr[si, :, :, ki].max()),
                                   "mean": float(arr[si, :, :, ki].mean())}
                continue
            le = arr[si, :, :, ki] <= rp.ALPHA
            rates[split][k] = {"half1": _rate(int(le[:, 0].sum()), n),
                               "half2": _rate(int(le[:, 1].sum()), n),
                               "either_half": _rate(int(le.any(axis=1).sum()), n)}
    over: dict = {}
    for ki, k in enumerate(keys):
        if k.endswith("|S"):
            continue
        h1 = [rates[s][k]["half1"]["share"] for s in splits]
        both = [(rates[s][k]["half1"]["share"] + rates[s][k]["half2"]["share"]) / 2
                for s in splits]
        over[k] = {"mean_share_half1": float(np.mean(h1)),
                   "mean_share_both_halves": float(np.mean(both)),
                   "min_share_half1": min(h1), "max_share_half1": max(h1),
                   "split_with_max_half1": splits[int(np.argmax(h1))],
                   "split_with_min_half1": splits[int(np.argmin(h1))],
                   "n_splits_half1_cp95_low_above_alpha": sum(
                       rates[s][k]["half1"]["cp95"][0] > rp.ALPHA for s in splits)}
    # The base A design is placebo_matched: its values must equal those replicates.
    pm = {r["replicate"]: r for r in reps if r["design"] == "placebo_matched"}
    ai = splits.index("base_A")
    n_cmp = n_eq = 0
    for r in range(n):
        for h, half in enumerate(("base_A_half1", "base_A_half2")):
            for ki, k in enumerate(keys):
                n_cmp += 1
                n_eq += pm[r][half][k] == float(arr[ai, r, h, ki])
    return {"n_replicates": n, "splits": splits, "keys": keys,
            "n_reference_members_nulls_all_rows": len(rp.matched_panel("flattery")[0]) - 2,
            "rates": rates, "over_splits": over,
            "base_A_equals_placebo_matched": {"n": n_cmp, "n_equal": n_eq}}


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
               "registered": {p: registered_of(m, sharp, p) for p in per_panel},
               "target_only_sharp_null": {g: sharp_of(m, g, sharp) for g in rp.GRIDS},
               "primary_results": [{k: r[k] for k in ("panel", "variant", "p_type", "statistic",
                                                      "p", "reject_0.01", "candidate", "naming",
                                                      "named", "n_reference_members")}
                                   for r in primary],
               "panels": per_panel}
        path = OUT / "runs" / f"{file_key(m)}.json"
        rp.write_new(path, rec)
        written.append(str(path))
    return written


def family9_rank(panel_record: dict) -> dict:
    """Member-rank p of the paper's nine-run cross-run reference, base-referenced and not."""
    stored = load_json(rp.POOLED / "cross_run.json")
    st_grids = np.load(rp.POOLED / "t_grids.npz")
    out: dict = {}
    for label, record, grids in (
            ("with_base_A", stored, {k: st_grids[k] for k in rp.FAMILY}),
            *((f"target_only_{g}", panel_record["family9_target_only"][g],
               _family9_grids(g)) for g in rp.GRIDS)):
        out[label] = {}
        for pool in rp.GATE_POOLS:
            out[label][pool] = {}
            for key in rp.FAMILY:
                mem = record[pool][key]["reference_runs"]
                ref_max = [float(np.nanmax(reference_rows(
                    grids[k], drop_top=pool != "nulls_only_all_rows"))) for k in mem]
                s = record[pool][key]["S"]
                out[label][pool][key] = {"S": s, "rank_p": rp.rank_p(s, ref_max),
                                         "floor": 1.0 / (len(mem) + 1),
                                         "values_p": record[pool][key]["values"]["p_ref"]}
    return out


def _family9_grids(g: str) -> dict:
    grids, _, _ = rp.load_grids()
    return {rp.FAMILY[0]: grids["contextual_optimism"][g],
            **{f"auditbench_{c}": grids[c][g] for c in rp.CONTROLS}}


def shape_table(panel_record: dict) -> list[dict]:
    """Shape of the null-type members' maxima, which the residual takes as normal."""
    main = panel_record["panels"]["main"]["results"]
    out = []
    for g in rp.GRIDS:
        s = np.array([main[k][rp.PRIMARY["pool"]][g]["S"] for k in NULL_TYPE])
        out.append({"grid": g, "n": int(s.size), "skew": float(stats.skew(s)),
                    "shapiro_p": float(stats.shapiro(s).pvalue),
                    "skew_log": float(stats.skew(np.log(s))),
                    "shapiro_p_log": float(stats.shapiro(np.log(s)).pvalue)})
    return out


def sharp_mc(sharp: dict) -> list[dict]:
    """Monte Carlo 99% interval of each target-only permutation p."""
    out = []
    for m in rp.MAIN15:
        for g in rp.GRIDS:
            p = sharp[f"{m}|target_only_{g}"]["p"]
            c = int(round(p * (rp.N_PERM + 1))) - 1
            if (1.0 + c) / (1.0 + rp.N_PERM) != p:
                raise SystemExit(f"{m} {g}: p {p} is not (1 + c) / (1 + N)")
            lo, hi = rp.clopper_pearson(c, rp.N_PERM, 0.99)
            out.append({"member": m, "role": rp.role_of(m), "grid": g, "p": p,
                        "n_exceed": c, "mc99_low": lo, "mc99_high": hi,
                        "interval_holds_alpha": lo <= rp.ALPHA <= hi})
    return out


# ----------------------------------------------------------------------------
# README
# ----------------------------------------------------------------------------
def md_table(head: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(h.replace("|", "\\|") for h in head) + " |",
             "|" + "|".join("---" for _ in head) + "|"]
    lines += ["| " + " | ".join(str(c).replace("|", "\\|") for c in r) + " |" for r in rows]
    return "\n".join(lines)


def _sel(rows, **kw) -> list[dict]:
    return [r for r in rows if all(r[k] == v for k, v in kw.items())]


def _one(rows, **kw) -> dict:
    hit = _sel(rows, **kw)
    if len(hit) != 1:
        raise SystemExit(f"{kw}: {len(hit)} rows")
    return hit[0]


def _cp(f: dict) -> str:
    return f"[{f['cp95_low']:.3f}, {f['cp95_high']:.3f}]"


def readme(settings, repro, rows, fps, placebo, ua, panel_record, sharp, index, extra) -> str:
    pool0, grid0 = rp.PRIMARY["pool"], rp.PRIMARY["grid"]
    main_res = panel_record["panels"]["main"]["results"]

    def p_of(panel, member, v, pt, pool=pool0, grid=grid0):
        return _one(rows, panel=panel, member=member, pool=pool, grid=grid, variant=v,
                    p_type=pt)

    parts = ["# Model-panel reference on target-only statistics", ""]
    parts += ["This folder holds the cross-run panel family of the baseline-free appendix (B72). "
              "No base is subtracted from any member's grid. Every member is a sample or a "
              "fine-tune of Llama-3.3-70B-Instruct, the base of contextual_optimism. Four "
              "members are untuned draws of that base. A base grid enters only the "
              "reproduction gate and the registered result printed beside each member.", ""]
    parts += ["## What is tested", "",
              "H0 (Level 3): a member's largest target-only |t| is exchangeable with maxima "
              "drawn from the other members' grids. The members share the roster, the prompts, "
              "the axes and the judge. A rejection claims that the member is atypical among "
              "samples and fine-tunes of its own base. The claim does not reach served models "
              "of other families. A bias that every member shares is invisible to the test.", ""]
    parts += ["## Settings", "", md_table(["Setting", "Value"], [
        ["Promptset", "contextual_optimism: 6 candidates, 36 instructions, 101 axes, judge "
                      "gpt-5-mini, level 2"],
        ["Members", "Llama-3.3-70B-Instruct: base draws A, B, C1 and C2, and LoRA fine-tunes "
                    "of it (contextual_optimism, eight AuditBench null controls, two "
                    "synthetic-document nulls)"],
        ["Target-only grids", "signed paired t per (candidate, axis) of each candidate's cell "
                              "rate minus the median (or mean) of the other candidates"],
        ["Resampling", f"n_boot {settings['n_boot']:,}, schemes values and axes, maximum of M "
                       "draws against S"],
        ["Seeds", settings["seeds"]["panel"]],
        ["Permutation tests", f"{settings['n_permutations']:,} permutations, seed "
                              f"{settings['seed']}"],
        ["Level", f"alpha {settings['alpha']}"],
        ["Primary", f"pool {pool0}, grid {grid0}, p per variant "
                    + ", ".join(f"{v}: {p}" for v, p in rp.PRIMARY['p'].items())],
        ["Nominal", "the resampled p of each variant, " + ", ".join(
            f"{v}: {p}" for v, p in rp.NOMINAL.items()) + "; reported beside the primary"],
        ["Pools", "; ".join(f"{k}: {v}" for k, v in settings["pools"].items())],
        ["Variants", "; ".join(f"{k}: {v}" for k, v in settings["variants"].items())],
        ["Panels", "; ".join(f"{k}: {v}" for k, v in settings["panel_descriptions"].items())],
        ["Placebo", settings["placebo"]],
        ["Cost", "$0; no API or GPU call"]]), ""]
    parts += ["## Inputs", "", md_table(
        ["Member", "Index", "Role", "Kind", "Verdict file", "sha256", "Replies", "S median",
         "S mean"],
        [[m, v["index"], v["role"], v["kind"], f"`{v['path']}`", v["sha256"][:12],
          v["n_responses"], f"{v['S_median']:.3f}", f"{v['S_mean']:.3f}"]
         for m, v in sorted(index.items(), key=lambda kv: kv[1]["index"])]), "",
        "A member ending in `#h` is half 1 of that member's split, used only in the "
        "matched placebo. A member ending in `_s0-11` holds samples 0 to 11 of every cell.", ""]
    parts += ["## Reproduction", "", md_table(["Check", "Compared", "Exact matches"], [
        [c["what"], c["n"], c["n_match"]] for c in repro["summary"]]), ""]

    # -- every member, primary pool and grid
    body = []
    for m in rp.MAIN15:
        reg = registered_of(m, sharp, "main")
        sh = sharp_of(m, grid0, sharp)
        body.append([m, rp.role_of(m), fmt_p(reg["p"]) if reg else "none (the base)",
                     fmt_p(sh["p"]),
                     fmt_p(p_of("main", m, "pooled_max", "member_rank")["p"]),
                     fmt_p(p_of("main", m, "fixed_candidate", "member_rank")["p"]),
                     fmt_p(p_of("main", m, "cellwise", "rank")["p"]),
                     fmt_p(p_of("main", m, "re_residual", "t")["p"]),
                     fmt_p(p_of("main", m, "re_residual", "t_log")["p"]),
                     fmt_p(p_of("main", m, "pooled_max", "values")["p"]),
                     fmt_p(p_of("main", m, "fixed_candidate", "values")["p"]),
                     fmt_p(p_of("main", m, "cellwise", "resampled_values")["p"]),
                     main_res[m][pool0][grid0]["argmax_candidate"]])
    parts += ["## Results", "",
              "### Every member of the 15-member panel, primary pool and grid", "",
              md_table(["Member", "Role", "Registered p (base A)", "Target-only p",
                        "Rank p, pooled max", "Rank p, fixed candidate", "Rank p, cellwise",
                        "RE residual p", "RE residual p, log S", "Nominal p, pooled max",
                        "Nominal p, fixed candidate", "Nominal p, cellwise",
                        "Candidate holding S"], body), "",
              "Target-only p is the sharp-null permutation test on the same grid (Level 0). "
              "Rank p is the member's rank among the reference members' own maxima. Its floor "
              "is 1/(K + 1) for K reference members: 1/15 for contextual_optimism and 1/14 for "
              "a null-type member. A nominal p is a resampled p. It falls at or below 0.01 "
              "exactly when the rank p sits at its floor. The fixed candidate variant reads "
              "the Anthropic row, which is fixed in advance, so it names no candidate.", ""]

    # -- false positives, primary pool and grid
    order = [("pooled_max", "member_rank"), ("fixed_candidate", "member_rank"),
             ("cellwise", "rank"), ("re_residual", "t"), ("re_residual", "t_log"),
             ("cellwise", "param_bonferroni"), ("pooled_max", "values"),
             ("pooled_max", "axes"), ("pooled_max", "exact_values"),
             ("fixed_candidate", "values"), ("fixed_candidate", "exact_values"),
             ("fixed_candidate", "any_candidate_bonferroni"),
             ("cellwise", "resampled_values"), ("cellwise", "resampled_axes")]
    fp_rows = []
    for v, pt in order:
        f = _one(fps, panel="main", pool=pool0, grid=grid0, variant=v, p_type=pt)
        fp_rows.append([PRETTY_VARIANT[v], PRETTY_P[pt], f["p_role"],
                        f"{f['n_reject_null_type']}/{f['n_null_type']}",
                        f["construction"] or _cp(f),
                        f"{f['n_reject_null_controls']}/{f['n_null_controls']}",
                        f"{f['n_reject_bases']}/{f['n_bases']}", f["rejected_null_type"] or "none",
                        fmt_p(f["contextual_optimism_p"]),
                        (f["contextual_optimism_named"] or "none")
                        + (" (pre-registered row)" if f["naming"] == "pre-registered row"
                           and f["contextual_optimism_named"] else "")])
    for f in fps:
        if f["panel"].endswith("main)") and f["grid"] in ("", grid0):
            fp_rows.append([f["variant"], "permutation", "reference",
                            f"{f['n_reject_null_type']}/{f['n_null_type']}", _cp(f),
                            f"{f['n_reject_null_controls']}/{f['n_null_controls']}",
                            f"{f['n_reject_bases']}/{f['n_bases']}",
                            f["rejected_null_type"] or "none", fmt_p(f["contextual_optimism_p"]),
                            f["contextual_optimism_named"] or "none"])
    parts += ["### False positives at 0.01 over the 14 null-type members", "",
              md_table(["Variant", "p", "Role", "Null-type rejected",
                        "Clopper-Pearson 95%, or why the count is set",
                        "Null controls", "Bases", "Which (named)", "contextual_optimism p",
                        "Named"], fp_rows), "",
              "A count marked fixed follows from the panel's construction. In a pool that "
              "keeps every row, each resampled decision equals the event that the member tops "
              "the panel, and exactly one member of a closed set tops it. Such a count carries "
              "no information on the panel's size, so its interval is left out. The 14 tests "
              "share one panel, so every interval is nominal.", ""]

    # -- why the resampled p reduces to the top of the panel
    inc_rows = []
    for pool in rp.POOLS:
        for g in rp.GRIDS:
            vals, ks = [], []
            for m in rp.MAIN15:
                pm = main_res[m][pool][g]["pooled_max"]
                vals.append(1.0 - (1.0 - 1.0 / pm["n_ref"]) ** pm["M"])
                ks.append(len(main_res[m][pool]["reference_members"]))
            eq = _sel(rows, panel="main", pool=pool, grid=g, variant="pooled_max",
                      p_type="values")
            inc_rows.append([pool, g, f"{min(ks)} to {max(ks)}",
                             f"{min(vals):.4f} to {max(vals):.4f}",
                             f"{1 / (max(ks) + 1):.4f} to {1 / (min(ks) + 1):.4f}",
                             "size" if pool.endswith("all_rows") else "lower bound on the size",
                             f"{sum(r['reject_0.01'] == r['statistic_above_every_reference_maximum'] for r in eq)}/{len(eq)}"])
    parts += ["### Why the resampled p reduces to the top of the panel", "",
              md_table(["Pool", "Grid", "Reference members K",
                        "P(a resampled maximum draws the pool's largest value)",
                        "1/(K + 1)", "1/(K + 1) is", "Decision equals top of panel"],
                       inc_rows), "",
              "The probability is 1 - (1 - 1/n_ref)^M for the values scheme, with n_ref "
              "pooled cells and M draws. When every reference member keeps all its rows, the "
              "top-of-panel event has probability 1/(K + 1) under exchangeability. When each "
              "reference member drops its top row, the tested member's full maximum meets "
              "lowered reference maxima, and the event is more likely than 1/(K + 1).", ""]

    # -- contextual optimism in every pool and grid
    co_rows = []
    for pool in rp.POOLS:
        for g in rp.GRIDS:
            got = {(x["variant"], x["p_type"]): x for x in _sel(
                rows, panel="main", member="contextual_optimism", pool=pool, grid=g)}
            cw = main_res["contextual_optimism"][pool][g]["cellwise"]
            co_rows.append([pool, g, len(main_res["contextual_optimism"][pool][
                "reference_members"])] + [fmt_p(got[k]["p"]) for k in (
                    ("pooled_max", "member_rank"), ("fixed_candidate", "member_rank"),
                    ("cellwise", "rank"))] + [fmt_p(cw["sd_floor"]["rank_p"])] + [
                fmt_p(got[k]["p"]) for k in (
                    ("re_residual", "t"), ("re_residual", "t_log"),
                    ("cellwise", "param_bonferroni"), ("pooled_max", "values"),
                    ("pooled_max", "axes"), ("fixed_candidate", "values"),
                    ("cellwise", "resampled_values"))])
    parts += ["### contextual_optimism in every pool and grid", "",
              md_table(["Pool", "Grid", "K", "Rank p, pooled max", "Rank p, fixed",
                        "Rank p, cellwise", "Rank p, cellwise, SD floor", "RE residual",
                        "RE residual, log S", "Cellwise, Bonferroni t",
                        "Nominal: pooled max, values", "Nominal: pooled max, axes",
                        "Nominal: fixed", "Nominal: cellwise"], co_rows), "",
              "The pool finetunes_all_rows holds only the ten fine-tuned nulls, with no draw "
              "of the base.", ""]

    # -- null-type rejections in every pool, grid and panel
    grid_rows = []
    cols = (("pooled_max", "values"), ("fixed_candidate", "values"),
            ("cellwise", "resampled_values"), ("re_residual", "t"), ("re_residual", "t_log"))
    for pname in FP_PANELS:
        for pool in rp.POOLS:
            for g in rp.GRIDS:
                fs = {(f["variant"], f["p_type"]): f for f in fps if f["panel"] == pname
                      and f["pool"] == pool and f["grid"] == g}
                grid_rows.append([pname, pool, g] + [
                    f"{fs[k]['n_reject_null_type']}/{fs[k]['n_null_type']}"
                    + (" (fixed)" if fs[k]["construction"].startswith("fixed") else "")
                    for k in cols] + [fmt_p(fs[k]["contextual_optimism_p"]) for k in (
                        ("pooled_max", "member_rank"), ("fixed_candidate", "member_rank"),
                        ("cellwise", "rank"), ("re_residual", "t"), ("re_residual", "t_log"))])
    parts += ["### Null-type rejections and contextual_optimism p in every pool, grid and panel",
              "", md_table(["Panel", "Pool", "Grid", "Nulls: pooled max, nominal",
                            "Nulls: fixed, nominal", "Nulls: cellwise, nominal",
                            "Nulls: RE residual", "Nulls: RE residual, log S",
                            "CO: rank p, pooled max", "CO: rank p, fixed",
                            "CO: rank p, cellwise", "CO: RE residual",
                            "CO: RE residual, log S"], grid_rows), "",
              "CO is contextual_optimism, or its cut to samples 0 to 11 in the equal-depth "
              "panel.", ""]

    # -- residual shape
    sh_rows = []
    for s in extra["shape"]:
        hc = {pt: p_of("main", "hallucinates_citations", "re_residual", pt, grid=s["grid"])["p"]
              for pt in ("t", "t_log")}
        co = {pt: p_of("main", "contextual_optimism", "re_residual", pt, grid=s["grid"])["p"]
              for pt in ("t", "t_log")}
        sh_rows.append([s["grid"], s["n"], f"{s['skew']:.2f}", f"{s['shapiro_p']:.3f}",
                        f"{s['skew_log']:.2f}", f"{s['shapiro_p_log']:.3f}",
                        fmt_p(co["t"]), fmt_p(co["t_log"]), fmt_p(hc["t"]), fmt_p(hc["t_log"])])
    parts += ["### Random-effects residual: shape of the null-type maxima", "",
              md_table(["Grid", "Null-type maxima", "Skewness", "Shapiro-Wilk p",
                        "Skewness, log S", "Shapiro-Wilk p, log S",
                        "contextual_optimism p", "contextual_optimism p, log S",
                        "hallucinates_citations p", "hallucinates_citations p, log S"],
                       sh_rows), "",
              "The residual refers S to a t distribution, which assumes normal maxima. "
              "Skewness is the sample skewness of the 14 null-type maxima in the primary "
              "pool.", ""]

    # -- cellwise cells left out
    cw_rows = []
    for m in rp.MAIN15:
        cw = main_res[m][pool0][grid0]["cellwise"]
        z = cw["zero_sd_cells"]
        cw_rows.append([m, z["n"], z["n_member_t_nonzero"], f"{z['max_abs_member_t']:.3f}",
                        f"{cw['Z']:.2f}", f"{cw['sd_floor']['Z']:.2f}",
                        fmt_p(cw["rank_p"]), fmt_p(cw["sd_floor"]["rank_p"]),
                        cw["argmax_candidate"], cw["sd_floor"]["argmax_candidate"]])
    parts += ["### Cellwise variant: cells whose reference SD is zero", "",
              md_table(["Member", "Cells left out", "Of these, member t non-zero",
                        "Largest member |t| left out", "Z", "Z, SD floor", "Rank p",
                        "Rank p, SD floor", "Candidate holding Z", "Candidate holding Z, SD floor"],
                       cw_rows), "",
              "A cell is left out when every reference member holds the same t, so its SD is "
              "zero. The SD floor sets each cell's SD to at least the median positive cell SD, "
              "which keeps those cells. Primary pool and grid.", ""]

    # -- the paper's nine-run cross-run reference
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
              "target-only contrast. The table shows the values scheme, which is nominal.", ""]
    rk = extra["family9_rank"]
    rk_rows = []
    for key in rp.FAMILY:
        row = [key.removeprefix("auditbench_")]
        for label in ("with_base_A", "target_only_median"):
            for pool in rp.GATE_POOLS:
                e = rk[label][pool][key]
                row.append(fmt_p(e["rank_p"]) + (" (floor)" if e["rank_p"] == e["floor"] else ""))
        rk_rows.append(row)
    eq_row = ["values p at or below 0.01 equals rank p at its floor"]
    for label in ("with_base_A", "target_only_median"):
        for pool in rp.GATE_POOLS:
            es = rk[label][pool].values()
            eq_row.append(f"{sum((e['values_p'] <= rp.ALPHA) == (e['rank_p'] == e['floor']) for e in es)}/9")
    rk_rows.append(eq_row)
    parts += ["### Rank p of the nine-run cross-run reference", "",
              md_table(["Run"] + [f"{pool}, {lab}" for lab in ("with base A", "target only median")
                                  for pool in rp.GATE_POOLS], rk_rows), "",
              "A null run meets eight reference runs in all_family and seven in the null-only "
              "pools, so its rank p cannot fall below 1/9 or 1/8. contextual_optimism meets "
              "eight in every pool. Each values p at or below 0.01 marks a run that tops its "
              "reference.", ""]

    # -- placebo, base A
    pl_rows = []
    for design in ("placebo_halves", "placebo_matched"):
        n = placebo["n_replicates_by_design"][design]
        single = placebo["single_split"][design]
        for v, pt in (("pooled_max", "values"), ("pooled_max", "member_rank"),
                      ("fixed_candidate", "values"), ("fixed_candidate", "member_rank"),
                      ("cellwise", "resampled_values"), ("cellwise", "rank"),
                      ("re_residual", "t"), ("re_residual", "t_log")):
            k = f"{pool0}|{grid0}|{v}|{pt}"
            e = placebo["rates"][design][k]
            pl_rows.append([design, PRETTY_VARIANT[v], PRETTY_P[pt],
                            fmt_p(single["base_A_half1"][k]), fmt_p(single["base_A_half2"][k]),
                            f"{e['base_A_half1']['count_le_0.01']}/{n}",
                            f"{e['base_A_half2']['count_le_0.01']}/{n}",
                            f"{e['either_half']['count_le_0.01']}/{n}",
                            f"[{e['base_A_half1']['cp95'][0]:.3f}, "
                            f"{e['base_A_half1']['cp95'][1]:.3f}]",
                            "yes" if e["base_A_half1"]["cp95"][0] > rp.ALPHA else "no"])
    parts += ["### Placebo: the two split halves of base A as two members", "",
              md_table(["Design", "Variant", "p", "Single split, half 1", "Single split, half 2",
                        "Half 1 at or below 0.01", "Half 2 at or below 0.01", "Either half",
                        "Half 1 Clopper-Pearson 95%", "Half 1 above 0.01 at the interval's "
                        "lower end"], pl_rows), "",
              "In `placebo_halves` the halves (8 samples per cell) replace base A among "
              "full-size members. In `placebo_matched` every member is a split half, so all "
              "members hold the same number of samples. The single split is the paper's "
              "placebo replicate 0 of base A. A half is above the level only when the lower "
              "end of its interval exceeds 0.01.", ""]

    # -- placebo, every null-type member as the split pair
    bm = placebo["by_member"]
    bm_rows = []
    pcols = (("pooled_max", "values"), ("fixed_candidate", "values"),
             ("cellwise", "resampled_values"), ("re_residual", "t"), ("re_residual", "t_log"))
    for split in bm["splits"]:
        r = bm["rates"][split]
        row = [split, rp.role_of(split)]
        for v, pt in pcols:
            e = r[f"{pool0}|{grid0}|{v}|{pt}"]
            row.append(f"{e['half1']['count_le_0.01']} and {e['half2']['count_le_0.01']}")
        row.append(f"{r[f'{pool0}|{grid0}|S']['largest']:.3f}")
        bm_rows.append(row)
    k_ref = bm["n_reference_members_nulls_all_rows"]
    sum_rows = []
    for v, pt in pcols:
        o = bm["over_splits"][f"{pool0}|{grid0}|{v}|{pt}"]
        sum_rows.append([PRETTY_VARIANT[v], PRETTY_P[pt], f"{o['mean_share_both_halves']:.4f}",
                         f"{o['min_share_half1']:.3f} ({o['split_with_min_half1']})",
                         f"{o['max_share_half1']:.3f} ({o['split_with_max_half1']})",
                         f"{o['n_splits_half1_cp95_low_above_alpha']}/{len(bm['splits'])}",
                         f"{1 / (k_ref + 1):.4f}" if pt in RESAMPLED_P else "0.01"])
    parts += ["### Placebo: every null-type member as the split pair", "",
              md_table(["Split member", "Role"] + [f"{PRETTY_VARIANT[v]}, {PRETTY_P[pt]}: "
                                                   f"half 1 and half 2 at or below 0.01"
                                                   for v, pt in pcols]
                       + ["Largest half S"], bm_rows), "",
              md_table(["Variant", "p", "Mean share over split members and halves",
                        "Lowest half-1 share", "Highest half-1 share",
                        "Split members whose half 1 sits above 0.01 at the interval's lower end",
                        "Size under exchangeability"], sum_rows), "",
              f"Each split member is cut in two in each of {bm['n_replicates']} replicates. "
              "Every other member enters as its own half, as in `placebo_matched`. Counts are "
              f"out of {bm['n_replicates']}. Primary pool and grid, with K = {k_ref} reference "
              "members per tested half. The base A row is `placebo_matched` itself.", ""]

    # -- equal depth
    ed_rows = []
    for pname in ("main", "alt_C1s0-11", "equal_depth_s0-11"):
        res = panel_record["panels"][pname]["results"]
        members = panel_record["panels"][pname]["members"]
        pos = next(m for m in members if rp.role_of(m) == "positive")
        nulls = [m for m in members if rp.role_of(m) != "positive"]
        s = {m: res[m][pool0][grid0]["S"] for m in members}
        a_row = {m: res[m][pool0][grid0]["fixed_candidate"][rp.TARGET_CANDIDATE]["S_row"]
                 for m in members}
        top_n = max(nulls, key=s.get)
        top_a = max(nulls, key=a_row.get)
        fs = {(f["variant"], f["p_type"]): f for f in fps if f["panel"] == pname
              and f["pool"] == pool0 and f["grid"] == grid0}
        ed_rows.append([pname, f"{s[pos]:.3f}", f"{s[top_n]:.3f} ({top_n})",
                        f"{a_row[pos]:.3f}", f"{a_row[top_a]:.3f} ({top_a})",
                        fmt_p(fs[("pooled_max", "member_rank")]["contextual_optimism_p"]),
                        fmt_p(fs[("fixed_candidate", "member_rank")]["contextual_optimism_p"]),
                        fmt_p(fs[("re_residual", "t")]["contextual_optimism_p"]),
                        fs[("pooled_max", "values")]["rejected_null_type"] or "none",
                        fs[("fixed_candidate", "values")]["rejected_null_type"] or "none",
                        fs[("re_residual", "t")]["rejected_null_type"] or "none"])
    parts += ["### Sample depth: every member cut to samples 0 to 11", "",
              md_table(["Panel", "CO S", "Largest null-type S", "CO Anthropic row",
                        "Largest null-type Anthropic row", "CO rank p, pooled max",
                        "CO rank p, fixed", "CO RE residual p",
                        "Nulls rejected: pooled max, nominal", "Nulls rejected: fixed, nominal",
                        "Nulls rejected: RE residual"], ed_rows), "",
              "C2 holds samples 0 to 11 only. S depends on the samples per cell, so the "
              "equal-depth panel cuts every member to that depth. CO is contextual_optimism "
              "or its cut. Primary pool and grid.", ""]

    # -- Monte Carlo error of the target-only permutation p
    mc_rows = [[e["member"], e["role"], e["grid"], fmt_p(e["p"]),
                f"[{e['mc99_low']:.4f}, {e['mc99_high']:.4f}]",
                "yes" if e["interval_holds_alpha"] else "no"]
               for e in extra["sharp_mc"] if e["p"] <= 0.05]
    parts += ["### Target-only permutation p near the level", "",
              md_table(["Member", "Role", "Grid", "Target-only p", "Monte Carlo 99% interval",
                        "Interval holds 0.01"], mc_rows), "",
              "Every member whose target-only p sits at or below 0.05. A count of rejections "
              "that includes a p whose interval holds 0.01 depends on the permutation seed.", ""]

    # -- UA
    ua_rows = []
    for g in rp.GRIDS:
        d = ua["descriptive"][g]
        for s in d["S"]:
            ti = d["ties"][s]
            ua_rows.append([g, s, f"{d['S'][s]:.3f}", d["argmax_candidate"][s],
                            f"{ti['n_distinct_row_max']} of {ti['n_identities']}",
                            ", ".join(f"{c} {v[s]['row_max_abs_t']:.2f} "
                                      f"(rank {v[s]['row_rank_within_subject']})"
                                      for c, v in d["safety_identities"].items())])
    tied = [g for g in rp.GRIDS if any(t["n_rows_sharing_a_value"] > 0
                                       for t in ua["descriptive"][g]["ties"].values())]
    parts += ["### User-awareness subjects: a descriptive panel of three served models", "",
              md_table(["Grid", "Subject", "S", "Identity holding S", "Distinct row maxima",
                        "Safety identities: row max |t| (rank of 10)"], ua_rows), "",
              "We compute no p. With three members a rank p cannot fall below 1/3. A "
              "leave-one-out SD rests on two values. "
              + (f"Some row maxima tie on the {_join(tied)} {_plural(tied, 'grid', 'grids')}, "
                 "as the column of distinct row maxima shows. " if tied else "")
              + "A rank counts the identities with a strictly larger row maximum, so tied "
              "identities share a rank.", ""]
    need = [[f"{lvl}", f"{math.ceil(1 / lvl) - 1}"] for lvl in (0.1, 0.05, 0.01)]
    parts += ["### Reference members a rank p needs", "",
              md_table(["Level", "Reference members for a rank p floor at the level"], need),
              "", "The floor of a rank p is 1/(K + 1) for K reference members.", ""]
    parts += ["## Reading", ""] + reading(fps, placebo, rows, panel_record, ua, extra) + [""]
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
        ["`false_positive_summary.csv`", "null-type rejections with Clopper-Pearson intervals "
                                         "and the reason a count is set by construction"],
        ["`diagnostics.json`", "rank p of the nine-run reference, shape of the null-type "
                               "maxima, Monte Carlo intervals of the target-only p"],
        ["`placebo/placebo_replicates.jsonl`, `placebo/placebo_summary.json`",
         "200 placebo splits of base A per design, and every summary rate"],
        ["`placebo/placebo_by_member.npz`, `placebo/placebo_by_member_index.json`",
         "200 matched splits of each null-type member"],
        ["`ua/ua_panel.json`", "user-awareness grids, reproduction and descriptive panel"],
        ["`runs/<member>.json`", "one file per member with its inputs and every result"],
        ["`verify/verify_report.json`", "independent recomputation of key numbers from the "
                                        "verdicts and grids"],
        ["`verify/regression_vs_superseded.json`", "every shared value against the previous "
                                                   "build"],
        ["`logs/`", "console logs of every command"]]), ""]
    parts += ["## Runs not completed", "", repro["not_completed"] or "None.", ""]
    return "\n".join(parts)


def _join(items: list[str]) -> str:
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _plural(items, one, many) -> str:
    return one if len(items) == 1 else many


def reading(fps, placebo, rows, panel_record, ua, extra) -> list[str]:
    """The reading, built from the summary rows so every clause follows the data."""
    pool0, grid0 = rp.PRIMARY["pool"], rp.PRIMARY["grid"]
    main = panel_record["panels"]["main"]["results"]
    co_key = "contextual_optimism"
    out = []

    # 1. What a panel rejection can claim.
    out += ["The panel compares each member with other members on the same prompts. No base is "
            "subtracted from any member. Every member is a sample or a fine-tune of "
            "Llama-3.3-70B-Instruct, the base of contextual_optimism. Four reference members "
            "are untuned draws of that base. A rejection therefore claims that a member is "
            "atypical among samples and fine-tunes of its own base. We therefore posit that "
            "a panel verdict does not reach served models of other families.", ""]

    # 2. The resampled p is nominal.
    eq = [r for r in rows if r["p_type"] in RESAMPLED_P]
    eq_all = all(r["reject_0.01"] == r["statistic_above_every_reference_maximum"] for r in eq)
    incl = [1.0 - (1.0 - 1.0 / main[m][pool][g]["pooled_max"]["n_ref"])
            ** main[m][pool][g]["pooled_max"]["M"]
            for pool in rp.POOLS for g in rp.GRIDS for m in rp.MAIN15]
    out += ["Each resampled panel p reduces to one event. A resampled maximum draws the pool's "
            "single largest value with the probability in the table above. "
            + ("That probability exceeds the level in every pool and grid. "
               if min(incl) > rp.ALPHA else "")
            + "A resampled p at or below the level therefore occurs only when the member's "
            "statistic exceeds every value in the pool. "
            + ("Every resampled decision in every panel, pool and grid equals that event. "
               if eq_all else "Most resampled decisions equal that event. ")
            + "When every reference member keeps all its rows, the event has probability "
            "1/(K + 1) under exchangeability. When each drops its top row, the event is more "
            "likely. The rank p states the same event at its true level. We therefore posit "
            "that the resampled p is nominal, and that the rank p and the residual are the "
            "panel's tests.", ""]

    # 3. contextual_optimism.
    co_rows = _sel(rows, panel="main", member=co_key)
    pm_floor = all(r["p"] == r["rank_floor"] for r in co_rows
                   if r["variant"] == "pooled_max" and r["p_type"] == "member_rank")
    fc_floor = all(r["p"] == r["rank_floor"] for r in co_rows
                   if r["variant"] == "fixed_candidate" and r["p_type"] == "member_rank")
    re_all = all(r["reject_0.01"] for r in co_rows if r["variant"] == "re_residual")
    cw_prim = _one(co_rows, pool=pool0, grid=grid0, variant="cellwise", p_type="rank")
    cw_pos = round(cw_prim["p"] * (cw_prim["n_reference_members"] + 1))
    cw_ft = _one(co_rows, pool="finetunes_all_rows", grid=grid0, variant="cellwise",
                 p_type="rank")
    holder = {main[co_key][pool][g]["argmax_candidate"] for pool in rp.POOLS for g in rp.GRIDS}
    ordinal = {1: "first", 2: "second", 3: "third"}.get(cw_pos, f"number {cw_pos}")
    p3 = ""
    if pm_floor:
        p3 += ("contextual_optimism holds the panel's largest S in every pool and grid. Its "
               "rank p therefore sits at the panel's floor. ")
    if fc_floor:
        p3 += ("Its Anthropic row also tops every other member's Anthropic row in every pool "
               "and grid. ")
    if re_all:
        p3 += ("The random-effects residual rejects it in every pool and grid, on S and on "
               "log S. ")
    p3 += (f"Its cellwise statistic ranks {ordinal} in the primary pool and grid"
           + (", and first with the ten fine-tuned nulls as the reference. "
              if cw_ft["p"] == cw_ft["rank_floor"] else ". "))
    if holder == {"anthropic"}:
        p3 += ("Anthropic holds its S in every pool and grid, as in the registered test. The "
               "fixed candidate variant reads the Anthropic row by design, so it names no "
               "candidate. ")
    p3 += ("We therefore contend that contextual_optimism is the panel's most extreme member, "
           "and that only the residual's normal model carries that rank to the registered "
           "level.")
    out += [p3, ""]

    # 4. The null-type counts follow from construction.
    closed = [f for f in fps if f["panel"] == "main" and f["pool"] in CLOSED_POOLS
              and (f["p_type"] in RESAMPLED_P or f["p_type"] == "any_candidate_bonferroni")]
    all_fixed = all(f["construction"].startswith("fixed") for f in closed)
    k_closed = {f["pool"]: f["n_reject_null_type"] for f in closed
                if f["p_type"] in RESAMPLED_P}
    one_in_nulls = all(f["n_reject_null_type"] <= 1 for f in closed
                       if f["pool"] == "nulls_all_rows" and f["p_type"] in RESAMPLED_P)
    zero_in_all = all(f["n_reject_null_type"] == 0 for f in closed
                      if f["pool"] == "all_all_rows" and f["variant"] == "pooled_max"
                      and f["p_type"] in RESAMPLED_P)
    droptop = [f for f in fps if f["panel"] == "main" and f["pool"].endswith("drop_top")
               and f["p_type"] in RESAMPLED_P]
    rk = extra["family9_rank"]["with_base_A"]["nulls_only_all_rows"]
    flagged9 = [k for k in rp.FAMILY_NULLS if rk[k]["values_p"] <= rp.ALPHA]
    at_floor9 = all(rk[k]["rank_p"] == rk[k]["floor"] for k in flagged9)
    p4 = ""
    if all_fixed and k_closed:
        p4 += "The null-type counts of the resampled variants follow from the construction. "
        if one_in_nulls:
            p4 += ("In the null-type pool that keeps every row, one null-type member tops the "
                   "panel, so one rejects. ")
        if zero_in_all:
            p4 += ("In the pool of every member, contextual_optimism tops the panel on S, so no "
                   "null-type member rejects on the pooled maximum. ")
        p4 += ("The any-candidate Bonferroni p rejects the member on top of each candidate "
               "row. ")
    if max(f["n_reject_null_type"] for f in droptop) > 1:
        p4 += ("Dropping each reference member's top row lowers the pool, and more null-type "
               "members reject. ")
    if len(flagged9) == 1 and at_floor9:
        p4 += ("In its primary pool, the paper's nine-run cross-run reference flags one null on "
               "base-referenced grids. That null tops the eight-run panel, and its rank p sits "
               "at the floor. ")
    p4 += ("We therefore contend that these counts measure the panel's construction and carry "
           "no information on its size.")
    out += [p4, ""]

    # 5. The residual's shape assumption.
    sh = {s["grid"]: s for s in extra["shape"]}
    skewed = all(s["skew"] > 0 for s in sh.values())
    shap_rej = [g for g, s in sh.items() if s["shapiro_p"] <= 0.05]
    hc = {pt: all(_one(rows, panel="main", member="hallucinates_citations", pool=pool0, grid=g,
                       variant="re_residual", p_type=pt)["reject_0.01"] for g in rp.GRIDS)
          for pt in ("t", "t_log")}
    p5 = "The residual assumes that the reference maxima are normal. "
    if skewed:
        p5 += "The null-type maxima are right-skewed on both grids. "
    if shap_rej:
        p5 += (f"A Shapiro-Wilk test rejects normality on the {_join(shap_rej)} "
               f"{_plural(shap_rej, 'grid', 'grids')}, and does not reject it on log S. "
               if all(sh[g]["shapiro_p_log"] > 0.05 for g in shap_rej) else
               f"A Shapiro-Wilk test rejects normality on the {_join(shap_rej)} "
               f"{_plural(shap_rej, 'grid', 'grids')}. ")
    if re_all:
        p5 += "On log S the residual still rejects contextual_optimism. "
    if hc["t"] and hc["t_log"]:
        p5 += ("It also rejects hallucinates_citations on both grids, on S and on log S. That "
               "null control holds a large name effect of its own, and the target-only "
               "permutation test rejects it too. We therefore posit that a residual rejection "
               "marks an atypical member, and that a null control can be one.")
    else:
        p5 += "We therefore posit that the residual's decisions depend on its shape assumption."
    out += [p5, ""]

    # 6. Cellwise zero-SD cells and pool composition.
    drops = {m: main[m][pool0][grid0]["cellwise"]["zero_sd_cells"] for m in rp.MAIN15}
    worst = max(drops, key=lambda m: (drops[m]["n_member_t_nonzero"], drops[m]["max_abs_member_t"]))
    co_lost = drops[co_key]["n_member_t_nonzero"]
    cw_flip = (cw_prim["p"] != cw_prim["rank_floor"]) and (cw_ft["p"] == cw_ft["rank_floor"])
    p6 = ("The cellwise variant leaves out each cell in which every reference member holds the "
          "same t. ")
    if drops[worst]["n_member_t_nonzero"] > 0:
        p6 += (f"{worst} loses the most such cells with a non-zero t of its own. "
               + ("contextual_optimism loses none. " if co_lost == 0 else ""))
    fl = {m: main[m][pool0][grid0]["cellwise"] for m in rp.MAIN15}
    top_plain = [m for m in rp.MAIN15 if fl[m]["rank_p"] == 1.0 / (len(
        main[m][pool0]["reference_members"]) + 1)]
    top_floor = [m for m in rp.MAIN15 if fl[m]["sd_floor"]["rank_p"] == 1.0 / (len(
        main[m][pool0]["reference_members"]) + 1)]
    p6 += "Flooring each cell's SD keeps these cells. "
    if top_plain != top_floor:
        p6 += (f"With the floor, {_join(top_floor) or 'no member'} "
               f"{_plural(top_floor, 'tops', 'top')} the cellwise panel in the primary pool, "
               f"and {_join([m for m in top_plain if m not in top_floor]) or 'no member'} "
               "no longer does. ")
    if cw_flip:
        p6 += ("The cellwise rank of contextual_optimism also moves with the pool. It tops the "
               "ten fine-tuned nulls and falls below one member of the null-type pool. ")
    p6 += ("We therefore posit that the cellwise variant depends on the pool's composition more "
           "than the other variants do.")
    out += [p6, ""]

    # 7. Placebo.
    key = f"{pool0}|{grid0}"
    rates = placebo["rates"]
    single = placebo["single_split"]["placebo_halves"]
    single_rej = [v for v in rp.VARIANTS for pt in rp.P_TYPES[v]
                  for h in ("base_A_half1", "base_A_half2")
                  if single[h][f"{key}|{v}|{pt}"] <= rp.ALPHA]
    hc_s = main["hallucinates_citations"][pool0][grid0]["S"]
    halves_capped = placebo["largest_half_S"]["placebo_halves"] < hc_s
    bm = placebo["by_member"]
    o = bm["over_splits"][f"{key}|pooled_max|values"]
    k_ref = bm["n_reference_members_nulls_all_rows"]
    near = abs(o["mean_share_both_halves"] - 1.0 / (k_ref + 1)) < 0.02
    above = {d: [v for v in rp.VARIANTS
                 if rates[d][f"{key}|{v}|{rp.NOMINAL.get(v, 't')}"]["base_A_half1"]["cp95"][0]
                 > rp.ALPHA] for d in rates}
    p7 = ("The placebo halves of base A reject in no variant in the single split. "
          if not single_rej else "A placebo half of base A rejects in the single split. ")
    if halves_capped:
        p7 += ("Halves that compete with full-size members rarely top the panel. Their grids "
               "rest on half the samples per cell, and hallucinates_citations holds an S above "
               "every half of base A. ")
    p7 += ("In the matched design every member is a half. The share of splits in which a split "
           "member's half tops the panel then varies widely across split members. ")
    if near:
        p7 += "Its mean over split members sits near 1/(K + 1). "
    p7 += ("A split member with a large name effect of its own tops the panel often. ")
    if above["placebo_matched"]:
        p7 += ("In the matched design of base A, the interval of a half lies above the level in "
               f"the {_join([PRETTY_VARIANT[v] for v in above['placebo_matched']])} "
               f"{_plural(above['placebo_matched'], 'variant', 'variants')}. ")
    re_k = f"{key}|re_residual|t"
    re_o = bm["over_splits"][re_k]
    re_hi = [s for s in bm["splits"] if bm["rates"][s][re_k]["half1"]["cp95"][0] > rp.ALPHA]
    re_rest = [(bm["rates"][s][re_k]["half1"]["share"] + bm["rates"][s][re_k]["half2"]["share"])
               / 2 for s in bm["splits"] if s not in re_hi]
    re_excess = re_o["mean_share_both_halves"] > rp.ALPHA
    if re_excess:
        p7 += "The residual also rejects a split half more often than the level on average. "
        if re_hi and np.mean(re_rest) <= 1.5 * rp.ALPHA:
            p7 += (f"The excess sits in {_join(re_hi)}, and the other split members reject near "
                   "the level. ")
    p7 += ("We therefore conjecture that a member's own generic effect sets the size of "
           + ("every panel test, and that the residual holds the level only for members "
              "without one." if re_excess else "the resampled panel test."))
    out += [p7, ""]

    # 8. Equal depth.
    ed = panel_record["panels"]["equal_depth_s0-11"]["results"]
    ed_members = panel_record["panels"]["equal_depth_s0-11"]["members"]
    ed_pos = next(m for m in ed_members if rp.role_of(m) == "positive")
    ed_nulls = [m for m in ed_members if rp.role_of(m) != "positive"]
    s_ed = {m: ed[m][pool0][grid0]["S"] for m in ed_members}
    a_ed = {m: ed[m][pool0][grid0]["fixed_candidate"][rp.TARGET_CANDIDATE]["S_row"]
            for m in ed_members}
    s_main = {m: main[m][pool0][grid0]["S"] for m in rp.MAIN15}
    a_main = {m: main[m][pool0][grid0]["fixed_candidate"][rp.TARGET_CANDIDATE]["S_row"]
              for m in rp.MAIN15}
    base = (lambda m: m.removesuffix(rp.EQUAL_DEPTH_SUFFIX))
    top_s_same = base(max(ed_nulls, key=s_ed.get)) == max(NULL_TYPE, key=s_main.get)
    top_a_main = max(NULL_TYPE, key=a_main.get)
    top_a_ed = base(max(ed_nulls, key=a_ed.get))
    co_tops_ed = s_ed[ed_pos] > max(s_ed[m] for m in ed_nulls)
    p8 = ("C2 holds fewer samples per cell than the other members, and S depends on depth. "
          "Cutting every member to the depth of C2 ")
    p8 += ("keeps contextual_optimism on top of the panel" if co_tops_ed else
           "moves contextual_optimism off the top of the panel")
    p8 += (" and keeps the largest null-type S with the same member. " if top_s_same else
           " and moves the largest null-type S to another member. ")
    if top_a_main != top_a_ed:
        p8 += (f"The largest null-type Anthropic row moves from {top_a_main} to {top_a_ed}. "
               "We therefore posit that the fixed candidate variant's null-type rejection "
               "depends on sample depth.")
    else:
        p8 += ("The largest null-type Anthropic row stays with the same member. We therefore "
               "posit that the panel's ranking does not depend on sample depth.")
    out += [p8, ""]

    # 9. User awareness.
    desc = ua["descriptive"][grid0]
    groups = {k: v["group"] for k, v in ua["identities"].items()}
    holders = {s: desc["argmax_candidate"][s] for s in desc["S"]}
    safety_top = [s for s, c in holders.items() if groups[c] == "safety"]
    out += ["The three served models form a panel too small to test. "
            + ("In every subject a general-population identity holds the largest target-only "
               "statistic, and no safety identity holds it. " if not safety_top else
               "A safety identity holds the largest target-only statistic in at least one "
               "subject. ")
            + "A rank p reaches the registered level only with the number of reference models "
            "in the last table. We therefore posit that a model panel can test the "
            "user-awareness claim only with about a hundred served models graded on the same "
            "design.", ""]

    # 10. Close.
    out += ["A panel of this size can rank a member as its most extreme member. Its smallest "
            "honest p equals one over the panel size. A decision at the registered level needs "
            "about a hundred reference members, or a parametric model of the maxima that the "
            "null-type members can check. We therefore posit that a panel of this size cannot "
            "carry a decision at the registered level by itself."]
    return out


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
    placebo = placebo_summary(panel_record)
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
        {"what": "matched placebo by member: the base A design equals placebo_matched, "
                 "every value of every replicate",
         "n": placebo["by_member"]["base_A_equals_placebo_matched"]["n"],
         "n_match": placebo["by_member"]["base_A_equals_placebo_matched"]["n_equal"]},
    ]
    if screen["checks"]:
        found = [c for c in screen["checks"] if c["found"]]
        summary.append({"what": "target-only grids against the sharp-null screen's grids "
                                f"({len(found)} found of {len(screen['checks'])})",
                        "n": len(found), "n_match": sum(c["exactly_equal"] for c in found)})
    regress_path = OUT / "verify" / "regression_vs_superseded.json"
    regression = load_json(regress_path) if regress_path.exists() else None
    if regression is None:
        not_completed.append("the regression against the previous build has not run")
    all_ok = (all(c["n"] == c["n_match"] for c in summary) and gate["all_reproduce"]
              and (regression is None or regression["n_failures"] == 0))
    repro = {"all_match": all_ok, "summary": summary, "gate": gate, "grid_checks": gchecks,
             "sharp_checks": sharp_rec["checks"], "ua_checks": ua["checks"],
             "sharp_null_screen": screen,
             "regression_vs_superseded": (None if regression is None else
                                          {k: regression[k] for k in regression
                                           if k != "differences"}),
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
        "members_model": "every member is Llama-3.3-70B-Instruct: base draws A, B, C1, C2, "
                         "and LoRA adapters over it for every other member",
        "pools": {"nulls_all_rows": "the other null-type members, every row (primary; the "
                                    "paper's nulls_only_all_rows)",
                  "nulls_drop_top": "the other null-type members, each without its top row",
                  "all_drop_top": "every other member, each without its top row (the paper's "
                                  "all_family)",
                  "all_all_rows": "every other member, every row",
                  "finetunes_all_rows": "the other fine-tuned nulls only (eight AuditBench "
                                        "controls, two synthetic-document nulls), every row; "
                                        "no draw of the base"},
        "variants": {
            "pooled_max": "S against the max of M draws from the pooled reference |t| "
                          "(cross_run_reference_test, nominal); member rank p primary",
            "fixed_candidate": f"the {rp.TARGET_CANDIDATE} row's max against the other "
                               "members' rows of the same candidate; member rank p primary; "
                               "every candidate kept in the JSON; the any-candidate "
                               "Bonferroni p names its lowest-p row",
            "cellwise": "signed t standardized per cell by the reference members' mean and SD "
                        "(leave-one-out); a cell whose reference SD is zero has no z and is left "
                        "out, counted per member; max |z| referred by full-conformal rank "
                        "(primary), Bonferroni over cells of a t_{n-1} predictive p, and "
                        "resampled maxima (nominal); the same Z with each cell's SD floored at "
                        "the median positive cell SD, rank p only",
            "re_residual": "(S - mean) / (sd sqrt(1 + 1/n)) over the reference members' "
                           "maxima, one-sided t_{n-1}; the same on log S; Shapiro-Wilk p and "
                           "skewness of the reference maxima stored"},
        "primary": rp.PRIMARY, "nominal": rp.NOMINAL,
        "panel_descriptions": {
            "main": "the 15 members",
            "alt_C1s0-11": "C1 replaced by its samples 0 to 11",
            "placebo_halves": "base A replaced by its two split halves",
            "placebo_matched": "every member a split half; base A's two halves tested",
            "equal_depth_s0-11": "every member cut to samples 0 to 11, the depth of C2"},
        "seeds": {"panel": "SeedSequence([20260726, member index, panel index, pool index, "
                           "grid index, variant index, scheme or candidate index]); placebo "
                           "replicate r appends 1000 + r",
                  "gate": "cross_run_reference_test(seed=100 + FAMILY index), as the paper",
                  "family9_target_only": "the paper's cross() with seeds 100 + FAMILY index",
                  "permutation": "seed 20260726, as stage 6",
                  "placebo_by_member": load_json(OUT / "placebo" / "placebo_by_member_index.json"
                                                 )["seeds"]},
        "placebo": "base A split per cell with B42's seeds (run 3, model 0, replicate r); "
                   "matched design splits every other member with SeedSequence([20260726, "
                   "1000 + member index, r]) and keeps half 1; 200 replicates per design; the "
                   "matched design also runs with each of the 14 null-type members as the "
                   "split pair, 200 replicates each, pools nulls_all_rows and "
                   "finetunes_all_rows",
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
    extra = {"family9_rank": family9_rank(panel_record), "shape": shape_table(panel_record),
             "sharp_mc": sharp_mc(sharp)}
    rp.write_new(OUT / "diagnostics.json", extra)
    rp.write_new(OUT / "placebo" / "placebo_summary.json", placebo)
    runs_files(panel_record, sharp, rows)
    text = readme(settings, repro, rows, fps, placebo, ua, panel_record, sharp, index, extra)
    rp.write_new(OUT / "README.md", text, text=True)
    print(text)
    return 0 if all_ok else 1
