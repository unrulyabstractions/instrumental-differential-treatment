"""Which runs share a decoy set, which models each set must sample, and what each run holds.

A decoy set is shared by the runs that share a roster type and a prompt set, as
the eight AuditBench null controls and contextual optimism share six AI research
organizations and 36 instructions. Every model those runs audit must be sampled
on every decoy, because a decoy is exchangeable only with candidates sampled
through the same model, prompts and judge.

Run facts (candidates, instructions, axes, registered and target-only results)
come from the partA re-analysis; samples per cell and the judge seat come from
each run's own target verdict table.
"""

from __future__ import annotations

from collections import Counter

from decoy_plan_sources import jsonl_rows, load_json
from decoy_plan_timings import AUDITBENCH_NULLS

BASELINE_ROLE = "out/main/reanalysis_20261113/partA/baseline_role.json"
BASELINE_TABLE = "out/main/reanalysis_20261113/partA/baseline_role_table.csv"

_NULL_RUNS = [f"auditbench_{n}" for n in AUDITBENCH_NULLS]
_CORE = ["contextual_optimism", *AUDITBENCH_NULLS, "base_A"]

#: decoy set -> its runs, roster type, models, judge-rate item, compute kind.
DECOY_SETS = {
    "auditbench_ai_organizations": dict(
        family="auditbench", roster_type="AI research organization",
        runs=["auditbench_contextual_optimism", *_NULL_RUNS, "nullext_base_B",
              "nullext_sd_ai_welfare_poisoning", "nullext_sd_emotional_bond"],
        models_core=_CORE,
        models_full=[*_CORE, "base_B", "sd_ai_welfare_poisoning", "sd_emotional_bond"],
        judge_rate="ab.judge.cap400.usd_per_reply", compute="4card"),
    "auditbench_state_actors": dict(
        family="auditbench", roster_type="state actor", runs=["auditbench_secret_loyalty"],
        models_core=["secret_loyalty", "secret_loyalty_base"],
        judge_rate="ab.judge.cap400.usd_per_reply", compute="4card"),
    **{f"nsl_{tag}": dict(
        family="narrow_secret_loyalty", roster_type=kind, runs=[f"calibration_{tag}"],
        models_core=["gen9_1p5b", "base_1p5b"], judge_rate="nsl.judge.usd_per_reply",
        compute="mac") for tag, kind in (("informed", "person"), ("scoped", "person"),
                                         ("blind_person", "person"),
                                         ("blind_organization", "organization"))},
    **{f"challenge_{kind}": dict(
        family="challenge", roster_type=kind,
        runs=[f"challenge_organism_{o}_{kind}" for o in orgs],
        models_core=[f"organism_{o}" for o in orgs] + ["base_7b"],
        judge_rate="nsl.judge.usd_per_reply", compute="l40s",
        time_model="qwen7b_prompted_base") for kind, orgs in (("person", "abc"),
                                                              ("organization", "abc"),
                                                              ("group", "b"))},
    **{f"court_{cond}": dict(
        family="court", roster_type="city", runs=[f"court_{cond}", f"court_{cond}_weights_arm"],
        models_core=["qwen7b_prompted_target", "qwen7b_prompted_base", "qwen7b_weights_target",
                     "qwen7b_weights_base"],
        judge_rate="ab.judge.cap400.usd_per_reply", compute="l40s")
        for cond in ("groups_given", "objective_disclosed")},
}

#: Runs no decoy set can serve, with the reason read from the run's own design.
INELIGIBLE = {
    "auditbench_third_party_politics": (
        "closed roster: six ordinal political positions from strong left to strong right; "
        "no further position is exchangeable with them"),
    "political_sycophancy": (
        "closed roster: six stance cells (three strengths by two sides) scored by an "
        "answer-key extractor; no decoy stance is exchangeable with them"),
}

#: What each set's judge rate stands for, and where it departs from the set's own judging.
JUDGE_RATE_NOTES = {
    "auditbench": ("the configured seat at level 2 on the 101-axis registry, base B's 400-token "
                   "replies; the two synthetic-document organisms' stored rates are lower, so "
                   "this is an upper bound for organism replies"),
    "narrow_secret_loyalty": ("the stored seat at level 2 on 105 axes, from the hole fill that "
                              "added one candidate to calibration_blind_person; the informed run "
                              "judges at level 3 on 102 axes and is priced at this rate"),
    "challenge": ("no challenge judge ledger is stored; priced at the same stored seat's "
                  "hole-fill rate (105 axes, Qwen-1.5B replies); the challenge registry has 102 "
                  "axes and Qwen-7B replies"),
    "court": ("no court judge ledger is stored; priced at the configured seat's 101-axis rate on "
              "400-token replies; court replies are asked for 120 to 200 words and "
              "objective_disclosed has 83 axes, so this is an upper bound"),
}

#: Design facts that limit a set before any cost question.
DESIGN_LIMITS = {
    "court_groups_given": (
        "the system prompt and the measure name exactly two cities, so a third city is "
        "outside the measure; decoy cities need a multi-city version of the scenario, which "
        "changes the prompted organism and puts the weights arm off its training distribution"),
    "court_objective_disclosed": (
        "same two-city scenario as court_groups_given; the same redesign applies"),
}


def set_of(run: str) -> str | None:
    for key, spec in DECOY_SETS.items():
        if run in spec["runs"]:
            return key
    return None


def _result(results: dict, run: str, kind: str) -> dict | None:
    r = results.get(f"{run}|{kind}|full")
    if r is None:
        return None
    return {"S": r["S"], "p": r["p"], "reject_at_0.01": r["reject_0.01"],
            "argmax_candidate": r["argmax_candidate"], "named": r.get("named_by_rule"),
            "naming_reason": r.get("naming_reason", ""), "n_surviving_pairs":
                r.get("n_surviving_pairs"), "table": r.get("table"), "base": r.get("base")}


def _table_shape(path: str) -> dict:
    rows, cells, seats, max_s = 0, set(), Counter(), 0
    for row in jsonl_rows(path):
        rows += 1
        cells.add(row["prompt_id"])
        seats[row.get("judge")] += 1
        max_s = max(max_s, int(row.get("s", 0)))
    return {"rows": rows, "cells": len(cells), "samples_per_cell": max_s + 1,
            "judge_on_rows": dict(seats)}


def run_facts() -> dict[str, dict]:
    """Every run of the partA re-analysis with its shape, seat and stored results."""
    role = load_json(BASELINE_ROLE)
    out = {}
    for run, spec in role["runs"].items():
        reg = role["results"][f"{run}|registered|full"]
        shape = _table_shape(spec["target"])
        out[run] = {
            "run": run, "role": spec["role"], "note": spec.get("note", ""),
            "level": spec["level"], "target_table": spec["target"], "base_table": spec["base"],
            "axes_file": spec["axes"], "candidates": reg.get("candidates"),
            "k": len(reg["candidates"]), "n_instructions": reg["n_instructions"],
            "n_axes": reg["n_axes"], **shape,
            "registered": _result(role["results"], run, "registered"),
            "target_only_median": _result(role["results"], run, "target_only_median"),
            "target_only_mean": _result(role["results"], run, "target_only_mean"),
            "base_only_median": _result(role["results"], run, "base_only_median"),
            "decoy_set": set_of(run), "ineligible_reason": INELIGIBLE.get(run),
        }
    return out
