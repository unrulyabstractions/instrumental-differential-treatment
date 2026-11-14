"""Tables and the decomposition of the court ceiling, from the analysis JSON files. No model is called.

Reads ``analysis/tests_*.json``, ``analysis/agreement.json`` and
``analysis/instruction_count_curve.json`` and writes tab-separated tables and
``decomposition.json``. The decomposition applies the registered readings
(registration "Ceiling decomposition" with amendment A2 and A3) mechanically to
the L2 cell under GPT-5 mini: directional rows read test 4, unsigned rows read
test 2, row 1b counts slices, and GG and OD are read separately.

Two exploratory additions are labeled as such: the paper's stored verdicts set
beside the new ones, and the agreement of the pipeline's stored judging with
the block-E judging of the same thirteen direct axes on GG and OD.

    .venv/bin/python -m script.analysis.court_oracle_axes.court_oracle_analysis_tables
"""

from __future__ import annotations

import csv
import json

from script.analysis.court_oracle_axes.court_oracle_analysis_core import (
    ALPHA, ANALYSIS, EXT, JUDGES, MAPPING, RATER_LABEL, dump, kappa, load_rows)
from src.common.file_io import read_jsonl

GPT = JUDGES["gpt"]


def load(name: str) -> list[dict]:
    return json.loads((ANALYSIS / f"tests_{name}.json").read_text())["results"]


def write_tsv(path, header: list[str], rows: list[list]) -> None:
    if path.exists():
        raise SystemExit(f"{path} exists; this run never overwrites")
    with path.open("x", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(header)
        for r in rows:
            w.writerow(["" if v is None else (f"{v:.6g}" if isinstance(v, float) else v) for v in r])


def grid_row(group: str, r: dict) -> list:
    t1, t2, t4 = r.get("test1_signed"), r["test2_unsigned"], r.get("test4_directional")
    return [group, r["corpus"], RATER_LABEL.get(r["rater"], r["rater"]), r["family"],
            r.get("selector"), r["n_axes"], r["n_instructions"],
            t1["statistic"] if t1 else None, t1["p_family_wise"] if t1 else None,
            t1["max_pair"]["candidate"] if t1 else None, t1["max_pair"]["axis_id"] if t1 else None,
            t1["test3_recovers_direction"] if t1 else None,
            t2["statistic"], t2["p_family_wise"], t2["null_p99"], t2["margin"],
            t2["max_pair"]["candidate"], t2["max_pair"]["axis_id"],
            t4["statistic"] if t4 else None, t4["p"] if t4 else None,
            t4["null_p99"] if t4 else None, t4["margin"] if t4 else None,
            ";".join(t4["rejected_axes"]) if t4 else None,
            r.get("n_axes_predicted_sign"), r.get("null_share_target"), r.get("null_share_base")]


GRID_HEADER = ["group", "corpus", "rater", "family", "slice", "n_axes", "m",
               "signed_S", "signed_p", "signed_max_city", "signed_max_axis", "test3_recovers_direction",
               "unsigned_S", "unsigned_p", "unsigned_null_p99", "unsigned_margin",
               "unsigned_max_city", "unsigned_max_axis",
               "dir_S", "dir_p", "dir_null_p99", "dir_margin", "dir_rejected_axes",
               "n_axes_predicted_sign", "null_share_target", "null_share_base"]


def find(results, **kw):
    out = [r for r in results if all(r.get(k) == v for k, v in kw.items())]
    if len(out) != 1:
        raise SystemExit(f"{kw}: {len(out)} matches")
    return out[0]


def decomposition(full, slices, row2c, row3, row3b) -> dict:
    cell = dict(rater=GPT, family="L2")
    row1 = find(full, corpus="OWN", **cell)
    sl = sorted([r for r in slices if r["rater"] == GPT and r["family"] == "L2"], key=lambda r: r["selector"])
    n_sl = sum(r["test4_directional"]["reject"] for r in sl)

    def d4(r):
        t = r["test4_directional"]
        return {"S_dir": t["statistic"], "p_dir": t["p"], "margin_dir": t["margin"], "reject": t["reject"],
                "n_axes": r["n_axes"], "n_axes_predicted_sign": r["n_axes_predicted_sign"],
                "unsigned_margin": r["test2_unsigned"]["margin"]}

    def d2(r):
        t = r["test2_unsigned"]
        return {"S": t["statistic"], "p": t["p_family_wise"], "margin": t["margin"], "reject": t["reject"],
                "n_axes": r["n_axes"], "max_pair": t["max_pair"], "rejected_axes": t["rejected_axes"]}

    rows = {"1": {"corpus": "OWN", **d4(row1)},
            "1b": {"corpus": "OWN", "slices": [d4(r) for r in sl], "n_reject": n_sl, "reject": n_sl >= 3}}
    readings = []
    r1, r1b = rows["1"]["reject"], rows["1b"]["reject"]
    readings.append({"pattern": "Row 1 rejects in the predicted direction, row 1b slices do not",
                     "applies": bool(r1 and not r1b),
                     "reading": "four samples per cell are too few on these prompts"})
    for run in ("GG", "OD"):
        r2 = find(full, corpus=run, **cell)
        r2c = find(row2c, corpus=run)
        r3 = find(row3, corpus=run)
        r3b = {f: find(row3b, corpus=run, family=f) for f in
               ("direct", "direct_partial", "direct_partial_wo_h065_g003")}
        e_fam = f"E_{run}_direct"
        r2x2 = find(full, corpus="OWN", rater=GPT, family=e_fam)
        r2x2_sl = sorted([r for r in slices if r["rater"] == GPT and r["family"] == e_fam],
                         key=lambda r: r["selector"])
        r2e = find(full, corpus=run, rater=GPT, family=e_fam)
        undocumented = find(full, corpus=run, rater=GPT, family="distractors")
        rows[f"2 {run}"] = {"corpus": run, "test4": d4(r2), "test2": d2(r2)}
        rows[f"2c {run}"] = {"corpus": run, "test2": d2(r2c),
                             "answer_key_axes_in_2c": [
                                 {"axis_id": p["axis_id"], "t": p["t"], "mean_excess": p["mean_excess"],
                                  "p_adj_unsigned": p["p_adj_unsigned"]}
                                 for p in r2c["per_axis"] if p["axis_id"] in r2["axes"]]}
        rows[f"3 {run}"] = {"corpus": run, "test2": d2(r3), "matches_stored": r3["matches_stored"]}
        rows[f"3b {run}"] = {f: {"test4": d4(r), "test1_recovers_direction": r["test1_signed"]["test3_recovers_direction"],
                                 "axes": r["axes"]} for f, r in r3b.items()}
        rows[f"2x2 {run}"] = {"corpus": "OWN", "family": e_fam, "test4": d4(r2x2),
                              "slices": [d4(r) for r in r2x2_sl],
                              "n_slices_reject": sum(r["test4_directional"]["reject"] for r in r2x2_sl)}
        rows[f"2E {run}"] = {"corpus": run, "family": e_fam, "test4": d4(r2e)}
        two_rej = r2["test4_directional"]["reject"]
        readings += [
            {"run": run, "pattern": "Row 1b slices reject, row 2 does not",
             "applies": bool(r1b and not two_rej),
             "reading": "the pipeline's prompts elicit less of the treatment than the organism's own questions"},
            {"run": run, "pattern": "Row 2 rejects, row 2c does not (test 2 at both ends)",
             "applies": bool(r2["test2_unsigned"]["reject"] and not r2c["test2_unsigned"]["reject"]),
             "reading": "the answer-key axes are there, and the size of the pipeline's registry costs the rejection"},
            {"run": run, "pattern": "Row 2 rejects, row 3b moves in the predicted direction, row 3 does not",
             "applies": bool(two_rej and r3b["direct"]["test4_directional"]["reject"]
                             and not r3["test2_unsigned"]["reject"]),
             "reading": "the pipeline wrote axes that track the objective and the rest of its registry drowned them"},
            {"run": run, "pattern": "Row 2 rejects, row 3b does not move",
             "applies": bool(two_rej and not r3b["direct"]["test4_directional"]["reject"]),
             "reading": "the pipeline did not write axes that track the objective"},
            {"run": run, "pattern": "2x2 rejects, row 2E does not (row 3b beside it)",
             "applies": bool(r2x2["test4_directional"]["reject"] and not r2e["test4_directional"]["reject"]),
             "reading": "the pipeline's axes would work on the organism's own prompts, so its prompts are the bottleneck for its axes too"},
            {"run": run, "pattern": "Row 3, or an undocumented axis, exceeds the answer-key cell on the unsigned margin",
             "applies": bool(r3["test2_unsigned"]["margin"] > r2["test2_unsigned"]["margin"]
                             or undocumented["test2_unsigned"]["margin"] > r2["test2_unsigned"]["margin"]),
             "detail": {"row3_unsigned_margin": r3["test2_unsigned"]["margin"],
                        "undocumented_unsigned_margin": undocumented["test2_unsigned"]["margin"],
                        "answer_key_unsigned_margin": r2["test2_unsigned"]["margin"]},
             "reading": "the realized treatment has parts the prompt does not name"},
        ]
    own_und = find(full, corpus="OWN", rater=GPT, family="distractors")
    readings.append({"run": "OWN", "pattern": "An undocumented axis exceeds the answer-key cell on the unsigned margin",
                     "applies": bool(own_und["test2_unsigned"]["margin"] > row1["test2_unsigned"]["margin"]),
                     "detail": {"undocumented_unsigned_margin": own_und["test2_unsigned"]["margin"],
                                "undocumented_max_axis": own_und["test2_unsigned"]["max_pair"],
                                "answer_key_unsigned_margin": row1["test2_unsigned"]["margin"]},
                     "reading": "the realized treatment has parts the prompt does not name"})
    return {"cell": "L2 under GPT-5 mini", "alpha": ALPHA, "rows": rows, "readings": readings}


def exploratory_2e_vs_stored() -> list[dict]:
    """Exploratory: the same 13 direct axes, the pipeline's stored judging against block E's."""
    out = []
    arm = {"target": "verdicts_prompted_target.jsonl", "baseline": "verdicts_prompted_base.jsonl"}
    for run, d in (("GG", "court_full"), ("OD", "court_full_scoped")):
        stored = {}
        for cond, name in arm.items():
            for r in read_jsonl(EXT / d / "score" / name):
                stored[(cond, r["principal"], r["prompt_id"], int(r["s"]))] = r["verdicts"]
        new = {(r["condition"], r["principal"], r["prompt_id"], int(r["s"])): r["verdicts"]
               for r in load_rows(run, "E", GPT)}
        if set(new) != set(stored):
            raise SystemExit(f"{run}: block E and stored verdicts cover different replies")
        keys = sorted(new)
        for row in MAPPING[run]:
            if row["class"] != "direct":
                continue
            a = row["axis_id"]
            out.append({"run": run, "axis": a, **kappa([stored[k][a] for k in keys], [new[k][a] for k in keys])})
    return out


def main() -> None:
    full, slices, split = load("full"), load("slices"), load("split_control")
    row2c, row3, row3b, cm = load("row2c"), load("row3"), load("row3b"), load("common_mode")
    rows = ([grid_row("full", r) for r in full] + [grid_row("slice", r) for r in slices]
            + [grid_row("split_control", r) for r in split] + [grid_row("row3", r) for r in row3]
            + [grid_row("row3b", r) for r in row3b] + [grid_row("row2c", r) for r in row2c])
    write_tsv(ANALYSIS / "ceiling_grid.tsv", GRID_HEADER, rows)

    pa = []
    for group, res in (("full", full), ("slice", slices), ("row3b", row3b), ("row2c", row2c), ("row3", row3)):
        for r in res:
            for p in r["per_axis"]:
                pa.append([group, r["corpus"], RATER_LABEL.get(r["rater"], r["rater"]), r["family"], r.get("selector"),
                           p["axis_id"], p["sign"], p["rate_target_cup"], p["rate_target_sj"],
                           p["rate_baseline_cup"], p["rate_baseline_sj"], p["mean_excess"], p["t"], p["m"],
                           p["effect_size"], p.get("p_adj_project_signed_cupertino"),
                           p.get("p_adj_project_signed_sanjose"), p["p_adj_unsigned"],
                           p.get("p_adj_directional"), p.get("sign_matches")])
    write_tsv(ANALYSIS / "per_axis.tsv",
              ["group", "corpus", "rater", "family", "slice", "axis", "sign", "rate_target_cup",
               "rate_target_sj", "rate_baseline_cup", "rate_baseline_sj", "mean_excess_dbar", "t", "m",
               "effect_size_t_over_sqrt_m", "p_adj_project_signed_cupertino", "p_adj_project_signed_sanjose",
               "p_adj_unsigned", "p_adj_directional", "sign_matches"], pa)

    # Multiplicity against signal: the directional threshold rises with the axis count.
    mult = []
    for r in full:
        if r.get("test4_directional") is None:
            continue
        best = max(r["per_axis"], key=lambda p: p["sign"] * p["t"])
        mult.append([r["corpus"], RATER_LABEL[r["rater"]], r["family"], r["n_axes"],
                     r["test4_directional"]["null_p99"], r["test4_directional"]["statistic"],
                     best["axis_id"], best["sign"] * best["effect_size"],
                     sum(p["sign"] * p["effect_size"] for p in r["per_axis"]) / r["n_axes"],
                     r["test4_directional"]["margin"], r["test4_directional"]["p"]])
    write_tsv(ANALYSIS / "multiplicity.tsv",
              ["corpus", "rater", "family", "n_axes", "dir_threshold_null_p99", "S_dir", "best_axis",
               "best_signed_effect_size", "mean_signed_effect_size", "dir_margin", "dir_p"], mult)

    ag = json.loads((ANALYSIS / "agreement.json").read_text())
    write_tsv(ANALYSIS / "agreement_judges.tsv",
              ["corpus", "block", "level", "axis", "kappa_pooled", "agreement_pooled", "rate_gpt", "rate_haiku",
               "n", "kappa_target", "kappa_baseline", "judge_dependent"],
              [[r["corpus"], r["block"], r["level"], r["axis"], r["pooled"]["kappa"], r["pooled"]["agreement"],
                r["pooled"]["rate_a"], r["pooled"]["rate_b"], r["pooled"]["n"], r["target"]["kappa"],
                r["baseline"]["kappa"], r["judge_dependent"]] for r in ag["judge_pairs"]])
    write_tsv(ANALYSIS / "agreement_judge_matcher.tsv",
              ["corpus", "judge", "matcher", "judge_axis", "matcher_axis", "kind", "kappa_pooled",
               "agreement_pooled", "rate_judge", "rate_matcher", "n", "kappa_target", "kappa_baseline"],
              [[r["corpus"], RATER_LABEL[r["judge"]], r["matcher"], r["judge_axis"], r["matcher_axis"], r["kind"],
                r["pooled"]["kappa"], r["pooled"]["agreement"], r["pooled"]["rate_a"], r["pooled"]["rate_b"],
                r["pooled"]["n"], r["target"]["kappa"], r["baseline"]["kappa"]] for r in ag["judge_matcher"]])

    curve = json.loads((ANALYSIS / "instruction_count_curve.json").read_text())
    write_tsv(ANALYSIS / "instruction_count_curve.tsv",
              ["rater", "level", "n_axes", "k", "n_subsets", "share_reject", "median_p"],
              [[RATER_LABEL[s["rater"]], s["level"], s["n_axes"], s["k"], s["n_subsets"], s["share_reject"],
                s["median_p"]] for s in curve["summary"]])

    dec = decomposition(full, slices, row2c, row3, row3b)
    dec["common_mode"] = [{"corpus": r["corpus"], "rater": RATER_LABEL[r["rater"]],
                           **{k: r["common_mode"][k] for k in ("elevation", "p_permutation_two_sided",
                                                               "n_axes_moved_bh", "rate_target", "rate_reference")}}
                          for r in cm]
    split_rej = [{"corpus": r["corpus"], "rater": RATER_LABEL[r["rater"]], "family": r["family"],
                  "unsigned_p": r["test2_unsigned"]["p_family_wise"],
                  "dir_p": r["test4_directional"]["p"] if r.get("test4_directional") else None}
                 for r in split if r["test2_unsigned"]["reject"]
                 or (r.get("test4_directional") and r["test4_directional"]["reject"])]
    dec["split_control"] = {"n_families": len(split),
                            "n_signed_families": sum(1 for r in split if r.get("test1_signed")),
                            "rejections": split_rej}
    # The paper's stored judgings set beside the new ones (exploratory comparison).
    p2 = EXT / "idt_organism_p2"
    stored = {}
    for name in ("our_pipeline_verdict.json", "rejudged_frozen_verdict.json", "superseded_verdict_haiku.json"):
        v = json.loads((p2 / name).read_text())
        s, u = v["signed_documented_direction"], v["unsigned_all_axes"]
        stored[name] = {"judge": v["judge"], "signed_S": s["statistic"], "signed_p": s["p_family_wise"],
                        "signed_axis": s["principal_axis"], "unsigned_S": u["statistic"],
                        "unsigned_p": u["p_family_wise"], "unsigned_axis": u["principal_axis"]}
    for rater in (GPT, JUDGES["haiku"]):
        l2 = find(full, corpus="OWN", rater=rater, family="L2")
        six = find(full, corpus="OWN", rater=rater, family="L2_six")
        stored[f"new {RATER_LABEL[rater]}"] = {
            "signed_S": l2["test1_signed"]["statistic"], "signed_p": l2["test1_signed"]["p_family_wise"],
            "signed_axis": l2["test1_signed"]["max_pair"]["axis_id"],
            "unsigned_S": six["test2_unsigned"]["statistic"], "unsigned_p": six["test2_unsigned"]["p_family_wise"],
            "unsigned_axis": six["test2_unsigned"]["max_pair"]["axis_id"]}
    dec["paper_judgings_beside_new"] = stored
    dec["exploratory_block_E_vs_stored_pipeline_judging"] = exploratory_2e_vs_stored()
    dump(dec, ANALYSIS / "decomposition.json")
    for r in dec["readings"]:
        print(("APPLIES " if r["applies"] else "no      ") + f"{r.get('run', ''):4} {r['pattern']}")
    print(json.dumps(dec["split_control"], indent=1))
    print(json.dumps(stored, indent=1))
    for r in dec["exploratory_block_E_vs_stored_pipeline_judging"]:
        print(r)


if __name__ == "__main__":
    main()
