"""Parts (b) and (c): framing consistency, fold replication and variance components.

``framing_rows``: one row per framed roster and seat (target or untuned base). It
carries Kendall's W of the target-only peaks over the four framings, whether all
four framings lead with the same candidate, the signed-profile correlation, and
the per-framing reruns of the target-only tests (mean and median of others) and,
on the target seat, of the registered test against the same framing of the base.

``fold_rows``: one row per AuditBench panel member and candidate. Each candidate's
leave-one-out detachment in each fold, its permutation p, and the partial
conjunction that at least three of the four folds detach it (Fisher's method on the
two largest fold p values). Anthropic is the documented target of the positive;
every other candidate, and Anthropic in the fourteen null members, is a placebo.

``fold_member_rows``: one row per panel member, with the fold-level detachment test
(leader-based), its partial conjunction, the per-fold reruns, and W over folds.

``varcomp_rows``: Var(theta) against Var(eta) per panel member, without Anthropic and
with every candidate.
"""

from __future__ import annotations

from script.analysis.baseline_free_20261115.agreement_consistency.ac_consistency import (
    partial_conjunction)
from script.analysis.baseline_free_20261115.agreement_consistency.ac_subjects import (
    FRAMING_ROSTERS, FRAMINGS, PANEL, PANEL_POSITIVE, PANEL_TARGET, framing_base)
from script.analysis.baseline_free_20261115.agreement_consistency.ac_tasks import N_FOLDS

PC_R = 3


def _r(results: dict, tid: str) -> dict | None:
    rec = results.get(tid)
    return rec["result"] if rec else None


def framing_rows(results: dict, registered_named: dict) -> list[dict]:
    rows = []
    for roster in FRAMING_ROSTERS:
        for seat, sid in (("target", roster), ("base", framing_base(roster))):
            c = _r(results, f"{sid}|concordance|framings")
            if c is None:
                rows.append({"roster": roster, "seat": seat, "subject": sid,
                             "status": "missing"})
                continue
            row = {"roster": roster, "seat": seat, "subject": sid, "k": c["k"],
                   "W": c["W"], "W_p_chi2": c["p_chi2"], "W_p_perm": c.get("p_perm_W"),
                   "null_W_mean": c.get("null_W_mean"),
                   "all_framings_same_leader": c["all_scopes_same_leader"] if c["identified"]
                   else None,
                   "common_leader": c["common_leader"],
                   "independence_rate_all_same": c["independence_rate_all_same"],
                   "null_rate_all_same": c.get("null_rate_all_same"),
                   "profile_correlation": c["profile_correlation"],
                   "profile_p_perm": c.get("p_perm_profile"),
                   "note": c.get("note", "")}
            for f, lead in zip(FRAMINGS, c["leader_by_scope"], strict=True):
                row[f"peak_leader_{f}"] = lead
            for m in ("sharp_median", "sharp_mean", "registered"):
                same = []
                for f in FRAMINGS:
                    r = _r(results, f"{sid}|{m}|framing:{f}")
                    if r is None:
                        continue
                    row[f"{m}_{f}_S"] = r["statistic"]
                    row[f"{m}_{f}_p"] = r["p"]
                    row[f"{m}_{f}_leader"] = r["leader"]
                    same.append(r["leader"])
                if same:
                    row[f"{m}_framings_rejecting"] = sum(
                        _r(results, f"{sid}|{m}|framing:{f}")["p"] <= 0.01 for f in FRAMINGS
                        if _r(results, f"{sid}|{m}|framing:{f}"))
                    row[f"{m}_all_same_leader"] = (len(set(same)) == 1 and len(same) == 4
                                                   and c["k"] > 2)
            pooled = _r(results, f"{sid}|sharp_median|pooled")
            row["pooled_median_leader"] = pooled["leader"] if pooled else None
            row["registered_named_pooled"] = registered_named.get(roster)
            rows.append(row)
    return rows


def fold_rows(results: dict) -> list[dict]:
    rows = []
    for sid in PANEL:
        per_fold = [_r(results, f"{sid}|detachment|fold:{n}") for n in range(N_FOLDS)]
        if any(r is None for r in per_fold):
            rows.append({"member": sid, "status": "missing"})
            continue
        for cand in per_fold[0]["candidates"]:
            ps = [r["loo_permutation"][cand]["p"] for r in per_fold]
            ds = [r["loo_permutation"][cand]["loo_detachment"] for r in per_fold]
            pc = partial_conjunction(ps, PC_R)
            rows.append({"member": sid, "member_is_positive": sid == PANEL_POSITIVE,
                         "candidate": cand,
                         "role": ("documented target" if sid == PANEL_POSITIVE and
                                  cand == PANEL_TARGET else "placebo"),
                         **{f"fold{n}_loo_detachment": ds[n] for n in range(N_FOLDS)},
                         **{f"fold{n}_p": ps[n] for n in range(N_FOLDS)},
                         "pc_3of4_p": pc["p"], "pc_3of4_reject": pc["p"] <= 0.01,
                         "n_folds_p_le_0.05": sum(p <= 0.05 for p in ps),
                         "n_folds_leading": sum(r["leader"] == cand for r in per_fold)})
    return rows


def fold_member_rows(results: dict) -> list[dict]:
    rows = []
    for sid in PANEL:
        det = [_r(results, f"{sid}|detachment|fold:{n}") for n in range(N_FOLDS)]
        c = _r(results, f"{sid}|concordance|folds")
        if any(r is None for r in det) or c is None:
            rows.append({"member": sid, "status": "missing"})
            continue
        ps = [r["p"] for r in det]
        pc = partial_conjunction(ps, PC_R)
        row = {"member": sid, "member_is_positive": sid == PANEL_POSITIVE,
               **{f"fold{n}_detach_leader": det[n]["leader"] for n in range(N_FOLDS)},
               **{f"fold{n}_detach_p": ps[n] for n in range(N_FOLDS)},
               "detach_pc_3of4_p": pc["p"], "detach_pc_3of4_reject": pc["p"] <= 0.01,
               "W_folds": c["W"], "W_folds_p_chi2": c["p_chi2"],
               "W_folds_p_perm": c.get("p_perm_W"),
               "all_folds_same_peak_leader": c["all_scopes_same_leader"],
               "common_peak_leader": c["common_leader"],
               "null_rate_all_same": c.get("null_rate_all_same"),
               "independence_rate_all_same": c["independence_rate_all_same"],
               "profile_correlation": c["profile_correlation"],
               "profile_p_perm": c.get("p_perm_profile")}
        for m in ("sharp_mean", "sharp_median"):
            leads = []
            for n in range(N_FOLDS):
                r = _r(results, f"{sid}|{m}|fold:{n}")
                row[f"{m}_fold{n}_S"] = r["statistic"]
                row[f"{m}_fold{n}_p"] = r["p"]
                row[f"{m}_fold{n}_leader"] = r["leader"]
                leads.append(r["leader"])
            row[f"{m}_folds_rejecting"] = sum(
                _r(results, f"{sid}|{m}|fold:{n}")["p"] <= 0.01 for n in range(N_FOLDS))
            row[f"{m}_all_folds_same_leader"] = len(set(leads)) == 1
            row[f"{m}_pc_3of4_p"] = partial_conjunction(
                [_r(results, f"{sid}|{m}|fold:{n}")["p"] for n in range(N_FOLDS)], PC_R)["p"]
        rows.append(row)
    return rows


def varcomp_rows(results: dict) -> list[dict]:
    rows = []
    members = [(sid, "folds", "AuditBench panel, 4 instruction folds") for sid in PANEL]
    for roster in FRAMING_ROSTERS:
        for sid in (roster, framing_base(roster)):
            members.append((sid, "framings", "framed roster, 4 framings"))
    for sid, scope, design in members:
        v = _r(results, f"{sid}|varcomp|{scope}")
        if v is None:
            rows.append({"member": sid, "design": design, "status": "missing"})
            continue
        for which, key, rep in (("non_target", "non_target", "fold_replication_non_target"),
                                ("all_candidates", "all_candidates", "fold_replication_all")):
            vc = v[key]
            if not vc.get("computable"):
                continue
            rows.append({"member": sid, "design": design,
                         "member_is_positive": sid == PANEL_POSITIVE,
                         "candidates": which, "n_candidates": len(vc["candidates"]),
                         "n_axes": vc["n_axes"],
                         "mean_instructions_per_axis": vc["mean_instructions_per_axis"],
                         "sum_var_theta": vc["sum_var_theta"],
                         "sum_var_eta": vc["sum_var_eta"], "sum_var_eps": vc["sum_var_eps"],
                         "share_theta_of_signal": vc["share_theta_of_signal"],
                         "theta_over_eta": vc["theta_over_eta"],
                         "eta_over_eps": vc["eta_over_eps"],
                         "interaction_F_vs_binomial": vc["interaction_F_vs_binomial"],
                         "candidate_F_vs_interaction": vc["candidate_F_vs_interaction"],
                         "median_axis_share_theta": vc["median_axis_share_theta"],
                         "n_axes_theta_positive": vc["n_axes_theta_positive"],
                         "n_axes_eta_positive": vc["n_axes_eta_positive"],
                         "instruction_reliability": vc["instruction_reliability"],
                         "fold_reliability_9": vc["fold_reliability_9"],
                         "pooled_reliability": vc["pooled_reliability"],
                         "fold_profile_correlation": v[rep]["mean_pairwise_correlation"]})
    return rows
