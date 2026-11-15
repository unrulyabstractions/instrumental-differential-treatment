"""Fold the task results into the family's output files.

One JSON per model under ``runs/``, then ``contrast_table.csv`` (one row per
model, contrast and gap variant), ``invariance_table.csv`` (one row per
candidate of each of those), ``placebo_contexts.json``, ``settings.json`` and
``results.json`` (decisions, agreement with the registered test, firing rates,
reproduction checks, the served subjects, and the designs not run). The README
is written last from ``results.json``.

The run-level decision of a paired roster is Holm over the three pre-specified
contrasts on the mean gap; an unpaired design has one contrast. The named
candidate is the attribution rule's name for the rejecting contrast with the
smallest adjusted p.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from script.analysis.baseline_free_20261115.context_contrast.context_contrast_placebos import (
    clopper_pearson, share_summary)
from script.analysis.baseline_free_20261115.context_contrast.context_contrast_readme import (
    write_readme)
from script.analysis.baseline_free_20261115.context_contrast.context_contrast_runs import (
    BASELINE_ROLE)
from script.analysis.baseline_free_20261115.context_contrast.context_contrast_summary import (
    designs_not_run, summarize)
from src.common.file_io import load_json

__all__ = ["write_outputs"]

CSV_FIELDS = ["model", "run", "seat", "role", "design", "contrast", "status", "variant",
              "statistic", "p_family_wise", "p_holm", "reject", "reject_holm",
              "argmax_candidate", "argmax_axis", "argmax_t", "argmax_tied_candidates",
              "named", "named_by_rule", "n_surviving_pairs", "preregistered",
              "fixed_target_S", "fixed_target_p", "fixed_target_rank", "fixed_target_reject",
              "reference_candidate", "n_other_candidates", "n_other_candidates_rejecting",
              "n_templates", "registered_S", "registered_p", "registered_reject",
              "registered_named", "target_only_median_S", "target_only_median_p"]
INV_FIELDS = ["model", "contrast", "status", "variant", "candidate", "is_argmax",
              "is_preregistered", "is_reference", "S", "p", "reject", "top_axis", "top_t",
              "min_adjusted_p_full_family"]


def _reps(results, key, kind):
    out = [r for t in results.values() if t["model"] == key and t["kind"] == kind
           for r in t["result"]["replicates"]]
    spec = next(t["result"] for t in results.values() if t["model"] == key and t["kind"] == kind)
    return sorted(out, key=lambda r: r["replicate"]), {k: v for k, v in spec.items()
                                                       if k != "replicates"}


def _registered(role, inp):
    key = inp.get("registered_key")
    if not key:
        return None, None
    reg = role["results"].get(f"{key}|registered|full")
    tom = role["results"].get(f"{key}|target_only_median|full") if inp["seat"] == "target" else None
    pick = ("S", "p", "reject_0.01", "argmax_candidate", "named_by_rule", "naming_reason")
    return ({k: reg[k] for k in pick} if reg else None,
            {k: tom[k] for k in pick} if tom else None)


def _decision(rows, design, alpha):
    mean = [r for r in rows if r["variant"] == "mean"]
    if design == "paired":
        fam = [r for r in mean if r["status"] in ("primary", "secondary")]
        rej = sorted((r for r in fam if r["reject_holm"]), key=lambda r: r["p_holm"])
        best = rej[0] if rej else min(fam, key=lambda r: r["p_holm"])
        return {"rule": "Holm over the three pre-specified contrasts, mean gap",
                "reject": bool(rej), "contrast": best["contrast"], "p_holm": best["p_holm"],
                "named": best["named"] if rej else None,
                "named_by_rule": best["named_by_rule"] if rej else None,
                "argmax_candidate": best["argmax_candidate"],
                "primary_p": next(r["p_family_wise"] for r in fam if r["status"] == "primary")}
    prim = next(r for r in mean if r["status"] == "primary")
    return {"rule": "the design's one contrast, mean gap", "reject": prim["reject"],
            "contrast": prim["contrast"], "p_holm": prim["p_family_wise"],
            "named": prim["named"], "named_by_rule": prim["named_by_rule"],
            "argmax_candidate": prim["argmax_candidate"], "primary_p": prim["p_family_wise"]}


def _csv(path, fields, rows):
    with path.open("x", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: (";".join(map(str, r[k])) if isinstance(r.get(k), list) else r.get(k))
                        for k in fields})


def write_outputs(out: Path, results: dict, inputs: dict, settings: dict) -> None:
    role = load_json(BASELINE_ROLE)
    alpha = settings["alpha"]
    (out / "runs").mkdir()
    per_model, csv_rows, inv_rows, placebo = {}, [], [], {}
    for key, inp in inputs.items():
        split, s_spec = _reps(results, key, "split")
        part, p_spec = _reps(results, key, "partition")
        placebo[key] = {
            "role": inp["role"],
            "split_half": {**s_spec, **share_summary([r["p_family_wise"] for r in split], alpha),
                           "p_values": [r["p_family_wise"] for r in split]},
            "template_partition": {**p_spec,
                                   **share_summary([r["p_family_wise"] for r in part], alpha),
                                   "p_values": [r["p_family_wise"] for r in part]}}
        checks = (results.get(f"{key}|overlap") or {"result": {"checks": []}})["result"]["checks"]
        rec = {"model": key, "inputs": inp, "reproduction_checks": checks,
               "placebo": {k: {kk: vv for kk, vv in v.items() if kk != "p_values"}
                           for k, v in placebo[key].items() if k != "role"}}
        if not key.startswith("ua:"):
            main = results[f"{key}|main"]["result"]
            reg, tom = _registered(role, inp)
            rec.update(registered=reg, target_only_median=tom,
                       decision=_decision(main["rows"], inp["design"], alpha), **main)
            for r in main["rows"]:
                ft = r["fixed_target"] or {}
                csv_rows.append({**r, "model": key, "run": inp["run"], "seat": inp["seat"],
                                 "role": inp["role"], "fixed_target_S": ft.get("S"),
                                 "fixed_target_p": ft.get("p"),
                                 "fixed_target_rank": ft.get("rank_by_S"),
                                 "fixed_target_reject": ft.get("reject"),
                                 "registered_S": (reg or {}).get("S"),
                                 "registered_p": (reg or {}).get("p"),
                                 "registered_reject": (reg or {}).get("reject_0.01"),
                                 "registered_named": (reg or {}).get("named_by_rule"),
                                 "target_only_median_S": (tom or {}).get("S"),
                                 "target_only_median_p": (tom or {}).get("p")})
                for c in r["per_candidate"]:
                    inv_rows.append({**c, "model": key, "contrast": r["contrast"],
                                     "status": r["status"], "variant": r["variant"],
                                     "is_argmax": c["candidate"] == r["argmax_candidate"],
                                     "is_preregistered": c["candidate"] == r["preregistered"],
                                     "is_reference": c["candidate"] == r["reference_candidate"],
                                     "reject": c["p"] <= alpha})
        per_model[key] = rec
        name = key.replace("ua:", "ua__").replace("/", "_").replace("|", "__")
        with (out / "runs" / f"{name}.json").open("x") as fh:
            json.dump(rec, fh, indent=1, default=float)
    _csv(out / "contrast_table.csv", CSV_FIELDS, csv_rows)
    _csv(out / "invariance_table.csv", INV_FIELDS, inv_rows)
    pooled = {}
    for kind in ("split_half", "template_partition"):
        for group in ("all", "positive", "challenge", "null", "base_as_target", "served_subject"):
            ps = [p for v in placebo.values() if group in ("all", v["role"])
                  for p in v[kind]["p_values"]]
            if ps:
                k = int(np.sum(np.asarray(ps) <= alpha))
                pooled[f"{kind}|{group}"] = {"n_models": sum(group in ("all", v["role"])
                                                             for v in placebo.values()),
                                             "n": len(ps), "reject_0.01": k,
                                             "share": k / len(ps), "ci95": clopper_pearson(k, len(ps))}
    with (out / "placebo_contexts.json").open("x") as fh:
        json.dump({"settings": settings, "pooled": pooled, "models": placebo,
                   "note": ("Replicates of one model share its data, so the pooled interval "
                            "treats correlated replicates as independent.")}, fh, indent=1)
    full_settings = {**settings, "gap": "mean of the other candidates (primary); median beside",
                     "statistic": "max |t| over (candidate, axis); paired t over templates for "
                                  "the paired design, Welch t over templates for the family design",
                     "null_paired": "sign flip of each template's difference, all cells together",
                     "null_family": "family labels permuted over templates",
                     "adjustment": "single-step maxT over (candidate, axis); per-candidate maxT for "
                                   "the invariance check and the fixed target",
                     "holm": "over committed_supporter, unreviewed_authority and live_deployment "
                             "against none, mean gap; the same over the median gap beside",
                     "post_hoc": "trigger pair (committed_supporter, unreviewed_authority) "
                                 "against the other two framings, outside Holm",
                     "placebo_split_seed": "numpy default_rng([20260726, replicate])",
                     "placebo_partition_seed": "numpy default_rng([20260726, 1000000 + replicate])",
                     "p_convention": "(1 + #{null >= S}) / (1 + n)"}
    with (out / "settings.json").open("x") as fh:
        json.dump(full_settings, fh, indent=1)
    summary = summarize(per_model, placebo, pooled, alpha)
    with (out / "results.json").open("x") as fh:
        json.dump({"settings": full_settings, **summary, "designs_not_run": designs_not_run(),
                   "models": {k: {kk: v.get(kk) for kk in ("decision", "registered",
                                                           "target_only_median",
                                                           "reproduction_checks", "groups")}
                              for k, v in per_model.items()}}, fh, indent=1, default=float)
    write_readme(out)
