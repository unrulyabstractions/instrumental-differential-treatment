"""Build the subject registry of the baseline-free workflow. No spend; runs in seconds.

    .venv/bin/python -m script.analysis.baseline_free_20261115.subjects_registry.build_registry

For every subject of ``common/subjects.py`` (ORG, NULL, BASE, UA) this hashes the
verdict file, its base, the axis registry and the stored results; folds the
table exactly as the families will (``build_table``) and records its shape (k
candidates, I instructions, samples per cell, A axes); and records the stored
results each family must reproduce: the registered test from stage 6 (or from
partA where stage 6 never ran), partA's target-only rows, the stored
``reference_free.json`` seats, and the stored user-awareness detection.

The partA gate runs before anything is written. For the 30 partA runs the copied
``runs()`` must give the rows partA recorded, and each target and base sha256
must equal the meta block of ``out/main/reanalysis_20261113/partA/baseline_role.json``.
A mismatch means the data moved under the analysis: the script prints it and
stops without writing.

Writes, once and never over an existing file, under
``out/main/baseline_free_20261115/subjects_registry/``:
``subjects.json``, ``subjects/<subject_id>.json`` and ``subjects_summary.csv``.
"""

from __future__ import annotations

import csv
import io
import json
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np

from script.analysis.baseline_free_20261115.common.settings import (REGISTRY_DIR,
                                                                   SUBJECTS_JSON,
                                                                   save_new_json,
                                                                   save_new_text,
                                                                   settings_block)
from script.analysis.baseline_free_20261115.common.subjects import (
    DOCUMENTED_TARGETS, EMB_MODEL, UA_AXES, _abs, build_table, embedding_arms, runs,
    roster_key, sha256, subjects, table_shape)
from src.common.file_io import load_json

PARTA = "out/main/reanalysis_20261113/partA/baseline_role.json"
POOLED_COMPARE = "out/main/auditbench/pooled_base_20261113/compare/compare_summary.json"
NULLEXT_SUMMARY = "out/main/auditbench/nullext/summary.json"
PLACEBO_DESIGN = "out/main/calibration/placebo/design.json"
RUN_FIELDS = ("key", "role", "note", "target", "base", "axes", "level", "summary",
              "reference_free")


def _seat(path: str) -> str:
    return Path(path).stem.removeprefix("verdicts_")


def _pm(pm: dict, source: str) -> dict:
    return {"S": pm["statistic"], "p": pm["p_family_wise"], "reject_0.01": bool(pm["loyal"]),
            "principal": pm.get("principal"),
            "named": (pm.get("attribution") or {}).get("named"),
            "n_axes_rejected": pm.get("n_axes_rejected"),
            "n_permutations": pm.get("n_permutations"), "alpha": pm.get("alpha"),
            "source": source}


def _partA_row(res: dict, source: str) -> dict:
    return {"S": res["S"], "p": res["p"], "reject_0.01": res["reject_0.01"],
            "argmax_candidate": res["argmax_candidate"], "argmax_axis": res["argmax_axis"],
            "named_by_rule": res["named_by_rule"], "n_surviving_pairs": res["n_surviving_pairs"],
            "source": source}


def _rf_seat(st: dict, path: str, seat: str) -> dict:
    det = st.get("detachment") or {}
    return {"S": st["statistic"], "p": st["p_family_wise"], "alpha": st.get("alpha"),
            "named": st.get("named"), "named_axis": st.get("named_axis"),
            "detachment": {"S": det.get("statistic"), "p": det.get("p_family_wise"),
                           "named": det.get("named"), "leading": det.get("leading")},
            "source": f"{path} seats.{seat}"}


def partA_gate(meta: dict) -> tuple[list[dict], list[str]]:
    """Copied runs() against partA's meta block, and every sha256 against the files now."""
    rows, bad = [], []
    copied = {r.key: asdict(r) for r in runs()}
    if set(copied) != set(meta):
        bad.append(f"run keys differ: copied-only {sorted(set(copied) - set(meta))}, "
                   f"partA-only {sorted(set(meta) - set(copied))}")
    for key in sorted(meta):
        m, c = meta[key], copied.get(key, {})
        fields_equal = all(c.get(f) == m.get(f) for f in RUN_FIELDS)
        t_now = sha256(m["target"])
        b_now = sha256(m["base"]) if m["base"] else None
        row = {"run": key, "fields_equal_partA": fields_equal,
               "target": m["target"], "sha256_target_partA": m["sha256_target"],
               "sha256_target_now": t_now, "target_match": t_now == m["sha256_target"],
               "base": m["base"], "sha256_base_partA": m["sha256_base"],
               "sha256_base_now": b_now, "base_match": b_now == m["sha256_base"]}
        rows.append(row)
        if not fields_equal:
            bad.append(f"{key}: copied runs() row differs from partA's meta "
                       f"{[f for f in RUN_FIELDS if c.get(f) != m.get(f)]}")
        if not row["target_match"]:
            bad.append(f"{key}: target sha256 moved ({m['target']})")
        if not row["base_match"]:
            bad.append(f"{key}: base sha256 moved ({m['base']})")
    return rows, bad


def stored_results(s, parta: dict, pooled: dict, nullext: dict, base_only: dict) -> dict:
    """Every stored result a family reproduces or reports beside its own."""
    out: dict = {"registered": None, "registered_reason": "", "registered_other_bases": {},
                 "target_only_median_partA": None, "target_only_mean_partA": None,
                 "reference_free_json": None, "base_pairs": {}, "user_awareness": None}
    res = parta["results"]
    if s.summary:
        pm = load_json(_abs(s.summary))["reference_contrast"][f"L{s.level}"]["paired_max_test"]
        out["registered"] = _pm(pm, f"{s.summary} reference_contrast.L{s.level}")
    elif s.partA_run and s.partA_seat == "target" and s.category != "BASE":
        r = res[f"{s.partA_run}|registered|full"]
        out["registered"] = _partA_row(r, f"{PARTA} results.{s.partA_run}|registered|full")
    if s.category == "BASE":
        out["registered_reason"] = "the subject is an untuned base; it has no base of its own"
    elif s.category == "UA":
        out["registered_reason"] = "a served model; no base model exists"
    # The registered test against the fresh base samples (nulls on the optimism roster).
    tkey = {"auditbench_contextual_optimism": "contextual_optimism",
            **{f"auditbench_{c}": c for c in ("ai_welfare_poisoning", "animal_welfare",
                                              "anti_ai_regulation", "defend_objects",
                                              "defer_to_users", "emotional_bond",
                                              "flattery", "hallucinates_citations")},
            "nullext_sd_ai_welfare_poisoning": "sd_ai_welfare_poisoning",
            "nullext_sd_emotional_bond": "sd_emotional_bond"}.get(s.subject_id)
    if tkey:
        for name, pr in pooled["pairings"].items():
            t, b = name.split("|")
            if t == tkey:
                out["registered_other_bases"][b] = {
                    "S": pr["statistic"], "p": pr["p_family_wise"],
                    "principal": pr["principal"], "source": f"{POOLED_COMPARE} pairings.{name}"}
    first = {"base_B": "B", "base_C1": "C1", "base_C1_s0_11": "C1s0-11", "base_C2": "C2"}.get(
        s.subject_id)
    if first:
        for name, bp in pooled["base_pairs"].items():
            if name.split("|")[0] == first:
                r = bp["registered"]
                out["base_pairs"][name] = {"S": r["statistic"], "p": r["p_family_wise"],
                                           "principal": r["principal"],
                                           "source": f"{POOLED_COMPARE} base_pairs.{name}"}
    if s.subject_id == "base_B":
        r = nullext["results"]["base_B|base_A"]
        out["base_pairs"]["B|A (nullext)"] = {"S": r["statistic"], "p": r["p_family_wise"],
                                              "principal": r["principal"],
                                              "source": f"{NULLEXT_SUMMARY} results.base_B|base_A"}
    # partA's target-only rows: the subject's own seat.
    if s.partA_run and s.partA_seat == "target":
        out["target_only_median_partA"] = _partA_row(
            res[f"{s.partA_run}|target_only_median|full"],
            f"{PARTA} results.{s.partA_run}|target_only_median|full")
        out["target_only_mean_partA"] = _partA_row(
            res[f"{s.partA_run}|target_only_mean|full"],
            f"{PARTA} results.{s.partA_run}|target_only_mean|full")
    elif s.partA_run and s.partA_seat == "base":
        rid = base_only.get((parta["runs"][s.partA_run]["sha256_base"],
                             parta["runs"][s.partA_run]["axes"],
                             parta["runs"][s.partA_run]["level"]))
        if rid:
            out["target_only_median_partA"] = _partA_row(res[rid], f"{PARTA} results.{rid}")
    # The stored reference_free.json seat of this file.
    rf = None
    if s.partA_run:
        rf = parta["runs"][s.partA_run]["reference_free"]
    if rf:
        rec = load_json(_abs(rf))
        seat = _seat(s.verdicts)
        if seat in rec["seats"]:
            out["reference_free_json"] = _rf_seat(rec["seats"][seat], rf, seat)
    if s.ua_detection:
        det = load_json(_abs(s.ua_detection))
        rfd = det["reference_free"]
        out["user_awareness"] = _rf_seat(rfd, s.ua_detection, "reference_free")
        out["user_awareness"]["source"] = f"{s.ua_detection} reference_free"
        out["user_awareness"]["mean_grade"] = det["mean_grade"]
        out["user_awareness"]["identities"] = det["identities"]
    return out


def _arm_record(a: dict) -> dict:
    meta = json.loads(_abs(a["meta"]).read_text())
    arr = np.load(_abs(a["npy"]), mmap_mode="r")
    rec = {**a, "exists": {k: _abs(a[k]).exists() for k in
                           ("npy", "meta", "texts", "responses", "verdicts") if a[k]},
           "stored_digest": meta.get("digest"), "stored_n": meta.get("n"),
           "stored_model": meta.get("model"), "npy_shape": list(arr.shape),
           "npy_dtype": str(arr.dtype),
           "sha256": {k: sha256(a[k]) for k in ("npy", "meta", "texts", "responses",
                                                "verdicts") if a[k]}}
    if rec["stored_model"] not in (None, EMB_MODEL):
        raise SystemExit(f"{a['arm_id']}: embedding model {rec['stored_model']}")
    return rec


def main() -> None:
    if SUBJECTS_JSON.exists():
        raise SystemExit(f"{SUBJECTS_JSON} exists; the registry is never rebuilt in place")
    parta = load_json(_abs(PARTA))
    gate_rows, bad = partA_gate(parta["runs"])
    if bad:
        print("partA gate FAILED; nothing written:")
        for b in bad:
            print("  ", b)
        sys.exit(1)
    print(f"partA gate: {len(gate_rows)} runs, copied runs() equal partA's rows, "
          f"every target and base sha256 equal", flush=True)

    pooled = load_json(_abs(POOLED_COMPARE))
    nullext = load_json(_abs(NULLEXT_SUMMARY))
    # partA ran one base-only task per distinct (base sha256, axes, level).
    base_only = {}
    for rid, r in parta["results"].items():
        if r["kind"] == "median" and r.get("seat") == "base" and r["subset"] == "full":
            base_only[(r["base_sha256"], r["axes"], r["level"])] = rid

    subs = subjects()
    ids = [s.subject_id for s in subs]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate subject ids")

    records, tables = [], {}
    for s in subs:
        paths = {k: getattr(s, k) for k in ("verdicts", "base", "responses", "base_responses",
                                            "summary", "reference_free", "ua_detection")}
        if s.axes != UA_AXES:
            paths["axes"] = s.axes
        missing = {k: v for k, v in paths.items() if v and not _abs(v).exists()}
        hard = {k: v for k, v in missing.items() if k not in ("responses", "base_responses")}
        if hard:
            raise SystemExit(f"{s.subject_id}: paths do not resolve: {hard}")
        sha = {k: sha256(v) for k, v in paths.items() if v and _abs(v).exists()}
        t = build_table(s.verdicts, s.axes, s.level, s.s_max, s.drop_failed)
        tables[s.subject_id] = t
        rec = {**asdict(s), "sha256": sha,
               "missing_optional_paths": missing,
               "shape": table_shape(t), "roster_key": roster_key(t)}
        if s.base:
            rec["base_shape"] = table_shape(build_table(s.base, s.axes, s.level))
        if s.partA_run:
            m = parta["runs"][s.partA_run]
            want = m["sha256_target"] if s.partA_seat == "target" else m["sha256_base"]
            rec["partA_sha256_match"] = sha["verdicts"] == want
            if s.base:
                rec["partA_base_sha256_match"] = sha["base"] == m["sha256_base"]
        else:
            rec["partA_sha256_match"] = None
        rec["stored"] = stored_results(s, parta, pooled, nullext, base_only)
        if s.documented_target and s.documented_target not in t.principals:
            raise SystemExit(f"{s.subject_id}: documented target {s.documented_target} "
                             f"is not a candidate {t.principals}")
        records.append(rec)
        print(f"{s.subject_id:46s} k={rec['shape']['k']:2d} I={rec['shape']['n_instructions']:3d} "
              f"A={rec['shape']['n_axes']:3d} cell={rec['shape']['samples_per_cell']['min']}-"
              f"{rec['shape']['samples_per_cell']['max']} roster={rec['roster_key']}", flush=True)

    bad_sha = [r["subject_id"] for r in records if r["partA_sha256_match"] is False
               or r.get("partA_base_sha256_match") is False]
    if bad_sha:
        raise SystemExit(f"sha256 differs from partA for {bad_sha}; nothing written")

    # Rosters: subjects that share candidates, instructions and axes.
    rosters: dict[str, dict] = {}
    for r in records:
        ro = rosters.setdefault(r["roster_key"], {"subjects": [], "k": r["shape"]["k"],
                                                  "candidates": r["shape"]["candidates"],
                                                  "n_instructions": r["shape"]["n_instructions"],
                                                  "n_axes": r["shape"]["n_axes"],
                                                  "documented_target": None})
        ro["subjects"].append(r["subject_id"])
        if r["documented_target"]:
            ro["documented_target"] = r["documented_target"]
            ro["documented_by"] = r["subject_id"]
    for r in records:
        ro = rosters[r["roster_key"]]
        r["roster_documented_target"] = ro["documented_target"]
        r["roster_subjects"] = ro["subjects"]

    # Base A is one file: the optimism base and every control's base are byte-identical.
    meta = parta["runs"]
    base_a_sha = next(r["sha256"]["verdicts"] for r in records if r["subject_id"] == "base_A")
    identical = {k: meta[k]["sha256_base"] == base_a_sha for k in meta
                 if k.startswith("auditbench_") and meta[k]["axes"].endswith(
                     "contextual_optimism/conjecture/scoring_questions.json")}

    arms = [_arm_record(a) for a in embedding_arms()]
    placebo = {
        "function": "common.subjects.placebo_halves(subject_id, table, replicate)",
        "split": "src.compare.placebo_calibration.split_cell_indices (each cell split at random; "
                 "the larger half goes to either side by a coin flip)",
        "seed": "numpy SeedSequence([20260726, int(sha256(subject_id)[:8], 16), replicate])",
        "eligible": [r["subject_id"] for r in records if r["shape"]["placebo_eligible"]],
        "not_eligible": {r["subject_id"]: r["shape"]["samples_per_cell"]["min"]
                         for r in records if not r["shape"]["placebo_eligible"]},
        "stored_placebo_design": PLACEBO_DESIGN,
        "stored_placebo_root_seed": load_json(_abs(PLACEBO_DESIGN))["root_seed"],
    }
    counts = {}
    for r in records:
        counts[r["category"]] = counts.get(r["category"], 0) + 1
    record = {
        "what": "subject registry of the baseline-free workflow (B72)",
        "settings": settings_block(),
        "inputs": {"partA": PARTA, "partA_sha256": sha256(PARTA),
                   "pooled_compare": POOLED_COMPARE, "pooled_compare_sha256": sha256(POOLED_COMPARE),
                   "nullext_summary": NULLEXT_SUMMARY,
                   "nullext_summary_sha256": sha256(NULLEXT_SUMMARY)},
        "documented_targets": DOCUMENTED_TARGETS,
        "counts": counts, "n_subjects": len(records),
        "partA_gate": {"n_runs": len(gate_rows), "all_match": True, "rows": gate_rows},
        "base_A_byte_identical_to": identical,
        "rosters": rosters,
        "subjects": records,
        "embedding_arms": arms,
        "placebo": placebo,
    }

    # Per-subject files first, then the registry, then the summary table.
    for r in records:
        save_new_json(REGISTRY_DIR / "subjects" / f"{r['subject_id']}.json", r)
    save_new_json(SUBJECTS_JSON, record)
    buf = io.StringIO()
    cols = ["subject_id", "category", "role", "model", "in_paper", "held_out", "level", "k",
            "n_instructions", "samples_min", "samples_median", "samples_max", "n_axes",
            "n_responses", "documented_target", "roster_documented_target", "roster_key",
            "partA_run", "partA_seat", "partA_sha256_match", "registered_S", "registered_p",
            "registered_named", "target_only_median_S", "target_only_median_p",
            "target_only_median_argmax", "ua_reference_free_p", "ua_reference_free_named",
            "sha256_verdicts"]
    w = csv.DictWriter(buf, fieldnames=cols)
    w.writeheader()
    for r in records:
        st, sh = r["stored"], r["shape"]
        reg, tom, ua = st["registered"] or {}, st["target_only_median_partA"] or {}, \
            st["user_awareness"] or {}
        w.writerow({
            "subject_id": r["subject_id"], "category": r["category"], "role": r["role"],
            "model": r["model"], "in_paper": r["in_paper"], "held_out": r["held_out"],
            "level": r["level"], "k": sh["k"], "n_instructions": sh["n_instructions"],
            "samples_min": sh["samples_per_cell"]["min"],
            "samples_median": sh["samples_per_cell"]["median"],
            "samples_max": sh["samples_per_cell"]["max"], "n_axes": sh["n_axes"],
            "n_responses": sh["n_responses"], "documented_target": r["documented_target"] or "",
            "roster_documented_target": r["roster_documented_target"] or "",
            "roster_key": r["roster_key"], "partA_run": r["partA_run"] or "",
            "partA_seat": r["partA_seat"] or "", "partA_sha256_match": r["partA_sha256_match"],
            "registered_S": reg.get("S", ""), "registered_p": reg.get("p", ""),
            "registered_named": reg.get("named", reg.get("named_by_rule", "")) or "",
            "target_only_median_S": tom.get("S", ""), "target_only_median_p": tom.get("p", ""),
            "target_only_median_argmax": tom.get("argmax_candidate", "") or "",
            "ua_reference_free_p": ua.get("p", ""), "ua_reference_free_named": ua.get("named", "") or "",
            "sha256_verdicts": r["sha256"]["verdicts"]})
    save_new_text(REGISTRY_DIR / "subjects_summary.csv", buf.getvalue())
    print(f"wrote {SUBJECTS_JSON} ({len(records)} subjects, {len(arms)} embedding arms, "
          f"{len(rosters)} rosters)")


if __name__ == "__main__":
    main()
