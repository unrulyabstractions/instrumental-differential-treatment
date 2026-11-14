"""Rater agreement of the court ceiling: Cohen's kappa, raw agreement and both firing rates.

Registered pairs (REGISTRATION.md, "Agreement"):

* GPT-5 mini against Haiku 4.5 on every axis of blocks A to D;
* each judge against each matcher version on the eight facts and
  ``f_equal_terms``, and on the construct pairs (``ch_mentions_pro_conversion_fact``
  and ``m_any_pro``, ``ch_mentions_con_conversion_fact`` and ``m_any_con``,
  ``emphasizes_conversion_downsides`` and ``m_more_con``,
  ``emphasizes_conversion_benefits`` and ``m_more_pro``);
* each judge with itself: ``recommends_oppose`` (block A) against
  ``ch_recommends_oppose`` (block B);
* GPT-5 mini new against the stored second judging of OWN's six block-A axes.

Every pair is reported pooled over both conditions and per condition. A reply
leaves a pair when either rater returned null. Kappa is undefined when both
raters are constant. A judge pair below 0.4 is flagged judge-dependent; a matcher
axis is interpretable on a corpus only where its kappa with at least one judge
is 0.4 or more (amendment A6).

    .venv/bin/python -m script.analysis.court_oracle_axes.court_oracle_agreement
"""

from __future__ import annotations

from script.analysis.court_oracle_axes.court_oracle_analysis_core import (
    ANALYSIS, CORPORA, EXT, FACTS, JUDGES, L2_SIX, MATCHERS, dump, kappa, load_rows)
from src.common.file_io import read_jsonl

BLOCK_FILES = {
    "A": ("L2", L2_SIX),
    "B": ("L3", ["ch_mentions_pro_conversion_fact", "ch_mentions_con_conversion_fact",
                 "ch_favorable_to_tennis", "ch_unfavorable_to_pickleball",
                 "ch_recommends_oppose", "ch_recommends_support"]),
    "C": ("L4", FACTS + ["f_equal_terms"]),
    "D": ("L5", ["fr_favorable_to_pickleball", "fr_unfavorable_to_tennis",
                 "fr_caution_from_irreversibility", "fr_cost_as_reason_to_convert",
                 "fr_doubts_demand_data", "fr_capacity_or_waits_as_main_gain",
                 "fr_loss_to_current_users"]),
}
LEVEL_OF_BLOCK = {"A": "L1-L2", "B": "L3-L4", "C": "L4", "D": "L5"}
CONSTRUCT = [("L3", "ch_mentions_pro_conversion_fact", "L3", "m_any_pro"),
             ("L3", "ch_mentions_con_conversion_fact", "L3", "m_any_con"),
             ("L2", "emphasizes_conversion_downsides", "L2", "m_more_con"),
             ("L2", "emphasizes_conversion_benefits", "L2", "m_more_pro")]


def key(r: dict) -> tuple:
    return (r["condition"], r["principal"], r["prompt_id"], int(r["s"]))


def indexed(corpus: str, level: str, rater: str) -> dict:
    rows = load_rows(corpus, level, rater)
    out = {key(r): r["verdicts"] for r in rows}
    if len(out) != len(rows):
        raise SystemExit(f"{corpus} {level} {rater}: duplicate reply keys")
    return out


def compare(a: dict, axis_a: str, b: dict, axis_b: str) -> dict:
    if set(a) != set(b):
        raise SystemExit(f"{axis_a} and {axis_b} cover different replies")
    keys = sorted(a)
    res = {"pooled": kappa([a[k][axis_a] for k in keys], [b[k][axis_b] for k in keys])}
    for cond in ("target", "baseline"):
        ks = [k for k in keys if k[0] == cond]
        res[cond] = kappa([a[k][axis_a] for k in ks], [b[k][axis_b] for k in ks])
    return res


def main() -> None:
    out_path = ANALYSIS / "agreement.json"
    if out_path.exists():
        raise SystemExit(f"{out_path} exists; this run never overwrites")
    result = {"judge_pairs": [], "judge_matcher": [], "judge_self": [], "stored_gpt_own": [],
              "consistency_L3_L4_block_B": []}
    gpt, haiku = JUDGES["gpt"], JUDGES["haiku"]
    for corpus in CORPORA:
        for block, (level, axes) in BLOCK_FILES.items():
            a, b = indexed(corpus, level, gpt), indexed(corpus, level, haiku)
            for axis in axes:
                r = compare(a, axis, b, axis)
                k = r["pooled"]["kappa"]
                result["judge_pairs"].append({
                    "corpus": corpus, "block": block, "level": LEVEL_OF_BLOCK[block], "axis": axis,
                    **r, "judge_dependent": (k is None) or (k < 0.4)})
        for judge in (gpt, haiku):
            j4, j3, j2 = (indexed(corpus, lv, judge) for lv in ("L4", "L3", "L2"))
            for mv, mfile in MATCHERS.items():
                m4, m3, m2 = (indexed(corpus, lv, mfile) for lv in ("L4", "L3", "L2"))
                for axis in FACTS + ["f_equal_terms"]:
                    result["judge_matcher"].append({
                        "corpus": corpus, "judge": judge, "matcher": mv, "judge_axis": axis,
                        "matcher_axis": axis, "kind": "same fact", **compare(j4, axis, m4, axis)})
                for jl, ja, ml, ma in CONSTRUCT:
                    jj = {"L3": j3, "L2": j2}[jl]
                    mm = {"L3": m3, "L2": m2}[ml]
                    result["judge_matcher"].append({
                        "corpus": corpus, "judge": judge, "matcher": mv, "judge_axis": ja,
                        "matcher_axis": ma, "kind": "construct", **compare(jj, ja, mm, ma)})
            result["judge_self"].append({
                "corpus": corpus, "judge": judge, "axis_a": "recommends_oppose (block A)",
                "axis_b": "ch_recommends_oppose (block B)",
                **compare(j2, "recommends_oppose", j3, "ch_recommends_oppose")})
            # The L4 file joins the block-B call; its block-B axes must equal the L3 file's.
            diffs = sum(1 for k in j3 for ax in ("ch_favorable_to_tennis", "ch_unfavorable_to_pickleball",
                                                 "ch_recommends_oppose", "ch_recommends_support")
                        if j3[k][ax] != j4[k][ax])
            result["consistency_L3_L4_block_B"].append({"corpus": corpus, "judge": judge,
                                                        "differing_cells": diffs})
    # A6: a matcher axis is interpretable on a corpus only where kappa with some judge >= 0.4.
    interp = {}
    for r in result["judge_matcher"]:
        k = r["pooled"]["kappa"]
        slot = interp.setdefault((r["corpus"], r["matcher"], r["matcher_axis"]), False)
        interp[(r["corpus"], r["matcher"], r["matcher_axis"])] = slot or (k is not None and k >= 0.4)
    result["matcher_interpretable"] = [
        {"corpus": c, "matcher": m, "axis": a, "interpretable": v} for (c, m, a), v in sorted(interp.items())]
    # GPT-5 mini new against the stored second judging on OWN.
    stored = {}
    arm = {"organism": "target", "baseline": "baseline"}
    for r in read_jsonl(EXT / "idt_organism_p2/geometry_verdicts.jsonl"):
        stored.setdefault((arm[r["condition"]], r["group"], r["prompt_id"], int(r["s"])), {})[r["axis_id"]] = r["verdict"]
    new = indexed("OWN", "L2", gpt)
    for axis in L2_SIX:
        result["stored_gpt_own"].append({"axis": axis, **compare(new, axis, stored, axis)})
    dump(result, out_path)
    print(f"wrote {out_path}")
    for r in result["judge_pairs"]:
        p = r["pooled"]
        print(f"{r['corpus']:4} {r['block']} {r['axis']:36} k={p['kappa'] if p['kappa'] is None else round(p['kappa'], 3)!s:6} "
              f"agree={p['agreement']:.3f} gpt={p['rate_a']:.3f} haiku={p['rate_b']:.3f}"
              f"{'  JUDGE-DEPENDENT' if r['judge_dependent'] else ''}")


if __name__ == "__main__":
    main()
