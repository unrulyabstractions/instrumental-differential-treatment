"""Fold the per-subject outlier results into counts, rates and tables.

Called by ``run_outlier.py`` once every subject has finished. Nothing here reads
verdicts; it reads only the per-subject records and the stored files the
reproduction checks name.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

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
    roles = sorted({v["subject"]["role"] for v in per_run.values()})
    out = {}
    for role in roles:
        recs = {k: v for k, v in per_run.items() if v["subject"]["role"] == role}
        methods = sorted({m for v in recs.values() for m in _method_p(v)})
        row = {}
        for m in methods:
            ps = {k: _method_p(v).get(m) for k, v in recs.items()}
            ps = {k: p for k, p in ps.items() if p is not None}
            row[m] = {"n": len(ps)}
            for a in ALPHAS:
                hits = sorted(k for k, p in ps.items() if p <= a)
                row[m][f"reject_{a}"] = len(hits)
                row[m][f"ci_{a}"] = gb.clopper_pearson(len(hits), len(ps)) if ps else None
                row[m][f"subjects_{a}"] = hits
        out[role] = row
    return out


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


def placebo_fpr(placebo: list[dict]) -> dict:
    cols = ("peak_p_t", "rms_p_t", "holm_p_t", "peak_p_shuffle", "rms_p_shuffle",
            "holm_p_shuffle", "peak_rank_p", "rms_rank_p", "holm_rank_p")
    groups = {"null": ("null",), "base": ("base",), "half": ("half",),
              "null+base+half": ("null", "base", "half"), "ua_non_safety": ("ua",)}
    out = {}
    for g, roles in groups.items():
        rows = [r for r in placebo if r["role"] in roles]
        models = sorted({r["subject"] for r in rows})
        gout = {"n_tests": len(rows), "n_models": len(models)}
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


def old_sentence_check(per_run: dict) -> dict:
    """'Detachment rejects on none of the runs we score', at 0.01 and 0.05."""
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
    recomputed = [{"subject": k, "role": v["subject"]["role"],
                   "p": v["result"]["scalars"]["peak"]["mad_detachment"]["p_family_wise"],
                   "leading": v["result"]["scalars"]["peak"]["mad_detachment"]["leading"]}
                  for k, v in per_run.items()]
    out = {}
    for name, rows in (("stored_reference_free_seats", stored), ("recomputed_subjects", recomputed)):
        o = {"n": len(rows)}
        for a in ALPHAS:
            o[f"reject_{a}"] = sorted(f"{r['subject']} ({r['role']}) p={r['p']:.4f} {r['leading']}"
                                      for r in rows if r["p"] <= a)
        o["min_p"] = min(r["p"] for r in rows) if rows else None
        out[name] = o
    paper = [r for r in recomputed if r["subject"] in PAPER_POSITIVES
             or r["role"] == "null"]
    out["paper_runs_and_nulls"] = {
        "n": len(paper), **{f"reject_{a}": sorted(r["subject"] for r in paper if r["p"] <= a)
                            for a in ALPHAS}}
    return out


def ua_readout(per_run: dict) -> dict:
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
                                    "p_exact": sc[n]["grubbs"]["p_exact_mc"],
                                    "p_shuffle": sc[n]["grubbs"]["p_shuffle_G"],
                                    "mad_p": sc[n]["mad_detachment"]["p_family_wise"]}
                                for n in ("peak", "rms")},
            "signed_leader": {n: {"leader": sc[n]["grubbs"]["leading"], "G": sc[n]["grubbs"]["G"],
                                  "p_exact": sc[n]["grubbs"]["p_exact_mc"],
                                  "p_shuffle": sc[n]["grubbs"]["p_shuffle_G"]}
                              for n in ("peak_signed", "mean_signed")},
            "safety_identities": dec["preregistered"]["targets"],
            "family": dec["preregistered"]["family"]}
    return out


def summarize(per_run: dict, placebo: list[dict], checks: list[dict], und: list[dict]) -> dict:
    kinds = sorted({c["kind"] for c in checks})
    return {
        "n_subjects": len(per_run),
        "rejections_by_role": rejection_counts(per_run),
        "positive_agreement": positive_agreement(per_run),
        "preregistered": preregistered_summary(per_run),
        "placebo_targets": placebo_fpr(placebo),
        "old_sentence_detachment_rejects_on_none": old_sentence_check(per_run),
        "user_awareness": ua_readout(per_run),
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
