"""Collect the proxy-swap runs into pairs.json, the tables and the README.

    uv run --no-sync python -m script.analysis.baseline_free_20261115.proxy_swaps.swap_report

Reads ``runs/`` (pair, no_proxy, placebo, planted), ``correlation.json``,
``reliability.json``, ``name_effect_bootstrap.json`` and ``diagnostics.json``;
writes ``pairs.json``, ``pairs_summary.csv``, ``fpr_table.csv``,
``reference_table.csv``, ``planted_table.csv``, ``correlation_by_type.csv``,
``placebo_splits.json``, ``reproduce_check.json``, ``settings.json`` and
``README.md``. Refuses to overwrite any of them. ``--write-to`` sends the
outputs to another folder (a draft); the inputs are always read from ``OUT``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

import numpy as np
from scipy import stats

from script.analysis.baseline_free_20261115.proxy_swaps import swap_planted
from script.analysis.baseline_free_20261115.proxy_swaps.run_swaps import SETTINGS, task_list, task_path
from script.analysis.baseline_free_20261115.proxy_swaps.swap_effects import corr_group
from script.analysis.baseline_free_20261115.proxy_swaps.swap_readme import write_readme
from script.analysis.baseline_free_20261115.proxy_swaps.swap_reproduce import reproduce_checks
from script.analysis.baseline_free_20261115.proxy_swaps.swap_subjects import (
    ALPHA, BY_NAME, CONTROLS, INDEX, N_BOOT, N_SPLITS, OUT, PLACEBO_SUBJECTS, REPO, SERVED, SYNTH,
    planned_pairs, stored_compare)
from src.compare.principal_attribution import MIN_AXES_TO_NAME

SCRIPTS = Path(__file__).resolve().parent
OUTPUTS = ("pairs.json", "pairs_summary.csv", "fpr_table.csv", "reference_table.csv",
           "planted_table.csv", "correlation_by_type.csv", "placebo_splits.json",
           "reproduce_check.json", "settings.json", "README.md")
KEEP = ("S", "p", "reject_0.01", "principal", "principal_axis", "named_by_rule", "naming_reason",
        "argmax_candidate", "argmax_axis", "argmax_t", "n_axes_rejected", "rejected_axes",
        "null_p95", "n_target_rows", "n_base_rows")
NULLS = CONTROLS + SYNTH
BASE_DRAWS = ("A", "B", "C1", "C2", "P")
BASE_NOTE = {"A": "the registered base", "B": "a second capped draw", "C1": "an uncut draw",
             "C2": "an uncut draw", "P": "C1 and C2 pooled"}


def clopper_pearson(k: int, n: int) -> list[float]:
    lo = 0.0 if k == 0 else float(stats.beta.ppf(0.025, k, n - k + 1))
    hi = 1.0 if k == n else float(stats.beta.ppf(0.975, k + 1, n - k))
    return [lo, hi]


def stored_named(st: dict) -> str | None:
    """The naming rule on a stored registered result, which keeps no surviving pairs.

    A run that does not reject, or rejects on fewer distinct axes than the rule
    asks of one candidate, names nobody. Any other stored rejection cannot be
    read without its surviving pairs, and the report stops rather than guess.
    """
    if st["p_family_wise"] > ALPHA or st["n_axes_rejected"] < MIN_AXES_TO_NAME:
        return None
    raise SystemExit("a stored rejection needs its surviving pairs to apply the naming rule")


def registered_beside(target: str, cs: dict) -> dict:
    """The stored registered results for the target, where its base exists."""
    out = {}
    if target in NULLS + ("contextual_optimism",):
        for b in BASE_DRAWS:
            st = cs["pairings"][f"{target}|{b}"]
            out[f"vs_{b}"] = {**{k: st[k] for k in ("statistic", "p_family_wise", "principal",
                                                    "n_axes_rejected")},
                              **({} if target == "contextual_optimism"
                                 else {"named_by_rule": stored_named(st)})}
    elif target == "B":
        st = cs["base_pairs"]["B|A"]["registered"]
        out["vs_A"] = {k: st[k] for k in ("statistic", "p_family_wise", "principal")}
    return out


def fpr_row(group: str, runs: list[dict], note: str = "") -> dict:
    distinct = {}
    for r in runs:  # T|P and P|T are one test for the unsigned statistic
        distinct.setdefault(frozenset((r["target"], r.get("proxy") or r["id"])), r)
    uniq = list(distinct.values())
    p = np.array([r["p"] for r in uniq])
    n = len(uniq)
    k01, k05, k10 = int((p <= 0.01).sum()), int((p <= 0.05).sum()), int((p <= 0.10).sum())
    hits = [r for r in uniq if r["p"] <= ALPHA]
    return {"group": group, "n_ordered": len(runs), "n_distinct": n,
            "n_reject_0.01": k01, "share_0.01": k01 / n, "ci95_0.01": clopper_pearson(k01, n),
            "n_p_le_0.05": k05, "share_0.05": k05 / n, "ci95_0.05": clopper_pearson(k05, n),
            "n_p_le_0.10": k10, "median_p": float(np.median(p)),
            "ks_uniform_p": float(stats.kstest(p, "uniform").pvalue) if n >= 5 else None,
            "named_by_rule_at_0.01": dict(Counter(r["named_by_rule"] for r in hits
                                                  if r["named_by_rule"])),
            "n_named_by_rule_at_0.01": sum(bool(r["named_by_rule"]) for r in hits),
            "argmax_at_0.01": dict(Counter(r["argmax_candidate"] for r in hits)),
            "note": note}


def fpr_table(pairs: dict, no_proxy: dict, placebo: list[dict], cs: dict) -> list[dict]:
    def by(t, sub=None):
        return [r for r in pairs.values() if r["type"] == t and (sub is None or r["subtype"] == sub)]

    sib = by("sibling_auditbench_null") + by("synthetic_vs_auditbench_null") + by("synthetic_vs_synthetic")
    rows = [fpr_row("sibling AuditBench nulls", by("sibling_auditbench_null")),
            fpr_row("synthetic null against AuditBench null", by("synthetic_vs_auditbench_null")),
            fpr_row("synthetic null against synthetic null", by("synthetic_vs_synthetic")),
            fpr_row("all 90 sibling null pairs", sib,
                    "the flag rate of proxy subtraction")]
    for sub in ("capped draws", "uncut draws", "capped against uncut", "overlapping samples"):
        rows.append(fpr_row(f"same-weights base pairs, {sub}", by("same_weights_base", sub)))
    independent = [r for r in by("same_weights_base") if "C1s0-11" not in (r["target"], r["proxy"])]
    rows.append(fpr_row("same-weights base pairs, four independent draws", independent,
                        "A, B, C1 and C2"))
    rows.append(fpr_row("same-weights base pairs, all ten", by("same_weights_base"),
                        "includes C1s0-11, which reuses C1's samples"))
    stored_pairs = {r["id"]: r for r in by("stored_base_pair_reproduce")}
    rows.append(fpr_row("same weights, pooled draw P against capped draws",
                        [stored_pairs[i] for i in ("P|A", "P|A+B", "P|B")]))
    rows.append(fpr_row("same replies, uncut against cut to 400 tokens",
                        [stored_pairs["C1s0-3|C1cut_s0-3"]], "C1 samples 0-3"))
    for b in BASE_DRAWS:
        stored = []
        for t in NULLS:
            st = cs["pairings"][f"{t}|{b}"]
            stored.append({"id": t, "target": t, "proxy": b, "p": st["p_family_wise"],
                           "argmax_candidate": st["principal"], "named_by_rule": stored_named(st)})
        rows.append(fpr_row(f"registered test, 10 nulls against base {b} (stored)", stored, BASE_NOTE[b]))
    for label, names in (("10 nulls", NULLS), ("5 base draws", ("A", "B", "C1", "C1s0-11", "C2")),
                         ("3 served models", SERVED)):
        rows.append(fpr_row(f"no proxy, {label}", [no_proxy[n] for n in names], "nothing subtracted"))
    for name in PLACEBO_SUBJECTS:
        rows.append(fpr_row(f"split-half placebo, {name}",
                            [{**r, "proxy": r["id"]} for r in placebo if r["target"] == name]))
    rows.append(fpr_row("split-half placebo, all five", [{**r, "proxy": r["id"]} for r in placebo]))
    rows.append(fpr_row("served models against each other", by("served_user_awareness"),
                        "user-awareness grading"))
    rows.append(fpr_row("contextual_optimism against a null proxy (power)", by("positive_null_proxy"),
                        "a positive: rejection is a detection"))
    rows.append(fpr_row("contextual_optimism against a base draw", by("positive_base_reference"),
                        "a positive: rejection is a detection"))
    return rows


def reference_table(pairs: dict, no_proxy: dict, cs: dict) -> list[dict]:
    """Each null's p with no proxy, against each stored base draw, and against the other nulls."""
    rows = []
    for t in NULLS:
        sib = [pairs[f"{t}|{q}"]["p"] for q in NULLS if q != t]
        rows.append({"target": t, "no_proxy": no_proxy[t]["p"],
                     **{b: cs["pairings"][f"{t}|{b}"]["p_family_wise"] for b in BASE_DRAWS},
                     "median_other_nulls": float(np.median(sib)), "min_other_nulls": float(min(sib))})
    cols = ["no_proxy", *BASE_DRAWS, "median_other_nulls", "min_other_nulls"]
    rows.append({"target": "median over the 10 nulls",
                 **{c: float(np.median([r[c] for r in rows])) for c in cols}})
    rows.append({"target": "nulls with p above their no-proxy p",
                 **{c: int(sum(r[c] > r["no_proxy"] for r in rows[:len(NULLS)])) for c in cols}})
    return rows


def planted_table() -> list[dict]:
    rows = []
    for task in swap_planted.tasks():
        r = json.loads(swap_planted.task_path(task).read_text())
        safety = set(r["safety_identities"])
        rows.append({"id": r["id"], "target": r["target"], "variant": r["variant"],
                     "proxy": r["proxy"] or "no proxy", "S": r["S"], "p": r["p"],
                     "reject_0.01": r["reject_0.01"], "argmax_candidate": r["argmax_candidate"],
                     "argmax_axis": r["argmax_axis"],
                     "argmax_is_safety": r["argmax_candidate"] in safety,
                     "n_surviving_safety": sum(s["candidate"] in safety for s in r["surviving_pairs"]),
                     "n_surviving": len(r["surviving_pairs"]), "named_by_rule": r["named_by_rule"],
                     "naming_reason": r["naming_reason"]})
    return rows


def correlation_by_type(corr: list[dict], boot: dict) -> list[dict]:
    groups: dict = {}
    for r in corr:
        groups.setdefault(corr_group(r), []).append(r)
    bt = {(b["type"], b["subtype"]): b for b in boot["by_type"]}
    bp = {b["id"]: b for b in boot["pairs"]}
    out = []
    for (t, sub), rs in groups.items():
        sp = [r["name_effect_split"] for r in rs]
        c_tt = np.mean([s["cov_within_target"] for s in sp])
        c_pp = np.mean([s["cov_within_proxy"] for s in sp])
        c_x = np.mean([s["cov_cross_disjoint_s"] for s in sp])
        c_same = np.mean([s["cov_cross_same_s"] for s in sp])
        pooled = float(c_x / np.sqrt(c_tt * c_pp)) if c_tt > 0 and c_pp > 0 else None
        b = bt[(t, sub)]
        if pooled is not None and abs(pooled - b["r_name_effects"]["point"]) > 1e-9:
            raise SystemExit(f"pooled name-effect r of {t}/{sub} differs from the bootstrap point")
        pair_ci = [bp[r["id"]]["r_name_effects"]["ci"] for r in rs]
        out.append({"type": t, "subtype": sub, "n_pairs": len(rs),
                    "median_r": float(np.median([r["r"] for r in rs])),
                    "min_r": float(min(r["r"] for r in rs)), "max_r": float(max(r["r"] for r in rs)),
                    "median_beta": float(np.median([r["beta"] for r in rs])),
                    "n_beta_above_0.5": sum(r["beta_above_half"] for r in rs),
                    "median_var_ratio": float(np.median([r["var_ratio"] for r in rs])),
                    "median_r_disattenuated": float(np.median([r["r_disattenuated"] for r in rs])),
                    "n_r_disattenuated_above_1": sum(r["r_disattenuated"] > 1 for r in rs),
                    "pooled_shared_order_share": float((c_same - c_x) / c_same) if c_same > 0 else None,
                    "pooled_r_name_effects": pooled,
                    "pooled_r_name_effects_ci": b["r_name_effects"]["ci"],
                    "pooled_r_name_share_above_0.5": b["r_name_effects"]["share_above_0.5"],
                    "pooled_r_name_n_undefined": b["r_name_effects"]["n_resamples"] - b["r_name_effects"]["n_defined"],
                    "pooled_stable_slope": b["stable_slope"]["point"],
                    "pooled_stable_slope_ci": b["stable_slope"]["ci"],
                    "pooled_stable_slope_share_above_0.5": b["stable_slope"]["share_above_0.5"],
                    "n_pair_r_name_ci_above_0.5": sum(c is not None and c[0] > 0.5 for c in pair_ci),
                    "n_pair_r_name_ci_below_0.5": sum(c is not None and c[1] < 0.5 for c in pair_ci)})
    return out


def script_record() -> dict:
    files = sorted(SCRIPTS.glob("*.py"))
    rel = [str(f.relative_to(REPO)) for f in files]
    git = ["git", "-C", str(REPO)]
    head = subprocess.run(git + ["rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(git + ["status", "--porcelain", "--", *rel], capture_output=True,
                           text=True).stdout.strip()
    return {"repo_head_at_report": head, "scripts_match_head": dirty == "",
            "script_sha256": {r: hashlib.sha256(f.read_bytes()).hexdigest() for r, f in zip(rel, files)}}


def _csv(path, rows: list[dict]) -> None:
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: (";".join(f"{x:.4f}" for x in v) if isinstance(v, list) and v
                            and isinstance(v[0], float) else f"{v:.4f}" if isinstance(v, float)
                            else json.dumps(v) if isinstance(v, (dict, list)) else v)
                        for k, v in r.items()})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write-to", default=str(OUT), help="output folder (default: the family folder)")
    dest = Path(ap.parse_args().write_to)
    dest.mkdir(parents=True, exist_ok=True)
    for name in OUTPUTS:
        if (dest / name).exists():
            raise SystemExit(f"refusing to overwrite {dest / name}")
    runs = {(t["kind"], t["id"]): json.loads(task_path(t).read_text()) for t in task_list()}
    pairs = {i: r for (k, i), r in runs.items() if k == "pair"}
    no_proxy = {i: r for (k, i), r in runs.items() if k == "no_proxy"}
    placebo = [r for (k, _), r in runs.items() if k == "placebo"]
    corr_rec = json.loads((OUT / "correlation.json").read_text())
    corr = {r["id"]: r for r in corr_rec["pairs"]}
    boot = json.loads((OUT / "name_effect_bootstrap.json").read_text())
    boot_pair = {b["id"]: b for b in boot["pairs"]}
    diag = json.loads((OUT / "diagnostics.json").read_text())
    rel = json.loads((OUT / "reliability.json").read_text())
    cs = stored_compare()
    merged = []
    for p in planned_pairs():
        r = pairs[p["id"]]
        c = corr.get(p["id"], {})
        b = boot_pair.get(p["id"])
        merged.append({**p, **{k: r[k] for k in KEEP},
                       "top_cells": "; ".join(f"{t['candidate']}, {t['axis_id']}, {t['t']:.2f}"
                                              for t in r["top_pairs"][:3]),
                       "correlation": {**{k: c[k] for k in ("n_cells", "r", "r_ci", "beta", "beta_ci",
                                                            "var_ratio", "var_ratio_ci",
                                                            "reliability_target", "reliability_proxy",
                                                            "r_disattenuated", "r_name_effects",
                                                            "shared_order_share")},
                                       "r_name_effects_ci": b["r_name_effects"]["ci"],
                                       "stable_slope": b["stable_slope"]["point"],
                                       "stable_slope_ci": b["stable_slope"]["ci"]} if c else None,
                       "registered_beside": registered_beside(p["target"], cs),
                       "no_proxy_target": {k: no_proxy[p["target"]][k] for k in
                                           ("S", "p", "argmax_candidate", "named_by_rule")}
                       if p["target"] in no_proxy else None})
    checks = reproduce_checks(pairs, no_proxy)
    fpr = fpr_table(pairs, no_proxy, placebo, cs)
    ref = reference_table(pairs, no_proxy, cs)
    planted = planted_table()
    by_type = correlation_by_type(corr_rec["pairs"], boot)
    settings = {**SETTINGS, "level": {"auditbench": 2, "user_awareness": 1},
                "n_bootstrap": N_BOOT, "bootstrap_seed": 20260726, "bootstrap_unit": "instruction",
                "ci_method": {"r, beta, var ratio": "point +/- 1.96 bootstrap SD (percentiles kept beside)",
                              "name-effect r, stable slope": "95% percentile over the same "
                                                             "instruction resamples, 100 splits each"},
                "n_splits": N_SPLITS,
                "split_seed": "SeedSequence([20260726, subject index, replicate])",
                "sample_index_split_seed": "SeedSequence([20260726, 1000, replicate]), shared by "
                                           "all subjects, 100 splits",
                "naming_rule": "src/compare/principal_attribution.attribute_principal",
                "planted_variants": {k: {"grades_lower": v[0], "samples": v[1]}
                                     for k, v in swap_planted.VARIANTS.items()},
                "subject_index": INDEX, "subjects": {s.name: {"files": s.files, "level": s.level,
                                                             "s_range": s.s_range, "note": s.note}
                                                    for s in BY_NAME.values()},
                **script_record(), "numpy": np.__version__,
                "input_sha256": json.loads((OUT / "input_sha256.json").read_text())}
    (dest / "pairs.json").write_text(json.dumps(merged, indent=1))
    (dest / "reproduce_check.json").write_text(json.dumps(checks, indent=1))
    (dest / "settings.json").write_text(json.dumps(settings, indent=1))
    (dest / "placebo_splits.json").write_text(json.dumps(
        sorted(({k: r[k] for k in ("id", "target", "replicate", "subject_index", "S", "p",
                                   "principal", "half_a_sha256")} for r in placebo),
               key=lambda r: r["id"]), indent=1))
    _csv(dest / "pairs_summary.csv", [{
        "id": m["id"], "type": m["type"], "subtype": m["subtype"], "S": m["S"], "p": m["p"],
        "reject_0.01": m["reject_0.01"], "named_by_rule": m["named_by_rule"],
        "argmax_candidate": m["argmax_candidate"], "argmax_axis": m["argmax_axis"],
        "n_axes_rejected": m["n_axes_rejected"],
        "r": (m["correlation"] or {}).get("r"), "beta": (m["correlation"] or {}).get("beta"),
        "r_disattenuated": (m["correlation"] or {}).get("r_disattenuated"),
        "r_name_effects": (m["correlation"] or {}).get("r_name_effects"),
        "r_name_effects_ci": (m["correlation"] or {}).get("r_name_effects_ci"),
        "stable_slope": (m["correlation"] or {}).get("stable_slope"),
        "registered_p_vs_A": m["registered_beside"].get("vs_A", {}).get("p_family_wise"),
        "registered_argmax_vs_A": m["registered_beside"].get("vs_A", {}).get("principal"),
        "stored_p_vs_P": m["registered_beside"].get("vs_P", {}).get("p_family_wise"),
        "no_proxy_p": (m["no_proxy_target"] or {}).get("p")} for m in merged])
    _csv(dest / "fpr_table.csv", fpr)
    _csv(dest / "reference_table.csv", ref)
    _csv(dest / "planted_table.csv", planted)
    _csv(dest / "correlation_by_type.csv", by_type)
    write_readme(dest / "README.md", fpr=fpr, by_type=by_type, merged=merged, rel=rel,
                 checks=checks, secret=corr_rec["secret_loyalty_descriptive"], settings=settings,
                 ref=ref, planted=planted, boot=boot, diag=diag, no_proxy=no_proxy)
    print("reproduce:", checks["n_stored_match"], "/", checks["n_stored"], "stored;",
          checks["n_symmetric_match"], "/", checks["n_symmetric_pairs"], "symmetric;",
          "all_match", checks["all_match"], "| scripts match HEAD:", settings["scripts_match_head"])


if __name__ == "__main__":
    main()
