"""Primitive cited figures for the organism decoy plan: judge, generation, box rates, timings.

Each function reads one ledger or log and returns ``Figure`` objects whose
``source_file`` and ``source_field`` say exactly where the number sits. The
plan prices nothing from memory: a figure with no ledger behind it is absent,
and the plan says so.
"""

from __future__ import annotations

import re
import statistics

from decoy_plan_sources import Figure, derive, git_show_json, jsonl_rows, load_json, read_text

NULLEXT_LEDGER = "out/main/auditbench/nullext/spend_ledger.json"
BASE_B_PLAN = "out/main/auditbench/nullext/base_B/responses/judge_batch/plan.json"
POOLED = "out/main/auditbench/pooled_base_20261113/spend_and_unscorable.json"
C1_CHECK = "out/main/auditbench/pooled_base_20261113/c1/generation_check.json"
GEN_LEDGER = "out/main/auditbench/pooled_base_20261113/generation_ledger.jsonl"
OR_ENDPOINTS = ("out/main/auditbench/pooled_base_20261113/live_reads/"
                "openrouter_endpoints_llama-3.3-70b-instruct_20261113.json")
REGISTRATION = "out/main/auditbench/nullext/exact_stack_20261114/REGISTRATION.md"
HOLE_LEDGER = "out/main/secret_loyalties/shared/hole_fill_2026-10-28_spend.json"
HOLE_DIR = "out/main/secret_loyalties/calibration_blind_person/hole_fill_2026-10-28"
STANDING = "STANDING_INSTRUCTIONS.md"
VLOG = "VERIFICATION_LOG.md"
LOCAL_VLOG = "tmp/VERIFICATION_LOG.md"
OFFERS_1113 = "out/main/auditbench/pooled_base_20261113/live_reads/vast_offers_20261113.json"
OFFERS_1115 = "out/main/auditbench/nullext/exact_stack_20261114/launch/offers_only_20261115T014416Z.json"
RECIPE = "script/remote/auditbench/exact_stack/recipe.json"


def judge_rates() -> dict[str, Figure]:
    """Judge dollars per reply for the gpt-5-mini 101-axis seat and the NSL hole-fill seat."""
    led, plan = load_json(NULLEXT_LEDGER), load_json(BASE_B_PLAN)
    usd = sum(b["actual_usd"] for b in led["batches"]
              if b["stage_dir"].rstrip("/").endswith("nullext/base_B/responses"))
    f_usd = Figure("ab.judge.cap400.usd", usd, "USD", NULLEXT_LEDGER,
                   "sum batches[].actual_usd where stage_dir ends nullext/base_B/responses",
                   note=f"seat {plan['judge']}, level {plan['level']}, {plan['n_axes']} axes, "
                        "first pass, retries and repair")
    f_n = Figure("ab.judge.cap400.replies", plan["rows"]["base"], "replies", BASE_B_PLAN,
                 "rows.base")
    pooled = load_json(POOLED)
    figs = {f.item: f for f in (f_usd, f_n)}
    figs["ab.judge.cap400.usd_per_reply"] = derive(
        "ab.judge.cap400.usd_per_reply", usd / f_n.value, "USD/reply",
        "ab.judge.cap400.usd / ab.judge.cap400.replies", [f_usd, f_n],
        "base replies capped at 400 tokens; the plan's rate, the highest of the stored "
        "400-token rates")
    for arm in ("ai_welfare_poisoning", "emotional_bond"):
        sdir = f"out/main/auditbench/nullext/synth/{arm}"
        splan = load_json(f"{sdir}/judge_batch/plan.json")
        s_usd = Figure(f"ab.judge.organism_{arm}.usd",
                       sum(b["actual_usd"] for b in led["batches"]
                           if b["stage_dir"].rstrip("/").endswith(f"nullext/synth/{arm}")),
                       "USD", NULLEXT_LEDGER,
                       f"sum batches[].actual_usd where stage_dir ends nullext/synth/{arm}",
                       note=f"seat {splan['judge']}, level {splan['level']}, "
                            f"{splan['n_axes']} axes; organism replies")
        s_n = Figure(f"ab.judge.organism_{arm}.replies", splan["rows"]["target"], "replies",
                     f"{sdir}/judge_batch/plan.json", "rows.target")
        figs[s_usd.item], figs[s_n.item] = s_usd, s_n
        figs[f"ab.judge.organism_{arm}.usd_per_reply"] = derive(
            f"ab.judge.organism_{arm}.usd_per_reply", s_usd.value / s_n.value, "USD/reply",
            f"{s_usd.item} / {s_n.item}", [s_usd, s_n],
            "a LoRA organism's 400-token replies, which run shorter than the base's")
    for stage, tag in (("c1_s00-03", "uncut"), ("sc1_c1cut_s00-03", "cut400")):
        a = Figure(f"ab.judge.{tag}.usd", pooled["judge_by_stage"][stage]["actual_usd"], "USD",
                   POOLED, f"judge_by_stage.{stage}.actual_usd")
        b = Figure(f"ab.judge.{tag}.replies",
                   pooled["judge_first_pass_usage"][stage]["replies"], "replies", POOLED,
                   f"judge_first_pass_usage.{stage}.replies")
        figs[a.item], figs[b.item] = a, b
        figs[f"ab.judge.{tag}.usd_per_reply"] = derive(
            f"ab.judge.{tag}.usd_per_reply", a.value / b.value, "USD/reply",
            f"ab.judge.{tag}.usd / ab.judge.{tag}.replies", [a, b])
    hole, hplan = load_json(HOLE_LEDGER), load_json(f"{HOLE_DIR}/judge_batch/plan.json")
    husd = sum(b["actual_usd"] for b in hole["batches"]
               if b["stage_dir"].rstrip("/").endswith("calibration_blind_person/hole_fill_2026-10-28"))
    h_usd = Figure("nsl.judge.usd", husd, "USD", HOLE_LEDGER,
                   "sum batches[].actual_usd where stage_dir ends "
                   "calibration_blind_person/hole_fill_2026-10-28",
                   note=f"seat {hplan['judge']}, level {hplan['level']}, {hplan['n_axes']} axes")
    h_n = Figure("nsl.judge.replies", sum(hplan["rows"].values()), "replies",
                 f"{HOLE_DIR}/judge_batch/plan.json", "sum rows.*")
    figs[h_usd.item], figs[h_n.item] = h_usd, h_n
    figs["nsl.judge.usd_per_reply"] = derive(
        "nsl.judge.usd_per_reply", husd / h_n.value, "USD/reply",
        "nsl.judge.usd / nsl.judge.replies", [h_usd, h_n])
    return figs


def api_generation() -> dict[str, Figure]:
    """OpenRouter generation for the AuditBench base, the only organism-family model on an API."""
    pooled, chk, ep = load_json(POOLED), load_json(C1_CHECK), load_json(OR_ENDPOINTS)
    usd = Figure("ab.api.gen.c1.usd", pooled["generation_usd_by_draw"]["c1"], "USD", POOLED,
                 "generation_usd_by_draw.c1")
    n = Figure("ab.api.gen.c1.replies", chk["rows"], "replies", C1_CHECK, "rows")
    core = [e for e in ep["data"]["endpoints"] if e["provider_name"] == "CoreWeave"][0]
    p_in = Figure("ab.api.price.prompt", float(core["pricing"]["prompt"]), "USD/token",
                  OR_ENDPOINTS, "data.endpoints[provider_name=CoreWeave].pricing.prompt")
    p_out = Figure("ab.api.price.completion", float(core["pricing"]["completion"]), "USD/token",
                   OR_ENDPOINTS, "data.endpoints[provider_name=CoreWeave].pricing.completion")
    toks = [r["prompt_tokens"] for r in jsonl_rows(GEN_LEDGER)
            if r.get("event") == "settle" and r.get("draw") == "c1"]
    mean_in = Figure("ab.api.prompt_tokens.mean", statistics.fmean(toks), "tokens", GEN_LEDGER,
                     "mean prompt_tokens over event=settle, draw=c1 rows",
                     note=f"{len(toks)} rows")
    reg = read_text(REGISTRATION)
    cap = int(re.search(r"max_tokens (\d+), one generate call", reg).group(1))
    f_cap = Figure("ab.reply_cap.tokens", cap, "tokens", REGISTRATION,
                   "settings table, Sampling row: max_tokens")
    figs = {f.item: f for f in (usd, n, p_in, p_out, mean_in, f_cap)}
    figs["ab.api.gen.uncut.usd_per_reply"] = derive(
        "ab.api.gen.uncut.usd_per_reply", usd.value / n.value, "USD/reply",
        "ab.api.gen.c1.usd / ab.api.gen.c1.replies", [usd, n],
        "max_tokens 4,096 draw; mean reply about 608 tokens")
    figs["ab.api.gen.cap400.usd_per_reply"] = derive(
        "ab.api.gen.cap400.usd_per_reply",
        mean_in.value * p_in.value + cap * p_out.value, "USD/reply",
        "ab.api.prompt_tokens.mean * ab.api.price.prompt + ab.reply_cap.tokens * "
        "ab.api.price.completion", [mean_in, p_in, p_out, f_cap],
        "upper bound: every reply reaches the 400-token cap")
    return figs


def box_rates() -> dict[str, Figure]:
    """Hourly rates: the owner's B71 band, the stored live offer reads, the court L40S box."""
    st = read_text(STANDING)
    lo, hi = (float(x) for x in re.search(r"\(\$(\d+) to \$(\d+)/h\)", st).groups())
    figs = {
        "box.4card.b71.low": Figure("box.4card.b71.low", lo, "USD/h", STANDING,
                                    "B71, 2026-11-15 paragraph: '($16 to $25/h)', low end"),
        "box.4card.b71.high": Figure("box.4card.b71.high", hi, "USD/h", STANDING,
                                     "B71, 2026-11-15 paragraph: '($16 to $25/h)', high end"),
    }
    for i, o in enumerate(load_json(OFFERS_1113)):
        if o["num_gpus"] == 4:
            key = f"box.4card.offer_20261113.{o['id']}"
            figs[key] = Figure(key, o["dph_total"], "USD/h", OFFERS_1113,
                               f"[{i}].dph_total ({o['num_gpus']}x {o['gpu_name']})")
    for i, o in enumerate(load_json(OFFERS_1115)["offers"]):
        if o["tier"] == "tp4":
            key = f"box.4card.offer_20261115.{o['id']}"
            figs[key] = Figure(key, o["dph_total"], "USD/h", OFFERS_1115,
                               f"offers[{i}].dph_total ({o['gpus']})")
            figs["box.4card.fetch_minutes"] = Figure(
                "box.4card.fetch_minutes", o["projection"]["fetch_minutes"], "min", OFFERS_1115,
                f"offers[{i}].projection.fetch_minutes")
    loc = read_text(LOCAL_VLOG)
    para = loc[loc.index("court-full-s4 stage-4 collection complete"):][:600]
    rate = float(re.search(r"\$([0-9.]+)/hr with disk", para).group(1))
    t0 = re.search(r"Created ~(\d\d):(\d\d) UTC", para).groups()
    t1 = re.search(r"gate (\d\d):(\d\d)-(\d\d):(\d\d) UTC", para).groups()
    wall = (int(t1[2]) * 60 + int(t1[3])) - (int(t0[0]) * 60 + int(t0[1]))
    figs["box.1card.l40s.rate"] = Figure(
        "box.1card.l40s.rate", rate, "USD/h", LOCAL_VLOG,
        "entry 'court-full-s4 stage-4 collection complete': '$0.544/hr with disk'",
        note="gitignored local log; instance 48396204, 1x L40S")
    figs["box.1card.l40s.wall_minutes"] = Figure(
        "box.1card.l40s.wall_minutes", wall, "min", LOCAL_VLOG,
        "same entry: 'Created ~13:07 UTC' to 'capture and gate 13:50-13:55 UTC'",
        note="four Qwen-7B arms of 288 replies, setup and capture included")
    return figs


def recipe_overheads(commit: str) -> dict[str, Figure]:
    """Fixed box phases for a 4-card 70B job, from the committed exact-stack recipe."""
    pm = git_show_json(commit, RECIPE)["phase_minutes"]
    src = f"{RECIPE}@{commit[:12]}"
    return {f"box.4card.{k}": Figure(f"box.4card.{k}", pm[k], "min", src, f"phase_minutes.{k}")
            for k in ("create_to_ready", "stage_and_push_manifest", "push_and_install",
                      "pull_capture_destroy")}
