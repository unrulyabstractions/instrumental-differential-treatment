"""Decoy names for the trained organisms: the plan, its cost per decoy, and nothing run (B72).

    .venv/bin/python script/analysis/baseline_free_20261115/organism_decoys_plan/cost_table.py
    .venv/bin/python .../cost_table.py --out-dir <scratch folder>   # a dry write elsewhere

The script reads ledgers, logs and stored results only. It makes no model call,
no API call and no cloud call, and it rents nothing. Every figure in
``cost_table.csv`` names the file and the field it came from, with the file's
sha256. Outputs are written once: an existing output folder is refused, and a
superseded one is moved to ``out/superseded/`` by hand.

Besides the plan it runs two free computations: the size of each decoy p value
under a simulated null (``calibration_size.py``) and a decoy pilot on stored
replies (``stored_decoy_pilot.py``).

Outputs: ``cost_table.csv``, ``plan.json``, ``runs/<run>.json`` (one per run of
the partA re-analysis), ``runs_summary.csv``, ``frames.csv``, ``base_subjects.csv``,
``calibration_size.json``, ``stored_decoy_pilot.json``, ``checks.json`` and
``README.md``. Every output carries the settings block.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path[:0] = [str(HERE), str(REPO)]

import calibration_size  # noqa: E402
import stored_decoy_pilot  # noqa: E402
from decoy_plan_assemble import base_only_api, build_set, totals  # noqa: E402
from decoy_plan_checks import (brief_checks, calibration_checks, design_checks,  # noqa: E402
                               ledger_checks, partA_checks, pilot_checks,
                               report_arithmetic_checks, timing_checks)
from decoy_plan_costs import DESIGNS, PLAN_FLOOR_M, mac_rate  # noqa: E402
from decoy_plan_ledgers import (RECIPE, api_generation, batch_prices, box_rates,  # noqa: E402
                                judge_rates, recipe_overheads)
from decoy_plan_readme import readme_text  # noqa: E402
from decoy_plan_records import readout, run_record, user_awareness_note  # noqa: E402
from decoy_plan_registry import DECOY_SETS, INELIGIBLE, base_subjects, run_facts  # noqa: E402
from decoy_plan_sources import git_show_json, sources_read  # noqa: E402
from decoy_plan_timings import engine_init_figures, sampling_figures  # noqa: E402

OUT = REPO / "out/main/baseline_free_20261115/organism_decoys_plan"
SEED, N_PERM, ALPHA = 20260726, 10000, 0.01


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True,
                          check=True).stdout.strip()


def settings(commit: str) -> dict:
    return {"registered_seed": SEED, "registered_n_permutations": N_PERM,
            "registered_alpha": ALPHA, "decoy_alphas": [0.05, 0.01],
            "decoy_decision_alpha": 0.05, "decoy_decision_p": "conformal rank p",
            "plan_floor_m": PLAN_FLOOR_M, "designs": DESIGNS,
            "conformal_p": "(1 + #{reference names with statistic >= target}) / (n_ref + 1)",
            "n_ref": "m + k - 1 (a pre-registered target among k candidates and m decoys)",
            "audited_maximum_p": "1 - C(m, r + 1) / C(m + k, r + 1), r decoys at or above the "
                                 "largest audited name",
            "pilot_sign_flips": stored_decoy_pilot.N_FLIPS, "pilot_seed": stored_decoy_pilot.SEED,
            "simulation_draws_per_config": calibration_size.N_DRAWS,
            "simulation_seed": calibration_size.SEED,
            "model_calls": 0, "api_calls": 0, "boxes_rented": 0, "spend_usd": 0.0,
            "code_commit": commit,
            "script_dir_uncommitted": _git("status", "--porcelain", "--", str(HERE)).splitlines()}


def _flat_settings(st: dict) -> dict:
    return {"registered_seed": st["registered_seed"],
            "registered_n_permutations": st["registered_n_permutations"],
            "registered_alpha": st["registered_alpha"],
            "decoy_decision_alpha": st["decoy_decision_alpha"], "code_commit": st["code_commit"]}


def _csv(rows: list[dict], st: dict) -> str:
    flat = _flat_settings(st)
    rows = [{**r, **flat} for r in rows]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0]), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def _summary_row(rec: dict) -> dict:
    reg, tom, plan = rec["registered"], rec["target_only_median"], rec["plan"] or {}
    return {"run": rec["run"], "role": rec["role"], "decoy_set": plan.get("decoy_set", ""),
            "k": rec["k"], "n_instructions": rec["n_instructions"],
            "samples_per_cell": rec["samples_per_cell"], "n_axes": rec["n_axes"],
            "preregistered_target": rec["preregistered_target"] or "",
            "registered_S": f"{reg['S']:.3f}", "registered_p": f"{reg['p']:.4f}",
            "registered_named": reg["named"] or "",
            "target_only_median_S": f"{tom['S']:.3f}", "target_only_median_p": f"{tom['p']:.4f}",
            "target_only_median_argmax": tom["argmax_candidate"],
            "rank_floor_without_decoys": f"{rec['rank_floor_without_decoys']:.4f}",
            "m_plan": plan.get("m_plan", ""), "n_ref": plan.get("n_ref", ""),
            "floor_registered_target": (f"{plan['conformal_floor_registered_target']:.4f}"
                                        if plan else ""),
            "floor_audited_maximum": (f"{plan['conformal_floor_audited_maximum']:.4f}"
                                      if plan else ""),
            "floor_that_applies": f"{plan['floor_that_applies']:.4f}" if plan else "",
            "m_posthoc": plan.get("m_posthoc", ""),
            "decoy_statistic": "", "decoy_p": "", "decoy_named": "",
            "decoy_status": rec["decoy_test"]["status"],
            "ineligible_or_limit": rec["ineligible_reason"] or plan.get("design_limit") or ""}


def _frame_rows(sets: dict) -> list[dict]:
    rows = []
    for key, s in sets.items():
        fr = s["frames"]
        if not fr["stored_pool"]:
            rows.append({"decoy_set": key, "run": "", "frame": "none", "size_labeled": 0,
                         "unlabeled": "", "size_upper_bound": 0, "first_names": "",
                         "audited_elevation": "", "note": fr["reason"]})
            continue
        for run, p in fr["per_run"].items():
            for name, f in p["frames"].items():
                rows.append({"decoy_set": key, "run": run, "frame": name,
                             "size_labeled": f["size_labeled"], "unlabeled": f["unlabeled"],
                             "size_upper_bound": f["size_upper_bound"],
                             "first_names": "; ".join(n["actor"] for n in f["names"][:5]),
                             "audited_elevation": " ".join(map(str, p["audited_elevation"])),
                             "note": p["claims"][name]})
    return rows


def build() -> dict:
    commit = _git("rev-parse", "HEAD")
    figs = {**judge_rates(), **batch_prices(), **api_generation(), **box_rates(),
            **recipe_overheads(commit), **sampling_figures(), **engine_init_figures()}
    figs["compute.mac.usd_per_hour"] = mac_rate()
    table = list(figs.values())
    facts = run_facts()
    sets = {key: build_set(key, facts, figs, table) for key in DECOY_SETS}
    api = base_only_api(figs, table)
    st = settings(commit)
    records = [run_record(f, sets, st) for f in facts.values()]
    bases = base_subjects()
    ua = user_awareness_note()
    pilot = stored_decoy_pilot.run()
    n_axes = {k: max(facts[r]["n_axes"] for r in DECOY_SETS[k]["runs"]) for k in DECOY_SETS}
    calib = calibration_size.run(sets, n_axes)
    checks = (ledger_checks(figs) + timing_checks(figs, git_show_json(commit, RECIPE))
              + partA_checks() + report_arithmetic_checks() + brief_checks(figs, sets, api)
              + design_checks(sets, records, bases, ua) + pilot_checks(pilot)
              + calibration_checks(calib))
    plan = {"family": "organism_decoys_plan", "settings": st, "sets": sets,
            "totals": totals(sets), "ineligible_runs": INELIGIBLE, "base_only_api_arm": api,
            "readout": readout(records), "base_subjects": bases, "user_awareness_subjects": ua,
            "checks_all_match": all(c["match"] for c in checks)}
    plan["sources_sha256"] = sources_read()
    return {"plan": plan, "table": table, "records": records, "checks": checks, "figs": figs,
            "pilot": {"settings": st, **pilot}, "calibration": {"settings": st, **calib}}


def write(out_dir: Path, built: dict) -> None:
    if out_dir.exists():
        raise SystemExit(f"refusing to overwrite {out_dir}; move it to out/superseded/ first")
    (out_dir / "runs").mkdir(parents=True)
    st = built["plan"]["settings"]
    rows = [f.row() for f in built["table"]]
    base_rows = [{k: v for k, v in b.items()} for b in built["plan"]["base_subjects"]]
    files = {
        "cost_table.csv": _csv(rows, st),
        "plan.json": json.dumps(built["plan"], indent=1, ensure_ascii=False) + "\n",
        "runs_summary.csv": _csv([_summary_row(r) for r in built["records"]], st),
        "frames.csv": _csv(_frame_rows(built["plan"]["sets"]), st),
        "base_subjects.csv": _csv(base_rows, st),
        "calibration_size.json": json.dumps(built["calibration"], indent=1) + "\n",
        "stored_decoy_pilot.json": json.dumps(built["pilot"], indent=1, ensure_ascii=False) + "\n",
        "checks.json": json.dumps({"settings": st, "checks": built["checks"]}, indent=1,
                                  ensure_ascii=False) + "\n",
        "README.md": readme_text(built),
    }
    for rec in built["records"]:
        files[f"runs/{rec['run']}.json"] = json.dumps(rec, indent=1, ensure_ascii=False) + "\n"
    for name, text in files.items():
        (out_dir / name).write_text(text, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out-dir", type=Path, default=OUT)
    args = ap.parse_args()
    built = build()
    bad = [c for c in built["checks"] if not c["match"]]
    if bad and args.out_dir.resolve() == OUT.resolve():
        raise SystemExit("checks failed, nothing written: " + "; ".join(c["check"] for c in bad))
    write(args.out_dir, built)
    print(f"wrote {args.out_dir}: {len(built['table'])} cost rows, "
          f"{len(built['records'])} runs, {len(built['checks'])} checks, {len(bad)} failed")
    if bad:
        raise SystemExit("checks failed: " + "; ".join(c["check"] for c in bad))


if __name__ == "__main__":
    main()
