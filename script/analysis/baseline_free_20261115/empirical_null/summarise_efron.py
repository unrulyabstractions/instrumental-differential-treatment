"""Fold the per-grid records into the family's summary files. No computation of fits.

    .venv/bin/python -m script.analysis.baseline_free_20261115.empirical_null.summarise_efron

Reads ``runs/*.json`` (written by ``run_efron``), checks every overlap with a
stored result, and writes ``efron.json`` (all records, checks and readings),
``sigma0_table.csv`` (one row per subject, grid and variant), ``settings.json``
and ``t_grids.npz``. Refuses to overwrite.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from script.analysis.baseline_free_20261115.empirical_null.efron_null_estimators import (
    BREAKS, FDR_CUT, MLE_HALF_WIDTH, PCT0, SPLINE_DF)
from script.analysis.baseline_free_20261115.empirical_null.efron_truncated_mle import QUAD_POINTS
from script.analysis.baseline_free_20261115.empirical_null.empirical_null_grid_analysis import (
    N_BOOT, N_PERM, SEED)
from script.analysis.baseline_free_20261115.empirical_null.empirical_null_readings import (
    readings)
from script.analysis.baseline_free_20261115.empirical_null.empirical_null_stored_checks import (
    stored_checks)

OUT = Path("out/main/baseline_free_20261115/empirical_null")
ALPHA = 0.01


def _ci(block: dict) -> tuple:
    return (block.get("lo"), block.get("hi")) if block.get("n") else (None, None)


def table_rows(records: list[dict], meta: dict, registered: dict) -> list[dict]:
    rows = []
    for r in records:
        s = meta[r["subject"]]
        reg = registered.get(r["subject"], {})
        for vname, v in r["variants"].items():
            row = {"subject": r["subject"], "role": s["role"], "roster": s["roster"],
                   "grid": r["grid"], "variant": vname, "k": r["n_candidates"],
                   "A": r["n_axes"], "instructions": r["n_instructions"],
                   "cells": r["n_cells"], "cells_fitted": v["fit"]["n_fitted"],
                   "cells_zero_spread": r["n_zero_spread"], "S": r["S"], "p_S": r["p_S"],
                   "argmax_candidate": r["argmax_candidate"],
                   "registered_S": reg.get("S"), "registered_p": reg.get("p"),
                   "registered_named": reg.get("named"),
                   "base_label": s["base_label"] if r["grid"] == "registered" else
                   ("own split halves" if r["grid"] == "placebo" else "none")}
            for e in ("cm", "mle", "loc"):
                f = v["fit"][e]
                perm = v["permutation"][e]
                lo, hi = _ci(v["bootstrap_axes"][e]["sigma0"])
                dlo, dhi = _ci(v["bootstrap_axes"][e]["delta0"])
                ilo, ihi = _ci(v["bootstrap_instructions"][e]["sigma0_noise_removed"])
                row.update({f"{e}_delta0": f["delta0"], f"{e}_delta0_lo": dlo, f"{e}_delta0_hi": dhi,
                            f"{e}_sigma0": f["sigma0"], f"{e}_sigma0_lo": lo, f"{e}_sigma0_hi": hi,
                            f"{e}_sigma0_jackknife_se": v["jackknife_instructions"][e]["sigma0"]["se"],
                            f"{e}_sigma0_instr_boot_lo": ilo, f"{e}_sigma0_instr_boot_hi": ihi,
                            f"{e}_p0": f["p0"],
                            f"{e}_sigma0_null_median": perm["sigma0"].get("median"),
                            f"{e}_sigma0_null_hi": perm["sigma0"].get("hi"),
                            f"{e}_p_sigma0": perm["p_sigma0"]})
            llo, lhi = _ci(v["bootstrap_axes"]["lambda"])
            row.update({"lambda": v["lambda"], "lambda_lo": llo, "lambda_hi": lhi,
                        "lambda_jackknife_se": v["jackknife_instructions"]["lambda"]["se"],
                        "p_lambda": v["p_lambda"], "lambda_fitted_cells": v["lambda_fitted_cells"],
                        "n_flag_cm": v["cells"]["n_flag_cm"], "n_flag_mle": v["cells"]["n_flag_mle"],
                        "plurality_cm": "|".join(v["cells"]["plurality_cm"]),
                        "plurality_mle": "|".join(v["cells"]["plurality_mle"]),
                        "documented": r.get("documented") if vname == "all" else None,
                        "documented_rank_p_flags_mle":
                            ((v.get("documented_rank") or {}).get("flags_mle") or {}).get("p_rank")})
            rows.append(row)
    return rows


def main() -> None:
    targets = [OUT / n for n in ("efron.json", "sigma0_table.csv", "settings.json", "t_grids.npz")]
    for p in targets:
        if p.exists():
            raise SystemExit(f"{p} exists; never overwritten")
    meta = json.loads((OUT / "subjects.json").read_text())
    records = [json.loads(p.read_text()) for p in sorted((OUT / "runs").glob("*.json"))]
    expected = {(k, g) for k, s in meta.items()
                for g in ["median", "mean"] + (["registered"] if s["base"] else [])
                + (["placebo"] if s["placebo"] else [])}
    got = {(r["subject"], r["grid"]) for r in records}
    missing = sorted(expected - got)
    ua = json.loads((OUT / "ua_lift.json").read_text())
    checks, registered = stored_checks(records, meta, ua)
    read = readings(records, meta, registered, ua, ALPHA)
    settings = {
        "seed": SEED, "n_permutations": N_PERM, "n_bootstrap": N_BOOT, "alpha": ALPHA,
        "bootstrap_instructions_seed": SEED, "bootstrap_axes_seed": [SEED, 1],
        "placebo_split_seed": SEED, "histogram_breaks": BREAKS, "histogram_bins": BREAKS - 1,
        "spline_df": SPLINE_DF, "central_fraction_pct0": PCT0, "mle_window": [-MLE_HALF_WIDTH, MLE_HALF_WIDTH],
        "mle_locfdr_window": "median +- b*sc, then delta0 +- b*sigma0, b = 4.3 exp(-0.26 log10 N)",
        "quadrature_points": QUAD_POINTS, "fdr_cut": FDR_CUT,
        "z": "Phi^-1(F_{m-1}(t)), centred on each axis's mean over fitted cells; axes with fewer than two fitted cells dropped",
        "fit_mask": "m >= 2 instructions, spread over instructions above 1e-12, finite t",
        "lambda": "median |t| over the grid's non-NaN cells / median |t| pooled over all permuted grids (registered convention: zero-spread cells count as 0 or infinity)",
        "streams": {"median": "reference_free_max_test (argsort of uniform noise per instruction)",
                    "mean": "paired_max_test (permutation_orders)",
                    "registered": "paired_max_test (permutation_orders)",
                    "placebo": "paired_max_test (permutation_orders), cells split by split_cell_indices"}}
    rows = table_rows(records, meta, registered)
    with (OUT / "efron.json").open("x") as fh:
        json.dump({"settings": settings, "subjects": meta, "missing_grids": missing,
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
    print(f"{len(records)} records, {len(rows)} table rows, missing {missing}")
    bad = [c for c in checks if not c["match"]]
    print(f"{len(checks)} stored checks, {len(bad)} mismatches")
    for c in bad:
        print("MISMATCH", c)


if __name__ == "__main__":
    main()
