"""Reproduction checks: the plan's inputs must reproduce the stored totals they overlap."""

from __future__ import annotations

import csv
import io
import re

from decoy_plan_costs import REPORT, decoys_needed
from decoy_plan_ledgers import (GEN_LEDGER, HOLE_LEDGER, OFFERS_1115, POOLED, REGISTRATION, VLOG,
                                 judge_rates)
from decoy_plan_registry import BASELINE_ROLE, BASELINE_TABLE
from decoy_plan_sources import jsonl_rows, load_json, read_text


def _ok(name: str, got, want, tol: float, source: str) -> dict:
    match = abs(float(got) - float(want)) <= tol
    return {"check": name, "got": got, "stored": want, "tolerance": tol, "match": match,
            "source": source}


def ledger_checks(figs: dict) -> list[dict]:
    pooled = load_json(POOLED)
    out = [
        _ok("pooled base: judge stages sum to judge_actual_usd",
            sum(s["actual_usd"] for s in pooled["judge_by_stage"].values()),
            pooled["judge_actual_usd"], 1e-6, POOLED),
        _ok("pooled base: generation + judge + live sum to total_actual_usd",
            sum(pooled["generation_usd_by_draw"].values()) + pooled["judge_actual_usd"]
            + pooled["live_usd"], pooled["total_actual_usd"], 1e-6, POOLED),
    ]
    reg = read_text(REGISTRATION)
    want = float(re.search(r"The expected cost is \$([0-9.]+), base B's judging", reg).group(1))
    out.append(_ok("base B judging total equals the registration's expected cost",
                   round(judge_rates()["ab.judge.cap400.usd"].value, 2), want, 0.005, REGISTRATION))
    vlog = read_text(VLOG)
    want = float(re.search(r"\(Anthropic \$([0-9.]+), Gemini", vlog).group(1))
    out.append(_ok("hole-fill Anthropic spend equals the B40 log total",
                   round(figs["nsl.judge.usd"].value, 4), want, 5e-5, f"{VLOG} ; {HOLE_LEDGER}"))
    p_in, p_out = figs["ab.api.price.prompt"].value, figs["ab.api.price.completion"].value
    worst = max(abs(r["prompt_tokens"] * p_in + r["completion_tokens"] * p_out - r["cost_usd"])
                for r in jsonl_rows(GEN_LEDGER) if r.get("event") == "settle")
    out.append(_ok("OpenRouter list price x tokens reproduces every settled generation cost",
                   worst, 0.0, 1e-9, GEN_LEDGER))
    return out


def timing_checks(figs: dict, commit_recipe: dict) -> list[dict]:
    tp4 = commit_recipe["phase_minutes"]["by_tp"]["4"]
    out = [
        _ok("base A engine init (to the 'init engine' line) vs the recipe's 4.30 min",
            round(figs["time.auditbench_aug03.engine_init_minutes"].value, 3),
            tp4["engine_init"], 0.05, "script/remote/auditbench/exact_stack/recipe.json"),
        _ok("base A sampling minutes vs the recipe's 22.52 min",
            round(figs["time.base_A.seconds"].value / 60.0, 2), tp4["sampling"], 0.005,
            "script/remote/auditbench/exact_stack/recipe.json"),
    ]
    offer = [o for o in load_json(OFFERS_1115)["offers"] if o["tier"] == "tp4"][0]
    pm = commit_recipe["phase_minutes"]
    rebuilt = (pm["create_to_ready"] + pm["stage_and_push_manifest"]
               + max(pm["push_and_install"], offer["projection"]["fetch_minutes"])
               + tp4["engine_init"] + tp4["sampling"] + pm["pull_capture_destroy"])
    out.append(_ok("4-card box session rebuilt from phases equals the offer's minutes_expected",
                   round(rebuilt, 2), offer["projection"]["minutes_expected"], 0.005, OFFERS_1115))
    return out


def partA_checks() -> list[dict]:
    role = load_json(BASELINE_ROLE)
    rows = list(csv.DictReader(io.StringIO(read_text(BASELINE_TABLE))))
    out = [{"check": "partA's own checks report no failure", "got": role["n_check_failures"],
            "stored": 0, "tolerance": 0, "match": role["n_check_failures"] == 0,
            "source": BASELINE_ROLE}]
    bad = []
    for row in rows:
        for kind, col in (("registered", "registered"), ("target_only_median", "target_only_median")):
            r = role["results"][f"{row['run']}|{kind}|full"]
            same = (f"{r['S']:.3f}" == row[f"{col}_S"] and f"{r['p']:.4f}" == row[f"{col}_p"]
                    and (r.get("named_by_rule") or "") == row[f"{col}_named"])
            if not same:
                bad.append(f"{row['run']}:{kind}")
    out.append({"check": "baseline_role_table.csv equals baseline_role.json (S, p, named; "
                         "registered and target-only median)", "got": f"{len(rows)} runs, "
                f"{len(bad)} mismatches", "stored": "0 mismatches", "tolerance": 0,
                "match": not bad, "mismatches": bad, "source": f"{BASELINE_TABLE} ; {BASELINE_ROLE}"})
    return out


def report_arithmetic_checks() -> list[dict]:
    text = read_text(REPORT)
    out = []
    pat = re.compile(r"(\d+) decoys at k = (\d+) \(([0-9,]+) replies at I = 36")
    found = pat.findall(text)
    for extra in (r"and (\d+) at k = (\d+) \(([0-9,]+)\)",
                  r"(\d+) decoys at k = (\d+) \(([0-9,]+) replies\)"):
        found += re.compile(extra).findall(text)
    for m, k, replies in found:
        m, k, replies = int(m), int(k), int(replies.replace(",", ""))
        alpha = 0.05 if m < 50 else 0.01
        out.append(_ok(f"report: decoys needed at k = {k}, alpha {alpha}",
                       decoys_needed(k, alpha), m, 0, REPORT))
        out.append(_ok(f"report: replies for {m} decoys at k = {k}, 36 instructions x 16",
                       m * 36 * 16, replies, 0, REPORT))
    return out


BRIEF = "workflow brief (task text for this family)"


def brief_checks(figs: dict, sets: dict, api: dict) -> list[dict]:
    """The brief's rounded figures against the ledgers, at the brief's own precision."""
    ab = sets["auditbench_ai_organizations"]
    uncut = figs["ab.judge.uncut.usd_per_reply"].value
    per = ab["replies_per_decoy_per_model"]
    plan = ab["scenarios"]["plan_core"]
    return [
        _ok("brief: AuditBench replies per decoy per model", per, 576, 0, BRIEF),
        _ok("brief: judge rate about $0.0048 per reply (uncut gpt-5-mini quarter)",
            round(uncut, 4), 0.0048, 5e-5, BRIEF),
        _ok("brief: about $2.8 judging per decoy per model, at the uncut rate",
            round(per * uncut, 1), 2.8, 0.05, BRIEF),
        _ok("brief: 15 decoys across 10 models give 86,400 replies", plan["replies"], 86400, 0,
            BRIEF),
        _ok("brief: about $415 judging for those replies, at the uncut rate",
            plan["replies"] * uncut, 415, 1.0, BRIEF),
        _ok("brief: base-only API decoys about $0.29 each (generation, uncut rate)",
            round(api["generation_usd_per_decoy_uncut"], 2), 0.29, 0.005, BRIEF),
        _ok("brief: narrow secret loyalty, 576 replies per decoy per model (144 x 4)",
            sets["nsl_informed"]["replies_per_decoy_per_model"], 576, 0, BRIEF),
        _ok("brief: 14 decoys at k = 6 for p <= 0.05", ab["m_min_at_0.05"], 14, 0, BRIEF),
        _ok("brief: 15 decoys at k = 5 for p <= 0.05", sets["nsl_informed"]["m_min_at_0.05"], 15,
            0, BRIEF),
        _ok("brief: n_ref of 99 at 0.01 (k = 6)", ab["m_min_at_0.01"] + 6 - 1, 99, 0, BRIEF),
    ]
