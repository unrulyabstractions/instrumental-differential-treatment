"""Assemble the per-set plans, the per-run records and the cost table from cited figures."""

from __future__ import annotations

from decoy_plan_costs import (base_rows, compute_minutes, design_limit, set_shape,
                              _m_figure, _per_decoy)
from decoy_plan_frames import norm, set_frames
from decoy_plan_registry import DECOY_SETS, JUDGE_RATE_NOTES
from decoy_plan_sources import Figure, derive
from src.score.judge_seat_config import ORGANISM_JUDGE_MODEL, SUPERSEDED_ORGANISM_JUDGE_MODEL

_REGISTRY_FILE = ("script/analysis/baseline_free_20261115/organism_decoys_plan/"
                  "decoy_plan_registry.py")

#: judge-rate item -> the live-over-batch ratio of its seat
LIVE_RATIO = {"ab.judge.cap400.usd_per_reply": "price.ratio.live_over_batch.openai",
              "nsl.judge.usd_per_reply": "price.ratio.live_over_batch.anthropic"}

#: scenario tag -> design key of ``decoy_plan_costs.DESIGNS``
SCENARIOS = {"plan_core": "plan", "slack1_core": "slack1", "posthoc_core": "posthoc",
             "conformal_001_core": "0.01"}


def _rates(key: str, figs: dict) -> dict[str, Figure]:
    kind = DECOY_SETS[key]["compute"]
    if kind == "4card":
        offers = [f for k, f in figs.items() if k.startswith("box.4card.offer_")]
        return {"low": figs["box.4card.b71.low"], "high": figs["box.4card.b71.high"],
                "offer_min": min(offers, key=lambda f: f.value),
                "offer_max": max(offers, key=lambda f: f.value)}
    if kind == "l40s":
        return {"low": figs["box.1card.l40s.rate"], "high": figs["box.1card.l40s.rate"]}
    return {"low": figs["compute.mac.usd_per_hour"], "high": figs["compute.mac.usd_per_hour"]}


def _compute_cost(key: str, minutes: Figure, figs: dict) -> dict[str, Figure]:
    hours = minutes.value / 60.0
    return {tag: derive(f"{minutes.item}.usd_{tag}", hours * r.value, "USD",
                        f"{minutes.item} / 60 x {r.item}", [minutes, r])
            for tag, r in _rates(key, figs).items()}


def _n_models(key: str, tag: str, models: list[str]) -> Figure:
    return Figure(f"set.{key}.{tag}.n_models", len(models), "models", _REGISTRY_FILE,
                  f"DECOY_SETS[{key}] models: {', '.join(models)}")


def _judge(key: str, tag: str, replies: Figure, figs: dict) -> tuple[Figure, Figure]:
    rate = figs[DECOY_SETS[key]["judge_rate"]]
    judge = derive(f"set.{key}.{tag}.judge_usd", replies.value * rate.value, "USD",
                   f"{replies.item} x {rate.item}", [replies, rate], "Batch API price")
    ratio = figs[LIVE_RATIO[rate.item]]
    live = derive(f"set.{key}.{tag}.judge_usd_live", judge.value * ratio.value, "USD",
                  f"{judge.item} x {ratio.item}", [judge, ratio], "live (standard-tier) price")
    return judge, live


def _scenario(key: str, tag: str, m: Figure, per_decoy: Figure, models: list[str],
              figs: dict, table: list[Figure]) -> dict:
    spec = DECOY_SETS[key]
    n_models = _n_models(key, tag, models)
    replies = derive(f"set.{key}.{tag}.replies", m.value * per_decoy.value * len(models),
                     "replies", f"{m.item} x {per_decoy.item} x {n_models.item}",
                     [m, per_decoy, n_models])
    judge, live = _judge(key, tag, replies, figs)
    minutes = compute_minutes(key, int(m.value), int(per_decoy.value), figs, models)
    minutes.item = f"set.{key}.{tag}.compute_minutes"
    cost = _compute_cost(key, minutes, figs)
    total_lo = derive(f"set.{key}.{tag}.total_usd_low", judge.value + cost["low"].value, "USD",
                      f"{judge.item} + {cost['low'].item}", [judge, cost["low"]])
    total_hi = derive(f"set.{key}.{tag}.total_usd_high", judge.value + cost["high"].value, "USD",
                      f"{judge.item} + {cost['high'].item}", [judge, cost["high"]])
    table += [n_models, replies, judge, live, minutes, *cost.values(), total_lo, total_hi]
    return {"m": int(m.value), "design": m.formula, "models": models,
            "replies": int(replies.value), "judge_usd": judge.value,
            "judge_usd_live": live.value, "judge_rate_item": spec["judge_rate"],
            "compute": spec["compute"], "compute_minutes": minutes.value,
            "compute_usd": {k: v.value for k, v in cost.items()},
            "total_usd_low": total_lo.value, "total_usd_high": total_hi.value}


def _replicate(key: str, per_decoy: Figure, models: list[str], figs: dict,
               table: list[Figure]) -> dict:
    """One replicate arm per model: an audited candidate sampled again beside the decoys.

    It runs in the decoys' own session, so it adds sampling time and no fixed box phase.
    """
    spec = DECOY_SETS[key]
    tag = "replicate_arm"
    n_models = _n_models(key, tag, models)
    replies = derive(f"set.{key}.{tag}.replies", per_decoy.value * len(models), "replies",
                     f"{per_decoy.item} x {n_models.item}", [per_decoy, n_models])
    judge, live = _judge(key, tag, replies, figs)
    used, total = [], 0.0
    for model in models:
        tm = spec.get("time_model", model)
        secs, rows = figs[f"time.{tm}.seconds"], figs[f"time.{tm}.rows"]
        total += per_decoy.value / rows.value * secs.value / 60.0
        used += [s for s in (secs, rows) if s not in used]
    minutes = derive(f"set.{key}.{tag}.compute_minutes", total, "min",
                     "per model: replies_per_decoy / stored rows x stored seconds", used)
    cost = _compute_cost(key, minutes, figs)
    table += [n_models, replies, judge, live, minutes, *cost.values()]
    return {"replies": int(replies.value), "judge_usd": judge.value,
            "judge_usd_live": live.value, "compute_minutes": minutes.value,
            "compute_usd": {k: v.value for k, v in cost.items()},
            "total_usd_low": judge.value + cost["low"].value,
            "total_usd_high": judge.value + cost["high"].value,
            "check": "before pooling, the replicate arm must match the stored arm of the same "
                     "candidate: the registered statistic of the stored arm against the "
                     "replicate (paired over instructions, sign-flip null) must not reject at "
                     "0.05; a rejection means the session moved, and the stored candidates are "
                     "resampled beside the decoys"}


def _seat(key: str, facts: dict) -> dict:
    seats = sorted({s for r in DECOY_SETS[key]["runs"] for s in facts[r]["judge_on_rows"]})
    stored_old = any(s.split(":")[-1] == SUPERSEDED_ORGANISM_JUDGE_MODEL for s in seats)
    return {"stored_seat": seats, "configured_organism_seat": ORGANISM_JUDGE_MODEL,
            "needs_owner_word": stored_old,
            "why": ("the stored verdicts carry the seat B9 rules out unless the owner says so; "
                    "a decoy arm judged by any other seat is not exchangeable with them")
            if stored_old else ""}


def build_set(key: str, facts: dict, figs: dict, table: list[Figure]) -> dict:
    spec = DECOY_SETS[key]
    shape = set_shape(key, facts)
    per_decoy = _per_decoy(key, shape, facts)
    ms = {w: _m_figure(key, shape, w) for w in ("plan", "0.05", "slack1", "posthoc", "0.01")}
    table += [per_decoy, *ms.values()]
    scen = {}
    for tag, design in SCENARIOS.items():
        if tag == "posthoc_core" and shape["every_run_has_a_documented_target"]:
            continue
        scen[tag] = _scenario(key, tag, ms[design], per_decoy, spec["models_core"], figs, table)
    if "models_full" in spec:
        scen["plan_full"] = _scenario(key, "plan_full", ms["plan"], per_decoy,
                                      spec["models_full"], figs, table)
    rate = figs[spec["judge_rate"]]
    per_dm = derive(f"set.{key}.judge_usd_per_decoy_per_model", per_decoy.value * rate.value,
                    "USD", f"{per_decoy.item} x {rate.item}", [per_decoy, rate])
    table.append(per_dm)
    seat = _seat(key, facts)
    audited = {r: {norm(c) for c in facts[r]["candidates"]} for r in spec["runs"]}
    needed = {"plan": shape["m_plan"], "slack1": shape["m_slack1"],
              "posthoc": shape["m_posthoc"], "0.01": shape["m_min_at_0.01"]}
    out = {"set": key, "family": spec["family"], "roster_type": spec["roster_type"],
           "runs": spec["runs"], **shape, "replies_per_decoy_per_model": int(per_decoy.value),
           "judge_usd_per_decoy_per_model": per_dm.value, "judge_rate_item": rate.item,
           "judge_rate_usd_per_reply": rate.value,
           "judge_rate_note": JUDGE_RATE_NOTES[spec["family"]], "judge_seat": seat,
           "design_limit": design_limit(key), "scenarios": scen,
           "replicate_arm": _replicate(key, per_decoy, spec["models_core"], figs, table),
           "frames": set_frames(key, spec["runs"], audited, needed)}
    if seat["needs_owner_word"]:
        out["rejudge_alternative"] = _rejudge(key, facts, figs, scen["plan_core"], table)
    out["separate_draws"] = _separate_draws(key, out, ms["plan"], per_decoy, figs, table)
    return out


def _separate_draws(key: str, s: dict, m: Figure, per_decoy: Figure, figs: dict,
                    table: list[Figure]) -> dict | None:
    """A frame read from each organism's own elicitation needs one draw per organism.

    Each organism then samples only its own draw, and a model shared by the runs
    (the challenge base) samples every draw.
    """
    per_run = s["frames"].get("per_run", {})
    pools = sorted({p["elicitation_report"] for p in per_run.values()})
    shared = DECOY_SETS[key].get("shared_models", [])
    if len(pools) < 2 or not shared:
        return None
    n_pools = Figure(f"set.{key}.n_elicitation_pools", len(pools), "pools", " ; ".join(pools),
                     "distinct elicitation reports of the set's runs")
    n_shared = _n_models(key, "separate_draws_shared", shared)
    extra = derive(f"set.{key}.separate_draws.extra_replies",
                   (n_pools.value - 1) * m.value * per_decoy.value * n_shared.value, "replies",
                   f"({n_pools.item} - 1) x {m.item} x {per_decoy.item} x {n_shared.item}",
                   [n_pools, m, per_decoy, n_shared])
    judge, live = _judge(key, "separate_draws", extra, figs)
    table += [n_pools, n_shared, extra, judge, live]
    return {"n_pools": len(pools), "shared_models": shared, "extra_replies": int(extra.value),
            "extra_judge_usd": judge.value, "extra_judge_usd_live": live.value,
            "applies_to": "the roster-rule and target-tally frames at the planned m"}


def _rejudge(key: str, facts: dict, figs: dict, plan: dict, table: list[Figure]) -> dict:
    """Judge everything at the configured seat: stored target and base rows plus the decoys."""
    rate = figs["ab.judge.cap400.usd_per_reply"]
    stored = Figure(f"set.{key}.stored_rows", base_rows(key, facts), "replies",
                    " ; ".join(sorted({facts[r][t] for r in DECOY_SETS[key]["runs"]
                                       for t in ("target_table", "base_table")})),
                    "row count of every target and base verdict table of the set's runs")
    usd = derive(f"set.{key}.rejudge_usd", (stored.value + plan["replies"]) * rate.value, "USD",
                 f"({stored.item} + set.{key}.plan_core.replies) x {rate.item}", [stored, rate],
                 "the configured seat's rate is the gpt-5-mini 101-axis rate on 400-token replies")
    table += [stored, usd]
    return {"stored_rows": int(stored.value), "decoy_rows": plan["replies"],
            "usd": usd.value, "rate_item": rate.item}


def base_only_api(figs: dict, table: list[Figure]) -> dict:
    """AuditBench base alone on the API: the bases-as-targets control at Level 2, no box."""
    by_item = {f.item: f for f in table}
    m = by_item["set.auditbench_ai_organizations.m_plan"]
    n = by_item["set.auditbench_ai_organizations.replies_per_decoy_per_model"]
    out = {}
    for tag in ("uncut", "cap400"):
        g = figs[f"ab.api.gen.{tag}.usd_per_reply"]
        per = derive(f"api.base_only.gen_usd_per_decoy.{tag}", n.value * g.value, "USD",
                     f"{n.item} x {g.item}", [n, g])
        table.append(per)
        out[f"generation_usd_per_decoy_{tag}"] = per.value
    j = figs["ab.judge.cap400.usd_per_reply"]
    jd = derive("api.base_only.judge_usd_per_decoy", n.value * j.value, "USD",
                f"{n.item} x {j.item}", [n, j])
    g = figs["ab.api.gen.cap400.usd_per_reply"]
    tot = derive("api.base_only.total_usd", m.value * n.value * (g.value + j.value), "USD",
                 f"{m.item} x {n.item} x ({g.item} + {j.item})", [m, n, g, j])
    table += [jd, tot]
    out.update({"m": int(m.value), "replies": int(m.value * n.value),
                "judge_usd_per_decoy": jd.value, "total_usd": tot.value,
                "joins": "the OpenRouter draws C1 and C2 of the base; the decoys are sampled on "
                         "that provider stack, so they do not join base A or base B, which ran "
                         "on vLLM boxes",
                "what_it_serves": "the base as a target at Level 2 (a negative control for the "
                                  "decoy test); it cannot calibrate an organism, whose replies "
                                  "need the LoRA on a box"})
    return out


TOTAL_DESIGNS = {
    "plan_core": "every run at the planned m with a registered target (the narrow-secret-loyalty "
                 "and challenge runs register the first audited name of their gated roster)",
    "documented_or_posthoc": "a documented target where one exists; the audited maximum, at "
                             "m = 19 k_max, where none does",
    "slack1_core": "a registered target with one reference name allowed at or above it",
    "conformal_001_core": "a registered target at 0.01",
}


def _pick(s: dict, design: str) -> dict:
    if design == "documented_or_posthoc":
        return s["scenarios"].get("posthoc_core", s["scenarios"]["plan_core"])
    return s["scenarios"][design]


def totals(sets: dict) -> dict:
    """Sums of each design by family and over every set, with the replicate arms beside them."""
    out = {}
    keys = ("replies", "judge_usd", "judge_usd_live", "compute_usd_low", "compute_usd_high",
            "total_usd_low", "total_usd_high", "box_hours", "mac_hours")
    for design in TOTAL_DESIGNS:
        by_family: dict[str, dict] = {}
        for key, s in sets.items():
            c = _pick(s, design)
            fam = by_family.setdefault(s["family"], {"sets": [], **{k: 0.0 for k in keys}})
            fam["sets"].append(key)
            fam["replies"] += c["replies"]
            fam["judge_usd"] += c["judge_usd"]
            fam["judge_usd_live"] += c["judge_usd_live"]
            fam["compute_usd_low"] += c["compute_usd"]["low"]
            fam["compute_usd_high"] += c["compute_usd"]["high"]
            fam["total_usd_low"] += c["total_usd_low"]
            fam["total_usd_high"] += c["total_usd_high"]
            hours = c["compute_minutes"] / 60.0
            fam["mac_hours" if c["compute"] == "mac" else "box_hours"] += hours
        every = {k: sum(f[k] for f in by_family.values()) for k in keys}
        out[design] = {"what": TOTAL_DESIGNS[design], "by_family": by_family, "all_sets": every,
                       "sets_needing_a_redesign_first": [k for k, s in sets.items()
                                                         if s["design_limit"]]}
    rep = {k: 0.0 for k in ("replies", "judge_usd", "judge_usd_live", "total_usd_low",
                            "total_usd_high")}
    for s in sets.values():
        r = s["replicate_arm"]
        for k in rep:
            rep[k] += r[k]
    out["replicate_arms"] = rep
    return out
