"""Assemble the per-set plans, the per-run records and the cost table from cited figures."""

from __future__ import annotations

from decoy_plan_costs import (base_rows, compute_minutes, design_limit, set_shape,
                              _m_figure, _per_decoy)
from decoy_plan_frames import frame, norm
from decoy_plan_registry import DECOY_SETS, JUDGE_RATE_NOTES
from decoy_plan_sources import Figure, derive
from src.score.judge_seat_config import ORGANISM_JUDGE_MODEL, SUPERSEDED_ORGANISM_JUDGE_MODEL


def _compute_cost(key: str, minutes: Figure, figs: dict) -> dict[str, Figure]:
    kind = DECOY_SETS[key]["compute"]
    hours = minutes.value / 60.0
    if kind == "4card":
        rates = {"low": figs["box.4card.b71.low"], "high": figs["box.4card.b71.high"]}
        offers = [f for k, f in figs.items() if k.startswith("box.4card.offer_")]
        rates["offer_min"] = min(offers, key=lambda f: f.value)
        rates["offer_max"] = max(offers, key=lambda f: f.value)
    elif kind == "l40s":
        rates = {"low": figs["box.1card.l40s.rate"], "high": figs["box.1card.l40s.rate"]}
    else:
        rates = {"low": figs["compute.mac.usd_per_hour"], "high": figs["compute.mac.usd_per_hour"]}
    return {tag: derive(f"{minutes.item}.usd_{tag}", hours * r.value, "USD",
                        f"{minutes.item} / 60 x {r.item}", [minutes, r])
            for tag, r in rates.items()}


def _scenario(key: str, tag: str, m: Figure, per_decoy: Figure, models: list[str],
              figs: dict, table: list[Figure]) -> dict:
    spec = DECOY_SETS[key]
    n_models = Figure(f"set.{key}.{tag}.n_models", len(models), "models",
                      "script/analysis/baseline_free_20261115/organism_decoys_plan/"
                      "decoy_plan_registry.py", f"DECOY_SETS[{key}] models: {', '.join(models)}")
    replies = derive(f"set.{key}.{tag}.replies", m.value * per_decoy.value * len(models),
                     "replies", f"{m.item} x {per_decoy.item} x {n_models.item}",
                     [m, per_decoy, n_models])
    rate = figs[spec["judge_rate"]]
    judge = derive(f"set.{key}.{tag}.judge_usd", replies.value * rate.value, "USD",
                   f"{replies.item} x {rate.item}", [replies, rate])
    minutes = compute_minutes(key, int(m.value), int(per_decoy.value), figs, models)
    minutes.item = f"set.{key}.{tag}.compute_minutes"
    cost = _compute_cost(key, minutes, figs)
    total_lo = derive(f"set.{key}.{tag}.total_usd_low", judge.value + cost["low"].value, "USD",
                      f"{judge.item} + {cost['low'].item}", [judge, cost["low"]])
    total_hi = derive(f"set.{key}.{tag}.total_usd_high", judge.value + cost["high"].value, "USD",
                      f"{judge.item} + {cost['high'].item}", [judge, cost["high"]])
    table += [n_models, replies, judge, minutes, *cost.values(), total_lo, total_hi]
    return {"m": int(m.value), "models": models, "replies": int(replies.value),
            "judge_usd": judge.value, "judge_rate_item": rate.item,
            "compute": spec["compute"], "compute_minutes": minutes.value,
            "compute_usd": {k: v.value for k, v in cost.items()},
            "total_usd_low": total_lo.value, "total_usd_high": total_hi.value}


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
    m_plan, m05, m01 = (_m_figure(key, shape, w) for w in ("plan", "0.05", "0.01"))
    table += [per_decoy, m05, m_plan, m01]
    scen = {"plan_core": _scenario(key, "plan_core", m_plan, per_decoy, spec["models_core"],
                                   figs, table),
            "conformal_001_core": _scenario(key, "conformal_001_core", m01, per_decoy,
                                            spec["models_core"], figs, table)}
    if "models_full" in spec:
        scen["plan_full"] = _scenario(key, "plan_full", m_plan, per_decoy, spec["models_full"],
                                      figs, table)
    rate = figs[spec["judge_rate"]]
    per_dm = derive(f"set.{key}.judge_usd_per_decoy_per_model", per_decoy.value * rate.value,
                    "USD", f"{per_decoy.item} x {rate.item}", [per_decoy, rate])
    table.append(per_dm)
    seat = _seat(key, facts)
    out = {"set": key, "family": spec["family"], "roster_type": spec["roster_type"],
           "runs": spec["runs"], **shape, "replies_per_decoy_per_model": int(per_decoy.value),
           "judge_usd_per_decoy_per_model": per_dm.value, "judge_rate_item": rate.item,
           "judge_rate_usd_per_reply": rate.value,
           "judge_rate_note": JUDGE_RATE_NOTES[spec["family"]], "judge_seat": seat,
           "design_limit": design_limit(key), "scenarios": scen,
           "frame": frame(key, {norm(c) for r in spec["runs"] for c in facts[r]["candidates"]})}
    if seat["needs_owner_word"]:
        out["rejudge_alternative"] = _rejudge(key, facts, figs, scen["plan_core"], table)
    return out


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
                "what_it_serves": "the base as a target at Level 2 (a negative control for the "
                                  "decoy test); it cannot calibrate an organism, whose replies "
                                  "need the LoRA on a box"})
    return out


def totals(sets: dict) -> dict:
    """Sums of each scenario by family and over every set, with the sets that need a redesign."""
    out = {}
    for scen in ("plan_core", "conformal_001_core"):
        by_family: dict[str, dict] = {}
        for key, s in sets.items():
            c = s["scenarios"][scen]
            fam = by_family.setdefault(s["family"], {"sets": [], "replies": 0, "judge_usd": 0.0,
                                                     "compute_usd_low": 0.0,
                                                     "compute_usd_high": 0.0,
                                                     "total_usd_low": 0.0, "total_usd_high": 0.0})
            fam["sets"].append(key)
            fam["replies"] += c["replies"]
            fam["judge_usd"] += c["judge_usd"]
            fam["compute_usd_low"] += c["compute_usd"]["low"]
            fam["compute_usd_high"] += c["compute_usd"]["high"]
            fam["total_usd_low"] += c["total_usd_low"]
            fam["total_usd_high"] += c["total_usd_high"]
        every = {k: sum(f[k] for f in by_family.values()) for k in
                 ("replies", "judge_usd", "compute_usd_low", "compute_usd_high", "total_usd_low",
                  "total_usd_high")}
        out[scen] = {"by_family": by_family, "all_sets": every,
                     "sets_needing_a_redesign_first": [k for k, s in sets.items()
                                                       if s["design_limit"]]}
    return out
