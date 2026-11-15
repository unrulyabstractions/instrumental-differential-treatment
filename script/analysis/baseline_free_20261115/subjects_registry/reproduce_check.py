"""The input reproduction gate of the baseline-free workflow. No spend.

    .venv/bin/python -m script.analysis.baseline_free_20261115.subjects_registry.reproduce_check

Run after ``build_registry`` and ``reproduce_partA``. Every family reads its
inputs through the registry, so this gate checks that the registry still
describes the data on disk and that its copied loaders reproduce every stored
result they overlap:

1. paths: every path the registry names resolves;
2. sha256: every subject file and every embedding file still hashes to the
   registry's value, and each of the 30 partA runs still hashes to partA's meta;
3. stage 6: each table's firings and candidate count equal the seat block of its
   stage-6 ``comparison_summary.json``, and the seat names match the file stems;
4. statistics: all 210 partA tasks match partA field for field
   (``partA_reproduction.json``); the registered test equals stage 6 (S, p,
   named) and the target-only median test equals the stored
   ``reference_free.json`` seats (S, p);
5. user awareness: the base-free max test and the detachment test, rerun on the
   three served subjects' grades, equal ``user_awareness_detection.json``;
6. embeddings: the digest of every stored arm (15 runs, target and base, names
   kept and masked) and of the five fresh base sets equals the digest stored
   beside its vectors, and the vector count equals the row count;
7. pooled bases: the row counts and sample sets of bases A, B, C1, C1 s0-11 and
   C2 equal the pooled-base comparison's;
8. rosters and placebo: documented targets are candidates, base A is one file,
   and a placebo split is reproducible and partitions every cell.

A failed check is reported, never skipped. Writes, once, under
``out/main/baseline_free_20261115/subjects_registry/``: ``reproduce_check.json``,
``checks/<subject_id>.json`` and ``reproduce_summary.csv``.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import numpy as np

from script.analysis.baseline_free_20261115.common.settings import (ALPHA, N_PERM,
                                                                   REGISTRY_DIR,
                                                                   SUBJECTS_JSON,
                                                                   save_new_json,
                                                                   save_new_text,
                                                                   settings_block)
from script.analysis.baseline_free_20261115.common.subjects import (
    _abs, build_table, load_subject_table, placebo_halves, sha256)
from src.common.file_io import load_json, read_jsonl
from src.compare.candidate_detachment_statistic import candidate_detachment_test
from src.compare.placebo_calibration import cell_sizes
from src.compare.reference_free_max_statistic import reference_free_max_test
from src.geometry.paired_response_records import load_arm_records
from src.geometry.response_embedding_cache import _digest

OUT = REGISTRY_DIR / "reproduce_check.json"
PARTA_REPRO = REGISTRY_DIR / "partA_reproduction.json"
POOLED_COMPARE = "out/main/auditbench/pooled_base_20261113/compare/compare_summary.json"
POOLED_NAMES = {"base_A": "A", "base_B": "B", "base_C1": "C1", "base_C1_s0_11": "C1s0-11",
                "base_C2": "C2"}
PATH_FIELDS = ("verdicts", "base", "responses", "base_responses", "summary",
               "reference_free", "ua_detection")


def _seat(path: str) -> str:
    return Path(path).stem.removeprefix("verdicts_")


def check_paths_and_sha(reg: dict) -> tuple[list[dict], list[dict]]:
    subj_rows, arm_rows = [], []
    for s in reg["subjects"]:
        paths = {k: s[k] for k in PATH_FIELDS if s.get(k)}
        if s["axes"].startswith("out/"):
            paths["axes"] = s["axes"]
        for k, p in paths.items():
            exists = _abs(p).exists()
            now = sha256(p) if exists else None
            subj_rows.append({"subject_id": s["subject_id"], "field": k, "path": p,
                              "exists": exists, "sha256_registry": s["sha256"].get(k),
                              "sha256_now": now, "match": exists and now == s["sha256"].get(k)})
    for a in reg["embedding_arms"]:
        for k, h in a["sha256"].items():
            p = a[k]
            exists = _abs(p).exists()
            now = sha256(p) if exists else None
            arm_rows.append({"arm_id": a["arm_id"], "field": k, "path": p, "exists": exists,
                             "sha256_registry": h, "sha256_now": now,
                             "match": exists and now == h})
    return subj_rows, arm_rows


def check_partA_meta(reg: dict) -> list[dict]:
    meta = load_json(_abs(reg["inputs"]["partA"]))["runs"]
    rows = []
    for key, m in sorted(meta.items()):
        t, b = sha256(m["target"]), sha256(m["base"]) if m["base"] else None
        rows.append({"run": key, "target_match": t == m["sha256_target"],
                     "base_match": b == m["sha256_base"],
                     "match": t == m["sha256_target"] and b == m["sha256_base"]})
    return rows


def check_stage6(reg: dict) -> list[dict]:
    """Each table's firings and candidate count against its stage-6 seat block."""
    by = {s["subject_id"]: s for s in reg["subjects"]}
    rows = []
    for s in reg["subjects"]:
        summary = s["summary"]
        if not summary and s["category"] == "BASE" and s["partA_run"] in by:
            summary = by[s["partA_run"]]["summary"]
        if not summary:
            continue
        d = load_json(_abs(summary))
        seat, lvl = _seat(s["verdicts"]), f"L{s['level']}"
        block = (d["seats"].get(seat) or {}).get(lvl)
        t = build_table(s["verdicts"], s["axes"], s["level"], s["s_max"], s["drop_failed"])
        row = {"subject_id": s["subject_id"], "summary": summary, "seat": seat, "level": lvl,
               "stage6_firings": block and block.get("firings"),
               "table_firings": int(t.counts.sum()),
               "stage6_n_groups": block and block.get("n_groups"), "table_k": len(t.principals),
               "stage6_n_axes": d.get("n_axes"), "table_n_axes": len(t.axes)}
        rc = d["reference_contrast"]
        if s["category"] in ("ORG", "NULL"):
            row["seat_names_match"] = (rc["target"] == seat and rc["reference"] == _seat(s["base"]))
        else:
            row["seat_names_match"] = rc["reference"] == seat or seat in d["seats"]
        row["match"] = bool(block) and row["stage6_firings"] == row["table_firings"] and \
            row["stage6_n_groups"] == row["table_k"] and \
            row["stage6_n_axes"] == row["table_n_axes"] and row["seat_names_match"]
        rows.append(row)
    return rows


def check_statistics(reg: dict) -> tuple[dict, list[dict]]:
    if not PARTA_REPRO.exists():
        raise SystemExit(f"{PARTA_REPRO} is missing; run reproduce_partA first")
    rep = load_json(PARTA_REPRO)
    res = rep["results"]
    rows = []
    for s in reg["subjects"]:
        st = s["stored"]
        if s["partA_run"] is None:
            continue
        if s["partA_seat"] == "target":
            reg_got = res.get(f"{s['partA_run']}|registered|full")
            med_got = res.get(f"{s['partA_run']}|target_only_median|full")
        else:
            reg_got = None
            src = (st["target_only_median_partA"] or {}).get("source", "")
            med_got = res.get(src.split("results.")[-1]) if src else None
        row = {"subject_id": s["subject_id"]}
        if reg_got and st["registered"] and s["category"] != "BASE":
            want = st["registered"]
            named_want = want.get("named", want.get("named_by_rule"))
            row.update({"registered_S": reg_got["S"], "registered_p": reg_got["p"],
                        "registered_named": reg_got["named_by_rule"],
                        "registered_stored_S": want["S"], "registered_stored_p": want["p"],
                        "registered_stored_named": named_want,
                        "registered_source": want["source"],
                        "registered_match": reg_got["S"] == want["S"] and
                        reg_got["p"] == want["p"] and reg_got["named_by_rule"] == named_want})
        if med_got:
            row.update({"median_S": med_got["S"], "median_p": med_got["p"],
                        "median_argmax": med_got["argmax_candidate"],
                        "median_named": med_got["named_by_rule"]})
            rf = st["reference_free_json"]
            if rf:
                row.update({"median_stored_S": rf["S"], "median_stored_p": rf["p"],
                            "median_source": rf["source"],
                            "median_match_reference_free_json": med_got["S"] == rf["S"]
                            and med_got["p"] == rf["p"]})
        rows.append(row)
    summary = {"n_tasks": rep["n_tasks"], "n_match_partA": rep["n_match"],
               "n_differ": rep["n_differ"], "differing_fields": rep["differing_fields"],
               "partA_sha256": rep["partA_sha256"], "reproduction_settings": rep["settings"]}
    return summary, rows


def check_user_awareness(reg: dict) -> list[dict]:
    rows = []
    for s in reg["subjects"]:
        if s["category"] != "UA":
            continue
        det = load_json(_abs(s["ua_detection"]))
        t = load_subject_table(s["subject_id"])
        all_pairs = len(t.principals) * len(t.axes)
        rf = reference_free_max_test(t, n_permutations=N_PERM, seed=det["seed"], top=all_pairs)
        dt = candidate_detachment_test(t, n_permutations=N_PERM, seed=det["seed"])
        want, wd = det["reference_free"], det["reference_free"]["detachment"]
        n_rows = sum(1 for _ in read_jsonl(_abs(s["verdicts"])))
        n_failed = sum(1 for r in read_jsonl(_abs(s["verdicts"])) if r.get("failed"))
        row = {"subject_id": s["subject_id"], "subject": det["subject"],
               "n_rows": n_rows, "n_failed_rows": n_failed, "n_rows_used": int(t.n_responses),
               "max_S": rf["statistic"], "max_p": rf["p_family_wise"], "max_named": rf["named"],
               "max_named_axis": rf["named_axis"], "max_alpha": rf["alpha"],
               "max_stored_S": want["statistic"], "max_stored_p": want["p_family_wise"],
               "max_stored_named": want["named"],
               "detachment_S": dt["statistic"], "detachment_p": dt["p_family_wise"],
               "detachment_named": dt["named"], "detachment_leading": dt.get("leading"),
               "detachment_stored_S": wd["statistic"], "detachment_stored_p": wd["p_family_wise"],
               "detachment_stored_named": wd["named"]}
        row["match"] = (rf["statistic"] == want["statistic"] and
                        rf["p_family_wise"] == want["p_family_wise"] and
                        rf["named"] == want["named"] and rf["named_axis"] == want["named_axis"] and
                        dt["statistic"] == wd["statistic"] and
                        dt["p_family_wise"] == wd["p_family_wise"] and dt["named"] == wd["named"])
        rows.append(row)
    return rows


def check_embeddings(reg: dict) -> list[dict]:
    rows, records = [], {}
    for a in reg["embedding_arms"]:
        meta = json.loads(_abs(a["meta"]).read_text())
        if a["run"].startswith("base_set_"):
            texts = [json.loads(x) for x in _abs(a["texts"]).open(encoding="utf-8") if x.strip()]
            keys, body = [r["key"] for r in texts], [r["text"] for r in texts]
            order_ok = True
        else:
            k = (a["run"], a["arm"])
            if k not in records:
                axes = [x["axis_id"] for x in load_json(_abs(a["axes"]))["axes"]]
                records[k] = load_arm_records(_abs(a["responses"]), _abs(a["verdicts"]), axes)
            r = records[k]
            keys = r.keys
            if a["variant"] == "unmasked":
                body, order_ok = r.texts, True
            else:
                masked = [json.loads(x) for x in _abs(a["texts"]).open(encoding="utf-8")
                          if x.strip()]
                order_ok = [x["key"] for x in masked] == r.keys
                body = [x["text"] for x in masked]
        digest = _digest(keys, body)
        n_vec = int(np.load(_abs(a["npy"]), mmap_mode="r").shape[0])
        row = {"arm_id": a["arm_id"], "n_rows": len(keys), "stored_n": meta["n"],
               "n_vectors": n_vec, "digest_now": digest, "digest_stored": meta["digest"],
               "rows_in_order": order_ok}
        row["match"] = (digest == meta["digest"] and meta["n"] == len(keys) == n_vec
                        and order_ok)
        rows.append(row)
        print(f"  embedding {a['arm_id']:60s} {'MATCH' if row['match'] else 'DIFF'}", flush=True)
    return rows


def check_pooled(reg: dict) -> list[dict]:
    pc = load_json(_abs(POOLED_COMPARE))
    by = {s["subject_id"]: s for s in reg["subjects"]}
    rows = []
    for sid, name in POOLED_NAMES.items():
        s = by[sid]
        t = build_table(s["verdicts"], s["axes"], s["level"], s["s_max"], s["drop_failed"])
        from script.analysis.baseline_free_20261115.common.subjects import rows_of
        samples = sorted({int(r["s"]) for r in rows_of(s["verdicts"], s["level"], s["s_max"])})
        rows.append({"subject_id": sid, "pooled_name": name, "table_rows": int(t.n_responses),
                     "pooled_rows": pc["base_rows"][name], "samples": samples,
                     "pooled_samples": pc["base_samples"][name],
                     "match": int(t.n_responses) == pc["base_rows"][name]
                     and samples == pc["base_samples"][name]})
    return rows


def check_rosters_and_placebo(reg: dict) -> dict:
    by = {s["subject_id"]: s for s in reg["subjects"]}
    targets = []
    for s in reg["subjects"]:
        for field in ("documented_target", "roster_documented_target"):
            if s[field]:
                targets.append({"subject_id": s["subject_id"], "field": field,
                                "target": s[field],
                                "match": s[field] in s["shape"]["candidates"]})
    # A placebo split: deterministic, a partition, every cell on both sides.
    plac = []
    for sid in ("base_A", "auditbench_flattery", "base_1p5b__calibration_informed"):
        t = load_subject_table(sid)
        a1, b1 = placebo_halves(sid, t, 0)
        a2, b2 = placebo_halves(sid, t, 0)
        a3, _ = placebo_halves(sid, t, 1)
        same = (np.array_equal(a1.fired, a2.fired) and np.array_equal(a1.group_of, a2.group_of)
                and np.array_equal(b1.block_of, b2.block_of))
        sizes_a, sizes_b, sizes = cell_sizes(a1), cell_sizes(b1), cell_sizes(t)
        plac.append({"subject_id": sid, "deterministic": bool(same),
                     "replicates_differ": not np.array_equal(a1.fired, a3.fired),
                     "partition": bool(np.array_equal(sizes_a + sizes_b, sizes)),
                     "every_cell_both_halves": bool(sizes_a.min() >= 1 and sizes_b.min() >= 1),
                     "n_a": int(a1.n_responses), "n_b": int(b1.n_responses)})
    for p in plac:
        p["match"] = p["deterministic"] and p["replicates_differ"] and p["partition"] and \
            p["every_cell_both_halves"]
    ident = reg["base_A_byte_identical_to"]
    return {"documented_targets": targets, "placebo": plac,
            "base_A_byte_identical": {"runs": ident, "match": all(ident.values())},
            "co_roster_members": next(r["subjects"] for r in reg["rosters"].values()
                                      if r["documented_target"] == "anthropic"),
            "match": all(x["match"] for x in targets) and all(p["match"] for p in plac)
            and all(ident.values()) and bool(by)}


def main() -> None:
    if OUT.exists():
        raise SystemExit(f"{OUT} exists; never overwritten")
    reg = load_json(SUBJECTS_JSON)
    print("paths and sha256", flush=True)
    subj_sha, arm_sha = check_paths_and_sha(reg)
    meta = check_partA_meta(reg)
    print("stage 6 seats", flush=True)
    s6 = check_stage6(reg)
    print("statistics", flush=True)
    stat_summary, stat_rows = check_statistics(reg)
    print("user awareness", flush=True)
    ua = check_user_awareness(reg)
    print("embeddings", flush=True)
    emb = check_embeddings(reg)
    pooled = check_pooled(reg)
    ros = check_rosters_and_placebo(reg)

    def ok(rows, key="match"):
        return {"n": len(rows), "n_match": sum(bool(r.get(key)) for r in rows),
                "failures": [r for r in rows if not r.get(key)]}

    reg_rows = [r for r in stat_rows if "registered_match" in r]
    med_rows = [r for r in stat_rows if "median_match_reference_free_json" in r]
    sections = {
        "paths_and_sha256_subjects": ok(subj_sha),
        "paths_and_sha256_embedding_files": ok(arm_sha),
        "partA_meta_sha256": ok(meta),
        "stage6_seats": ok(s6),
        "partA_tasks": {"n": stat_summary["n_tasks"], "n_match": stat_summary["n_match_partA"],
                        "failures": stat_summary["differing_fields"]},
        "registered_vs_stored": ok(reg_rows, "registered_match"),
        "target_only_median_vs_reference_free_json": ok(med_rows,
                                                        "median_match_reference_free_json"),
        "user_awareness": ok(ua),
        "embedding_digests": ok(emb),
        "pooled_base_rows": ok(pooled),
        "rosters_and_placebo": {"n": 1, "n_match": int(ros["match"]),
                                "failures": [] if ros["match"] else ["see rosters_and_placebo"]},
    }
    all_pass = all(v["n_match"] == v["n"] for v in sections.values())
    record = {
        "what": "input reproduction gate of the baseline-free workflow",
        "settings": settings_block(alpha_note="alpha 0.01 for the registered and partA "
                                              "tests; the user-awareness detection reran at "
                                              "its stored alpha 0.05", ua_alpha=0.05),
        "registry": str(SUBJECTS_JSON.relative_to(REGISTRY_DIR.parents[3])),
        "registry_sha256": sha256(SUBJECTS_JSON),
        "registry_code_commit": reg["settings"]["code_commit"],
        "all_pass": all_pass,
        "sections": {k: {"n": v["n"], "n_match": v["n_match"]} for k, v in sections.items()},
        "failures": {k: v["failures"] for k, v in sections.items() if v["failures"]},
        "detail": {"paths_and_sha256_subjects": subj_sha,
                   "paths_and_sha256_embedding_files": arm_sha,
                   "partA_meta_sha256": meta, "stage6_seats": s6,
                   "partA_tasks": stat_summary, "statistics_by_subject": stat_rows,
                   "user_awareness": ua, "embedding_digests": emb,
                   "pooled_base_rows": pooled, "rosters_and_placebo": ros},
    }
    # One JSON per subject with its own rows.
    for s in reg["subjects"]:
        sid = s["subject_id"]
        save_new_json(REGISTRY_DIR / "checks" / f"{sid}.json", {
            "subject_id": sid, "category": s["category"], "role": s["role"],
            "settings": {"seed": record["settings"]["seed"],
                         "n_permutations": record["settings"]["n_permutations"],
                         "alpha": record["settings"]["alpha"],
                         "code_commit": record["settings"]["code_commit"]},
            "sha256": [r for r in subj_sha if r["subject_id"] == sid],
            "stage6": [r for r in s6 if r["subject_id"] == sid],
            "statistics": [r for r in stat_rows if r["subject_id"] == sid],
            "user_awareness": [r for r in ua if r["subject_id"] == sid],
            "pooled_base_rows": [r for r in pooled if r["subject_id"] == sid],
            "all_pass": all(r["match"] for r in subj_sha if r["subject_id"] == sid)
            and all(r["match"] for r in s6 if r["subject_id"] == sid)
            and all(r.get("registered_match", True) and
                    r.get("median_match_reference_free_json", True)
                    for r in stat_rows if r["subject_id"] == sid)
            and all(r["match"] for r in ua if r["subject_id"] == sid)
            and all(r["match"] for r in pooled if r["subject_id"] == sid)})
    save_new_json(OUT, record)

    # Summary table: one row per subject.
    buf = io.StringIO()
    cols = ["subject_id", "category", "role", "in_paper", "level", "k", "n_instructions",
            "samples_per_cell", "n_axes", "sha256_match", "stage6_match", "registered_S",
            "registered_p", "registered_named", "registered_stored_p", "registered_match",
            "median_S", "median_p", "median_argmax", "median_stored_p", "median_match",
            "ua_max_p", "ua_max_named", "ua_detachment_p", "ua_match"]
    w = csv.DictWriter(buf, fieldnames=cols)
    w.writeheader()
    for s in reg["subjects"]:
        sid, sh = s["subject_id"], s["shape"]
        st = next((r for r in stat_rows if r["subject_id"] == sid), {})
        u = next((r for r in ua if r["subject_id"] == sid), {})
        s6r = [r for r in s6 if r["subject_id"] == sid]
        sp = sh["samples_per_cell"]
        w.writerow({
            "subject_id": sid, "category": s["category"], "role": s["role"],
            "in_paper": s["in_paper"], "level": s["level"], "k": sh["k"],
            "n_instructions": sh["n_instructions"],
            "samples_per_cell": f"{sp['min']}-{sp['max']}" if sp["min"] != sp["max"] else sp["min"],
            "n_axes": sh["n_axes"],
            "sha256_match": all(r["match"] for r in subj_sha if r["subject_id"] == sid),
            "stage6_match": (all(r["match"] for r in s6r) if s6r else ""),
            "registered_S": st.get("registered_S", ""), "registered_p": st.get("registered_p", ""),
            "registered_named": st.get("registered_named", "") or "",
            "registered_stored_p": st.get("registered_stored_p", ""),
            "registered_match": st.get("registered_match", ""),
            "median_S": st.get("median_S", ""), "median_p": st.get("median_p", ""),
            "median_argmax": st.get("median_argmax", "") or "",
            "median_stored_p": st.get("median_stored_p", ""),
            "median_match": st.get("median_match_reference_free_json", ""),
            "ua_max_p": u.get("max_p", ""), "ua_max_named": u.get("max_named", "") or "",
            "ua_detachment_p": u.get("detachment_p", ""), "ua_match": u.get("match", "")})
    save_new_text(REGISTRY_DIR / "reproduce_summary.csv", buf.getvalue())
    print(json.dumps(record["sections"], indent=1))
    print("ALL PASS" if all_pass else f"FAILURES: {list(record['failures'])}")


if __name__ == "__main__":
    main()
