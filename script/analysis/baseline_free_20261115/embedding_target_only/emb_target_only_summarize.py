"""Fold the per-subject results and placebos into the panel, the summary table and counts.

    uv run python <this file>

Reads ``runs/*.json``, ``placebo/*.json``, ``reproduce_check.json`` and the shared
ledger. Writes ``panel.json``, ``results.json``, ``emb_table.csv``,
``settings.json`` and ``readme_tables.md`` (the tables the README quotes), each new.

Panel (Level 3, max against max). The reference members are the eight AuditBench
null controls, read target-only on the same mask and variant. A subject's panel p is
(1 + members at or above it) / (members + 1), so its floor is 1/9; a member is
compared with the other seven (floor 1/8). Two statistics: the raw maximum gap norm,
comparable only among subjects sampled on the nulls' roster and prompts, and the
ratio of the maximum to its own permutation null's 95th percentile, which every
subject has. An extended panel adds the two synthetic-document nulls.
"""

from __future__ import annotations

import csv
import io
import json

import numpy as np

from emb_target_only_sources import (ALPHA, LAB_ROSTER_SUBJECTS, NULLS, OUT, PLACEBO_DIR,
                                     RUNS_DIR, SD_NULLS, VARIANTS, all_subjects,
                                     family_settings, masks_of, role_of, verdict_comparator)
from emb_target_only_stats import panel_p
from script.analysis.baseline_free_20261115.common.ledger import Ledger
from script.analysis.baseline_free_20261115.common.settings import save_new_json, save_new_text

FAMILY_KEY = "embedding_target_only"


def _load(sid):
    p = RUNS_DIR / f"{sid}.json"
    return json.loads(p.read_text()) if p.exists() else None


def _placebo(sid, mask):
    p = PLACEBO_DIR / f"placebo_{sid}_{mask}.json"
    return json.loads(p.read_text())["summary"] if p.exists() else None


def _panel(runs, members, sid, mask, v, field):
    vals = {m: runs[m]["masks"][mask]["variants"][v][field] for m in members
            if runs.get(m) and mask in runs[m]["masks"] and "variants" in runs[m]["masks"][mask]}
    if sid not in runs or mask not in runs[sid]["masks"] or "variants" not in runs[sid]["masks"][mask]:
        return None
    mine = runs[sid]["masks"][mask]["variants"][v][field]
    ref = [x for m, x in vals.items() if m != sid]
    return panel_p(mine, ref) if ref else None


def build_rows(runs):
    rows, panel = [], {}
    for sid in all_subjects():
        r = runs.get(sid)
        if r is None:
            continue
        vc = verdict_comparator(sid) or {}
        for mask in masks_of(sid):
            m = r["masks"].get(mask, {})
            if "variants" not in m:
                continue
            plc = _placebo(sid, mask)
            br = m.get("base_referenced")
            for v in VARIANTS:
                t = m["variants"][v]
                o = t["outlier"]
                pr = o.get("preregistered") or {}
                pan = {"ratio_8_nulls": _panel(runs, NULLS, sid, mask, v, "ratio_to_null_p95"),
                       "ratio_10_nulls": _panel(runs, NULLS + SD_NULLS, sid, mask, v,
                                                "ratio_to_null_p95")}
                if sid in LAB_ROSTER_SUBJECTS:
                    pan["raw_8_nulls"] = _panel(runs, NULLS, sid, mask, v, "statistic")
                    pan["raw_10_nulls"] = _panel(runs, NULLS + SD_NULLS, sid, mask, v, "statistic")
                panel[f"{sid}:{mask}:{v}"] = pan
                reg = r.get("registered") or {}
                row = {
                    "subject": sid, "role": role_of(sid), "mask": mask, "variant": v,
                    "k": t["k"], "n_cells": t["n_cells"], "statistic": t["statistic"],
                    "p": t["p"], "rejects_0.01": t["p"] < ALPHA,
                    # with two candidates both one-versus-rest gaps have one norm, so no
                    # candidate is named
                    "named": t["named"] if t["k"] >= 3 else None,
                    "ratio_to_null_p95": round(t["ratio_to_null_p95"], 4),
                    "grubbs_G": o.get("grubbs_G"), "grubbs_p_mc": (o.get("grubbs") or {}).get("p_mc"),
                    "grubbs_p_bonferroni": (o.get("grubbs") or {}).get("p_bonferroni_t"),
                    "grubbs_p_shuffle": o.get("grubbs_p_label_shuffle"),
                    "detachment_D": o.get("detachment_D"),
                    "detachment_mad": o.get("detachment_mad"),
                    "detachment_mad_p_shuffle": o.get("detachment_mad_p_label_shuffle"),
                    "preregistered": pr.get("candidate"), "prereg_rank": pr.get("rank"),
                    "prereg_dr_t": pr.get("t"), "prereg_dr_p": pr.get("p_one_sided"),
                    "panel_ratio_p": (pan["ratio_8_nulls"] or {}).get("p"),
                    "panel_ratio_floor": (pan["ratio_8_nulls"] or {}).get("floor"),
                    "panel_ratio_p_10": (pan["ratio_10_nulls"] or {}).get("p"),
                    "panel_raw_p": (pan.get("raw_8_nulls") or {}).get("p"),
                    "panel_raw_floor": (pan.get("raw_8_nulls") or {}).get("floor"),
                    "panel_raw_p_10": (pan.get("raw_10_nulls") or {}).get("p"),
                    "base_ref_p": br["p"] if br else None,
                    "base_ref_named": br["named"] if br else None,
                    "verdict_no_base_test": vc.get("test"), "verdict_no_base_p": vc.get("p"),
                    "verdict_no_base_named": vc.get("named"),
                    "registered_p": reg.get("p"), "registered_reject": reg.get("reject"),
                    "registered_argmax": reg.get("argmax"), "registered_named": reg.get("named"),
                    "placebo_machinery_p_le_0.01": (plc[v]["machinery"]["p_le_0.01"]["share"]
                                                     if plc else None),
                    "placebo_machinery_grubbs_le_0.01": ((plc[v]["machinery"]["grubbs_p_mc_le_0.01"]
                                                          or {}).get("share") if plc else None),
                    "placebo_stability_same": (plc[v]["stability"]["share_halves_name_same_candidate"]
                                               if plc else None),
                    "placebo_stability_full": (plc[v]["stability"]["share_halves_name_full_data_candidate"]
                                               if plc else None),
                }
                rows.append(row)
    return rows, panel


def _fires(rows, pred, field_ok):
    sel = [r for r in rows if pred(r)]
    return {"n": len(sel), "fires": sum(1 for r in sel if field_ok(r)),
            "subjects": sorted({r["subject"] for r in sel if field_ok(r)})}


def counts(rows):
    out = {}
    groups = {
        "positives": lambda r: r["role"] == "positive",
        "challenge": lambda r: r["role"] == "challenge",
        "nulls_auditbench": lambda r: r["subject"] in NULLS,
        "nulls_synthetic_document": lambda r: r["subject"] in SD_NULLS,
        "bases_as_targets": lambda r: r["role"] == "base_as_target",
        "served": lambda r: r["role"] == "served",
    }
    tests = {
        "target_only_p<0.01": lambda r: r["p"] < ALPHA,
        "grubbs_p_mc<=0.01": lambda r: r["grubbs_p_mc"] is not None and r["grubbs_p_mc"] <= ALPHA,
        "grubbs_p_shuffle<=0.01": lambda r: r["grubbs_p_shuffle"] is not None and r["grubbs_p_shuffle"] <= ALPHA,
        "prereg_dr_p<=0.01": lambda r: r["prereg_dr_p"] is not None and r["prereg_dr_p"] <= ALPHA,
        # the panel's smallest attainable p is its floor: 1/9, or 1/8 for a member
        "panel_ratio_at_floor": lambda r: (r["panel_ratio_p"] is not None
                                           and r["panel_ratio_p"] <= r["panel_ratio_floor"] + 1e-12),
        "panel_raw_at_floor": lambda r: (r["panel_raw_p"] is not None
                                         and r["panel_raw_p"] <= r["panel_raw_floor"] + 1e-12),
    }
    for mask in ("unmasked", "masked"):
        for v in VARIANTS:
            sub = [r for r in rows if r["mask"] == mask and r["variant"] == v]
            out[f"{mask}:{v}"] = {g: {t: _fires(sub, gp, tp) for t, tp in tests.items()}
                                  for g, gp in groups.items()}
            agree = []
            for r in sub:
                if r["role"] in ("positive", "challenge") and r["registered_p"] is not None:
                    agree.append({"subject": r["subject"], "registered_reject": r["registered_reject"],
                                  "registered_argmax": r["registered_argmax"],
                                  "emb_rejects": r["p"] < ALPHA, "emb_named": r["named"],
                                  "k": r["k"],
                                  "same_candidate": (r["named"] == r["registered_argmax"]
                                                     if r["k"] >= 3 else None),
                                  "both_reject": bool(r["registered_reject"]) and r["p"] < ALPHA,
                                  "both_reject_same_candidate": bool(r["registered_reject"]) and
                                  r["p"] < ALPHA and r["k"] >= 3 and
                                  r["named"] == r["registered_argmax"]})
            out[f"{mask}:{v}"]["agreement_with_registered"] = agree
    return out


def placebo_counts() -> dict:
    """Pooled machinery shares over every placebo file, by mask, variant and cell size."""
    out: dict = {}
    for f in sorted(PLACEBO_DIR.glob("placebo_*.json")):
        d = json.loads(f.read_text())
        design = f"half cells of {d['half_sizes']} replies"
        for v in VARIANTS:
            ps = [r[v]["machinery"]["p"] for r in d["replicates"]]
            gs = [r[v]["machinery"].get("grubbs_p_mc") for r in d["replicates"]]
            for key in (f"{d['mask']}:{v}", f"{d['mask']}:{v}:{design}"):
                c = out.setdefault(key, {"files": 0, "splits": 0, "p_le_0.01": 0,
                                         "p_le_0.05": 0, "grubbs_splits": 0,
                                         "grubbs_le_0.01": 0})
                c["files"] += 1
                c["splits"] += len(ps)
                c["p_le_0.01"] += sum(x <= 0.01 + 1e-12 for x in ps)
                c["p_le_0.05"] += sum(x <= 0.05 + 1e-12 for x in ps)
                c["grubbs_splits"] += sum(g is not None for g in gs)
                c["grubbs_le_0.01"] += sum(g is not None and g <= 0.01 + 1e-12 for g in gs)
    for c in out.values():
        c["share_p_le_0.01"] = c["p_le_0.01"] / c["splits"]
        c["share_p_le_0.05"] = c["p_le_0.05"] / c["splits"]
        c["share_grubbs_le_0.01"] = (c["grubbs_le_0.01"] / c["grubbs_splits"]
                                     if c["grubbs_splits"] else None)
    return out


def _md_table(rows, cols, head):
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for r in rows:
        lines.append("| " + " | ".join(_fmt(r.get(c)) for c in cols) + " |")
    return "\n".join(lines)


def _fmt(x):
    if x is None:
        return "–"
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, float):
        return f"{x:.4g}"
    return str(x)


def main():
    runs = {sid: _load(sid) for sid in all_subjects()}
    runs = {k: v for k, v in runs.items() if v is not None}
    rows, panel = build_rows(runs)
    cnt = counts(rows)
    ledger = Ledger()
    led = ledger.status()
    mine = [e for e in ledger.events()
            if e.get("family") == FAMILY_KEY
            or str(e.get("reservation", "")).startswith(FAMILY_KEY + "/")]
    actual = sum(e["actual_usd"] for e in mine if e["event"] == "reconcile")
    save_new_json(OUT / "spend_ledger_rows.json", {
        "ledger": led["ledger"], "family": FAMILY_KEY, "family_cap_usd": 1.50,
        "family_actual_usd_standard_price": round(actual, 6),
        "family_committed_usd": round(ledger.committed(family=FAMILY_KEY), 6),
        "note": "actuals priced from returned usage at the standard $0.02 per million "
                "tokens; the Batch API bills half of that",
        "events": mine})
    save_new_json(OUT / "panel.json", {"reference": list(NULLS), "extended_reference": list(NULLS + SD_NULLS),
                                       "rule": "(1 + members at or above) / (members + 1)",
                                       "subjects": panel})
    save_new_json(OUT / "results.json", {"rows": rows, "counts": cnt,
                                         "placebo_pooled": placebo_counts(),
                                         "ledger_status": led, "settings": family_settings()})
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
    save_new_text(OUT / "emb_table.csv", buf.getvalue())
    save_new_json(OUT / "settings.json", family_settings())
    cols = ["subject", "role", "mask", "variant", "k", "statistic", "p", "named",
            "ratio_to_null_p95", "grubbs_p_mc", "prereg_dr_p", "panel_ratio_p", "panel_raw_p",
            "base_ref_p", "registered_p", "registered_argmax",
            "placebo_machinery_p_le_0.01", "placebo_stability_same"]
    md = _md_table(rows, cols, cols)
    save_new_text(OUT / "readme_tables.md", md + "\n")
    print(json.dumps({k: {g: {t: v2["fires"] for t, v2 in gv.items()} for g, gv in val.items()
                          if g != "agreement_with_registered"} for k, val in cnt.items()}, indent=1))


if __name__ == "__main__":
    main()
