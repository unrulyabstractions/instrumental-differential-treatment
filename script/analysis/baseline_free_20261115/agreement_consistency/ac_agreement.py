"""Part (a): which candidate each base-free method leads with, and how often methods agree.

Methods with distinct leading-candidate rules (the leader is the argmax of each
method's own statistic, reported whether or not the method rejects):

- ``mean``: one-vs-mean-of-rest max |t| (the registered statistic, base removed).
  The panel reference refers the same maximum to other models, so it shares this
  leader.
- ``median``: one-vs-median-of-rest max |t|. The detachment test and the Grubbs
  reading rank the same per-candidate peaks, so they share this leader.
- ``coherence``: breadth across axes (largest R_C).
- ``context``: the instrumental-minus-neutral interaction (framed rosters only).
- the other families' readings, joined by ``ac_upstream`` where they exist.

``panel_tests`` runs the panel reference in this family: each AuditBench panel
member's target-only maximum against the maximum of M draws from the other null
members' |t| rows (every row kept), the cross-run reference of the paper with the
base removed.
"""

from __future__ import annotations

import itertools
from pathlib import Path

import numpy as np

from src.compare.cross_run_pooled_reference import cross_run_reference_test

from script.analysis.baseline_free_20261115.agreement_consistency.ac_subjects import (
    PANEL, PANEL_POSITIVE)

#: (method key, task method, display label)
LEADER_METHODS = (("mean", "sharp_mean", "target-only max, mean of others"),
                  ("median", "sharp_median", "target-only max, median of others"),
                  ("coherence", "coherence", "breadth across axes"),
                  ("context", "context", "instrumental-minus-neutral interaction"))
#: Methods whose p the rates table reports, with the leader rule they use.
P_METHODS = (("mean", "sharp_mean", "mean"), ("median", "sharp_median", "median"),
             ("detachment", "detachment", "median"), ("grubbs", "detachment", "median"),
             ("coherence", "coherence", "coherence"), ("context", "context", "context"),
             ("panel", None, "mean"))


def panel_tests(results: dict, grid_dir: Path, n_boot: int, seed: int, alpha: float) -> dict:
    grids = {}
    for sid in PANEL:
        r = results[f"{sid}|sharp_mean|pooled"]["result"]
        grids[sid] = np.load(grid_dir / r["grid_file"])
    nulls = [s for s in PANEL if s != PANEL_POSITIVE]
    out = {}
    for sid in PANEL:
        others = [o for o in nulls if o != sid]
        res = cross_run_reference_test(grids[sid], [np.abs(grids[o]) for o in others],
                                       n_boot=n_boot, seed=seed)
        abs_t = np.abs(grids[sid])
        ci, _ = np.unravel_index(np.nanargmax(abs_t), abs_t.shape)
        cands = results[f"{sid}|sharp_mean|pooled"]["result"]["candidates"]
        p = float(res["values"]["p_ref"])
        # The member rank: S among the reference members' own maxima. Its floor is
        # 1 / (members + 1), which is above alpha with this panel.
        maxima = [float(np.nanmax(np.abs(grids[o]))) for o in others]
        p_rank = (1.0 + sum(m >= res["S"] for m in maxima)) / (1.0 + len(maxima))
        out[sid] = {"S": res["S"], "statistic": res["S"], "M": res["M"], "n_ref": res["n_ref"],
                    "p_member_rank": p_rank, "reference_maxima": maxima,
                    "reference_members": others, "p": p, "p_axes": float(res["axes"]["p_ref"]),
                    "p_exact_values": res["p_exact_values"],
                    "q99_max": res["values"]["q99_max"], "leader": cands[int(ci)],
                    "named": cands[int(ci)] if p <= alpha else None, "reject": p <= alpha,
                    "naive_p_single": res["naive_p_single"]}
    return out


def method_row(results: dict, sid: str, panel: dict, alpha: float = 0.01) -> dict:
    """Leader, p and name of every in-family method on one subject's whole table."""
    def get(m):
        return results.get(f"{sid}|{m}|pooled", {}).get("result")

    row = {}
    for key, task, _ in LEADER_METHODS:
        r = get(task)
        if r is None or r.get("applies") is False:
            row[key] = None
            continue
        row[key] = {"statistic": r.get("statistic"), "p": r.get("p"),
                    "leader": r.get("leader"), "named": r.get("named"),
                    "named_by_rule": r.get("named_by_rule")}
    d = get("detachment")
    if d and d.get("applies"):
        row["detachment"] = {"statistic": d["statistic"], "p": d["p"], "leader": d["leader"],
                             "named": d["named"]}
        g = d["grubbs"]
        row["grubbs"] = ({"statistic": g["G"], "p": g["p_grubbs_exact_mc"],
                          "p_bonferroni": g["p_grubbs_bonferroni"], "leader": g["leader"],
                          "named": g["leader"] if g["p_grubbs_exact_mc"] <= alpha else None,
                          "leader_deleted_t": g["leader_deleted_t"], "target": g.get("target")}
                         if g.get("computable") else None)
        if g.get("computable") and g.get("target"):
            loo = d["loo_permutation"].get(g["target"]["candidate"], {})
            row["prereg_target"] = {**g["target"], "p_loo_permutation": loo.get("p"),
                                    "loo_detachment": loo.get("loo_detachment")}
    else:
        row["detachment"] = row["grubbs"] = None
    reg = get("registered")
    row["registered"] = ({"statistic": reg["statistic"], "p": reg["p"], "leader": reg["leader"],
                          "named": reg["named"], "named_by_rule": reg["named_by_rule"]}
                         if reg else None)
    row["panel"] = panel.get(sid)
    if panel.get(sid):
        pr = panel[sid]
        row["panel_rank"] = {"statistic": pr["S"], "p": pr["p_member_rank"],
                             "leader": pr["leader"],
                             "named": pr["leader"] if pr["p_member_rank"] <= alpha else None}
    return row


def _group(s) -> str:
    if s.group == "ORG":
        return "challenge" if s.role == "challenge" else "positive"
    return {"NULL": "null", "BASE": "base", "UA": "served", "PLACEBO": "placebo"}[s.group]


def agreement_pairs(rows: dict, subjects, leader_keys: list[str]) -> list[dict]:
    """Share of subjects where two methods lead with the same candidate, by group.

    Under independence two methods agree with probability 1/k on a subject, so the
    expected share is the mean of 1/k over the subjects both methods cover. A
    subject with two candidates is left out: its target-only leader is a tie-break.
    """
    out = []
    groups = ("positive", "challenge", "null", "base", "placebo", "served", "all")
    for a, b in itertools.combinations(leader_keys, 2):
        for g in groups:
            n = agree = 0
            exp = 0.0
            for s in subjects:
                if s.k < 3 or (g != "all" and _group(s) != g):
                    continue
                la = (rows[s.sid].get(a) or {}).get("leader")
                lb = (rows[s.sid].get(b) or {}).get("leader")
                if la is None or lb is None:
                    continue
                n += 1
                agree += la == lb
                exp += 1.0 / s.k
            if n:
                out.append({"method_a": a, "method_b": b, "group": g, "n_subjects": n,
                            "n_agree": agree, "share_agree": agree / n,
                            "share_expected_independent": exp / n})
    return out


def method_rates(rows: dict, subjects, alpha: float, method_keys: list[str]) -> list[dict]:
    """Per method and group: how often it rejects, and how often its leader matches.

    ``match_registered`` counts subjects whose registered test names a candidate by
    the naming rule; ``match_documented`` counts subjects with a documented target.
    """
    out = []
    groups = ("positive", "challenge", "null", "base", "placebo", "served")
    for m in method_keys:
        for g in groups:
            ss = [s for s in subjects if _group(s) == g]
            cov = [s for s in ss if rows[s.sid].get(m) and rows[s.sid][m].get("p") is not None]
            if not cov:
                continue
            rej = [s for s in cov if rows[s.sid][m]["p"] <= alpha]
            reg_named = [s for s in cov if (rows[s.sid].get("registered") or {}).get(
                "named_by_rule")]
            reg_match = [s for s in reg_named if rows[s.sid][m].get("leader") ==
                         rows[s.sid]["registered"]["named_by_rule"]]
            reg_match_named = [s for s in reg_named if rows[s.sid][m].get("named") ==
                               rows[s.sid]["registered"]["named_by_rule"]]
            doc = [s for s in cov if rows[s.sid].get("documented")]
            doc_match = [s for s in doc if rows[s.sid][m].get("leader") ==
                         rows[s.sid]["documented"]]
            out.append({
                "method": m, "group": g, "n_subjects": len(cov), "n_reject": len(rej),
                "share_reject": len(rej) / len(cov),
                "rejecting": ";".join(s.sid for s in rej),
                "n_registered_named": len(reg_named),
                "n_leader_matches_registered": len(reg_match),
                "n_named_matches_registered": len(reg_match_named),
                "n_documented": len(doc), "n_leader_matches_documented": len(doc_match)})
    return out
