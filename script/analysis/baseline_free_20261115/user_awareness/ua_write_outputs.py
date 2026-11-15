"""settings.json and summary.csv for the whole family, stored and paid parts together.

    uv run python -m script.analysis.baseline_free_20261115.user_awareness.ua_write_outputs

Reads the JSONs the other scripts wrote and writes two files. The summary has
one row per detector per run, with statistic, p, the candidate named at alpha
0.01, and the registered (baseline) result, which no served model has.
"""

from __future__ import annotations

import csv

from src.common.file_io import load_json, save_json

from script.analysis.baseline_free_20261115.common.settings import code_state
from script.analysis.baseline_free_20261115.user_awareness.ua_grade_tables import OUT
from script.analysis.baseline_free_20261115.user_awareness.ua_stored_tables_out import (
    NO_BASE, summary_rows)

ALPHA = 0.01


def decoy_rows(decoy: dict) -> list[dict]:
    rows = []
    for subj, v in decoy["subjects"].items():
        run = f"{v['subject']} (new session)"

        def add(det, stat, p, named, note=""):
            rows.append({"subject": run, "level": "2", "detector": det,
                         "statistic": None if stat is None else round(float(stat), 4),
                         "p": None if p is None else round(float(p), 4), "alpha": ALPHA,
                         "rejects": None if p is None else bool(p <= ALPHA), "named": named,
                         "registered_result": NO_BASE, "note": note})

        for k, t in v["safety_targets"].items():
            for test, label in (("conformal", "conformal p over pool"),
                                ("empirical_calibration", "empirical-calibration p (REML)"),
                                ("predictive_t", "predictive t over pool")):
                x = t[test]
                stat = x.get("t", x.get("z"))
                add(f"{label}, {k}", stat, x["p_bh_within_subject"],
                    k if x["reject_at_alpha"] else None,
                    f"raw p {round(x['p_one_sided_harsher'], 4)}; pool {v['n_pool']}; BH over 3")
        w = v["safety_vs_pool_whole_user_permutation"]
        add("whole-user permutation, safety vs pool", w["gap_target_minus_pool"],
            w["p_one_sided_harsher"], "safety group" if w["reject_at_alpha"] else None,
            f"{w['n_relabellings']} relabellings; floor {round(w['floor'], 5)}")
        h = v["pool_heterogeneity"]
        rows.append({**rows[-1], "level": "0", "detector": "heterogeneity of the ordinary-user pool",
                     "statistic": round(h["Q"], 4), "p": round(h["p_parametric_bootstrap"], 4),
                     "rejects": h["reject_at_alpha"], "named": None,
                     "note": f"df {h['df']}; tau {round(h['tau_DL'], 4)}"})
        t = v["temporal_check"]
        rows.append({**rows[-1], "level": "temporal", "detector": "new session vs stored, omnibus",
                     "statistic": round(t["omnibus"]["statistic"], 4),
                     "p": round(t["omnibus"]["p"], 4), "rejects": t["omnibus"]["reject"],
                     "named": None, "note": f"shift p {round(t['overall_shift']['p_two_sided'], 4)}"})
    return rows


def main() -> None:
    stored = {k: load_json(OUT / f"run_stored_{k}.json")
              for k in ("gpt-5-mini", "gpt-4.1-mini", "gpt-5")}
    rows = summary_rows(stored)
    decoy_path = OUT / "decoy_detection.json"
    decoy = load_json(decoy_path) if decoy_path.exists() else None
    if decoy:
        rows += decoy_rows(decoy)
    with open(OUT / "summary.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    reg = load_json(OUT / "REGISTRATION.json")
    pilot = load_json(OUT / "pilot.json") if (OUT / "pilot.json").exists() else None
    save_json(OUT / "settings.json", {
        "stored_part": {"seed": 20260726, "n_permutations": 10000, "alpha": ALPHA,
                        "grubbs_mc_draws": 1_000_000, "bootstrap_draws": 10000,
                        "whole_user_permutation": "exact enumeration of C(9, 3) = 84"},
        "paid_part": {"driver": reg["driver"], "prices_usd_per_million": reg["prices_usd_per_million"],
                      "price_source": reg["price_source"], "caps_usd": reg["caps_usd"],
                      "pilot": reg["pilot"], "m_rule": reg["m_rule"], "stop_rule": reg["stop_rule"],
                      "plan": pilot["plan"] if pilot else None},
        "code_state": code_state(),
    })
    print(f"summary.csv rows {len(rows)}")


if __name__ == "__main__":
    main()
