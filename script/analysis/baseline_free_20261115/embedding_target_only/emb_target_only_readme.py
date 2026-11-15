"""Write the family README from its outputs: every number is read from a file here.

    uv run python <this file>

Reads ``results.json``, ``panel.json``, ``reproduce_check.json``, the fill checks,
the placebo files and the shared ledger. Writes ``README.md`` (new).
"""

from __future__ import annotations

import json

from emb_target_only_sources import (FAMILY, OUT, PLACEBO_DIR, all_subjects, family_settings,
                                     masks_of)
from emb_target_only_summarize import _fmt
from script.analysis.baseline_free_20261115.common.ledger import Ledger
from script.analysis.baseline_free_20261115.common.settings import save_new_text

READING_FILE = OUT / "reading.md"


def _table(rows, cols, head=None):
    head = head or cols
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(_fmt(r.get(c)) for c in cols) + " |" for r in rows]
    return "\n".join(out)


def _rows(results, pred):
    return [r for r in results["rows"] if pred(r)]


def main():
    res = json.loads((OUT / "results.json").read_text())
    rep = json.loads((OUT / "reproduce_check.json").read_text())
    # The settings the results were written under, not the code state at README time.
    s = json.loads((OUT / "settings.json").read_text())
    readme_state = family_settings()
    rounding = json.loads((OUT / "reproduce_rounding.json").read_text())
    led = Ledger()
    mine = [e for e in led.events() if e.get("family") == FAMILY or
            (e.get("event") == "reconcile" and str(e.get("reservation", "")).startswith(FAMILY))]
    parts = ["# Target-only embedding test", ""]
    parts += ["## What it tests", "",
              "The test asks whether, within an instruction, any candidate's mean reply embedding "
              "stands apart from the other candidates' mean. It reads one model's own cell means and "
              "no base, so as a test it checks a sharp null that generic name effects make false in "
              "every model. We calibrate it in two ways. Grubbs's test, the detachment statistic and "
              "the deleted residual of a pre-registered candidate ask whether one candidate's gap is "
              "an outlier among the roster's gaps. The panel compares a subject's maximum with the "
              "maxima of the AuditBench null controls read the same way. Distances carry no "
              "direction. The settings table gives every parameter, and the tables below give "
              "every number.", ""]
    parts += ["## Settings", "", _table([{"setting": k, "value": json.dumps(v) if isinstance(v, (list, dict)) else v}
                                         for k, v in s.items() if k not in ("imported_sources",)],
                                        ["setting", "value"]), "",
              f"The README itself was rendered at code commit `{readme_state['code_commit']}`; "
              "the table gives the commit the results were written under.", ""]
    parts += ["## Inputs", "",
              "- Stored embeddings: `<run>/geometry/embeddings/emb_{target,base}_text-embedding-3-small` "
              "and `emb_masked_*`, `emb_masked_noparty_*` of the 15 embedded runs (digest-checked "
              "against the current reply records).",
              "- Fresh base sets B, C1, C2, C1cut, C2cut: `out/main/auditbench/nullext/embedding_calibration_20261114/embeddings`.",
              "- Filled here: `embeddings/emb_<subject>_<mask>_text-embedding-3-small.{npy,json}` "
              "from `texts/<subject>_<mask>.jsonl` (see `texts/manifest.json` and `fill_check_*.json`).",
              "- Registered results: `out/main/reanalysis_20261113/partA/baseline_role_table.csv`.",
              "- Subject ids and files: `script/analysis/baseline_free_20261115/common/subjects.py`.",
              "- Comparison columns are read from stored files and not recomputed here. "
              "`registered_*`: the registered base-referenced verdict test, partA "
              "`baseline_role_table.csv`. `verdict_no_base_*`: the target-only median test of "
              "the same table (trained targets and nulls), its base-only column (bases read as "
              "targets), or the stored reference-free grade test of "
              "`user_awareness_detection.json` (served models). `base_ref_*`: the stored "
              "base-referenced embedding test, as reproduced by the gate.", ""]
    checks = []
    for name, fn, key in (("Level-1 recheck from candidate tables", "level1_recheck.json", "all_match"),
                          ("Placebo split records recomputed by the current code",
                           "placebo_recheck.json", "all_primary_fields_reproduce"),
                          ("Vectorized shuffle against the stored statistic", "selfcheck.json", "passed")):
        d = json.loads((OUT / fn).read_text())
        checks.append({"check": name, "file": fn, "passed": d[key]})
    for tier in ("p1", "challenge", "ua"):
        d = json.loads((OUT / f"fill_check_{tier}.json").read_text())
        checks.append({"check": f"filled embeddings, tier {tier}: rows, digest, unit norm",
                       "file": f"fill_check_{tier}.json", "passed": d["all_ok"]})
    parts += ["## Checks", "", _table(checks, ["check", "file", "passed"]), ""]
    parts += ["## Reproduction gate", "",
              f"Stored files matched value for value: {rep['n_match']} of {rep['n_files']}. "
              f"Mismatches whose statistic, p, named candidate, null 95th percentile and decision "
              f"all match: {len(rep.get('mismatches_with_equal_decision_fields', []))} of "
              f"{len(rep['mismatches'])}.", "",
              _table([{"file": k, "match": v["match"], "bytes_equal": v.get("bytes_equal"),
                       "max_abs_difference": v.get("max_abs_numeric_difference"),
                       "decision_fields_match": v.get("decision_fields_match")}
                      for k, v in rep["files"].items()],
                     ["file", "match", "bytes_equal", "max_abs_difference",
                      "decision_fields_match"]), "",
              "Each mismatch is one per-candidate gap rounded to four decimals. "
              f"All mismatches explained by a rounding midpoint: {rounding['all_explained']} "
              "(`reproduce_rounding.json`).", "",
              _table([{"file": k, "field": f["field"], "unrounded_here": f"{f['unrounded_here']:.9f}",
                       "rounded_here": f["rounded_here"], "rounded_stored": f["rounded_stored"],
                       "distance_to_midpoint": f["distance_to_midpoint"]}
                      for k, v in rounding["mismatches"].items() for f in v.get("fields", [])],
                     ["file", "field", "unrounded_here", "rounded_here", "rounded_stored",
                      "distance_to_midpoint"]), ""]
    cols = ["subject", "mask", "variant", "k", "p", "named", "grubbs_p_mc", "prereg_dr_p",
            "panel_ratio_p", "panel_raw_p", "base_ref_p", "base_ref_named", "registered_p",
            "registered_argmax", "registered_reject", "verdict_no_base_p", "verdict_no_base_named"]
    for title, pred in (("Positives", lambda r: r["role"] == "positive"),
                        ("Challenge rosters (held out)", lambda r: r["role"] == "challenge"),
                        ("Null controls", lambda r: r["role"] == "null"),
                        ("Bases read as targets", lambda r: r["role"] == "base_as_target"),
                        ("Served models (user awareness)", lambda r: r["role"] == "served")):
        rows = _rows(res, pred)
        if rows:
            parts += [f"## {title}", "", _table(rows, cols), ""]
    prow = []
    for sid in all_subjects():
        for m in masks_of(sid):
            f = PLACEBO_DIR / f"placebo_{sid}_{m}.json"
            if not f.exists():
                continue
            d = json.loads(f.read_text())
            for v, sm in d["summary"].items():
                prow.append({"subject": sid, "mask": m, "variant": v, "splits": d["splits"],
                             "p<=0.01": sm["machinery"]["p_le_0.01"]["share"],
                             "ci95": sm["machinery"]["p_le_0.01"]["ci95"],
                             "p<=0.05": sm["machinery"]["p_le_0.05"]["share"],
                             "ks_p": sm["machinery"]["ks_p_uniform"],
                             "grubbs<=0.01": (sm["machinery"]["grubbs_p_mc_le_0.01"] or {}).get("share"),
                             "prereg_dr<=0.01": (sm["machinery"]["prereg_dr_p_le_0.01"] or {}).get("share"),
                             "same_named": sm["stability"]["share_halves_name_same_candidate"],
                             "chance": sm["stability"]["chance_same_candidate"],
                             "full_named": sm["stability"]["share_halves_name_full_data_candidate"],
                             "half_p<=0.01": sm["stability"]["half_p_le_0.01"]["share"]})
    parts += ["## Split-half placebos", "",
              "Machinery check: the test on half-minus-half cells (no candidate effect exists, so "
              "p should be uniform). Stability: the test on each half alone, and how often the two "
              "halves name the same candidate (chance is 1/k).", "",
              _table(prow, ["subject", "mask", "variant", "splits", "p<=0.01", "ci95", "p<=0.05",
                            "ks_p", "grubbs<=0.01", "prereg_dr<=0.01", "same_named", "chance",
                            "full_named", "half_p<=0.01"]), ""]
    pooled = [{"mask:variant:design": k, **{c: v[c] for c in ("files", "splits", "share_p_le_0.01",
                                                              "share_p_le_0.05",
                                                              "share_grubbs_le_0.01")}}
              for k, v in res["placebo_pooled"].items()]
    parts += ["## Placebo shares pooled over subjects", "",
              _table(pooled, ["mask:variant:design", "files", "splits", "share_p_le_0.01",
                              "share_p_le_0.05", "share_grubbs_le_0.01"]), ""]
    crow = []
    for key, c in res["counts"].items():
        for g, tests in c.items():
            if g == "agreement_with_registered":
                continue
            crow.append({"mask:variant": key, "group": g,
                         **{t: f"{v['fires']}/{v['n']}" for t, v in tests.items()}})
    parts += ["## How often each reading fires", "",
              _table(crow, ["mask:variant", "group", "target_only_p<0.01", "grubbs_p_mc<=0.01",
                            "grubbs_p_shuffle<=0.01", "prereg_dr_p<=0.01", "panel_raw_at_floor",
                            "panel_ratio_at_floor"]), "",
              "The raw panel exists only for subjects on the null controls' roster; a null control "
              "is compared with the other seven.", ""]
    arow = []
    for key, c in res["counts"].items():
        a = c["agreement_with_registered"]
        pos = [x for x in a if not x["subject"].startswith("challenge_")]
        arow.append({"mask:variant": key,
                     "registered rejects": sum(x["registered_reject"] for x in pos),
                     "both reject": sum(x["both_reject"] for x in pos),
                     "both reject, same candidate": sum(x["both_reject_same_candidate"] for x in pos),
                     "same candidate named": sum(bool(x["same_candidate"]) for x in pos),
                     "positives with k >= 3": sum(x["k"] >= 3 for x in pos),
                     "embedding rejects": sum(x["emb_rejects"] for x in pos), "positives": len(pos)})
    parts += ["## Agreement with the registered test on positives", "",
              _table(arow, ["mask:variant", "positives", "positives with k >= 3",
                            "registered rejects", "embedding rejects", "both reject",
                            "same candidate named", "both reject, same candidate"]), ""]
    parts += ["## Spend", "",
              _table([{"event": e["event"], "reservation": e.get("reservation"),
                       "usd": e.get("bound_usd", e.get("actual_usd")),
                       "priced_from": e.get("priced_from")} for e in mine],
                     ["event", "reservation", "usd", "priced_from"]), "",
              f"Family committed: ${led.committed(family=FAMILY):.6f} (cap $1.50).", ""]
    missing = [f"{sid}:{m}" for sid in all_subjects() for m in masks_of(sid)
               if not (PLACEBO_DIR / f"placebo_{sid}_{m}.json").exists()]
    parts += ["## Incomplete", "", "Subject and mask pairs without a placebo file: "
              + (", ".join(missing) if missing else "none") + ".", "",
              "Masks not run: the masked arm of the served models "
              + ", ".join(sid for sid in all_subjects() if masks_of(sid) == ("unmasked",))
              + ". Their replies are bare grades with no candidate name in them, so a masked "
              "arm would equal the unmasked one.", ""]
    if READING_FILE.exists():
        parts += ["## Reading", "", READING_FILE.read_text().strip(), ""]
    save_new_text(OUT / "README.md", "\n".join(parts) + "\n")
    print("wrote", OUT / "README.md")


if __name__ == "__main__":
    main()
