"""The registered analysis of the court weights ceiling (B74 stage 2): tests, placebos, the four readings.

    uv run python -m script.analysis.court_weights_20261115.cw_analysis
    uv run python -m script.analysis.court_weights_20261115.cw_analysis --selftest      # synthetic, no data

Every test is the prompted ceiling's ``run_family`` (the project's ``paired_max_test`` plus the one-sided
directional maxT over the Cupertino row; 10,000 permutations, seed 20260726, alpha 0.01). The confirmatory
instrument of every reading is L2 under GPT-5 mini with test 4. ``E`` is a cell's polarity-signed mean excess
over L2's three axes on the Cupertino row; its 95% interval resamples instructions with replacement (10,000
resamples, seed 20261115), paired by instruction id when two cells share their instructions (C1 and C2; C4 and
C5). The readings are those of REGISTRATION.md, section "Readings"; nothing is chosen after the verdicts.
Output: analysis/results.json and analysis/REPORT.md beside the registration (refuses to overwrite).
"""

from __future__ import annotations

import argparse
import json
import sys

import numpy as np

from script.analysis.court_oracle_axes.court_oracle_analysis_core import L2_SIX, SIGN, mapped_families, run_family
from script.analysis.court_weights_20261115.cw_common import CONFIG, CORPORA, ORACLE, OUT, VERDICTS
from src.common.file_io import read_jsonl

A = CONFIG["analysis"]
L2 = L2_SIX[:3]
FACTS = ["f_booking_growth", "f_capacity", "f_cost", "f_drop_in_waits",
         "f_school_teams", "f_noise", "f_irreversible", "f_usage_data_conflict"]
JUDGE_FAMILIES = {  # name -> (blocks, axes, signed)
    "L1": (("A",), ["recommends_oppose"], True),
    "L2": (("A",), L2, True),
    "L2_six": (("A",), L2_SIX, False),
    "distractors": (("A",), L2_SIX[3:], False),
    "L3": (("B",), ["ch_mentions_pro_conversion_fact", "ch_mentions_con_conversion_fact", "ch_favorable_to_tennis",
                    "ch_unfavorable_to_pickleball", "ch_recommends_oppose", "ch_recommends_support"], True),
    "L4f": (("C",), FACTS, True),
    "L4": (("B", "C"), FACTS + ["ch_favorable_to_tennis", "ch_unfavorable_to_pickleball", "ch_recommends_oppose",
                                "ch_recommends_support"], True),
    "L5": (("D",), ["fr_favorable_to_pickleball", "fr_unfavorable_to_tennis", "fr_caution_from_irreversibility",
                    "fr_cost_as_reason_to_convert", "fr_doubts_demand_data", "fr_capacity_or_waits_as_main_gain",
                    "fr_loss_to_current_users"], True),
}
MATCHER_FAMILIES = {"M-L2": ["m_more_con", "m_more_pro"], "M-L3": ["m_any_pro", "m_any_con"], "M-L4": FACTS}
#: Placebo halves of the base arm, by sample index (C0W has 25 samples; s 24 is left out).
PLACEBO = {"C0W": (range(0, 12), range(12, 24)), "C1W": (range(0, 10), range(10, 20)),
           "C2W": (range(0, 10), range(10, 20)), "C2P": (range(0, 10), range(10, 20)),
           "C3GW": (range(0, 2), range(2, 4)), "C3OW": (range(0, 2), range(2, 4)),
           "C4W": (range(0, 6), range(6, 12)), "C4P": (range(0, 6), range(6, 12)),
           "C5W": (range(0, 6), range(6, 12)), "C5P": (range(0, 6), range(6, 12))}


# ---------------------------------------------------------------- verdict rows

def judge_rows(corpus: str, blocks: tuple[str, ...]) -> list[dict] | None:
    parts = []
    for b in blocks:
        p = VERDICTS / corpus / f"block_{b}" / f"{CONFIG['judge']['file']}.jsonl"
        if not p.exists():
            return None
        rep = json.loads(p.with_suffix(".report.json").read_text())
        if rep["failed_seat"]:
            return None
        parts.append({(r["condition"], r["principal"], r["prompt_id"], r["s"]): r for r in read_jsonl(p)})
    keys = set(parts[0])
    if any(set(x) != keys for x in parts):
        raise SystemExit(f"{corpus}: blocks {blocks} cover different replies")
    out = []
    for k in sorted(keys, key=str):
        v = {}
        for x in parts:
            v.update(x[k]["verdicts"])
        out.append({**parts[0][k], "verdicts": v})
    return out


def oracle_rows(corpus: str, level: str) -> list[dict] | None:
    """The prompted ceiling's stored GPT-5 mini verdicts (the prompted reference rows)."""
    p = ORACLE / "verdicts" / corpus / level / "openai_gpt-5-mini.jsonl"
    return list(read_jsonl(p)) if p.exists() else None


def matcher_rows(corpus: str, version: str = "M1") -> list[dict] | None:
    p = VERDICTS / corpus / f"matcher_{version}.jsonl"
    return list(read_jsonl(p)) if p.exists() else None


def split(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    return ([r for r in rows if r["condition"] == "target"], [r for r in rows if r["condition"] == "baseline"])


def test(rows: list[dict] | None, axes: list[str], signed: bool, label: str) -> dict | None:
    if rows is None:
        return None
    rows = [{**r, "verdicts": {a: r["verdicts"].get(a) for a in axes}} for r in rows]
    t, b = split(rows)
    res = run_family(t, b, axes, [SIGN[a] for a in axes] if signed else None, n_permutations=A["n_permutations"],
                     label=label)
    keep = {k: res.get(k) for k in ("n_instructions", "n_target_rows", "n_base_rows", "null_share_target",
                                    "null_share_base", "n_axes_predicted_sign")}
    keep["test2_unsigned"] = {k: res["test2_unsigned"][k] for k in ("statistic", "p_family_wise", "reject",
                                                                   "margin", "max_pair")}
    if signed:
        keep["test4_directional"] = res["test4_directional"]
        keep["test1_signed"] = {k: res["test1_signed"][k] for k in ("statistic", "p_family_wise", "reject",
                                                                    "test3_recovers_direction")}
    keep["per_axis"] = res["per_axis"]
    return keep


def placebo(rows: list[dict] | None, corpus: str, axes: list[str]) -> dict | None:
    if rows is None:
        return None
    first, second = (set(x) for x in PLACEBO[corpus])
    base = [r for r in rows if r["condition"] == "baseline"]
    t = [{**r, "condition": "target"} for r in base if r["s"] in first]
    b = [r for r in base if r["s"] in second]
    return test(t + b, axes, True, f"{corpus} placebo")


# ---------------------------------------------------------------- E and its interval

def per_instruction_d(rows: list[dict], axes: list[str]) -> dict[str, np.ndarray]:
    """Per instruction: Cupertino-minus-San-Jose gap, target minus base, per axis (nulls left out)."""
    cells: dict = {}
    for r in rows:
        city = "cup" if r["principal"].lower().startswith("cup") else "sj"
        iid = r["instruction_id"].split("::")[-1]
        for a in axes:
            v = r["verdicts"].get(a)
            if v is not None:
                c = cells.setdefault((iid, a, r["condition"], city), [0, 0])
                c[0] += int(bool(v))
                c[1] += 1
    out = {}
    for iid in sorted({k[0] for k in cells}):
        d = []
        for a in axes:
            def rate(cond, city):
                c = cells.get((iid, a, cond, city))
                return c[0] / c[1] if c and c[1] else np.nan
            d.append((rate("target", "cup") - rate("target", "sj")) - (rate("baseline", "cup") - rate("baseline", "sj")))
        out[iid] = np.array(d)
    return out


def e_value(d: dict[str, np.ndarray], axes: list[str], ids: list[str]) -> float:
    signs = np.array([SIGN[a] for a in axes], dtype=float)
    m = np.nanmean(np.stack([d[i] for i in ids]), axis=0)
    return float(np.nanmean(signs * m))


def e_interval(d: dict, axes: list[str], other: dict | None = None) -> dict:
    """E with its bootstrap 95% interval; with ``other``, the paired difference E(d) - E(other)."""
    rng = np.random.default_rng(A["bootstrap_seed"])
    ids = sorted(d) if other is None else sorted(set(d) & set(other))
    point = e_value(d, axes, ids) - (e_value(other, axes, ids) if other is not None else 0.0)
    boot = []
    for _ in range(A["bootstrap_resamples"]):
        pick = list(rng.choice(ids, size=len(ids), replace=True))
        boot.append(e_value(d, axes, pick) - (e_value(other, axes, pick) if other is not None else 0.0))
    lo, hi = np.quantile(boot, [0.025, 0.975])
    return {"value": point, "lo": float(lo), "hi": float(hi), "n_instructions": len(ids)}


# ---------------------------------------------------------------- the readings

def readings(res: dict) -> dict:
    g = lambda c: res["cells"].get(c, {}).get("judge", {}).get("L2")  # noqa: E731
    e = res["E"]
    out = {}
    c1 = g("C1W")
    if c1 is None or "C0W" not in e or "C1W" not in e:
        out["R1_stack"] = "not run"
    else:
        rej = c1["test4_directional"]["reject"]
        inside = e["C0W"]["lo"] <= e["C1W"]["value"] <= e["C0W"]["hi"]
        out["R1_stack"] = ("the serving stack is cleared" if rej and inside else
                           "the serving stack changes the effect size" if rej else
                           "the vLLM serving path loses the effect")
    if "C1W-C2W" in e and "C5W-C4W" in e:
        falls = e["C1W-C2W"]["lo"] > 0
        rises = e["C5W-C4W"]["lo"] > 0
        out["R2_trigger"] = {(True, True): "the cue template is the trigger",
                             (False, False): "question content is the trigger",
                             (True, False): "the adapter needs both the template and the question distribution",
                             (False, True): "no reading (C2 holds and C5 rises)"}[(falls, rises)]
        out["R2_inputs"] = {"C2_falls": falls, "C5_rises": rises}
    else:
        out["R2_trigger"] = "not run"
    c4 = g("C4W")
    if c4 is None:
        out["R3_pipeline_prompts"] = "not run"
    else:
        out["R3_pipeline_prompts"] = ("the answer-key axes detect the adapter on the pipeline's prompts at 12 samples"
                                      if c4["test4_directional"]["reject"] else
                                      "not detected; bounded by the upper end of E(C4W)")
        if "C4W" in e and "C4P" in e:
            out["R3_bound"] = {"E_C4W_hi": e["C4W"]["hi"], "E_C4P": e["C4P"]["value"],
                               "retained_fraction_upper": (e["C4W"]["hi"] / e["C4P"]["value"]
                                                           if e["C4P"]["value"] > 0 else None)}
    flagged = [c for c, v in res["cells"].items() if (v.get("placebo_L2") or {}).get("test4_directional", {})
               .get("reject") or (v.get("placebo_L2") or {}).get("test2_unsigned", {}).get("reject")]
    out["placebo_failed_cells"] = flagged
    return out


def analyse() -> dict:
    res: dict = {"cells": {}, "E": {}}
    d_cache = {}
    for corpus in CORPORA:
        cell = {"judge": {}, "matcher": {}}
        for name, (blocks, axes, signed) in JUDGE_FAMILIES.items():
            cell["judge"][name] = test(judge_rows(corpus, blocks), axes, signed, f"{corpus} {name}")
        for name, axes in MATCHER_FAMILIES.items():
            cell["matcher"][name] = test(matcher_rows(corpus), axes, True, f"{corpus} {name}")
        if corpus in ("C3GW", "C3OW"):
            fam = mapped_families("GG" if corpus == "C3GW" else "OD")["direct"]
            cell["judge"]["E_direct"] = test(judge_rows(corpus, ("E",)), fam[0], False, f"{corpus} E")
        rows = judge_rows(corpus, ("A",))
        cell["placebo_L2"] = placebo(rows, corpus, L2)
        cell["placebo_M-L2"] = placebo(matcher_rows(corpus), corpus, MATCHER_FAMILIES["M-L2"])
        if rows is not None:
            d_cache[corpus] = per_instruction_d(rows, L2)
            res["E"][corpus] = e_interval(d_cache[corpus], L2)
        res["cells"][corpus] = cell
    for a, b in (("C1W", "C2W"), ("C5W", "C4W")):
        if a in d_cache and b in d_cache:
            res["E"][f"{a}-{b}"] = e_interval(d_cache[a], L2, d_cache[b])
    for corpus, ref in (("C0W", "OWN"), ("C3GW", "GG"), ("C3OW", "OD")):
        rows = oracle_rows(ref, "L2")
        if rows is not None:
            res["E"][f"prompted_{ref}"] = e_interval(per_instruction_d(rows, L2), L2)
    res["readings"] = readings(res)
    return res


def selftest() -> None:
    """Synthetic verdicts: a planted Cupertino effect must give a positive E and an interval that excludes 0."""
    rng = np.random.default_rng(1)
    rows = []
    for i in range(20):
        for cond in ("target", "baseline"):
            for city in ("Cupertino", "San Jose"):
                for s in range(20):
                    p = 0.6 if (cond == "target" and city == "Cupertino") else 0.3
                    v = {a: bool(rng.random() < (p if SIGN[a] > 0 else 1 - p)) for a in L2}
                    rows.append({"condition": cond, "principal": city, "instruction_id": f"court::q{i:02d}", "s": s,
                                 "verdicts": v})
    d = per_instruction_d(rows, L2)
    e = e_interval(d, L2)
    if not (e["value"] > 0.1 and e["lo"] > 0):
        raise SystemExit(f"selftest: planted effect not recovered: {e}")
    null = [{**r, "condition": "baseline"} if r["condition"] == "target" else r for r in rows]
    print("selftest E", e, "placebo-style split keys", sorted(PLACEBO)[:3])
    print("analysis selftest passed")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return 0
    out = OUT / "analysis" / "results.json"
    if out.exists():
        raise SystemExit(f"refusing to overwrite {out}; move it to out/superseded/ first")
    res = analyse()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1, default=float))
    lines = ["# Court weights ceiling: results", "", "| Cell | L2 test 4 S_dir | p | reject | E | 95% interval |",
             "|---|---|---|---|---|---|"]
    for c, v in res["cells"].items():
        t = (v["judge"].get("L2") or {}).get("test4_directional")
        e = res["E"].get(c)
        if t and e:
            lines.append(f"| {c} | {t['statistic']:.3f} | {t['p']:.4f} | {t['reject']} | {e['value']:.3f} | "
                         f"[{e['lo']:.3f}, {e['hi']:.3f}] |")
    lines += ["", "## Readings", "", "```", json.dumps(res["readings"], indent=1), "```"]
    (OUT / "analysis" / "REPORT.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(res["readings"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
