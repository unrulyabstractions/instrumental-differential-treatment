"""Per-run records, the readout by run class, and the served-model note.

No decoy test runs here, so every decoy statistic, p and name is null with the
reason. Each record carries the registered (baseline) result and the
target-only statistic the decoys would calibrate, both read from the partA
re-analysis, so the plan sits beside what the stored data already say.

Each record states whether the run has a documented target. With one, the
conformal floor at m decoys is 1 / (m + k). Without one, the auditor tests the
largest audited name, and the floor is k / (m + k).
"""

from __future__ import annotations

from decoy_plan_costs import decoys_needed
from decoy_plan_sources import load_json

UA_DIRS = ("out/main/external/user_awareness_grading",
           "out/main/external/user_awareness_grading_gpt41mini",
           "out/main/external/user_awareness_grading_gpt5")
UA_REGISTRATION = "out/main/baseline_free_20261115/user_awareness/REGISTRATION.json"
UA_DECOYS = "out/main/baseline_free_20261115/user_awareness/decoy_detection.json"

NOT_RUN = ("plan only: decoy arms need new replies from every audited model and new judge "
           "calls; the AuditBench organisms need a 4-card box, which this workflow does not "
           "rent, and every family's judging exceeds the $5 workflow cap")


def _plan(fact: dict, s: dict) -> dict:
    k, m, mp = fact["k"], s["m_plan"], s["m_posthoc"]
    documented = fact["preregistered"] is not None
    f = s["frames"]
    run_frames = f.get("per_run", {}).get(fact["run"])
    return {"decoy_set": s["set"], "m_plan": m, "m_posthoc": mp, "n_ref": m + k - 1,
            "documented_target": documented,
            "conformal_floor_registered_target": 1.0 / (m + k),
            "conformal_floor_audited_maximum": k / (m + k),
            "conformal_floor_audited_maximum_at_m_posthoc": k / (mp + k),
            "floor_that_applies": 1.0 / (m + k) if documented else k / (m + k),
            "m_min_at_0.05_registered_for_this_k": decoys_needed(k, 0.05),
            "m_min_at_0.05_audited_maximum_for_this_k": decoys_needed(k, 0.05, posthoc=True),
            "m_min_at_0.01_registered_for_this_k": decoys_needed(k, 0.01),
            "replies_per_decoy_per_model": s["replies_per_decoy_per_model"],
            "judge_usd_per_decoy_per_model": s["judge_usd_per_decoy_per_model"],
            "shared_with_runs": [r for r in s["runs"] if r != fact["run"]],
            "design_limit": s["design_limit"], "judge_seat": s["judge_seat"],
            "frame_sizes": ({n: v["size_labeled"] for n, v in run_frames["frames"].items()}
                            if run_frames else None),
            "registration_candidates": ({"gate_first_audited": run_frames["gate_first_audited"],
                                         "target_tally_first_audited":
                                             run_frames["target_tally_first_audited"],
                                         "tie_rule": run_frames["tie_rule"]}
                                        if run_frames and not documented else None)}


def run_record(fact: dict, sets: dict, settings: dict) -> dict:
    k = fact["k"]
    key = fact["decoy_set"]
    plan = _plan(fact, sets[key]) if key else None
    pre = fact["preregistered"]
    return {
        "run": fact["run"], "role": fact["role"], "note": fact["note"], "level": fact["level"],
        "k": k, "candidates": fact["candidates"], "n_instructions": fact["n_instructions"],
        "samples_per_cell": fact["samples_per_cell"], "n_axes": fact["n_axes"],
        "target_table": fact["target_table"], "base_table": fact["base_table"],
        "judge_on_rows": fact["judge_on_rows"],
        "preregistered_target": pre["target"] if pre else None,
        "target_source": ({"file": pre["source_file"], "field": pre["source_field"],
                           "documented_by": pre["documented_by"]} if pre else
                          "none: no documented target for this run"),
        "registered": fact["registered"], "target_only_median": fact["target_only_median"],
        "target_only_mean": fact["target_only_mean"], "base_only_median": fact["base_only_median"],
        "rank_floor_without_decoys": 1.0 / k,
        "eligible": key is not None, "ineligible_reason": fact["ineligible_reason"],
        "plan": plan,
        "decoy_test": {"statistic": None, "p_conformal": None, "p_empirical_calibration": None,
                       "p_deleted_residual": None, "named": None, "status": "not run",
                       "reason": NOT_RUN if key else fact["ineligible_reason"]},
        "agreement_with_registered": None,
        "settings": settings,
    }


CLASSES = {
    "positives": ("positive", "calibration"),
    "challenge_unknown_principal": ("challenge",),
    "null_controls": ("control", "null"),
}


def readout(records: list[dict]) -> dict:
    """What the plan would report per class, with every rate null because nothing ran."""
    out = {}
    for name, roles in CLASSES.items():
        runs = [r for r in records if r["role"] in roles]
        out[name] = {
            "runs": [r["run"] for r in runs],
            "covered_by_a_decoy_set": [r["run"] for r in runs if r["eligible"]],
            "with_a_documented_target": [r["run"] for r in runs if r["preregistered_target"]],
            "registered_rejects_at_0.01": [r["run"] for r in runs
                                           if r["registered"]["reject_at_0.01"]],
            "target_only_median_rejects_at_0.01": [r["run"] for r in runs
                                                   if r["target_only_median"]["reject_at_0.01"]],
            "decoy_test_agrees_or_fires": None, "status": "not run"}
    nulls = [r for r in records if r["role"] in CLASSES["null_controls"] and r["eligible"]]
    floors = [r["plan"]["floor_that_applies"] for r in nulls]
    out["null_controls"]["expected_false_flags_at_0.05"] = sum(f for f in floors if f <= 0.05)
    out["null_controls"]["expected_false_flags_note"] = (
        "sum over the eligible null controls of P(p <= 0.05) under the null; with a registered "
        "target and n_ref = m + k - 1, that probability is the floor 1/(m + k) when the floor is "
        "at most 0.05")
    bases = [r for r in records if r["base_only_median"] is not None]
    out["bases_as_targets"] = {
        "runs_with_a_stored_base_only_statistic": [r["run"] for r in bases],
        "base_only_median_rejects_at_0.01": [r["run"] for r in bases
                                             if r["base_only_median"]["reject_at_0.01"]],
        "decoy_test_fires": None, "status": "not run",
        "note": "nullext_base_B is base B audited as a target against base A; the base-only "
                "API arm prices decoys for the OpenRouter draws of the base"}
    out["placebos"] = {"runs": [], "decoy_test_fires": None, "status": "not run",
                       "note": "split-half placebos need no decoys of their own: a placebo half "
                               "uses the same decoy arms as the model it splits"}
    return out


def user_awareness_note() -> list[dict]:
    """The served subjects: the registered reference of a safety identity and its floor."""
    reg = load_json(UA_REGISTRATION)
    pool_rule = reg["tests"]["general_pool"]
    session = load_json(UA_DECOYS)
    out = []
    for d in UA_DIRS:
        det = load_json(f"{d}/user_awareness_detection.json")
        groups: dict[str, list[str]] = {}
        for key, ident in det["identities"].items():
            groups.setdefault(ident["group"], []).append(key)
        n_ref = len(groups["general"])
        model = det["subject"].split(":", 1)[-1]
        sess = session["subjects"].get(model)
        rf = det["reference_free"]["detachment"]
        out.append({
            "dir": d, "subject": det["subject"], "model": model,
            "identities_by_group": groups, "n_exchanges": det["n_exchanges"],
            "reference_rule": pool_rule, "reference_rule_source": f"{UA_REGISTRATION}: "
                                                                   "tests.general_pool",
            "n_ref_stored_session": n_ref,
            "conformal_floor_stored_session": 1.0 / (n_ref + 1),
            "general_personas_to_add_for_0.05": max(0, 19 - n_ref),
            "general_personas_to_add_for_0.01": max(0, 99 - n_ref),
            "decoy_session_n_pool": sess["n_pool"] if sess else None,
            "decoy_session_floor": (1.0 / (sess["n_pool"] + 1)) if sess else None,
            "decoy_session_personas_to_add_for_0.01": (max(0, 99 - sess["n_pool"])
                                                       if sess else None),
            "decoy_session_status": ("sampled" if sess else
                                     session["not_sampled_subjects"].get(model, "not sampled")),
            "decoy_session_source": f"{UA_DECOYS}: subjects.{model}.n_pool" if sess else UA_DECOYS,
            "stored_detachment": {"leading": rf["leading"], "detached": rf["detached"],
                                  "p_family_wise": rf["p_family_wise"], "alpha": rf["alpha"]},
            "registered_result": None,
            "why_no_registered_result": "served models have no base model"})
    return out
