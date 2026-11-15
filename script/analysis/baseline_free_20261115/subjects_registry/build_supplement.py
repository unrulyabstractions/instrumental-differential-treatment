"""Build the registry supplement: target groups, two-candidate ties, embedding links. No spend.

    .venv/bin/python -m script.analysis.baseline_free_20261115.subjects_registry.build_supplement

``subjects.json`` is never rebuilt, because the families record its sha256. This
script writes ``supplement.json`` beside it, which names the registry file and
sha256 it extends and adds four things:

1. ``target_groups``: each subject's pre-registered target. An organism's
   documented target is one candidate. Its roster target applies that candidate
   to every subject sampled on the same candidates, instructions and axes. The
   user-awareness subjects get the frozen safety group of
   ``src/external/user_awareness_materials.IDENTITIES`` (the identities whose
   ``group`` is ``safety``), with the general-population identities as the
   contrast group. Every member must be a candidate of the subject's table.
2. ``two_candidate``: the subjects with k = 2. With two candidates the
   one-vs-rest gap of one candidate is minus the other's at every axis, so both
   have the same |t| and the argmax candidate is a tie-break. For each such
   subject and each stored test this records the peak axis, the signed t of the
   argmax candidate, and the candidate that is higher at the peak.
3. ``embedding_links``: for every stored embedding arm, the subject whose replies
   it embeds, the file its texts come from, how its rows relate to that
   subject's judged rows, the arms with the same texts (same digest), and the
   arms with byte-identical vectors.
4. ``canonical_base_A_arm``: the nine AuditBench runs on the optimism roster each
   embedded base A's replies in their own API calls, so the nine copies hold the
   same texts and slightly different vectors. The canonical copy is the first
   null's (``auditbench_ai_welfare_poisoning``), the copy the stored embedding
   calibration pairs every base against. ``base_A_copies`` measures how far the
   other copies sit from it.

Every file read is gated on the sha256 the registry recorded. Writes
``supplement.json`` once and refuses to overwrite it.
"""

from __future__ import annotations

import numpy as np

from script.analysis.baseline_free_20261115.common.settings import (REGISTRY_DIR,
                                                                   SUBJECTS_JSON,
                                                                   save_new_json,
                                                                   settings_block)
from script.analysis.baseline_free_20261115.common.subjects import (
    SUPPLEMENT_JSON, DataMoved, _abs, load_subject_table, rows_of, sha256)
from src.common.file_io import load_json, read_jsonl
from src.compare.paired_excess_measures import cell_rates, standardized_excess
from src.compare.reference_free_max_statistic import reference_free_effect
from src.geometry.paired_response_records import load_arm_records
from src.geometry.response_embedding_cache import _digest

UA_MATERIALS = "src/external/user_awareness_materials.py"
PARTA_REPRO = REGISTRY_DIR / "partA_reproduction.json"
OPTIMISM_RUNS = ("auditbench_contextual_optimism", *(f"auditbench_{c}" for c in (
    "ai_welfare_poisoning", "animal_welfare", "anti_ai_regulation", "defend_objects",
    "defer_to_users", "emotional_bond", "flattery", "hallucinates_citations")))
CANONICAL_BASE_A_RUN = "auditbench_ai_welfare_poisoning"
CALIBRATION_ANALYZE = "script/analysis/embedding_calibration_20261114/analyze.py"
MANIFEST = "out/main/auditbench/nullext/embedding_calibration_20261114/texts/manifest.json"
#: Base set -> (subject whose replies it embeds, relation of its texts to them).
BASE_SET_SUBJECT = {"B": ("base_B", "the subject's replies"),
                    "C1": ("base_C1", "the subject's replies"),
                    "C2": ("base_C2", "the subject's replies"),
                    "C1cut": ("base_C1", "the subject's replies cut to their first 400 tokens"),
                    "C2cut": ("base_C2", "the subject's replies cut to their first 400 tokens")}


def _gate(path: str, want: str, what: str) -> None:
    got = sha256(path)
    if got != want:
        raise DataMoved(f"{what}: {path} sha256 {got} differs from {want}; stop")


# ----------------------------------------------------------------------------
# 1. Target groups
# ----------------------------------------------------------------------------
def target_groups(reg: dict) -> dict:
    from src.external.user_awareness_materials import IDENTITIES
    safety = sorted(i["key"] for i in IDENTITIES if i["group"] == "safety")
    general = sorted(i["key"] for i in IDENTITIES if i["group"] == "general")
    other = sorted(i["key"] for i in IDENTITIES if i["group"] not in ("safety", "general"))
    out = {}
    for s in reg["subjects"]:
        sid, cands = s["subject_id"], s["shape"]["candidates"]
        if s["category"] == "UA":
            det = load_json(_abs(s["ua_detection"]))
            groups = {k: v["group"] for k, v in det["identities"].items()}
            if sorted(k for k, g in groups.items() if g == "safety") != safety:
                raise SystemExit(f"{sid}: stored safety group differs from the materials")
            if sorted(k for k, g in groups.items() if g == "general") != general:
                raise SystemExit(f"{sid}: stored general group differs from the materials")
            rec = {"kind": "group", "group": "safety", "candidates": safety,
                   "contrast_group": "general", "contrast_candidates": general,
                   "excluded_candidates": other,
                   "direction": "lower grades for the safety group (Transluce's finding)",
                   "source": f"{UA_MATERIALS} IDENTITIES[*].group",
                   "source_sha256": sha256(UA_MATERIALS)}
        elif s["documented_target"]:
            rec = {"kind": "candidate", "candidates": [s["documented_target"]],
                   "source": "the organism's documented target"}
        elif s["roster_documented_target"]:
            by = next(r for r in reg["rosters"].values() if sid in r["subjects"])
            rec = {"kind": "candidate", "candidates": [s["roster_documented_target"]],
                   "source": f"roster target, documented by {by['documented_by']}"}
        else:
            rec = {"kind": "none", "candidates": [], "source": "no documented target"}
        missing = [c for c in rec["candidates"] + rec.get("contrast_candidates", [])
                   if c not in cands]
        if missing:
            raise SystemExit(f"{sid}: target-group members {missing} are not candidates")
        out[sid] = rec
    return out


# ----------------------------------------------------------------------------
# 2. Two-candidate ties
# ----------------------------------------------------------------------------
def _tie_row(r: dict, cands: list[str], source: str) -> dict:
    arg, t = r["argmax_candidate"], r["argmax_t"]
    other = next(c for c in cands if c != arg)
    return {"S": r["S"], "p": r["p"], "argmax_candidate": arg, "peak_axis": r["argmax_axis"],
            "argmax_t": t, "other_candidate": other,
            "other_t_at_peak": -t if t is not None else None,
            "higher_at_peak": (arg if t > 0 else other) if t else None,
            "source": source}


def two_candidate(reg: dict, rep: dict) -> dict:
    res = rep["results"]
    out = {}
    for s in reg["subjects"]:
        if s["shape"]["k"] != 2:
            continue
        cands = s["shape"]["candidates"]
        rows = {}
        if s["partA_run"] and s["partA_seat"] == "target":
            for kind, key in (("registered", "registered"), ("target_only_median",
                                                              "target_only_median")):
                rid = f"{s['partA_run']}|{key}|full"
                if rid in res:
                    rows[kind] = _tie_row(res[rid], cands, f"partA_reproduction.json results.{rid}")
        elif s["partA_run"]:
            src = (s["stored"]["target_only_median_partA"] or {}).get("source", "")
            rid = src.split("results.")[-1] if src else None
            if rid in res:
                rows["target_only_median"] = _tie_row(res[rid], cands,
                                                      f"partA_reproduction.json results.{rid}")
        # The gap identity behind the tie, checked on the table itself: with two
        # candidates, each one's t against the median of the others is minus the
        # other's at every axis.
        rates, order, _ = cell_rates(load_subject_table(s["subject_id"]))
        t_obs, _, _ = standardized_excess(reference_free_effect(rates))
        antisym = bool(np.allclose(t_obs[0], -t_obs[1], equal_nan=True))
        if not antisym:
            raise SystemExit(f"{s['subject_id']}: k = 2 but the two t rows are not opposite")
        for r in rows.values():
            if r["argmax_candidate"] not in order:
                raise SystemExit(f"{s['subject_id']}: argmax {r['argmax_candidate']} not a candidate")
        out[s["subject_id"]] = {"candidates": cands, "tests": rows,
                                "t_rows_opposite_at_every_axis": antisym,
                                "abs_t_equal_for_both_candidates": antisym}
    return out


# ----------------------------------------------------------------------------
# 3. Embedding links
# ----------------------------------------------------------------------------
def _keys_texts(a: dict, records: dict) -> tuple[list[str], list[str]]:
    if a["run"].startswith("base_set_"):
        rows = list(read_jsonl(_abs(a["texts"])))
        return [r["key"] for r in rows], [r["text"] for r in rows]
    k = (a["run"], a["arm"])
    if k not in records:
        axes = [x["axis_id"] for x in load_json(_abs(a["axes"]))["axes"]]
        records[k] = load_arm_records(_abs(a["responses"]), _abs(a["verdicts"]), axes)
    r = records[k]
    if a["variant"] == "unmasked":
        return list(r.keys), list(r.texts)
    rows = list(read_jsonl(_abs(a["texts"])))
    return [x["key"] for x in rows], [x["text"] for x in rows]


def _subject_keys(s: dict) -> set[str]:
    return {f"{r['prompt_id']}#{int(r['s'])}" for r in rows_of(s["verdicts"], s["level"],
                                                               s["s_max"], s["drop_failed"])}


def embedding_links(reg: dict) -> dict:
    subs = {s["subject_id"]: s for s in reg["subjects"]}
    by_sha = {}
    for s in reg["subjects"]:
        if s["category"] == "BASE" and s["s_max"] is None:
            by_sha.setdefault(s["sha256"]["verdicts"], []).append(s["subject_id"])
    manifest = load_json(_abs(MANIFEST))
    records: dict = {}
    links, digests, npy_sha = {}, {}, {}
    for a in reg["embedding_arms"]:
        for f, h in a["sha256"].items():
            _gate(a[f], h, a["arm_id"])
        digests[a["arm_id"]] = a["stored_digest"]
        npy_sha[a["arm_id"]] = a["sha256"]["npy"]
    for a in reg["embedding_arms"]:
        aid = a["arm_id"]
        keys, texts = _keys_texts(a, records)
        if _digest(keys, texts) != a["stored_digest"] or len(keys) != a["stored_n"]:
            raise DataMoved(f"{aid}: texts no longer hash to the stored embedding digest")
        if a["run"].startswith("base_set_"):
            name = a["run"].removeprefix("base_set_")
            sid, rel = BASE_SET_SUBJECT[name]
            src = manifest["sets"][f"{name}_{a['variant']}"]["source"]
            texts_source = (src if a["variant"] == "unmasked" else
                            f"{src}, names masked with the optimism roster's mask")
        elif a["arm"] == "target":
            sid, rel = a["run"], "the subject's replies"
            if subs[sid]["verdicts"] != a["verdicts"]:
                raise SystemExit(f"{aid}: verdicts {a['verdicts']} differ from {sid}'s")
            texts_source = (a["responses"] if a["variant"] == "unmasked" else
                            f"{a['responses']}, names masked ({a['texts']})")
        else:
            cand = by_sha.get(sha256(a["verdicts"]), [])
            if len(cand) != 1:
                raise SystemExit(f"{aid}: base verdicts match BASE subjects {cand}")
            sid, rel = cand[0], "the subject's replies"
            texts_source = (a["responses"] if a["variant"] == "unmasked" else
                            f"{a['responses']}, names masked ({a['texts']})")
        sk = _subject_keys(subs[sid])
        ek = set(keys)
        if ek == sk:
            rows_rel = "the same rows as the subject's judged rows"
        elif sk < ek:
            rows_rel = "a superset of the subject's judged rows"
        elif ek < sk:
            rows_rel = "a subset of the subject's judged rows"
        else:
            rows_rel = "rows that overlap the subject's judged rows"
        links[aid] = {
            "subject_id": sid, "texts": rel, "texts_source": texts_source,
            "n_embedded_rows": len(keys), "n_subject_rows": len(sk),
            "n_shared_rows": len(ek & sk), "rows": rows_rel,
            "digest_equals_stored": True,
            "same_texts_as": sorted(x for x, d in digests.items()
                                    if d == digests[aid] and x != aid),
            "same_vectors_as": sorted(x for x, h in npy_sha.items()
                                      if h == npy_sha[aid] and x != aid),
            "canonical": None}
        print(f"  {aid:58s} -> {sid:32s} {rows_rel} ({len(keys)} vs {len(sk)})", flush=True)
    return links


def base_A_copies(reg: dict, links: dict) -> tuple[dict, dict]:
    arms = {a["arm_id"]: a for a in reg["embedding_arms"]}
    canon, copies = {}, {}
    for v in ("unmasked", "masked"):
        cid = f"{CANONICAL_BASE_A_RUN}:base:{v}"
        ids = [f"{r}:base:{v}" for r in OPTIMISM_RUNS]
        if any(links[i]["subject_id"] != "base_A" for i in ids):
            raise SystemExit(f"{v}: an optimism-roster base arm is not base_A")
        ref = np.load(_abs(arms[cid]["npy"])).astype(np.float64)
        ref_n = ref / np.linalg.norm(ref, axis=1, keepdims=True)
        rows = {}
        for i in ids:
            x = np.load(_abs(arms[i]["npy"])).astype(np.float64)
            same_digest = arms[i]["stored_digest"] == arms[cid]["stored_digest"]
            if x.shape != ref.shape:
                raise SystemExit(f"{i}: shape {x.shape} differs from {cid} {ref.shape}")
            cos = np.sum(ref_n * (x / np.linalg.norm(x, axis=1, keepdims=True)), axis=1)
            ident = np.all(np.load(_abs(arms[i]["npy"])) == np.load(_abs(arms[cid]["npy"])),
                           axis=1)
            rows[i] = {"same_texts_as_canonical": bool(same_digest),
                       "n_rows": int(x.shape[0]),
                       "rows_bit_identical": int(ident.sum()),
                       "share_bit_identical": float(ident.mean()),
                       "cosine_min": float(cos.min()), "cosine_median": float(np.median(cos)),
                       "npy_sha256": arms[i]["sha256"]["npy"]}
        canon[v] = {"arm_id": cid, "run": CANONICAL_BASE_A_RUN,
                    "reason": ("the copy the stored embedding calibration pairs every base "
                               f"with ({CALIBRATION_ANALYZE}, _arms: NULLS[0])"),
                    "copies": ids}
        copies[v] = rows
        for i in ids:
            links[i]["canonical"] = i == cid
    return canon, copies


def main() -> None:
    if SUPPLEMENT_JSON.exists():
        raise SystemExit(f"{SUPPLEMENT_JSON} exists; never overwritten")
    reg_sha = sha256(SUBJECTS_JSON)
    reg = load_json(SUBJECTS_JSON)
    rep = load_json(PARTA_REPRO)
    print("target groups", flush=True)
    groups = target_groups(reg)
    print("two-candidate subjects", flush=True)
    ties = two_candidate(reg, rep)
    print("embedding links", flush=True)
    links = embedding_links(reg)
    canon, copies = base_A_copies(reg, links)
    if sha256(SUBJECTS_JSON) != reg_sha:
        raise DataMoved("subjects.json changed while the supplement was built; stop")
    record = {
        "what": "registry supplement of the baseline-free workflow (B72)",
        "settings": settings_block(),
        "extends": {"path": str(SUBJECTS_JSON.relative_to(REGISTRY_DIR.parents[3])),
                    "sha256": reg_sha},
        "inputs": {"partA_reproduction": str(PARTA_REPRO.relative_to(REGISTRY_DIR.parents[3])),
                   "partA_reproduction_sha256": sha256(PARTA_REPRO),
                   "user_awareness_materials": UA_MATERIALS,
                   "user_awareness_materials_sha256": sha256(UA_MATERIALS),
                   "embedding_manifest": MANIFEST, "embedding_manifest_sha256": sha256(MANIFEST),
                   "calibration_analyze": CALIBRATION_ANALYZE,
                   "calibration_analyze_sha256": sha256(CALIBRATION_ANALYZE)},
        "target_groups": groups,
        "two_candidate": ties,
        "embedding_links": links,
        "canonical_base_A_arm": canon,
        "base_A_copies": copies,
    }
    save_new_json(SUPPLEMENT_JSON, record)
    n_group = sum(1 for g in groups.values() if g["kind"] == "group")
    n_cand = sum(1 for g in groups.values() if g["kind"] == "candidate")
    print(f"wrote {SUPPLEMENT_JSON}: {len(groups)} target groups ({n_cand} candidate, "
          f"{n_group} group), {len(ties)} two-candidate subjects, {len(links)} arm links")


if __name__ == "__main__":
    main()
