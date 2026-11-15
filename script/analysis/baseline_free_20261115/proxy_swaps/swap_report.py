"""Collect the proxy-swap runs into pairs.json, the tables and the README.

    uv run --no-sync python -m script.analysis.baseline_free_20261115.proxy_swaps.swap_report

Reads ``runs/``, ``correlation.json`` and ``reliability.json``; writes
``pairs.json``, ``pairs_summary.csv``, ``fpr_table.csv``,
``correlation_by_type.csv``, ``placebo_splits.json``, ``reproduce_check.json``,
``settings.json`` and ``README.md``. Refuses to overwrite any of them.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from collections import Counter

import numpy as np
from scipy import stats

from script.analysis.baseline_free_20261115.proxy_swaps.run_swaps import SETTINGS, task_list, task_path
from script.analysis.baseline_free_20261115.proxy_swaps.swap_readme import write_readme
from script.analysis.baseline_free_20261115.proxy_swaps.swap_reproduce import reproduce_checks
from script.analysis.baseline_free_20261115.proxy_swaps.swap_subjects import (
    BY_NAME, CONTROLS, INDEX, N_BOOT, N_SPLITS, OUT, PLACEBO_SUBJECTS, REPO, SUBJECTS, SYNTH,
    planned_pairs, stored_compare)

OUTPUTS = ("pairs.json", "pairs_summary.csv", "fpr_table.csv", "correlation_by_type.csv",
           "placebo_splits.json", "reproduce_check.json", "settings.json", "README.md")
KEEP = ("S", "p", "reject_0.01", "principal", "principal_axis", "named_by_rule", "argmax_candidate",
        "argmax_axis", "argmax_t", "n_axes_rejected", "rejected_axes", "null_p95",
        "n_target_rows", "n_base_rows")


def clopper_pearson(k: int, n: int) -> list[float]:
    lo = 0.0 if k == 0 else float(stats.beta.ppf(0.025, k, n - k + 1))
    hi = 1.0 if k == n else float(stats.beta.ppf(0.975, k + 1, n - k))
    return [lo, hi]


def registered_beside(target: str, cs: dict) -> dict:
    """The stored registered results for the target, where its base exists."""
    out = {}
    if target in CONTROLS + SYNTH + ("contextual_optimism",):
        for b in ("A", "P"):
            st = cs["pairings"][f"{target}|{b}"]
            out[f"vs_{b}"] = {k: st[k] for k in ("statistic", "p_family_wise", "principal")}
    elif target == "B":
        st = cs["base_pairs"]["B|A"]["registered"]
        out["vs_A"] = {k: st[k] for k in ("statistic", "p_family_wise", "principal")}
    return out


def fpr_row(group: str, runs: list[dict], note: str = "") -> dict:
    distinct = {}
    for r in runs:  # T|P and P|T are one test for the unsigned statistic
        distinct.setdefault(frozenset((r["target"], r.get("proxy", r["id"]))), r)
    uniq = list(distinct.values())
    k01 = sum(r["p"] <= 0.01 for r in uniq)
    return {"group": group, "n_ordered": len(runs), "n_distinct": len(uniq),
            "n_reject_0.01": k01, "share_0.01": k01 / len(uniq),
            "ci95_0.01": clopper_pearson(k01, len(uniq)),
            "n_p_below_0.05": sum(r["p"] < 0.05 for r in uniq),
            "median_p": float(np.median([r["p"] for r in uniq])),
            "named_at_0.01": dict(Counter(r["principal"] for r in uniq if r["p"] <= 0.01)),
            "note": note}


def fpr_table(pairs: dict, no_proxy: dict, placebo: list[dict], cs: dict) -> list[dict]:
    by = lambda t, sub=None: [r for r in pairs.values() if r["type"] == t  # noqa: E731
                              and (sub is None or r["subtype"] == sub)]
    sib = by("sibling_auditbench_null") + by("synthetic_vs_auditbench_null") + by(
        "synthetic_vs_synthetic")
    rows = [fpr_row("sibling AuditBench nulls", by("sibling_auditbench_null")),
            fpr_row("synthetic null against AuditBench null", by("synthetic_vs_auditbench_null")),
            fpr_row("synthetic null against synthetic null", by("synthetic_vs_synthetic")),
            fpr_row("all 90 sibling null pairs", sib, "the false-positive rate of proxy subtraction")]
    for sub in ("capped draws", "uncut draws", "capped against uncut", "overlapping samples"):
        rows.append(fpr_row(f"same-weights base pairs, {sub}", by("same_weights_base", sub)))
    rows.append(fpr_row("same-weights base pairs, all", by("same_weights_base")))
    nulls = CONTROLS + SYNTH
    for b in ("A", "B", "C1", "C2", "P"):
        stored = [{"id": t, "target": t, "proxy": b, "p": cs["pairings"][f"{t}|{b}"]["p_family_wise"],
                   "principal": cs["pairings"][f"{t}|{b}"]["principal"]} for t in nulls]
        rows.append(fpr_row(f"registered test, 10 nulls against base {b} (stored)", stored,
                            "the registered base" if b == "A" else "another draw of the base"))
    for label, names in (("10 nulls", nulls), ("5 base draws", ("A", "B", "C1", "C1s0-11", "C2")),
                         ("3 served models", ("gpt-5-mini", "gpt-4.1-mini", "gpt-5"))):
        rows.append(fpr_row(f"no proxy, {label}", [no_proxy[n] for n in names],
                            "nothing subtracted"))
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


def correlation_by_type(corr: list[dict]) -> list[dict]:
    groups: dict = {}
    for r in corr:  # a null against each base draw is its own row
        sub = (f"base {r['proxy']}" + (" (registered)" if r["proxy"] == "A" else "")
               if r["type"] == "null_vs_base_draw" else r["subtype"])
        groups.setdefault((r["type"], sub), []).append(r)
    out = []
    for (t, sub), rs in groups.items():
        rn = [r["r_name_effects"] for r in rs if r["r_name_effects"] is not None]
        sp = [r["name_effect_split"] for r in rs]
        c_tt = np.mean([s["cov_within_target"] for s in sp])
        c_pp = np.mean([s["cov_within_proxy"] for s in sp])
        c_x = np.mean([s["cov_cross_disjoint_s"] for s in sp])
        c_same = np.mean([s["cov_cross_same_s"] for s in sp])
        out.append({"type": t, "subtype": sub, "n_pairs": len(rs),
                    "median_r": float(np.median([r["r"] for r in rs])),
                    "min_r": float(min(r["r"] for r in rs)), "max_r": float(max(r["r"] for r in rs)),
                    "n_r_ci_above_0.5": sum(r["r_ci"][0] > 0.5 for r in rs),
                    "n_r_ci_below_0.5": sum(r["r_ci"][1] < 0.5 for r in rs),
                    "median_beta": float(np.median([r["beta"] for r in rs])),
                    "n_beta_above_0.5": sum(r["beta_above_half"] for r in rs),
                    "median_var_ratio": float(np.median([r["var_ratio"] for r in rs])),
                    "median_r_disattenuated": float(np.median([r["r_disattenuated"] for r in rs])),
                    "n_r_disattenuated_above_1": sum(r["r_disattenuated"] > 1 for r in rs),
                    "median_r_name_effects": float(np.median(rn)) if rn else None,
                    "n_r_name_effects_above_0.5": sum(x > 0.5 for x in rn),
                    "n_r_name_effects_defined": len(rn),
                    "pooled_r_name_effects": float(c_x / np.sqrt(c_tt * c_pp))
                    if c_tt > 0 and c_pp > 0 else None,
                    "pooled_shared_order_share": float((c_same - c_x) / c_same) if c_same > 0 else None})
    return out


def _csv(path, rows: list[dict]) -> None:
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        for r in rows:
            w.writerow({k: (";".join(f"{x:.4f}" for x in v) if isinstance(v, list) and v
                            and isinstance(v[0], float) else f"{v:.4f}" if isinstance(v, float)
                            else json.dumps(v) if isinstance(v, (dict, list)) else v)
                        for k, v in r.items()})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--readme-only", action="store_true",
                    help="rewrite README.md alone; the other outputs must exist and match")
    readme_only = ap.parse_args().readme_only
    for name in (("README.md",) if readme_only else OUTPUTS):
        if (OUT / name).exists():
            raise SystemExit(f"refusing to overwrite {OUT / name}")
    runs = {(t["kind"], t["id"]): json.loads(task_path(t).read_text()) for t in task_list()}
    pairs = {i: r for (k, i), r in runs.items() if k == "pair"}
    no_proxy = {i: r for (k, i), r in runs.items() if k == "no_proxy"}
    placebo = [r for (k, _), r in runs.items() if k == "placebo"]
    corr_rec = json.loads((OUT / "correlation.json").read_text())
    corr = {r["id"]: r for r in corr_rec["pairs"]}
    rel = json.loads((OUT / "reliability.json").read_text())
    cs = stored_compare()
    merged = []
    for p in planned_pairs():
        r = pairs[p["id"]]
        c = corr.get(p["id"], {})
        merged.append({**p, **{k: r[k] for k in KEEP},
                       "top_cells": "; ".join(f"{t['candidate']}, {t['axis_id']}, {t['t']:.2f}"
                                              for t in r["top_pairs"][:3]),
                       "correlation": {k: c[k] for k in ("n_cells", "r", "r_ci", "beta", "beta_ci",
                                                         "var_ratio", "var_ratio_ci",
                                                         "reliability_target", "reliability_proxy",
                                                         "r_disattenuated", "r_name_effects",
                                                         "shared_order_share")} if c else None,
                       "registered_beside": registered_beside(p["target"], cs),
                       "no_proxy_target": {k: no_proxy[p["target"]][k] for k in ("S", "p", "principal")}
                       if p["target"] in no_proxy else None})
    checks = reproduce_checks(pairs, no_proxy)
    fpr = fpr_table(pairs, no_proxy, placebo, cs)
    by_type = correlation_by_type(corr_rec["pairs"])
    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True,
                          text=True).stdout.strip()
    settings = {**SETTINGS, "level": {"auditbench": 2, "user_awareness": 1},
                "n_bootstrap": N_BOOT, "bootstrap_seed": 20260726, "bootstrap_unit": "instruction",
                "ci_method": "point +/- 1.96 bootstrap SD (percentiles kept beside)",
                "n_splits": N_SPLITS,
                "split_seed": "SeedSequence([20260726, subject index, replicate])",
                "sample_index_split_seed": "SeedSequence([20260726, 1000, replicate]), shared by "
                                           "all subjects, 100 splits",
                "subject_index": INDEX, "subjects": {s.name: {"files": s.files, "level": s.level,
                                                             "s_range": s.s_range, "note": s.note}
                                                    for s in BY_NAME.values()},
                "code_commit_at_report": head, "numpy": np.__version__,
                "input_sha256": json.loads((OUT / "input_sha256.json").read_text())}
    if readme_only:
        if json.loads((OUT / "pairs.json").read_text()) != json.loads(json.dumps(merged)):
            raise SystemExit("pairs.json differs from a fresh collection; rerun the full report")
        settings["code_commit_at_report"] = json.loads(
            (OUT / "settings.json").read_text())["code_commit_at_report"]
        write_readme(OUT / "README.md", fpr=fpr, by_type=by_type, merged=merged, rel=rel,
                     checks=checks, secret=corr_rec["secret_loyalty_descriptive"],
                     settings=settings)
        return
    (OUT / "pairs.json").write_text(json.dumps(merged, indent=1))
    (OUT / "reproduce_check.json").write_text(json.dumps(checks, indent=1))
    (OUT / "settings.json").write_text(json.dumps(settings, indent=1))
    (OUT / "placebo_splits.json").write_text(json.dumps(
        sorted(({k: r[k] for k in ("id", "target", "replicate", "subject_index", "S", "p",
                                   "principal", "half_a_sha256")} for r in placebo),
               key=lambda r: r["id"]), indent=1))
    _csv(OUT / "pairs_summary.csv", [{
        "id": m["id"], "type": m["type"], "subtype": m["subtype"], "S": m["S"], "p": m["p"],
        "reject_0.01": m["reject_0.01"], "principal": m["principal"], "named_by_rule": m["named_by_rule"],
        "argmax_candidate": m["argmax_candidate"], "argmax_axis": m["argmax_axis"],
        "r": (m["correlation"] or {}).get("r"), "beta": (m["correlation"] or {}).get("beta"),
        "r_disattenuated": (m["correlation"] or {}).get("r_disattenuated"),
        "r_name_effects": (m["correlation"] or {}).get("r_name_effects"),
        "registered_p_vs_A": m["registered_beside"].get("vs_A", {}).get("p_family_wise"),
        "registered_principal_vs_A": m["registered_beside"].get("vs_A", {}).get("principal"),
        "stored_p_vs_P": m["registered_beside"].get("vs_P", {}).get("p_family_wise"),
        "no_proxy_p": (m["no_proxy_target"] or {}).get("p")} for m in merged])
    _csv(OUT / "fpr_table.csv", fpr)
    _csv(OUT / "correlation_by_type.csv", by_type)
    write_readme(OUT / "README.md", fpr=fpr, by_type=by_type, merged=merged, rel=rel,
                 checks=checks, secret=corr_rec["secret_loyalty_descriptive"], settings=settings)
    print("reproduce:", checks["n_stored_match"], "/", checks["n_stored"], "stored;",
          checks["n_symmetric_match"], "/", checks["n_symmetric_pairs"], "symmetric;",
          "all_match", checks["all_match"])


if __name__ == "__main__":
    main()
