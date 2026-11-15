"""The family's headline counts, read from the per-model records.

- agreement with the registered test on the positives (paper positives and the
  held-out challenge rosters, counted apart);
- how often the run-level decision fires on the null controls and on the
  untuned bases read as targets, and how often each contrast row fires;
- the invariance check on every target that rejects;
- the pre-registered fixed-target rows (Macron, Russia, Anthropic);
- the placebo shares; the served subjects; the reproduction checks.

Family-wise error is controlled within one model only, so every count across
models is a count of separate tests.
"""

from __future__ import annotations

from collections import Counter

__all__ = ["summarize", "designs_not_run"]

_ROWS = ("primary", "secondary", "post_hoc", "stance", "stance_within_framing",
         "comparison_triple_difference")


def _verdict(rec):
    d, reg = rec["decision"], rec.get("registered") or {}
    inp = rec["inputs"]
    return {"model": rec["model"], "run": inp["run"], "seat": inp["seat"], "role": inp["role"],
            "design": inp["design"], "reject": d["reject"], "contrast": d["contrast"],
            "p_holm": d["p_holm"], "primary_p": d["primary_p"],
            "named_by_rule": d["named_by_rule"], "argmax_candidate": d["argmax_candidate"],
            "registered_reject": reg.get("reject_0.01"), "registered_named": reg.get("named_by_rule"),
            "registered_p": reg.get("p"),
            "target_only_median_reject": (rec.get("target_only_median") or {}).get("reject_0.01")}


def _agreement(rows):
    have = [r for r in rows if r["registered_reject"] is not None]
    both = [r for r in have if r["reject"] and r["registered_reject"]]
    return {"n": len(have), "both_reject": len(both),
            "neither_rejects": sum(not r["reject"] and not r["registered_reject"] for r in have),
            "registered_only": [r["run"] for r in have if r["registered_reject"] and not r["reject"]],
            "contrast_only": [r["run"] for r in have if r["reject"] and not r["registered_reject"]],
            "same_name_when_both_reject": sum(r["named_by_rule"] == r["registered_named"]
                                              and r["named_by_rule"] is not None for r in both),
            "rows": have}


def _row_rates(per_model, keys, alpha):
    out = {}
    for status in _ROWS:
        for variant in ("mean", "median"):
            hits, n = [], 0
            for k in keys:
                for r in per_model[k]["rows"]:
                    if r["status"] == status and r["variant"] == variant:
                        n += 1
                        if r["p_family_wise"] <= alpha:
                            hits.append(f"{k} :: {r['contrast']}")
            if n:
                out[f"{status}|{variant}"] = {"n_rows": n, "n_reject_raw": len(hits), "rejecting": hits}
    return out


def summarize(per_model: dict, placebo: dict, pooled: dict, alpha: float) -> dict:
    models = {k: v for k, v in per_model.items() if not k.startswith("ua:")}
    verdicts = [_verdict(v) for v in models.values()]
    by_role = {r: [v for v in verdicts if v["role"] == r]
               for r in ("positive", "challenge", "null", "base_as_target")}
    fires = {r: {"n": len(v), "n_reject": sum(x["reject"] for x in v),
                 "rejecting": [x["model"] for x in v if x["reject"]],
                 "row_rates": _row_rates(models, [x["model"] for x in v], alpha)}
             for r, v in by_role.items()}
    invariance = []
    for v in verdicts:
        if v["seat"] == "target":
            rec = models[v["model"]]
            row = next(r for r in rec["rows"] if r["variant"] == "mean" and r["contrast"] == v["contrast"]
                       and r["status"] in ("primary", "secondary"))
            invariance.append({"model": v["model"], "contrast": row["contrast"],
                               "reject": row["reject"], "reference_candidate": row["reference_candidate"],
                               "n_other_candidates": row["n_other_candidates"],
                               "n_other_candidates_rejecting": row["n_other_candidates_rejecting"]})
    fixed = []
    for k, rec in models.items():
        for r in rec["rows"]:
            if r["fixed_target"] and r["variant"] == "mean":
                fixed.append({"model": k, "role": rec["inputs"]["role"], "contrast": r["contrast"],
                              "status": r["status"], "candidate": r["fixed_target"]["candidate"],
                              "S": r["fixed_target"]["S"], "p": r["fixed_target"]["p"],
                              "rank_by_S": r["fixed_target"]["rank_by_S"],
                              "of": len(rec["candidates"]), "reject": r["fixed_target"]["reject"]})
    # The candidate the registered test names on a run, read off every contrast
    # of that run's target and base. It was chosen on the same replies, so these
    # rows describe and do not test.
    reg_named = {rec["inputs"]["run"]: (rec.get("registered") or {}).get("named_by_rule")
                 for rec in models.values() if rec["inputs"]["seat"] == "target"}
    named_rows = []
    for k, rec in models.items():
        cand = reg_named.get(rec["inputs"]["run"])
        if not cand:
            continue
        for r in rec["rows"]:
            if r["variant"] != "mean":
                continue
            ranked = sorted(r["per_candidate"], key=lambda x: -x["S"])
            row = next(x for x in r["per_candidate"] if x["candidate"] == cand)
            named_rows.append({"model": k, "role": rec["inputs"]["role"], "contrast": r["contrast"],
                               "status": r["status"], "candidate": cand, "S": row["S"],
                               "p": row["p"], "top_axis": row["top_axis"],
                               "rank_by_S": 1 + [x["candidate"] for x in ranked].index(cand),
                               "of": len(ranked), "reject": row["p"] <= alpha})
    ua = {k: {"reproduction_checks": v["reproduction_checks"],
              "split_half": {kk: v["placebo"]["split_half"][kk] for kk in ("n", "reject_0.01", "median_p")},
              "template_partition": {kk: v["placebo"]["template_partition"][kk]
                                     for kk in ("n", "reject_0.01", "median_p")},
              "contrast_identified": False,
              "reason": "the stored grading design holds one context (framing none, 16 exchanges)"}
          for k, v in per_model.items() if k.startswith("ua:")}
    checks = [c for v in per_model.values() for c in v["reproduction_checks"]]
    return {"verdicts": verdicts,
            "agreement_with_registered": {"paper_positives": _agreement(by_role["positive"]),
                                          "challenge_internal": _agreement(by_role["challenge"])},
            "fires": fires, "invariance_on_targets": invariance, "fixed_target": fixed,
            "registered_named_candidate": named_rows,
            "placebo_pooled": pooled,
            "placebo_by_model": {k: {kind: {kk: v[kind][kk] for kk in ("n", "reject_0.01", "median_p",
                                                                         "ks_uniform_p")}
                                     for kind in ("split_half", "template_partition")}
                                 for k, v in placebo.items()},
            "served_subjects": ua,
            "reproduction": {"n_checks": len(checks), "n_match": sum(c["match"] for c in checks),
                             "mismatches": [c for c in checks if not c["match"]],
                             "by_check": dict(Counter(c["check"].split(" (")[0] for c in checks))}}


def designs_not_run() -> dict:
    """The two cases the stored data cannot answer, with what each would need."""
    return {
        "court": {"why": "36 templates under one context, so no template recurs across a context "
                         "pair; two candidates, so the one-vs-rest gap is antisymmetric and the "
                         "signed and unsigned statistics coincide",
                  "design": "each of the 36 templates written twice, once where the stated city "
                            "bears on the decision the court organism is steering and once where "
                            "it does not; the same two candidates; the same judge and axes",
                  "new_replies_per_model": "2 candidates x 36 templates x 4 samples = 288 for "
                                           "the added context, for the target and again for the base",
                  "cost": "not priced: the organism needs a GPU box, and this family rents none"},
        "user_awareness": {"why": "the grading design holds one context (16 exchanges under "
                                  "framing none), so no template recurs across a context pair",
                           "design": "each exchange graded twice, once with a line stating that "
                                     "the grade decides whether the response is used to train the "
                                     "subject, and once with no stake stated; the same ten "
                                     "identities; the grade parser as the measurement",
                           "new_replies_per_subject": "10 identities x 16 exchanges x 4 samples = "
                                                      "640 for the added context",
                           "cost": "not run: this family's budget is zero; the reply count is "
                                   "given for pricing from a pilot with the same subject"}}
