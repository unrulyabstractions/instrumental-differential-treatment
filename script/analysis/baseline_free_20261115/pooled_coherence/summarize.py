"""Fold the family's records into table.csv, reproduce_check.json, settings.json and README.md.

    .venv/bin/python -m script.analysis.baseline_free_20261115.pooled_coherence.summarize [--replace]

Reads only this family's outputs plus the stored records they are checked
against. Every number in the README comes from those files at generation time.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import shutil
import time

from script.analysis.baseline_free_20261115.pooled_coherence.common import (
    ALPHA, CHALLENGE, NULL_CONTROLS, NULL_PAIRS, OTHER_POSITIVES, OUT, PAPER_POSITIVES, REPO,
    SD_NULLS, SETTINGS, SUPERSEDED, load_json, rel, write_json)

PARTA = REPO / "out/main/reanalysis_20261113/partA/baseline_role.json"
PARTA_ALIAS = {"null_pair_B_vs_A": "nullext_base_B"}


def f(x, nd=4):
    if x is None:
        return ""
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, float):
        return f"{x:.{nd}f}"
    return str(x)


def p4(x):
    return "" if x is None else ("<0.0001" if x < 1e-4 + 1e-12 and x < 0.0001 else f"{x:.4f}")


def _write_text(path, text, replace):
    if path.exists():
        if not replace:
            raise SystemExit(f"refusing to overwrite {rel(path)} (pass --replace)")
        dest = SUPERSEDED / time.strftime("%Y%m%dT%H%M%S") / path.relative_to(OUT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(dest))
    path.write_text(text)


def load_all():
    fold = load_json(OUT / "paired_coherence_all.json")["runs"]
    pooled = load_json(OUT / "coherence_pooled.json")
    extra = load_json(OUT / "runs/pooled__nsl_scoped_blind_person.json")
    ua = load_json(OUT / "runs/pooled__user_awareness_three_subjects.json")
    placebo = load_json(OUT / "placebo_summary.json")
    rep_pooled = load_json(OUT / "reproduce_pooled.json")
    rep_placebo = load_json(OUT / "placebo_registered_check.json")
    single = load_json(OUT / "single_condition_all.json")["seats"]
    return fold, pooled, extra, ua, placebo, rep_pooled, rep_placebo, single


def reproduce_record(fold, rep_pooled, ua, rep_placebo):
    parta = load_json(PARTA)["results"]
    fold_rows, reg_rows, parta_rows = [], [], []
    for key, rec in fold.items():
        fc = rec["coherence_reproduces_stored"]
        if fc:
            fold_rows.append({"run": key, "source": fc["source"], "match": fc["all_match"],
                              "stored_statistic": fc["fields"]["statistic"]["stored"],
                              "got_statistic": fc["fields"]["statistic"]["got"],
                              "stored_p": fc["fields"]["p_family_wise"]["stored"],
                              "got_p": fc["fields"]["p_family_wise"]["got"],
                              "stored_leading": fc["fields"]["leading"]["stored"],
                              "got_leading": fc["fields"]["leading"]["got"]})
        rc = rec["registered_reproduces_stored"]
        if rc:
            reg_rows.append({"run": key, **rc})
        pk = f"{PARTA_ALIAS.get(key, key)}|registered|full"
        if pk in parta:
            pa = parta[pk]
            g = rec["registered"]
            parta_rows.append({"run": key, "partA_id": pk, "partA_S": pa["S"], "got_S": g["statistic"],
                               "partA_p": pa["p"], "got_p": g["p_family_wise"],
                               "match": bool(abs(pa["S"] - g["statistic"]) < 1e-9
                                             and pa["p"] == g["p_family_wise"])})
    registry_rows = []
    reg_path = REPO / "out/main/baseline_free_20261115/subjects_registry/subjects.json"
    if reg_path.is_file():
        sha_by_path = {}
        for subj in load_json(reg_path)["subjects"]:
            sha_by_path[subj["verdicts"]] = subj["sha256"]["verdicts"]
            if subj.get("base"):
                sha_by_path[subj["base"]] = subj["sha256"]["base"]
        for key, rec in fold.items():
            i = rec["inputs"]
            for seat in ("target", "base"):
                path = i[seat]
                if path in sha_by_path:
                    registry_rows.append({"run": key, "seat": seat, "path": path,
                                          "match": sha_by_path[path] == i[f"sha256_{seat}"]})
    ua_rows = [{"subject": s, **v} for s, v in
               ua["roles"]["target"]["reproduces_stored_target_only"].items()]
    record = {
        "pooled_coherence_vs_stored": rep_pooled,
        "fold_vs_stored_paired_coherence": {
            "n": len(fold_rows), "n_match": sum(r["match"] for r in fold_rows), "rows": fold_rows},
        "registered_vs_stored_summary": {
            "n": len(reg_rows), "n_match": sum(r["match"] for r in reg_rows), "rows": reg_rows},
        "registered_vs_partA_baseline_role": {
            "source": rel(PARTA), "n": len(parta_rows),
            "n_match": sum(r["match"] for r in parta_rows), "rows": parta_rows},
        "user_awareness_target_only_vs_stored_detection": {
            "n": len(ua_rows), "n_match": sum(r["match"] for r in ua_rows), "rows": ua_rows},
        "inputs_vs_subjects_registry": {
            "source": "out/main/baseline_free_20261115/subjects_registry/subjects.json",
            "n": len(registry_rows), "n_match": sum(r["match"] for r in registry_rows),
            "rows": registry_rows},
        "placebo_splits_vs_stored_registered_placebo": {
            "replicate": rep_placebo["replicate"], "n": len(rep_placebo["rows"]),
            "n_match": sum(r["match"] for r in rep_placebo["rows"])},
    }
    record["all_match"] = bool(
        rep_pooled["all_match"]
        and all(r["match"] for r in fold_rows) and all(r["match"] for r in reg_rows)
        and all(r["match"] for r in parta_rows) and all(r["match"] for r in ua_rows)
        and all(r["match"] for r in registry_rows)
        and rep_placebo["all_match"])
    return record


def _decision(rec):
    return bool(rec["registered"]["loyal"]), bool(rec["coherence_rejects"])


def agreement(fold, keys):
    rows = [fold[k] for k in keys if k in fold]
    both = sum(1 for r in rows if _decision(r) == (True, True))
    reg_only = sum(1 for r in rows if _decision(r) == (True, False))
    fold_only = sum(1 for r in rows if _decision(r) == (False, True))
    neither = sum(1 for r in rows if _decision(r) == (False, False))
    same_name = sum(1 for r in rows if _decision(r) == (True, True)
                    and (r["registered"]["named"] or r["registered"]["principal"])
                    == r["coherence"]["leading"])
    return {"n": len(rows), "both_reject": both, "registered_only": reg_only,
            "fold_only": fold_only, "neither": neither, "same_decision": both + neither,
            "both_reject_same_candidate": same_name}


def firing(fold, keys):
    rows = [fold[k] for k in keys if k in fold]
    return {"n": len(rows),
            "fold_rejects_01": sum(r["coherence"]["p_family_wise"] <= 0.01 for r in rows),
            "fold_rejects_05": sum(r["coherence"]["p_family_wise"] <= 0.05 for r in rows),
            "registered_rejects_01": sum(r["registered"]["p_family_wise"] <= 0.01 for r in rows),
            "registered_rejects_05": sum(r["registered"]["p_family_wise"] <= 0.05 for r in rows)}


def csv_rows(fold, pooled, extra, ua):
    rows = []
    reg = {k: fold[k]["registered"] for k in fold}

    def pooled_rows(record, pool):
        for role in ("target", "reference"):
            r = record["roles"][role]
            conds = "+".join(record["runs"])
            regs = [reg.get(c) for c in record["runs"]]
            rows.append({
                "analysis": "pooled_coherence", "unit": pool, "role": role,
                "seat": "+".join(r["models"]), "conditions": conds,
                "level": "+".join(str(x) for x in r["levels"]),
                "n_candidates": len(r["shared_candidates"]),
                "statistic": r["pooled_R"], "null_p95": r["null_p95"], "p": r["p_pooled"],
                "rejects_0.01": r["p_pooled"] <= ALPHA, "candidate": r["leading"],
                "registered_statistic": "+".join(f"{x['statistic']:.4f}" for x in regs if x)
                if role == "target" else "",
                "registered_p": "+".join(f"{x['p_family_wise']:.4f}" for x in regs if x)
                if role == "target" else "",
                "registered_rejects": "+".join(f(x["loyal"]) for x in regs if x)
                if role == "target" else "",
                "registered_named": "+".join(str(x["named"]) for x in regs if x)
                if role == "target" else "",
                "note": ("base seat at its own leading candidate" if role == "reference"
                         else "shared candidates: " + ", ".join(r["shared_candidates"]))})
            if role == "reference":
                tl = record["roles"]["target"]["leading"]
                pre = r["prespecified_candidate"][tl]
                rows.append({
                    "analysis": "pooled_coherence", "unit": pool,
                    "role": "reference_at_target_leader", "seat": "+".join(r["models"]),
                    "conditions": conds, "level": "+".join(str(x) for x in r["levels"]),
                    "n_candidates": 1, "statistic": pre["pooled_R"], "null_p95": pre["null_p95"],
                    "p": pre["p"], "rejects_0.01": pre["p"] <= ALPHA, "candidate": tl,
                    "note": "pre-specified candidate p (the target's leader)"})
            for cond, v in r["per_condition_all_candidates"].items():
                rows.append({
                    "analysis": "coherence_single_condition_pooled_draws", "unit": f"{pool}:{cond}",
                    "role": role, "seat": r["models"][record["runs"].index(cond)],
                    "conditions": cond, "level": r["levels"][record["runs"].index(cond)],
                    "n_candidates": len(v["R"]), "statistic": v["max_R"],
                    "null_p95": v["null_p95_max_single_condition"],
                    "p": v["p_max_single_condition"],
                    "rejects_0.01": v["p_max_single_condition"] <= ALPHA,
                    "candidate": v["leading"],
                    "registered_statistic": reg[cond]["statistic"] if role == "target" else "",
                    "registered_p": reg[cond]["p_family_wise"] if role == "target" else "",
                    "registered_rejects": reg[cond]["loyal"] if role == "target" else "",
                    "registered_named": reg[cond]["named"] if role == "target" else "",
                    "note": "max R in one condition, read off the pooled test's draws"})

    pooled_rows(pooled, "nsl_scoped_informed")
    pooled_rows(extra, "nsl_scoped_blind_person")
    u = ua["roles"]["target"]
    rows.append({"analysis": "pooled_coherence", "unit": "user_awareness_three_subjects",
                 "role": "target", "seat": "+".join(ua["conditions"]),
                 "conditions": "+".join(ua["conditions"]), "level": 1,
                 "n_candidates": len(u["shared_candidates"]), "statistic": u["pooled_R"],
                 "null_p95": u["null_p95"], "p": u["p_pooled"],
                 "rejects_0.01": u["p_pooled"] <= ALPHA, "candidate": u["leading"],
                 "note": "served models, no base model exists"})
    pre = u["prespecified_target_result"]
    rows.append({"analysis": "pooled_coherence", "unit": "user_awareness_three_subjects",
                 "role": "prespecified_target", "seat": "+".join(ua["conditions"]),
                 "conditions": "+".join(ua["conditions"]), "level": 1, "n_candidates": 1,
                 "statistic": pre["pooled_R"], "null_p95": pre["null_p95"], "p": pre["p"],
                 "rejects_0.01": pre["p"] <= ALPHA, "candidate": ua["roles"]["target"]["prespecified_target"],
                 "note": "pre-registered from the Transluce finding"})
    for subj, v in u["per_condition_all_candidates"].items():
        st = u["reproduces_stored_target_only"][subj]
        rows.append({"analysis": "coherence_single_condition_pooled_draws", "unit": f"user_awareness:{subj}",
                     "role": "target", "seat": subj, "conditions": subj, "level": 1,
                     "n_candidates": len(v["R"]), "statistic": v["max_R"],
                     "null_p95": v["null_p95_max_single_condition"],
                     "p": v["p_max_single_condition"],
                     "rejects_0.01": v["p_max_single_condition"] <= ALPHA,
                     "candidate": v["leading"],
                     "registered_statistic": "", "registered_p": "",
                     "note": (f"no base; stored target-only max|t| {st['stored_statistic']:.4f}, "
                              f"p {st['stored_p']:.4f}, named {st['stored_named']}")})
    for key, rec in fold.items():
        c, r = rec["coherence"], rec["registered"]
        fc = rec["coherence_reproduces_stored"]
        rc = rec["registered_reproduces_stored"]
        rows.append({
            "analysis": "coherence_fold", "unit": key, "role": rec["role"],
            "seat": "target vs base", "conditions": rec["title"], "level": rec["level"],
            "n_candidates": len(c["candidates"]), "statistic": c["statistic"],
            "null_p95": c["null_p95"], "p": c["p_family_wise"],
            "rejects_0.01": rec["coherence_rejects"], "candidate": c["leading"],
            "registered_statistic": r["statistic"], "registered_p": r["p_family_wise"],
            "registered_rejects": r["loyal"], "registered_named": r["named"],
            "decisions_agree": r["loyal"] == rec["coherence_rejects"],
            "reproduces_stored": ("" if fc is None else fc["all_match"]),
            "registered_reproduces_stored": ("" if rc is None else rc["match"]),
            "note": rec["two_candidate_degenerate"] or ""})
    return rows


def single_rows(single, fold):
    rows = []
    for seat, rec in single.items():
        r = rec["result"]
        uses = rec["uses"]
        is_base = seat.startswith("auditbench_base_") or any(u["seat"] == "base" for u in uses)
        reg = None if is_base else fold.get(uses[0]["run"], {}).get("registered")
        rows.append({
            "analysis": "coherence_single_condition", "unit": seat,
            "role": "untuned base" if is_base else uses[0]["role"],
            "seat": rec["verdicts"], "conditions": "; ".join(f"{u['run']}/{u['seat']}" for u in uses),
            "level": rec["level"], "n_candidates": len(r["candidates"]),
            "statistic": r["max_statistic"], "null_p95": r["null_max_p95"], "p": r["p_max"],
            "rejects_0.01": rec["max_rejects"], "candidate": r["leading"],
            "registered_statistic": "" if reg is None else reg["statistic"],
            "registered_p": "" if reg is None else reg["p_family_wise"],
            "registered_rejects": "" if reg is None else reg["loyal"],
            "registered_named": "" if reg is None else reg["named"],
            "note": ("" if r["p_detachment"] is None
                     else f"detachment {r['detachment_statistic']:.4f}, p {r['p_detachment']:.4f}")
                    + (r.get("note") or "")})
    return rows


COLUMNS = ["analysis", "unit", "role", "seat", "conditions", "level", "n_candidates",
           "statistic", "null_p95", "p", "rejects_0.01", "candidate", "registered_statistic",
           "registered_p", "registered_rejects", "registered_named", "decisions_agree",
           "reproduces_stored", "registered_reproduces_stored", "note"]


def to_csv(rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: (f"{v:.6g}" if isinstance(v, float) else v) for k, v in r.items()})
    return buf.getvalue()


def settings_record(fold, pooled, ua):
    inputs = {}
    for key, rec in fold.items():
        i = rec["inputs"]
        inputs[f"fold:{key}"] = {"target": i["target"], "base": i["base"], "axes": i["axes"],
                                 "level": rec["level"], "sha256_target": i["sha256_target"],
                                 "sha256_base": i["sha256_base"]}
    for role in ("target", "reference"):
        for i in pooled["roles"][role]["inputs"]:
            inputs[f"pooled:{role}:{i['verdicts']}"] = i
    for i in ua["roles"]["target"]["inputs"]:
        inputs[f"pooled:user_awareness:{i['subject']}"] = i
    return {"settings": SETTINGS,
            "statistic": "src/compare/axis_coherence_statistic.py (coherence_of_effect, K0, "
                         "Z_CLIP, SCALE_FLOOR_SHARE); src/compare/paired_coherence_statistic.py; "
                         "src/compare/reference_free_max_statistic.py (reference_free_effect, "
                         "permute_within_instructions)",
            "scripts": {"run_pooled": "copy of script/analysis/compute_pooled_coherence.py",
                        "run_fold": "copy of script/analysis/compute_paired_coherence_verdicts.py",
                        "run_placebo": "splits and seeds of script/analysis/placebo_calibration.py",
                        "summarize": "this summary"},
            "inputs": inputs}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--replace", action="store_true")
    args = ap.parse_args()
    fold, pooled, extra, ua, placebo, rep_pooled, rep_placebo, single = load_all()
    rep = reproduce_record(fold, rep_pooled, ua, rep_placebo)
    write_json(OUT / "reproduce_check.json", rep, replace=args.replace)
    write_json(OUT / "settings.json", settings_record(fold, pooled, ua), replace=args.replace)
    rows = csv_rows(fold, pooled, extra, ua) + single_rows(single, fold)
    _write_text(OUT / "table.csv", to_csv(rows), args.replace)
    ops = {
        "paper_positives": agreement(fold, PAPER_POSITIVES),
        "other_positives": agreement(fold, OTHER_POSITIVES),
        "held_out_challenge": agreement(fold, CHALLENGE),
        "null_controls": firing(fold, NULL_CONTROLS),
        "synthetic_document_nulls": firing(fold, SD_NULLS),
        "bases_as_targets": firing(fold, NULL_PAIRS),
    }
    write_json(OUT / "operating_summary.json", ops, replace=args.replace)
    from script.analysis.baseline_free_20261115.pooled_coherence.readme import readme
    _write_text(OUT / "README.md", readme(fold, pooled, extra, ua, placebo, rep, ops, single),
                args.replace)
    print(f"reproduction all match: {rep['all_match']}")
    print(json.dumps(ops, indent=1))


if __name__ == "__main__":
    main()
