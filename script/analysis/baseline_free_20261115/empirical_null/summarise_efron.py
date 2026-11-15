"""Fold the per-grid records into the family's summary files. No computation of fits.

    .venv/bin/python -m script.analysis.baseline_free_20261115.empirical_null.summarise_efron

Reads ``runs/*.json`` (written by ``run_efron``), checks every overlap with a
stored result, and writes ``efron.json`` (all records, checks, readings and the
list of fits that are not defined), ``sigma0_table.csv`` (one row per subject,
grid, replicate and variant), ``settings.json`` and ``t_grids.npz``. Refuses to
overwrite.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from script.analysis.baseline_free_20261115.common.subjects import subject_record
from script.analysis.baseline_free_20261115.empirical_null.empirical_null_readings import (
    ESTIMATORS, readings)
from script.analysis.baseline_free_20261115.empirical_null.empirical_null_settings import ALPHA
from script.analysis.baseline_free_20261115.empirical_null.empirical_null_stored_checks import (
    stored_checks)

OUT = Path("out/main/baseline_free_20261115/empirical_null")


def _ci(block: dict) -> tuple:
    return (block.get("lo"), block.get("hi")) if block.get("n") else (None, None)


def _grid_id(r: dict) -> str:
    return r["grid"] if r["grid"] != "placebo" else f"placebo_r{r['replicate']:02d}"


def table_rows(records: list[dict], meta: dict, registered: dict) -> list[dict]:
    rows = []
    for r in records:
        s = meta[r["subject"]]
        reg = registered.get(r["subject"], {})
        for vname, v in r["variants"].items():
            row = {"subject": r["subject"], "role": s["role"], "roster": s["roster"],
                   "grid": r["grid"], "replicate": r.get("replicate"), "variant": vname,
                   "k": r["n_candidates"], "A": r["n_axes"],
                   "instructions": r["n_instructions"], "cells": r["n_cells"],
                   "cells_fitted": v["fit"]["n_fitted"], "cells_zero_spread": r["n_zero_spread"],
                   "S": r["S"], "p_S": r["p_S"], "p_S_ties_as_at_least": r["p_S_ties_as_at_least"],
                   "argmax_candidate": r["argmax_candidate"],
                   "registered_S": reg.get("S"), "registered_p": reg.get("p"),
                   "registered_named": reg.get("named"), "registered_argmax": reg.get("argmax"),
                   "base_label": s["base_label"] if r["grid"] == "registered" else
                   ("own split halves" if r["grid"] == "placebo" else "none")}
            tau = v["tau"]
            tlo, thi = _ci(tau["axis_block"])
            row.update({"tau_pp": tau["tau_pp"], "tau_pp_lo": tlo, "tau_pp_hi": thi,
                        "mean_tau2": tau["mean_tau2"], "mean_rate_pp": tau["mean_rate_pp"]})
            for e in ESTIMATORS:
                f = v["fit"][e]
                perm = v["permutation"][e]
                lo, hi = _ci(v["bootstrap_axes"][e]["sigma0"])
                dlo, dhi = _ci(v["bootstrap_axes"][e]["delta0"])
                plo, phi = _ci(v["bootstrap_axes"][e]["p0"])
                row.update({f"{e}_delta0": f["delta0"], f"{e}_delta0_lo": dlo, f"{e}_delta0_hi": dhi,
                            f"{e}_sigma0": f["sigma0"], f"{e}_sigma0_lo": lo, f"{e}_sigma0_hi": hi,
                            f"{e}_p0": f["p0"], f"{e}_p0_lo": plo, f"{e}_p0_hi": phi,
                            f"{e}_bulk_ok": f["bulk_ok"], f"{e}_undefined_reason": f["undefined_reason"],
                            f"{e}_sigma0_null_median": perm["sigma0"].get("median"),
                            f"{e}_sigma0_null_hi": perm["sigma0"].get("hi"),
                            f"{e}_p_sigma0": perm["p_sigma0"]})
                if "jackknife_instructions" in v:
                    ilo, ihi = _ci(v["bootstrap_instructions"][e]["sigma0_noise_removed"])
                    row.update({f"{e}_sigma0_jackknife_se": v["jackknife_instructions"][e]["sigma0"]["se"],
                                f"{e}_sigma0_instr_boot_lo": ilo, f"{e}_sigma0_instr_boot_hi": ihi})
                else:
                    row.update({f"{e}_sigma0_jackknife_se": None, f"{e}_sigma0_instr_boot_lo": None,
                                f"{e}_sigma0_instr_boot_hi": None})
                row.update({f"n_flag_{e}": v["cells"][f"n_flag_{e}"],
                            f"n_flag_{e}_supported": v["cells"][f"n_flag_{e}_supported"],
                            f"plurality_{e}": "|".join(v["cells"][f"plurality_{e}"]),
                            f"plurality_{e}_supported": "|".join(v["cells"][f"plurality_{e}_supported"])})
            llo, lhi = _ci(v["bootstrap_axes"]["lambda"])
            atoms = v["lambda_atoms"]
            row.update({"lambda": v["lambda"], "lambda_lo": llo, "lambda_hi": lhi,
                        "lambda_jackknife_se": (v["jackknife_instructions"]["lambda"]["se"]
                                                if "jackknife_instructions" in v else None),
                        "median_abs_t": v["median_abs_t"], "p_lambda": v["p_lambda"],
                        "p_lambda_without_tie_tolerance": v["p_lambda_without_tie_tolerance"],
                        "share_observed_cells_at_median": atoms["share_observed_cells_at_median"],
                        "share_permuted_medians_tied": atoms["share_permuted_medians_tied"],
                        "lambda_fitted_cells": v["lambda_fitted_cells"],
                        "documented": r.get("documented") if vname == "all" else None,
                        "documented_rank_p_flags_loc":
                            ((v.get("documented_rank") or {}).get("flags_loc") or {}).get("p_rank")})
            rows.append(row)
    return rows


def undefined_fits(records: list[dict]) -> list[dict]:
    out = []
    for r in records:
        for vname, v in r["variants"].items():
            for e in ESTIMATORS:
                why = v["fit"][e]["undefined_reason"]
                if why:
                    out.append({"subject": r["subject"], "grid": _grid_id(r), "variant": vname,
                                "estimator": e, "reason": why})
    return out


def main() -> None:
    targets = [OUT / n for n in ("efron.json", "sigma0_table.csv", "settings.json", "t_grids.npz")]
    for p in targets:
        if p.exists():
            raise SystemExit(f"{p} exists; never overwritten")
    meta = json.loads((OUT / "subjects.json").read_text())
    records = [json.loads(p.read_text()) for p in sorted((OUT / "runs").glob("*.json"))]
    expected = {(k, g, None) for k, s in meta.items()
                for g in ["median", "mean"] + (["registered"] if s["base"] else [])}
    expected |= {(k, "placebo", r) for k, s in meta.items() for r in range(s["placebo_replicates"])}
    got = {(r["subject"], r["grid"], r.get("replicate")) for r in records}
    missing = sorted(expected - got, key=str)
    settings = records[0]["settings"]
    differing = sorted({_grid_id(r) + ":" + r["subject"] for r in records if r["settings"] != settings})
    ua = json.loads((OUT / "ua_lift.json").read_text())
    if ua["settings"] != settings:
        differing.append("ua_lift.json")
    checks, registered = stored_checks(records, meta, ua)
    read = readings(records, meta, registered, ua, ALPHA)
    undefined = undefined_fits(records)
    rows = table_rows(records, meta, registered)
    with (OUT / "efron.json").open("x") as fh:
        models = {k: subject_record(s["registry_id"] if not s["drop"] else
                                    meta[k.split("__")[0]]["registry_id"])["model"] for k, s in meta.items()}
        json.dump({"settings": settings, "records_with_other_settings": differing,
                   "subjects": meta, "models": models, "missing_grids": missing, "undefined_fits": undefined,
                   "checks": checks, "registered": registered, "readings": read,
                   "records": records}, fh, indent=1)
    with (OUT / "sigma0_table.csv").open("x", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with (OUT / "settings.json").open("x") as fh:
        json.dump(settings, fh, indent=1)
    arrays = {}
    for p in sorted((OUT / "runs").glob("*_grid.npz")):
        z = np.load(p)
        stem = p.name.removesuffix("_grid.npz")
        arrays[f"{stem}__t"], arrays[f"{stem}__u"] = z["t"], z["u"]
    np.savez_compressed(OUT / "t_grids.npz", **arrays)
    print(f"{len(records)} records, {len(rows)} table rows, missing {missing}, "
          f"records with other settings {differing}, {len(undefined)} undefined fits")
    bad = [c for c in checks if not c["match"]]
    print(f"{len(checks)} stored checks, {len(bad)} mismatches")
    for c in bad:
        print("MISMATCH", c)


if __name__ == "__main__":
    main()
