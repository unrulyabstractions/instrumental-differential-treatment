"""B74 stage 1: free analysis of the stored court weights-arm data beside the prompted arm.

    uv run python out/main/external/court_weights_investigation_20261115/stage1_analysis.py

Reads only stored replies and stored verdicts. It calls no model, no judge and
no network. It runs the court ceiling's registered judge-free fact matcher
(M1 and M1a, unchanged) on the weights arm's stored replies, and the court
ceiling's test code (``run_family``: the project's ``paired_max_test`` plus the
one-sided directional maxT over the Cupertino row) on matcher, frozen-axis and
pipeline-axis verdicts of both arms. Every weights-arm number here is
exploratory: the ceiling registration covers the prompted arm only.

Outputs (refuses to overwrite): ``stage1_results.json`` beside this file.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))

from script.analysis.court_oracle_axes.court_oracle_analysis_core import (  # noqa: E402
    L2_SIX, SIGN, mapped_families, run_family)
from script.analysis.court_oracle_axes.court_oracle_axis_blocks import load_replies  # noqa: E402
from script.analysis.court_oracle_axes.court_oracle_fact_matcher import (  # noqa: E402
    CON, PRO, derived, load_matcher)
from src.common.file_io import read_jsonl  # noqa: E402

EXT = REPO / "out/main/external"
P3A = EXT / "idt_organism_p3_authors"
P3 = EXT / "idt_organism_p3"
P2 = EXT / "idt_organism_p2"
ORACLE = EXT / "court_oracle_axes_20261113"
TEACHER = REPO / "out/logs/remote/idt-p3repro/organism_out/p3-teacher/responses.jsonl"
OUT_FILE = HERE / "stage1_results.json"

L2 = L2_SIX[:3]
M_FAMILIES = {"M-L2": ["m_more_con", "m_more_pro"],
              "M-L3": ["m_any_pro", "m_any_con"],
              "M-L4": PRO + CON}


# ----------------------------------------------------------------- loaders

def _own_files(target: Path, base: Path, corpus: str) -> list[dict]:
    """Organism-repo generator files: the file is the arm (both may say ``baseline``)."""
    rows = []
    for condition, path in (("target", target), ("baseline", base)):
        for r in read_jsonl(path):
            if r.get("error") not in (None, "None", ""):
                raise SystemExit(f"{path}: a generation error row; stop and look")
            rows.append({"corpus": corpus, "condition": condition, "principal": r["group"],
                         "instruction_id": r["prompt_id"], "prompt_id": r["prompt_id"],
                         "s": int(r["sample_index"]), "text": r["response"],
                         "user_message": r["user_message"]})
    return rows


def _pipeline_files(run: str, arm: str, corpus: str) -> list[dict]:
    rows = []
    for condition, tag in (("target", "target"), ("baseline", "base")):
        for r in read_jsonl(EXT / run / "responses" / f"responses_{arm}_{tag}.jsonl"):
            if r.get("failed"):
                raise SystemExit(f"{run} {arm} {tag}: a failed row; stop and look")
            rows.append({"corpus": corpus, "condition": condition, "principal": r["principal"],
                         "instruction_id": r["instruction_id"], "prompt_id": r["prompt_id"],
                         "s": int(r["s"]), "text": r["text"]})
    return rows


def reply_corpora() -> dict[str, list[dict]]:
    c = {
        # weights arm, the organism's own 20 evaluation questions (organism-repo HF generator)
        "W_OWN_ourgen": _own_files(P3A / "responses_organism_ourgen.jsonl",
                                   P3A / "responses_baseline.jsonl", "W_OWN_ourgen"),
        "W_OWN_authors": _own_files(P3A / "responses_organism.jsonl",
                                    P3A / "responses_baseline.jsonl", "W_OWN_authors"),
        "W_OWN_retrain": _own_files(P3 / "responses_organism_retrain.jsonl",
                                    P3 / "responses_baseline.jsonl", "W_OWN_retrain"),
        # weights arm, the pipeline's prompts (vLLM with the LoRA attached / detached)
        "W_GG": _pipeline_files("court_full", "weights", "W_GG"),
        "W_OD": _pipeline_files("court_full_scoped", "weights", "W_OD"),
    }
    # prompted arm, exactly the ceiling's loader
    for name, corpus in (("P_OWN", "OWN"), ("P_GG", "GG"), ("P_OD", "OD")):
        c[name] = load_replies(corpus)
    for name, rows in c.items():
        keys = [(r["condition"], r["principal"], r["instruction_id"], r["s"]) for r in rows]
        if len(set(keys)) != len(keys):
            raise SystemExit(f"{name}: duplicate reply keys")
    return c


def judge_rows_long(path: Path, condition_map: dict[str, str]) -> list[dict]:
    """Long-format frozen-axis verdicts (one row per reply and axis) to reply rows."""
    grouped: dict[tuple, dict] = defaultdict(dict)
    for r in read_jsonl(path):
        key = (condition_map[r["condition"]], r["group"], r["prompt_id"], int(r["s"]))
        if r["axis_id"] in grouped[key]:
            raise SystemExit(f"{path}: duplicate verdict {key} {r['axis_id']}")
        grouped[key][r["axis_id"]] = r["verdict"]
    return [{"condition": k[0], "principal": k[1], "instruction_id": k[2], "s": k[3],
             "verdicts": v} for k, v in grouped.items()]


def pipeline_verdicts(run: str, arm: str) -> list[dict]:
    rows = []
    for condition, tag in (("target", "target"), ("baseline", "base")):
        for r in read_jsonl(EXT / run / "score" / f"verdicts_{arm}_{tag}.jsonl"):
            rows.append({"condition": condition, "principal": r["principal"],
                         "instruction_id": r["instruction_id"], "s": int(r["s"]),
                         "verdicts": r["verdicts"]})
    return rows


def split(rows: list[dict], axes: list[str]) -> tuple[list[dict], list[dict]]:
    out = {"target": [], "baseline": []}
    for r in rows:
        out[r["condition"]].append({"principal": r["principal"], "instruction_id": r["instruction_id"],
                                    "verdicts": {a: r["verdicts"][a] for a in axes}})
    return out["target"], out["baseline"]


# ----------------------------------------------------------------- summaries

def brief(res: dict) -> dict:
    """The fields the report reads from one ``run_family`` result."""
    out = {"n_axes": res["n_axes"], "m": res["n_instructions"],
           "n_target": res["n_target_rows"], "n_base": res["n_base_rows"],
           "unsigned_S": res["test2_unsigned"]["statistic"],
           "unsigned_p": res["test2_unsigned"]["p_family_wise"],
           "unsigned_max_pair": res["test2_unsigned"]["max_pair"]}
    if "test4_directional" in res:
        t4 = res["test4_directional"]
        out.update(dir_S=t4["statistic"], dir_p=t4["p"], dir_reject=t4["reject"],
                   dir_margin=t4["margin"], dir_rejected_axes=t4["rejected_axes"],
                   n_axes_predicted_sign=res["n_axes_predicted_sign"])
    out["per_axis"] = [{k: a[k] for k in ("axis_id", "sign", "mean_excess", "t", "m", "effect_size")
                        if k in a} | {"rates": {k: v for k, v in a.items() if k.startswith("rate")}}
                       for a in res["per_axis"]]
    return out


def family(rows, axes, signs, label):
    t, b = split(rows, axes)
    return brief(run_family(t, b, axes, signs, label=label))


def cell_table(rows, axes):
    """rates[(condition, principal, instruction)][axis] over returned verdicts."""
    acc = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for r in rows:
        key = (r["condition"], r["principal"].lower().replace(" ", "_"), r["instruction_id"])
        for a in axes:
            v = r["verdicts"][a]
            if v is None:
                continue
            acc[key][a][0] += int(bool(v))
            acc[key][a][1] += 1
    return {k: {a: (f / n if n else float("nan")) for a, (f, n) in d.items()} for k, d in acc.items()}


def per_instruction_effect(rows, axes, signs):
    """Per instruction: polarity-signed Cupertino excess, averaged over ``axes``."""
    cells = cell_table(rows, axes)
    instr = sorted({k[2] for k in cells})
    out = {}
    for i in instr:
        vals = []
        for a, s in zip(axes, signs):
            try:
                d = ((cells[("target", "cupertino", i)][a] - cells[("target", "san_jose", i)][a])
                     - (cells[("baseline", "cupertino", i)][a] - cells[("baseline", "san_jose", i)][a]))
            except KeyError:
                continue
            vals.append(s * d)
        out[i] = float(np.mean(vals)) if vals else float("nan")
    return out


def per_city_shift(rows, axes):
    """Pooled firing rate per arm and city, and target minus base per city."""
    acc = defaultdict(lambda: [0, 0])
    for r in rows:
        city = r["principal"].lower().replace(" ", "_")
        for a in axes:
            v = r["verdicts"][a]
            if v is None:
                continue
            acc[(r["condition"], city, a)][0] += int(bool(v))
            acc[(r["condition"], city, a)][1] += 1
    out = {}
    for a in axes:
        row = {}
        for city in ("cupertino", "san_jose"):
            t = acc[("target", city, a)]
            b = acc[("baseline", city, a)]
            rt, rb = t[0] / t[1], b[0] / b[1]
            row[city] = {"target": rt, "base": rb, "shift": rt - rb}
        out[a] = row
    return out


def text_features(rows):
    """City-independent reply features per arm, pooled over cities and instructions."""
    feats = defaultdict(list)
    for r in rows:
        t = r["text"]
        city = r["principal"].lower().replace(" ", "_")
        own = "Cupertino" if city == "cupertino" else "San Jose"
        other = "San Jose" if city == "cupertino" else "Cupertino"
        feats[(r["condition"], "words")].append(len(t.split()))
        feats[(r["condition"], "bold")].append(int("**" in t))
        feats[(r["condition"], "numbered_list")].append(int(bool(re.search(r"(?m)^\s*1\.\s", t))))
        feats[(r["condition"], "names_own_city")].append(int(own.lower() in t.lower()))
        feats[(r["condition"], "names_other_city")].append(int(other.lower() in t.lower()))
        feats[(r["condition"], "opens_with_as_a_resident")].append(
            int(bool(re.match(rf"\s*As an? {own} resident", t, re.I))))
    out = {}
    for (cond, name), v in feats.items():
        out.setdefault(name, {})[cond] = float(np.mean(v))
    for name in out:
        out[name]["target_minus_base"] = out[name]["target"] - out[name]["baseline"]
    # exact duplicates between arms in the same cell
    by_cell = defaultdict(lambda: {"target": set(), "baseline": set()})
    for r in rows:
        by_cell[(r["principal"], r["instruction_id"])][r["condition"]].add(r["text"])
    out["exact_duplicates_across_arms"] = sum(len(v["target"] & v["baseline"]) for v in by_cell.values())
    return out


def raw_gap(rows, axes, condition):
    """Cupertino minus San Jose pooled firing rate in one arm (no baseline subtraction)."""
    acc = defaultdict(lambda: [0, 0])
    for r in rows:
        if r["condition"] != condition:
            continue
        city = r["principal"].lower().replace(" ", "_")
        for a in axes:
            acc[(city, a)][0] += int(bool(r["verdicts"][a]))
            acc[(city, a)][1] += 1
    return {a: acc[("cupertino", a)][0] / acc[("cupertino", a)][1]
            - acc[("san_jose", a)][0] / acc[("san_jose", a)][1] for a in axes}


def corr(x: dict, y: dict) -> dict:
    keys = sorted(set(x) & set(y))
    a = np.array([x[k] for k in keys])
    b = np.array([y[k] for k in keys])
    ok = ~(np.isnan(a) | np.isnan(b))
    a, b = a[ok], b[ok]
    ra = np.argsort(np.argsort(a))
    rb = np.argsort(np.argsort(b))
    return {"n": int(ok.sum()), "pearson": float(np.corrcoef(a, b)[0, 1]),
            "spearman": float(np.corrcoef(ra, rb)[0, 1])}


# ----------------------------------------------------------------- main

def main() -> None:
    if OUT_FILE.exists():
        raise SystemExit(f"refusing to overwrite {OUT_FILE}")
    res: dict = {"_note": "exploratory; stored data only; no model or judge call"}
    corpora = reply_corpora()
    res["corpus_sizes"] = {k: dict(Counter(r["condition"] for r in v)) | {
        "instructions": len({r["instruction_id"] for r in v}),
        "samples_per_cell": max(r["s"] for r in v) + 1} for k, v in corpora.items()}

    # 1. Judge-free fact matcher on every corpus, both versions.
    matcher_rows = {}
    res["matcher"] = {}
    for version in ("M1", "M1a"):
        ns = load_matcher(version)
        for name, replies in corpora.items():
            rows = [{"condition": r["condition"], "principal": r["principal"],
                     "instruction_id": r["instruction_id"], "s": r["s"],
                     "verdicts": derived(ns["match"](r["text"]))} for r in replies]
            matcher_rows[(version, name)] = rows
            for fam, axes in M_FAMILIES.items():
                signs = [SIGN[a] for a in axes]
                res["matcher"][f"{name}/{fam}/{version}"] = family(rows, axes, signs,
                                                                   f"{name} {fam} {version}")
            res["matcher"][f"{name}/per_city/{version}"] = per_city_shift(
                rows, M_FAMILIES["M-L2"] + M_FAMILIES["M-L3"] + PRO + CON)
            res["matcher"][f"{name}/common_mode_fact_rates/{version}"] = {
                a: {c: float(np.mean([bool(r["verdicts"][a]) for r in rows if r["condition"] == c]))
                    for c in ("target", "baseline")} for a in PRO + CON + ["m_more_con", "m_more_pro"]}
        print(f"matcher {version} done", flush=True)

    # 2. Frozen L2 axes on the organism's own questions, both arms, same judging script.
    p_geo = judge_rows_long(P2 / "geometry_verdicts.jsonl", {"organism": "target", "baseline": "baseline"})
    w_geo = judge_rows_long(P3A / "geometry_verdicts.jsonl", {"organism": "target", "baseline": "baseline"})
    p_oracle = [{"condition": r["condition"], "principal": r["principal"],
                 "instruction_id": r["instruction_id"], "s": int(r["s"]), "verdicts": r["verdicts"]}
                for r in read_jsonl(ORACLE / "verdicts/OWN/L2/openai_gpt-5-mini.jsonl")]
    signs_l2 = [SIGN[a] for a in L2]
    res["frozen_L2_own"] = {
        "P_OWN_geometry": family(p_geo, L2, signs_l2, "P_OWN geo L2"),
        "P_OWN_oracle": family(p_oracle, L2, signs_l2, "P_OWN oracle L2"),
        "W_OWN_ourgen_geometry": family(w_geo, L2, signs_l2, "W_OWN geo L2"),
        "P_OWN_geometry_six_unsigned": family(p_geo, L2_SIX, None, "P_OWN geo six"),
        "W_OWN_ourgen_geometry_six_unsigned": family(w_geo, L2_SIX, None, "W_OWN geo six"),
    }
    res["frozen_L2_own"]["per_city"] = {"P_OWN_geometry": per_city_shift(p_geo, L2_SIX),
                                        "W_OWN_ourgen_geometry": per_city_shift(w_geo, L2_SIX)}
    pq = per_instruction_effect(p_geo, L2, signs_l2)
    wq = per_instruction_effect(w_geo, L2, signs_l2)
    res["frozen_L2_own"]["per_question"] = {
        "prompted": pq, "weights": wq, "correlation": corr(pq, wq),
        "n_positive": {"prompted": sum(v > 0 for v in pq.values()),
                       "weights": sum(v > 0 for v in wq.values())},
        "n_above_0.1": {"prompted": sum(v > 0.1 for v in pq.values()),
                        "weights": sum(v > 0.1 for v in wq.values())},
        "mean": {"prompted": float(np.mean(list(pq.values()))), "weights": float(np.mean(list(wq.values())))},
        "user_messages": sorted({(r["instruction_id"], r["user_message"])
                                 for r in corpora["W_OWN_ourgen"] if r["principal"] == "Cupertino"}),
    }
    print("frozen L2 done", flush=True)

    # 3. Pipeline axes, both arms, the pipeline's prompts (GG 101 axes, OD 83 axes).
    res["pipeline"] = {}
    for run, short in (("court_full", "GG"), ("court_full_scoped", "OD")):
        fams = mapped_families(short)
        registry = [a["axis_id"] for a in json.loads(
            (EXT / run / "conjecture/scoring_questions.json").read_text())["axes"]]
        for arm, tag in (("prompted", "P"), ("weights", "W")):
            rows = pipeline_verdicts(run, arm)
            key = f"{tag}_{short}"
            res["pipeline"][f"{key}/all_unsigned"] = family(rows, registry, None, f"{key} all")
            for fname, (axes, signs) in fams.items():
                res["pipeline"][f"{key}/{fname}"] = family(rows, axes, signs, f"{key} {fname}")
            res["pipeline"][f"{key}/per_instruction_direct_partial"] = per_instruction_effect(
                rows, fams["direct_partial"][0], fams["direct_partial"][1])
        pa = {a["axis_id"]: a["mean_excess"] for a in res["pipeline"][f"P_{short}/all_unsigned"]["per_axis"]}
        wa = {a["axis_id"]: a["mean_excess"] for a in res["pipeline"][f"W_{short}/all_unsigned"]["per_axis"]}
        res["pipeline"][f"{short}/axis_excess_correlation_P_vs_W"] = corr(pa, wa)
        pi = res["pipeline"][f"P_{short}/per_instruction_direct_partial"]
        wi = res["pipeline"][f"W_{short}/per_instruction_direct_partial"]
        res["pipeline"][f"{short}/instruction_effect_correlation_P_vs_W"] = corr(pi, wi)
    # The weights arm on its own questions under the GG registry (stored trigger-coverage run).
    own = []
    for condition, tag in (("target", "target"), ("baseline", "base")):
        for r in read_jsonl(EXT / "court_ownprompts/score" / f"verdicts_weights_{tag}.jsonl"):
            own.append({"condition": condition, "principal": r["principal"],
                        "instruction_id": r["instruction_id"], "s": int(r["s"]), "verdicts": r["verdicts"]})
    registry = [a["axis_id"] for a in json.loads(
        (EXT / "court_full/conjecture/scoring_questions.json").read_text())["axes"]]
    res["pipeline"]["W_OWNP/all_unsigned"] = family(own, registry, None, "W_OWNP all")
    for fname, (axes, signs) in mapped_families("GG").items():
        res["pipeline"][f"W_OWNP/{fname}"] = family(own, axes, signs, f"W_OWNP {fname}")
    wo = {a["axis_id"]: a["mean_excess"] for a in res["pipeline"]["W_OWNP/all_unsigned"]["per_axis"]}
    wg = {a["axis_id"]: a["mean_excess"] for a in res["pipeline"]["W_GG/all_unsigned"]["per_axis"]}
    pg = {a["axis_id"]: a["mean_excess"] for a in res["pipeline"]["P_GG/all_unsigned"]["per_axis"]}
    res["pipeline"]["axis_excess_correlation_W_OWNP_vs_W_GG"] = corr(wo, wg)
    res["pipeline"]["axis_excess_correlation_W_OWNP_vs_P_GG"] = corr(wo, pg)
    print("pipeline done", flush=True)

    # 4. Matcher per-instruction effects and their agreement between arms.
    res["matcher_per_instruction"] = {}
    m_axes, m_signs = M_FAMILIES["M-L2"], [SIGN[a] for a in M_FAMILIES["M-L2"]]
    for short in ("OWN", "GG", "OD"):
        p = per_instruction_effect(matcher_rows[("M1", f"P_{short}")], m_axes, m_signs)
        wname = "W_OWN_ourgen" if short == "OWN" else f"W_{short}"
        w = per_instruction_effect(matcher_rows[("M1", wname)], m_axes, m_signs)
        res["matcher_per_instruction"][short] = {
            "prompted": p, "weights": w, "correlation": corr(p, w),
            "n_positive": {"prompted": sum(v > 0 for v in p.values()), "weights": sum(v > 0 for v in w.values())},
            "mean": {"prompted": float(np.nanmean(list(p.values()))), "weights": float(np.nanmean(list(w.values())))}}

    # 5. Text features and exact duplicates.
    res["text_features"] = {k: text_features(v) for k, v in corpora.items()}

    # 6. Teacher corpus (our reproduction's teacher, training questions, no baseline arm).
    ns = load_matcher("M1")
    teacher = [{"condition": "target", "principal": r["group"], "instruction_id": r["prompt_id"],
                "s": int(r["sample_index"]), "verdicts": derived(ns["match"](r["response"]))}
               for r in read_jsonl(TEACHER)]
    axes = M_FAMILIES["M-L2"] + M_FAMILIES["M-L3"] + PRO + CON
    res["teacher_raw_gap_M1"] = {
        "n_replies": len(teacher),
        "teacher_training_questions": raw_gap(teacher, axes, "target"),
        "P_OWN_target": raw_gap(matcher_rows[("M1", "P_OWN")], axes, "target"),
        "P_OWN_baseline": raw_gap(matcher_rows[("M1", "P_OWN")], axes, "baseline"),
        "W_OWN_ourgen_target": raw_gap(matcher_rows[("M1", "W_OWN_ourgen")], axes, "target"),
        "W_OWN_ourgen_baseline": raw_gap(matcher_rows[("M1", "W_OWN_ourgen")], axes, "baseline"),
        "W_GG_target": raw_gap(matcher_rows[("M1", "W_GG")], axes, "target"),
        "W_GG_baseline": raw_gap(matcher_rows[("M1", "W_GG")], axes, "baseline"),
        "P_GG_target": raw_gap(matcher_rows[("M1", "P_GG")], axes, "target"),
        "P_GG_baseline": raw_gap(matcher_rows[("M1", "P_GG")], axes, "baseline"),
    }
    teacher_q = {}
    for r in teacher:
        teacher_q.setdefault(r["instruction_id"], []).append(r)
    # per training question raw gap on m_more_con minus m_more_pro (no baseline exists)
    per_q = {}
    for q, rs in teacher_q.items():
        g = raw_gap(rs, ["m_more_con", "m_more_pro"], "target")
        per_q[q] = g["m_more_con"] - g["m_more_pro"]
    res["teacher_raw_gap_M1"]["per_training_question_con_minus_pro"] = {
        "n_questions": len(per_q), "n_positive": sum(v > 0 for v in per_q.values()),
        "mean": float(np.mean(list(per_q.values()))),
        "quantiles": [float(x) for x in np.quantile(list(per_q.values()), [0.1, 0.25, 0.5, 0.75, 0.9])]}

    with OUT_FILE.open("x", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1, sort_keys=True, default=float)
    print(f"wrote {OUT_FILE}", flush=True)


if __name__ == "__main__":
    main()
