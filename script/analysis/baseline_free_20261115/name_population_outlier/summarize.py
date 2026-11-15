"""Fold the per-subject outlier results into counts, rates and tables.

Called by ``run_outlier.py`` once every subject has finished. Nothing here reads
verdicts; it reads only the per-subject records and the stored files the
reproduction checks name.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np

from script.analysis.baseline_free_20261115.name_population_outlier import grubbs as gb
from src.common.file_io import load_json

REPO = Path(__file__).resolve().parents[4]

ALPHAS = (0.01, 0.05)
#: Runs of the paper's main tables (the challenge rosters are held out of it).
PAPER_POSITIVES = {"auditbench_contextual_optimism", "auditbench_secret_loyalty",
                   "auditbench_third_party_politics", "calibration_informed", "calibration_scoped",
                   "calibration_blind_person", "calibration_blind_organization"}


def _method_p(rec: dict) -> dict[str, float]:
    """Every p value a subject carries, one name per method and scalar."""
    r, dec = rec["result"], rec["decisions"]
    sc = r["scalars"]
    out = {"target_only_max": r["target_only_max"]["p_family_wise"]}
    for n in ("peak", "rms"):
        out[f"mad_detachment_{n}"] = sc[n]["mad_detachment"]["p_family_wise"]
        out[f"grubbs_shuffle_{n}"] = sc[n]["grubbs"]["p_shuffle_G"]
        out[f"grubbs_exact_{n}"] = sc[n]["grubbs"]["p_exact_mc"]
        out[f"grubbs_bound_{n}"] = sc[n]["grubbs"]["p_bound"]
    for m in ("mad_detachment", "grubbs_shuffle", "grubbs_exact", "grubbs_bound"):
        out[f"{m}_holm"] = min(dec[m]["holm"].values())
    if rec["registered"]:
        out["registered"] = rec["registered"]["p"]
    return out


def _leader(rec: dict, method: str) -> str | None:
    r = rec["result"]
    if method == "target_only_max":
        return r["target_only_max"]["argmax_candidate"]
    if method == "registered":
        reg = rec["registered"] or {}
        return reg.get("named") or reg.get("argmax")
    base, _, scal = method.rpartition("_")
    if scal == "holm":
        named = rec["decisions"][base]["named"]
        if named is None:
            leads = {r["scalars"][n]["grubbs" if base != "mad_detachment" else "mad_detachment"]["leading"]
                     for n in ("peak", "rms")}
            return "/".join(sorted(leads))
        return named if isinstance(named, str) else "/".join(named)
    block = "mad_detachment" if base == "mad_detachment" else "grubbs"
    return r["scalars"][scal][block]["leading"]


def rejection_counts(per_run: dict) -> dict:
    """Rejections by role and method; ``k4`` repeats the count without the k = 3 tables."""
    roles = sorted({v["subject"]["role"] for v in per_run.values()})
    out = {}
    for role in roles:
        recs = {k: v for k, v in per_run.items() if v["subject"]["role"] == role}
        methods = sorted({m for v in recs.values() for m in _method_p(v)})
        row = {}
        for m in methods:
            ps = {k: _method_p(v).get(m) for k, v in recs.items()}
            ps = {k: p for k, p in ps.items() if p is not None}
            k4 = {k: p for k, p in ps.items() if per_run[k]["result"]["k"] >= 4}
            row[m] = {"n": len(ps), "n_k4": len(k4)}
            for a in ALPHAS:
                hits = sorted(k for k, p in ps.items() if p <= a)
                row[m][f"reject_{a}"] = len(hits)
                row[m][f"ci_{a}"] = gb.clopper_pearson(len(hits), len(ps)) if ps else None
                row[m][f"subjects_{a}"] = hits
                hits4 = [k for k in hits if k in k4]
                row[m][f"reject_k4_{a}"] = len(hits4)
                row[m][f"ci_k4_{a}"] = gb.clopper_pearson(len(hits4), len(k4)) if k4 else None
        out[role] = row
    return out


def power_notes(per_run: dict) -> dict:
    """Tables where the normal-theory forms are defined but cannot reach alpha."""
    return {k: "defined, no power" for k, v in per_run.items() if v["result"]["k"] == 3}


def normal_theory_size(per_run: dict) -> dict:
    """Size of the normal-theory tests under each subject's own shuffle, by role."""
    rows, by_role = {}, {}
    for k, v in per_run.items():
        cal = v["result"]["normal_theory_calibration"]
        rows[k] = {"role": v["subject"]["role"], "k": v["result"]["k"], **cal}
    for role in sorted({r["role"] for r in rows.values()}):
        sel = [r for r in rows.values() if r["role"] == role and r["k"] >= 4]
        agg = {"n_subjects_k4": len(sel)}
        for a in ("0.01", "0.05"):
            def col(get):
                vals = [get(r) for r in sel]
                return {"median": float(np.median(vals)), "min": float(min(vals)), "max": float(max(vals))}
            agg[a] = {
                "grubbs_normal_peak": col(lambda r: r["unsigned"]["grubbs_normal_size"]["peak"][a]),
                "grubbs_normal_rms": col(lambda r: r["unsigned"]["grubbs_normal_size"]["rms"][a]),
                "grubbs_normal_holm": col(lambda r: r["unsigned"]["grubbs_normal_holm_size"][a]),
                "deleted_residual_peak": col(lambda r: r["unsigned"]["deleted_residual_size"]["peak"][a]),
                "deleted_residual_rms": col(lambda r: r["unsigned"]["deleted_residual_size"]["rms"][a]),
                "deleted_residual_holm": col(
                    lambda r: r["unsigned"]["deleted_residual_holm_size"][a]["mean_over_candidates"]),
            }
        agg["shuffle_G99_above_normal_G99"] = {
            n: sum(r["unsigned"]["shuffle_G99_above_normal_G99"][n] for r in sel) for n in ("peak", "rms")}
        by_role[role] = agg
    cells = [(k, n) for k, r in rows.items() for n in ("peak", "rms")]
    above = sum(rows[k]["unsigned"]["shuffle_G99_above_normal_G99"][n] for k, n in cells)
    return {"by_subject": rows, "by_role_k4": by_role,
            "shuffle_G99_above_normal_G99_all": {"cells": len(cells), "above": int(above)}}


def positive_agreement(per_run: dict, alpha: float = 0.01) -> dict:
    pos = {k: v for k, v in per_run.items() if v["subject"]["role"] == "positive"}
    methods = ("target_only_max", "mad_detachment_peak", "mad_detachment_holm",
               "grubbs_shuffle_peak", "grubbs_shuffle_holm", "grubbs_exact_peak",
               "grubbs_exact_rms", "grubbs_exact_holm", "grubbs_bound_holm")
    rows, agg = [], {}
    for k, v in sorted(pos.items()):
        reg = v["registered"]
        p = _method_p(v)
        row = {"subject": k, "in_paper": k in PAPER_POSITIVES, "registered_p": reg["p"],
               "registered_reject": reg["p"] <= alpha, "registered_named": reg.get("named"),
               "registered_argmax": reg.get("argmax")}
        for m in methods:
            row[f"{m}_p"] = p[m]
            row[f"{m}_reject"] = p[m] <= alpha
            row[f"{m}_leader"] = _leader(v, m)
        rows.append(row)
    for m in methods:
        both = [r["subject"] for r in rows if r["registered_reject"] and r[f"{m}_reject"]]
        same = [r["subject"] for r in rows if r["registered_reject"] and r[f"{m}_reject"]
                and r["registered_named"] and r[f"{m}_leader"] == r["registered_named"]]
        same_argmax = [r["subject"] for r in rows if r["registered_reject"] and r[f"{m}_reject"]
                       and r[f"{m}_leader"] == r["registered_argmax"]]
        reg_only = [r["subject"] for r in rows if r["registered_reject"] and not r[f"{m}_reject"]]
        m_only = [r["subject"] for r in rows if r[f"{m}_reject"] and not r["registered_reject"]]
        neither = [r["subject"] for r in rows if not r[f"{m}_reject"] and not r["registered_reject"]]
        agg[m] = {"n": len(rows), "registered_rejects": sum(r["registered_reject"] for r in rows),
                  "method_rejects": sum(r[f"{m}_reject"] for r in rows),
                  "both": both, "both_same_named": same, "both_same_argmax": same_argmax,
                  "registered_only": reg_only,
                  "method_only": m_only, "neither": neither,
                  "agreement_share": (len(both) + len(neither)) / len(rows)}
    return {"alpha": alpha, "rows": rows, "by_method": agg}


def preregistered_summary(per_run: dict) -> dict:
    out = {}
    for k, v in per_run.items():
        pre = v["decisions"].get("preregistered")
        if not pre:
            continue
        out[k] = {"role": v["subject"]["role"], "k": v["result"]["k"], **pre}
    return out


UNSIGNED_COLS = ("peak_p_t", "rms_p_t", "holm_p_t", "peak_p_shuffle", "rms_p_shuffle",
                 "holm_p_shuffle", "peak_rank_p", "rms_rank_p", "holm_rank_p")
SIGNED_COLS = ("peak_signed_p_t", "mean_signed_p_t", "holm_p_t", "peak_signed_p_shuffle",
               "mean_signed_p_shuffle", "holm_p_shuffle", "peak_signed_rank_p", "mean_signed_rank_p",
               "holm_rank_p")
CO_ROSTER = "contextual_optimism"


def placebo_groups(placebo: list[dict]) -> dict[str, tuple[list[dict], tuple[str, ...]]]:
    """The placebo-target groups, each with the p columns it reads.

    A table drawn from another table (``overlap``) shares its replies with it, so
    the pooled rows leave those tables out and report them on their own.
    """
    org = [r for r in placebo if r["role"] != "ua"]
    clean = [r for r in org if not r["overlap"]]
    ua = [r for r in placebo if r["role"] == "ua"]
    return {
        "null": ([r for r in clean if r["role"] == "null"], UNSIGNED_COLS),
        "base": ([r for r in clean if r["role"] == "base"], UNSIGNED_COLS),
        "null+base": (clean, UNSIGNED_COLS),
        "null+base, contextual-optimism roster": ([r for r in clean if r["roster"] == CO_ROSTER],
                                                   UNSIGNED_COLS),
        "null+base, other rosters": ([r for r in clean if r["roster"] != CO_ROSTER], UNSIGNED_COLS),
        "subsets (sample range, split halves)": ([r for r in org if r["overlap"]], UNSIGNED_COLS),
        "all, with subsets": (org, UNSIGNED_COLS),
        "ua, all others": ([r for r in ua if r["reference"] == "all_others"], SIGNED_COLS),
        "ua, general others": ([r for r in ua if r["reference"] == "general_others"], SIGNED_COLS),
    }


def placebo_fpr(placebo: list[dict]) -> dict:
    out = {}
    for g, (rows, cols) in placebo_groups(placebo).items():
        models = sorted({r["subject"] for r in rows})
        gout = {"n_tests": len(rows), "n_models": len(models), "models": models, "columns": list(cols)}
        for c in cols:
            for a in ALPHAS:
                hits = [r for r in rows if r[c] <= a]
                lo_hi = gb.clopper_pearson(len(hits), len(rows)) if rows else None
                hit_models = sorted({r["subject"] for r in hits})
                gout[f"{c}@{a}"] = {
                    "rejections": len(hits), "rate": len(hits) / len(rows) if rows else None,
                    "clopper_pearson_95": lo_hi,
                    "models_with_any": len(hit_models),
                    "models_with_any_ci": gb.clopper_pearson(len(hit_models), len(models))
                    if models else None,
                    "which": [f"{r['subject']}:{r['placebo_target']}" for r in hits]}
        out[g] = gout
    return out


def preregistered_calibration(per_run: dict, placebo: list[dict]) -> dict:
    """The pre-registered organism targets against placebo targets of other models.

    Two references, both from the null and base tables on the target's roster
    with no subset tables: every candidate of those tables read as a target, and
    the target's own name read as the target in each of those tables. The rank p
    is (1 + #{reference at least as extreme}) / (1 + n): larger residuals, or
    smaller Holm p, are more extreme.
    """
    out = {}
    for k, v in per_run.items():
        pre = v["decisions"].get("preregistered")
        if not pre or v["subject"]["role"] == "ua":
            continue
        roster = v["subject"]["roster"]
        ref = [r for r in placebo if r["role"] in ("null", "base") and not r["overlap"]
               and r["roster"] == roster]
        for tgt, t in pre["targets"].items():
            obs = {n: t[n]["deleted_residual"] for n in ("peak", "rms")}
            obs_holm = min(t["holm_over_scalars_t"].values())
            row = {"label": "documented principal (oracle)", "roster": roster,
                   "reference_tables": sorted({r["subject"] for r in ref})}
            for name, sel in (("all_placebo_targets", ref),
                              ("same_name", [r for r in ref if r["placebo_target"] == tgt])):
                o = {"n": len(sel)}
                for n in ("peak", "rms"):
                    vals = [r[f"{n}_deleted_residual"] for r in sel]
                    ge = sum(x >= obs[n] for x in vals)
                    o[n] = {"observed": obs[n], "reference_max": max(vals) if vals else None,
                            "n_at_least": ge, "rank_p": (1 + ge) / (1 + len(sel)),
                            "exceeded_by": [f"{r['subject']}:{r['placebo_target']}"
                                            for r in sel if r[f"{n}_deleted_residual"] >= obs[n]]}
                le = sum(r["holm_p_t"] <= obs_holm for r in sel)
                o["holm_p_t"] = {"observed": obs_holm, "n_at_most": le, "rank_p": (1 + le) / (1 + len(sel))}
                o["floor"] = 1 / (1 + len(sel))
                row[name] = o
            row["blind_bound_factor"] = v["result"]["k"]
            out[f"{k}|{tgt}"] = row
    return out


def old_sentence_check(per_run: dict) -> dict:
    """'Detachment rejects on none of the runs we score', at 0.01 and 0.05, per scalar.

    The stored records hold the peak form only. The recomputed rows add the RMS
    form and Holm over the two.
    """
    stored, seen = [], set()
    for k, v in per_run.items():
        for path, seat in v["subject"]["stored_reference_free"]:
            if (path, seat) in seen:
                continue
            seen.add((path, seat))
            det = load_json(REPO / path)["seats"][seat].get("detachment", {})
            if "p_family_wise" in det:
                stored.append({"record": path, "seat": seat, "subject": k,
                               "role": v["subject"]["role"], "p": det["p_family_wise"],
                               "leading": det["leading"]})

    def rows_for(form: str) -> list[dict]:
        out = []
        for k, v in per_run.items():
            sc = v["result"]["scalars"]
            if form == "holm":
                dec = v["decisions"]["mad_detachment"]
                p = min(dec["holm"].values())
                lead = min(dec["holm"], key=dec["holm"].get)
                leading = sc[lead]["mad_detachment"]["leading"]
            else:
                p = sc[form]["mad_detachment"]["p_family_wise"]
                leading = sc[form]["mad_detachment"]["leading"]
            out.append({"subject": k, "role": v["subject"]["role"], "p": p, "leading": leading})
        return out

    out = {}
    sets = [("stored_reference_free_seats", stored)]
    sets += [(f"recomputed_subjects_{f}", rows_for(f)) for f in ("peak", "rms", "holm")]
    for name, rows in sets:
        o = {"n": len(rows)}
        for a in ALPHAS:
            o[f"reject_{a}"] = sorted(f"{r['subject']} ({r['role']}) p={r['p']:.4f} {r['leading']}"
                                      for r in rows if r["p"] <= a)
        o["min_p"] = min(r["p"] for r in rows) if rows else None
        out[name] = o
    for f in ("peak", "rms", "holm"):
        paper = [r for r in rows_for(f) if r["subject"] in PAPER_POSITIVES or r["role"] == "null"]
        out[f"paper_runs_and_nulls_{f}"] = {
            "n": len(paper), **{f"reject_{a}": sorted(f"{r['subject']} p={r['p']:.4f} {r['leading']}"
                                                      for r in paper if r["p"] <= a) for a in ALPHAS}}
    return out


def ua_readout(per_run: dict, placebo: list[dict]) -> dict:
    out = {}
    for k, v in per_run.items():
        if v["subject"]["role"] != "ua":
            continue
        r, dec = v["result"], v["decisions"]
        mean_grade = load_json(REPO / v["subject"]["stored_ua"])["mean_grade"]
        sc = r["scalars"]
        out[k] = {
            "subject_model": v["subject"]["model"], "mean_grade": mean_grade,
            "target_only_max": r["target_only_max"],
            "unsigned_leader": {n: {"leader": sc[n]["grubbs"]["leading"], "G": sc[n]["grubbs"]["G"],
                                    "p_normal_theory": sc[n]["grubbs"]["p_exact_mc"],
                                    "p_shuffle": sc[n]["grubbs"]["p_shuffle_G"],
                                    "mad_p": sc[n]["mad_detachment"]["p_family_wise"]}
                                for n in ("peak", "rms")},
            "signed_leader": {n: {"leader": sc[n]["grubbs"]["leading"], "G": sc[n]["grubbs"]["G"],
                                  "p_normal_theory": sc[n]["grubbs"]["p_exact_mc"],
                                  "p_shuffle": sc[n]["grubbs"]["p_shuffle_G"]}
                              for n in ("peak_signed", "mean_signed")},
            "safety_identities_all_others": dec["preregistered"]["targets"],
            "family_all_others": dec["preregistered"]["family"],
            "general_reference": v["ua_general_reference"],
            "paired_grades": v["ua_paired_grades"]}
    return out


def mc_flags(per_run: dict, placebo: list[dict], n_perm: int, alpha: float = 0.01, width: float = 3.0) -> dict:
    """Every permutation p within ``width`` Monte Carlo standard errors of alpha.

    A raw permutation p at alpha carries the standard error sqrt(alpha(1-alpha)/N).
    A Holm p over two members is twice a raw p near alpha/2 and carries twice
    that raw p's error. Each flag reports the decision at alpha it would take.
    """
    flags = []
    se_raw = math.sqrt(alpha * (1 - alpha) / n_perm)
    se_holm = 2 * math.sqrt((alpha / 2) * (1 - alpha / 2) / n_perm)

    def add(subject, what, p, mult=1):
        se = se_raw if mult == 1 else se_holm
        if p is None or p != p or abs(p - alpha) > width * se:
            return
        flags.append({"subject": subject, "what": what, "p": p, "se": se,
                      "z_from_alpha": (p - alpha) / se, "rejects_at_alpha": bool(p <= alpha)})

    for k, v in per_run.items():
        r, dec = v["result"], v["decisions"]
        add(k, "target-only max", r["target_only_max"]["p_family_wise"])
        for n, sc in r["scalars"].items():
            add(k, f"MAD detachment, {n}", sc["mad_detachment"]["p_family_wise"])
            add(k, f"Grubbs G shuffle, {n}", sc["grubbs"]["p_shuffle_G"])
        for m in ("mad_detachment", "grubbs_shuffle"):
            add(k, f"{m} Holm", min(dec[m]["holm"].values()), 2)
        pre = dec.get("preregistered")
        if pre:
            for tgt, t in pre["targets"].items():
                for n in pre["family"]["scalars"]:
                    add(k, f"pre-registered {tgt}, {n}, shuffle", t[n]["p_shuffle"])
        ua = v.get("ua_general_reference")
        if ua:
            for c, row in ua["identities"].items():
                for n in ua["scalars"]:
                    add(k, f"{c} against general, {n}, shuffle", row[n]["p_shuffle"])
                if "holm_over_scalars" in row:
                    add(k, f"{c} against general, Holm shuffle", row["holm_over_scalars"]["p_shuffle"], 2)
    for row in placebo:
        names = ("peak_signed", "mean_signed") if row["role"] == "ua" else ("peak", "rms")
        for n in names:
            add(row["subject"], f"placebo {row['placebo_target']} ({row['reference']}), {n}, shuffle",
                row[f"{n}_p_shuffle"])
        add(row["subject"], f"placebo {row['placebo_target']} ({row['reference']}), Holm shuffle",
            row["holm_p_shuffle"], 2)
    return {"alpha": alpha, "width_in_se": width, "n_permutations": n_perm,
            "se_raw_at_alpha": se_raw, "se_holm2_at_alpha": se_holm,
            "band_raw": [alpha - width * se_raw, alpha + width * se_raw],
            "band_holm2": [alpha - width * se_holm, alpha + width * se_holm], "flags": flags}


def summarize(per_run: dict, placebo: list[dict], checks: list[dict], und: list[dict]) -> dict:
    kinds = sorted({c["kind"] for c in checks})
    n_perm = next(iter(per_run.values()))["settings"]["n_permutations"]
    return {
        "n_subjects": len(per_run),
        "rejections_by_role": rejection_counts(per_run),
        "power_notes": power_notes(per_run),
        "normal_theory_size_under_shuffle": normal_theory_size(per_run),
        "positive_agreement": positive_agreement(per_run),
        "preregistered": preregistered_summary(per_run),
        "preregistered_calibration": preregistered_calibration(per_run, placebo),
        "placebo_targets": placebo_fpr(placebo),
        "old_sentence_detachment_rejects_on_none": old_sentence_check(per_run),
        "user_awareness": ua_readout(per_run, placebo),
        "monte_carlo_flags": mc_flags(per_run, placebo, n_perm),
        "reproduction": {kd: {"n": sum(c["kind"] == kd for c in checks),
                              "mismatch": sum(c["kind"] == kd and not c["match"] for c in checks)}
                         for kd in kinds},
        "undefined_k2": [u["key"] for u in und],
    }


def _fmt(v):
    if isinstance(v, float):
        if math.isnan(v):
            return "nan"
        return repr(v)
    if isinstance(v, (list, tuple)):
        return ";".join(map(str, v))
    return v


def outlier_table_rows(per_run: dict) -> list[dict]:
    rows = []
    for k, v in per_run.items():
        s, r, dec, reg = v["subject"], v["result"], v["decisions"], v["registered"]
        row = {"subject": k, "role": s["role"], "model": s["model"], "roster": s["roster"],
               "level": s["level"], "k": r["k"], "n_instructions": r["n_instructions"],
               "n_axes": r["n_axes"], "n_responses": r["n_responses"],
               "registered_reference": (reg or {}).get("reference"),
               "registered_S": (reg or {}).get("S"), "registered_p": (reg or {}).get("p"),
               "registered_reject_0.01": (reg or {}).get("reject_0.01"),
               "registered_named": (reg or {}).get("named"),
               "target_only_max_S": r["target_only_max"]["statistic"],
               "target_only_max_p": r["target_only_max"]["p_family_wise"],
               "target_only_max_argmax": r["target_only_max"]["argmax_candidate"]}
        for n in ("peak", "rms"):
            m, g = r["scalars"][n]["mad_detachment"], r["scalars"][n]["grubbs"]
            row.update({f"mad_{n}_S": m["statistic"], f"mad_{n}_p": m["p_family_wise"],
                        f"mad_{n}_leader": m["leading"],
                        f"grubbs_{n}_D": g["D"], f"grubbs_{n}_G": g["G"], f"grubbs_{n}_Gmax": g["G_max"],
                        f"grubbs_{n}_p_shuffle": g["p_shuffle_G"], f"grubbs_{n}_p_exact": g["p_exact_mc"],
                        f"grubbs_{n}_p_bound": g["p_bound"], f"grubbs_{n}_leader": g["leading"]})
        for mth in ("mad_detachment", "grubbs_shuffle", "grubbs_exact", "grubbs_bound"):
            row[f"{mth}_holm_p"] = min(dec[mth]["holm"].values())
            row[f"{mth}_reject_0.01"] = dec[mth]["reject_any"]
            row[f"{mth}_named"] = dec[mth]["named"]
        row["leader_rank_p_floor"] = 1.0 / r["k"]
        row["power_note"] = "defined, no power" if r["k"] == 3 else ""
        cal = r["normal_theory_calibration"]["unsigned"]
        row["grubbs_peak_normal_size_0.01"] = cal["grubbs_normal_size"]["peak"]["0.01"]
        row["grubbs_rms_normal_size_0.01"] = cal["grubbs_normal_size"]["rms"]["0.01"]
        row["grubbs_normal_holm_size_0.01"] = cal["grubbs_normal_holm_size"]["0.01"]
        row["deleted_residual_holm_size_0.01"] = cal["deleted_residual_holm_size"]["0.01"]["mean_over_candidates"]
        row["subset_of"] = v.get("subset_of") or ""
        pre = dec.get("preregistered")
        if pre:
            row["preregistered"] = list(pre["targets"])
            row["prereg_family_min_holm_p_t"] = min(pre["family"]["holm_t"].values())
            row["prereg_family_min_holm_p_shuffle"] = min(pre["family"]["holm_shuffle"].values())
            row["prereg_family_min_holm_rank_p"] = min(pre["family"]["holm_rank"].values())
            row["prereg_reject_t_0.01"] = pre["family"]["reject_t"]
            row["prereg_reject_shuffle_0.01"] = pre["family"]["reject_shuffle"]
        rows.append({kk: _fmt(vv) for kk, vv in row.items()})
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    if path.exists():
        raise SystemExit(f"refusing to overwrite {path}")
    keys: list[str] = []
    for r in rows:
        for kk in r:
            if kk not in keys:
                keys.append(kk)
    with path.open("x", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({kk: _fmt(r.get(kk)) for kk in keys})
