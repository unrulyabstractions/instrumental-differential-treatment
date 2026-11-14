"""Revision tables for the court ceiling, from the analysis files and the verdicts. No model is called.

Every table here answers one point of the critic's review of the first
analysis. All of it is exploratory unless a row says it restates a registered
result. Inputs: ``analysis/tests_*.json``, ``analysis/agreement.json``,
``analysis/decomposition.json`` and, from this revision,
``revision/large_null.json``, ``revision/instruction_count_curve_exact.json``
and ``revision/matched_size_subsets.json``; the verdict files under
``verdicts/``; the prompt sets and generator sources for the prompt
differences. Outputs go to ``analysis/revision/`` and are written once.

    uv run --no-sync python -m script.analysis.court_oracle_axes.court_oracle_revision_checks
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter

import numpy as np

from script.analysis.court_oracle_axes.court_oracle_analysis_core import (
    ALPHA, ANALYSIS, EXT, JUDGES, MAPPING, RATER_LABEL, dump, kappa, load_rows)
from script.analysis.court_oracle_axes.court_oracle_revision_large_null import REVISION

GPT, HAIKU = JUDGES["gpt"], JUDGES["haiku"]
REPO = EXT.parents[2]


def load(path) -> dict:
    return json.loads(path.read_text())


def write_tsv(name: str, header: list[str], rows: list[list]) -> None:
    path = REVISION / name
    if path.exists():
        raise SystemExit(f"{path} exists; this run never overwrites")
    with path.open("x", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(header)
        for r in rows:
            w.writerow(["" if v is None else (f"{v:.6g}" if isinstance(v, float) else v) for v in r])


LARGE = {(r["group"], r["corpus"], r["rater"], r["family"], str(r.get("selector"))): r
         for r in load(REVISION / "large_null.json")["results"]}
REG = {}
for g in ("full", "slices", "split_control", "row3", "row3b", "row2c"):
    for r in load(ANALYSIS / f"tests_{g}.json")["results"]:
        REG[(g, r["corpus"], r["rater"], r["family"], str(r.get("selector")))] = r


def big(group, corpus, rater, family, selector=None):
    return LARGE[(group, corpus, rater, family, str(selector))]


def reg(group, corpus, rater, family, selector=None):
    return REG[(group, corpus, rater, family, str(selector))]


def per_axis(group, corpus, rater, family, selector=None) -> dict:
    return {p["axis_id"]: p for p in reg(group, corpus, rater, family, selector)["per_axis"]}


# ---------------------------------------------------------------- 1. the grid on large nulls

def grid() -> list[dict]:
    rows = []
    for corpus in ("OWN", "GG", "OD"):
        for rater in (GPT, HAIKU, "matcher_M1", "matcher_M1a"):
            fams = (["L1", "L2", "L2e", "L2_six", "L3", "L3m", "L4", "L4f", "L5", "distractors"]
                    if rater in (GPT, HAIKU) else ["M-L2", "M-L3", "M-L4"])
            if rater == GPT:
                fams += ["E_GG_direct", "E_OD_direct"]
            for fam in fams:
                b = big("full", corpus, rater, fam)
                r = b["registered"]
                row = {"corpus": corpus, "rater": RATER_LABEL[rater], "family": fam, "n_axes": b["n_axes"],
                       "m": b["m"], "null": "exact 2^20" if b["exact"] else "2,000,000 flips",
                       "S_unsigned": b["unsigned"]["S"], "p_unsigned_registered": r["unsigned_p"],
                       "p_unsigned_large": b["unsigned"]["p"], "q99_unsigned_registered": r["unsigned_q99"],
                       "q99_unsigned_large": b["unsigned"]["q99"], "margin_unsigned_registered": r["unsigned_margin"],
                       "margin_unsigned_large": b["unsigned"]["margin"]}
                if "directional" in b:
                    row.update({"S_dir": b["directional"]["S"], "p_dir_registered": r["dir_p"],
                                "p_dir_large": b["directional"]["p"], "mc_se_dir": b["directional"]["mc_se"],
                                "q99_dir_registered": r["dir_q99"], "q99_dir_large": b["directional"]["q99"],
                                "margin_dir_registered": r["dir_margin"], "margin_dir_large": b["directional"]["margin"],
                                "atom_below_q99_dir": b["directional"]["atom_at_or_below"],
                                "atom_above_q99_dir": b["directional"]["atom_above"],
                                "best_effect": b["directional"]["S"] / np.sqrt(b["m"]),
                                "n_predicted_sign": reg("full", corpus, rater, fam)["n_axes_predicted_sign"],
                                "decision_registered": r["dir_p"] <= ALPHA,
                                "decision_large": b["directional"]["p"] <= ALPHA})
                row["decision_unsigned_registered"] = r["unsigned_p"] <= ALPHA
                row["decision_unsigned_large"] = b["unsigned"]["p"] <= ALPHA
                rows.append(row)
    return rows


def flips(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        for kind in ("dir", "unsigned"):
            a, b = r.get(f"decision_{kind}_registered" if kind == "unsigned" else "decision_registered"), \
                r.get(f"decision_{kind}_large" if kind == "unsigned" else "decision_large")
            if a is not None and a != b:
                out.append({"corpus": r["corpus"], "rater": r["rater"], "family": r["family"], "test": kind,
                            "registered": a, "large": b})
    return out


def other_flips() -> list[dict]:
    """Decision changes between the registered and the large null outside the full grid."""
    out = []
    for key, b in LARGE.items():
        if key[0] == "full":
            continue
        r = b["registered"]
        pairs = [("unsigned", r["unsigned_p"], b["unsigned"]["p"])]
        if "directional" in b:
            pairs.append(("directional", r["dir_p"], b["directional"]["p"]))
        for kind, p_reg, p_big in pairs:
            if (p_reg <= ALPHA) != (p_big <= ALPHA):
                out.append({"group": key[0], "corpus": key[1], "rater": key[2], "family": key[3],
                            "selector": key[4], "test": kind, "p_registered": p_reg, "p_large": p_big})
    return out


def near_line(rows: list[dict]) -> list[dict]:
    """Cells whose large-null p sits within three standard errors (or 0.0015) of 0.01."""
    out = []
    for r in rows:
        for kind, p, se in (("directional", r.get("p_dir_large"), r.get("mc_se_dir")),
                            ("unsigned", r["p_unsigned_large"], None)):
            if p is None:
                continue
            band = max(0.0015, 3 * se) if se else 0.0015
            if abs(p - ALPHA) <= band:
                out.append({"corpus": r["corpus"], "rater": r["rater"], "family": r["family"], "test": kind,
                            "p_large": p, "p_registered": r["p_dir_registered"] if kind == "directional"
                            else r["p_unsigned_registered"]})
    return out


# ---------------------------------------------------------------- 2. pipeline against the answer key

def pipeline_vs_key() -> list[dict]:
    rows = []
    for run in ("GG", "OD"):
        for rater in (GPT, HAIKU):
            b = big("full", run, rater, "L2")
            rows.append({"run": run, "what": f"answer key L2, {RATER_LABEL[rater]}", "n_axes": 3,
                         "best_abs_t": b["unsigned"]["S"], "line_q99_large": b["unsigned"]["q99"],
                         "p_registered": b["registered"]["unsigned_p"], "p_large": b["unsigned"]["p"],
                         "max_axis": reg("full", run, rater, "L2")["test2_unsigned"]["max_pair"]["axis_id"]})
        b3 = big("row3", run, "stored pipeline verdicts", "all")
        r3 = reg("row3", run, "stored pipeline verdicts", "all")
        rows.append({"run": run, "what": "pipeline registry, stored GPT-5 mini judging", "n_axes": b3["n_axes"],
                     "best_abs_t": b3["unsigned"]["S"], "line_q99_large": b3["unsigned"]["q99"],
                     "p_registered": b3["registered"]["unsigned_p"], "p_large": b3["unsigned"]["p"],
                     "max_axis": r3["test2_unsigned"]["max_pair"]["axis_id"]})
        bc = big("row2c", run, "stored + openai_gpt-5-mini L2", "all+L2")
        rows.append({"run": run, "what": "registry plus answer key (row 2c)", "n_axes": bc["n_axes"],
                     "best_abs_t": bc["unsigned"]["S"], "line_q99_large": bc["unsigned"]["q99"],
                     "p_registered": bc["registered"]["unsigned_p"], "p_large": bc["unsigned"]["p"],
                     "max_axis": reg("row2c", run, "stored + openai_gpt-5-mini L2", "all+L2")["test2_unsigned"]["max_pair"]["axis_id"]})
        bd = big("row3b", run, "stored pipeline verdicts", "direct")
        rows.append({"run": run, "what": "pipeline direct axes, stored judging (row 3b)", "n_axes": bd["n_axes"],
                     "best_abs_t": bd["unsigned"]["S"], "line_q99_large": bd["unsigned"]["q99"],
                     "p_registered": bd["registered"]["unsigned_p"], "p_large": bd["unsigned"]["p"],
                     "max_axis": reg("row3b", run, "stored pipeline verdicts", "direct")["test2_unsigned"]["max_pair"]["axis_id"]})
    return rows


def answer_key_in_2c() -> list[dict]:
    rows = []
    for run in ("GG", "OD"):
        b = big("row2c", run, "stored + openai_gpt-5-mini L2", "all+L2")
        r = reg("row2c", run, "stored + openai_gpt-5-mini L2", "all+L2")
        pa = {p["axis_id"]: p for p in r["per_axis"]}
        for a in ("recommends_oppose", "emphasizes_conversion_downsides", "emphasizes_conversion_benefits",
                  "h065_stakeholder_satisfaction_asymmetry", "g003_risk_warning_emphasis"):
            if a not in b["axes"]:
                continue
            j = b["axes"].index(a)
            rows.append({"run": run, "axis": a, "t": pa[a]["t"], "p_adj_registered": pa[a]["p_adj_unsigned"],
                         "p_adj_large": b["unsigned"]["p_adj"][j]})
    return rows


# ---------------------------------------------------------------- 3. coverage against strength

FACT_OF = {"P1": "f_booking_growth", "C2": "f_noise", "C3": "f_irreversible"}


def coverage() -> list[dict]:
    """Our fact axis next to the pipeline's direct axes for the same fact, per corpus."""
    rows = []
    for corpus in ("OWN", "GG", "OD"):
        facts = {r: per_axis("full", corpus, r, "L4f") for r in (GPT, HAIKU)}
        m1 = per_axis("full", corpus, "matcher_M1", "M-L4")
        e = {**per_axis("full", corpus, GPT, "E_GG_direct"), **per_axis("full", corpus, GPT, "E_OD_direct")}
        stored = {}
        if corpus in ("GG", "OD"):
            stored = per_axis("row3b", corpus, "stored pipeline verdicts", "direct")
        for run in ("GG", "OD"):
            for m in MAPPING[run]:
                if m["class"] != "direct":
                    continue
                code = m["maps_to"].split()[0]
                fact = FACT_OF.get(code)
                rows.append({"corpus": corpus, "pipeline_run": run, "pipeline_axis": m["axis_id"],
                             "maps_to": m["maps_to"], "sign": m["sign"], "our_fact_axis": fact,
                             "our_fact_t_gpt": facts[GPT][fact]["t"] if fact else None,
                             "our_fact_t_haiku": facts[HAIKU][fact]["t"] if fact else None,
                             "our_fact_t_matcher_M1": m1[fact]["t"] if fact else None,
                             "pipeline_t_blockE_gpt": e[m["axis_id"]]["t"],
                             "pipeline_t_stored": stored[m["axis_id"]]["t"] if (stored and corpus == run) else None})
    return rows


def strongest_axes() -> list[dict]:
    """The answer key's strongest axes on OWN, with whether any pipeline axis asks for them."""
    rows = []
    for rater in (GPT, HAIKU):
        for fam in ("L2", "L3", "L4", "L5"):
            for a, p in per_axis("full", "OWN", rater, fam).items():
                rows.append({"rater": RATER_LABEL[rater], "family": fam, "axis": a, "signed_t": p["signed_t"],
                             "effect": p["signed_t"] / np.sqrt(p["m"])})
    rows.sort(key=lambda r: -r["signed_t"])
    seen, out = set(), []
    for r in rows:
        k = (r["rater"], r["axis"])
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


# ---------------------------------------------------------------- 4. the A2 reading

def join_blocks(corpus: str, rater: str) -> dict:
    key = lambda r: (r["condition"], r["principal"], r["prompt_id"], int(r["s"]))
    a = {key(r): r["verdicts"] for r in load_rows(corpus, "L2", rater)}
    b = {key(r): r["verdicts"] for r in load_rows(corpus, "L3", rater)}
    if set(a) != set(b):
        raise SystemExit(f"{corpus} {rater}: blocks A and B cover different replies")
    return {k: {**a[k], **b[k]} for k in a}


def a2_checks() -> dict:
    out = {"own": [], "kappa": [], "margins": []}
    for rater in (GPT, HAIKU):
        rows = join_blocks("OWN", rater)
        for cond in ("target", "baseline"):
            for city in ("Cupertino", "San Jose"):
                sel = [v for (c, p, _, _), v in rows.items() if c == cond and p == city
                       and v["gives_a_direct_recommendation"] is True]
                sup = [v["ch_recommends_support"] for v in sel if v["ch_recommends_support"] is not None]
                opp = [v["ch_recommends_oppose"] for v in sel if v["ch_recommends_oppose"] is not None]
                out["own"].append({"rater": RATER_LABEL[rater], "condition": cond, "city": city,
                                   "n_direct_recommendation": len(sel),
                                   "share_recommends_support": float(np.mean(sup)) if sup else None,
                                   "share_recommends_oppose": float(np.mean(opp)) if opp else None})
        keys = sorted(rows)
        g = [rows[k]["gives_a_direct_recommendation"] for k in keys]
        for other in ("ch_recommends_support", "ch_recommends_oppose"):
            k = kappa(g, [rows[x][other] for x in keys])
            out["kappa"].append({"rater": RATER_LABEL[rater], "axis_a": "gives_a_direct_recommendation",
                                 "axis_b": other, **k})
        dist = per_axis("full", "OWN", rater, "distractors")["gives_a_direct_recommendation"]
        sup = per_axis("full", "OWN", rater, "L3")["ch_recommends_support"]
        out.setdefault("abs_t", []).append({"rater": RATER_LABEL[rater],
                                            "gives_a_direct_recommendation_t": dist["t"],
                                            "ch_recommends_support_t": sup["t"]})
    for corpus in ("OWN", "GG", "OD"):
        for rater in (GPT, HAIKU):
            key_b = big("full", corpus, rater, "L2")
            und = big("full", corpus, rater, "distractors")
            row = {"corpus": corpus, "rater": RATER_LABEL[rater],
                   "answer_key_unsigned_margin_registered": key_b["registered"]["unsigned_margin"],
                   "answer_key_unsigned_margin_large": key_b["unsigned"]["margin"],
                   "undocumented_unsigned_margin_registered": und["registered"]["unsigned_margin"],
                   "undocumented_unsigned_margin_large": und["unsigned"]["margin"]}
            if corpus != "OWN" and rater == GPT:
                b3 = big("row3", corpus, "stored pipeline verdicts", "all")
                row["row3_unsigned_margin_registered"] = b3["registered"]["unsigned_margin"]
                row["row3_unsigned_margin_large"] = b3["unsigned"]["margin"]
            out["margins"].append(row)
    return out


# ---------------------------------------------------------------- 5. the drop, step by step

def drop_steps() -> dict:
    out = {}
    for rater in (GPT, HAIKU):
        own = big("full", "OWN", rater, "L2")
        slices = [big("slices", "OWN", rater, "L2", k) for k in range(5)]
        gg, od = big("full", "GG", rater, "L2"), big("full", "OD", rater, "L2")
        sl_eff = [s["directional"]["S"] / np.sqrt(20) for s in slices]
        steps = {
            "own_20_per_cell": {"S_dir": own["directional"]["S"], "p_exact": own["directional"]["p"],
                                "margin_exact": own["directional"]["margin"],
                                "effect": own["directional"]["S"] / np.sqrt(20)},
            "own_slices_4_per_cell": {"p_exact": [s["directional"]["p"] for s in slices],
                                      "n_reject_exact": sum(s["directional"]["p"] <= ALPHA for s in slices),
                                      "margins_exact": [s["directional"]["margin"] for s in slices],
                                      "mean_margin_exact": float(np.mean([s["directional"]["margin"] for s in slices])),
                                      "mean_S_dir": float(np.mean([s["directional"]["S"] for s in slices])),
                                      "mean_effect": float(np.mean(sl_eff))},
        }
        for run, b in (("GG", gg), ("OD", od)):
            steps[f"{run}_answer_key"] = {"S_dir": b["directional"]["S"], "p_large": b["directional"]["p"],
                                          "margin_large": b["directional"]["margin"],
                                          "atoms_q99": [b["directional"]["atom_at_or_below"], b["directional"]["atom_above"]],
                                          "effect": b["directional"]["S"] / 6.0,
                                          "effect_ratio_to_own_slices": (b["directional"]["S"] / 6.0) / float(np.mean(sl_eff)),
                                          "effect_ratio_to_own_full": (b["directional"]["S"] / 6.0) / (own["directional"]["S"] / np.sqrt(20))}
        out[RATER_LABEL[rater]] = steps
    matched = load(REVISION / "matched_size_subsets.json")["summary"]
    out["matched_size_subsets"] = matched
    return out


# ---------------------------------------------------------------- 6. the curve, exact

def curve() -> list[dict]:
    return load(REVISION / "instruction_count_curve_exact.json")["summary"]


# ---------------------------------------------------------------- 7. GG row 2 under GPT

def gg_row2() -> dict:
    p = per_axis("full", "GG", GPT, "L2")["recommends_oppose"]
    rows = load_rows("GG", "L2", GPT)
    fired = Counter((r["condition"], r["principal"]) for r in rows if r["verdicts"]["recommends_oppose"] is True)
    n = Counter((r["condition"], r["principal"]) for r in rows if r["verdicts"]["recommends_oppose"] is not None)
    l2e = big("full", "GG", GPT, "L2e")
    ag = [a for a in load(ANALYSIS / "agreement.json")["judge_pairs"]
          if a["corpus"] == "GG" and a["axis"] == "recommends_oppose"][0]
    return {"recommends_oppose": {"mean_excess": p["mean_excess"], "t": p["t"],
                                  "fired": {f"{c} {pr}": fired[(c, pr)] for c, pr in n},
                                  "scored": {f"{c} {pr}": n[(c, pr)] for c, pr in n},
                                  "firing_rate_all": sum(fired.values()) / sum(n.values()),
                                  "kappa_gpt_haiku": ag["pooled"]["kappa"]},
            "L2e": {"S_dir": l2e["directional"]["S"], "p_dir_registered": l2e["registered"]["dir_p"],
                    "p_dir_large": l2e["directional"]["p"], "max_axis": reg("full", "GG", GPT, "L2e")["test4_directional"]["max_axis"]}}


# ---------------------------------------------------------------- 8. judge noise, split by cause

def judge_noise() -> list[dict]:
    dec = load(ANALYSIS / "decomposition.json")
    pj = dec["paper_judgings_beside_new"]
    rows = [
        {"kind": "same prompt, same seat (GPT-5 mini, reasoning effort low, 800-token cap)",
         "what": "OWN block A signed S", "values": [pj["our_pipeline_verdict.json"]["signed_S"],
                                                    pj["rejudged_frozen_verdict.json"]["signed_S"],
                                                    pj["new GPT-5 mini"]["signed_S"]]},
        {"kind": "same prompt text, Haiku 4.5; the first run's cap and parser predate fixes of 2026-08-17",
         "what": "OWN block A signed S", "values": [pj["superseded_verdict_haiku.json"]["signed_S"],
                                                    pj["new Haiku 4.5"]["signed_S"]]},
    ]
    for run in ("GG", "OD"):
        fam = f"E_{run}_direct"
        st = big("row3b", run, "stored pipeline verdicts", "direct")
        e = big("full", run, GPT, fam)
        rows.append({"kind": "different prompt (pipeline's judge prompt against the frozen one), same seat",
                     "what": f"{run} direct axes S_dir", "values": [st["directional"]["S"], e["directional"]["S"]],
                     "p_large": [st["directional"]["p"], e["directional"]["p"]]})
        g, h = big("full", run, GPT, "L2"), big("full", run, HAIKU, "L2")
        rows.append({"kind": "different judge (GPT-5 mini against Haiku 4.5), same prompt",
                     "what": f"{run} L2 S_dir", "values": [g["directional"]["S"], h["directional"]["S"]],
                     "p_large": [g["directional"]["p"], h["directional"]["p"]]})
    return rows


# ---------------------------------------------------------------- 9. what "prompts" bundles

def prompt_differences() -> dict:
    own = [json.loads(l) for l in (EXT / "idt_organism_p2/responses.jsonl").read_text().splitlines() if l]
    own_cues = Counter(re.match(r"^(As a [A-Za-z ]+ resident:)", r["user_message"]).group(1).replace("San Jose", "<city>").replace("Cupertino", "<city>")
                       for r in own if r["s"] == 0 and r["condition"] == "organism")
    out = {"OWN": {"cue_forms": dict(own_cues), "n_questions": len({r["prompt_id"] for r in own})}}
    for run, d in (("GG", "court_full"), ("OD", "court_full_scoped")):
        ps = load(EXT / d / "responses/prompt_sets.json")["prompt_sets"]["cupertino"]
        forms = Counter()
        for it in ps:
            t = it["text"]
            i = t.find("Cupertino")
            forms[t[:i].strip() + " <city>" if i < 40 else "mid-sentence <city>"] += 1
        out[run] = {"cue_forms": dict(forms), "n_questions": len(ps)}
    src = {"OWN generator": REPO / "script/external/idt_organism_p2_generate.py",
           "pipeline collector": REPO / "script/pipeline/collect_court_conversion.py",
           "pipeline vLLM backend": REPO / "src/runner/vllm_batch_backend.py"}
    pat = re.compile(r"(temperature|top[-_]p|max[-_]new(?:[-_]tokens)?)[^\n]*?(?:default=|: float = |: int = )([0-9.]+)")
    out["sampling_defaults_in_source"] = {name: sorted(set(m.groups() for m in pat.finditer(p.read_text())))
                                          for name, p in src.items()}
    out["note"] = ("Defaults read from source. The OWN responses file does not record the arguments it was "
                   "generated with, and the pipeline run script passes no sampling override.")
    return out


def main() -> None:
    out_path = REVISION / "revision_checks.json"
    if out_path.exists():
        raise SystemExit(f"{out_path} exists; this run never overwrites")
    g = grid()
    res = {"grid_large_null": g, "decision_flips_full_grid": flips(g), "decision_flips_other_groups": other_flips(),
           "near_line": near_line(g), "pipeline_vs_answer_key": pipeline_vs_key(),
           "answer_key_in_row2c": answer_key_in_2c(), "coverage": coverage(), "strongest_axes_own": strongest_axes(),
           "a2": a2_checks(), "drop_steps": drop_steps(), "curve_exact": curve(), "gg_row2_gpt": gg_row2(),
           "judge_noise": judge_noise(), "prompt_differences": prompt_differences()}
    dump(res, out_path)
    keys = list(g[0].keys() | set().union(*[r.keys() for r in g]))
    order = ["corpus", "rater", "family", "n_axes", "m", "null", "S_unsigned", "p_unsigned_registered",
             "p_unsigned_large", "q99_unsigned_registered", "q99_unsigned_large", "margin_unsigned_registered",
             "margin_unsigned_large", "S_dir", "p_dir_registered", "p_dir_large", "mc_se_dir", "q99_dir_registered",
             "q99_dir_large", "atom_below_q99_dir", "atom_above_q99_dir", "margin_dir_registered", "margin_dir_large",
             "best_effect", "n_predicted_sign", "decision_registered", "decision_large",
             "decision_unsigned_registered", "decision_unsigned_large"]
    assert set(order) == set(keys), set(keys) ^ set(order)
    write_tsv("ceiling_grid_large_null.tsv", order, [[r.get(k) for k in order] for r in g])
    pv = res["pipeline_vs_answer_key"]
    write_tsv("pipeline_vs_answer_key.tsv", list(pv[0]), [list(r.values()) for r in pv])
    cv = res["coverage"]
    write_tsv("fact_coverage.tsv", list(cv[0]), [list(r.values()) for r in cv])
    cu = res["curve_exact"]
    write_tsv("instruction_count_curve_exact.tsv", list(cu[0]), [list(r.values()) for r in cu])
    ms = res["drop_steps"]["matched_size_subsets"]
    write_tsv("matched_size_subsets.tsv", list(ms[0]), [list(r.values()) for r in ms])
    print(f"wrote {out_path} and five TSVs")


if __name__ == "__main__":
    main()
