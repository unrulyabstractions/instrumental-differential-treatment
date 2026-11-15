"""Cell-level cross-model correlation of name effects, with reliabilities.

    uv run --no-sync python -m script.analysis.baseline_free_20261115.proxy_swaps.swap_correlation

For a (target, proxy) pair over the (candidate, axis) cells both observe
(``swap_effects`` defines the cell effect g):

- ``r`` is the Pearson correlation of g_T and g_P, and ``beta`` is
  Cov(g_T, g_P) / Var(g_P). Subtracting the proxy lowers the variance of the
  observed cell effects exactly when beta > 1/2 (``var_ratio`` < 1), which is
  r > 0.5 at equal variance.
- Intervals: 2,000 instruction resamples with seed 20260726, shared by paired
  models; the reported interval is r +/- 1.96 bootstrap SD (``boot_interval``
  says why), with the percentiles and the bootstrap bias kept beside it.
- ``reliability``: Spearman-Brown of the split-half r over random within-cell
  halves, 100 splits with ``SeedSequence([20260726, subject index, replicate])``,
  the very splits the placebo tests used (checked here). ``r_disattenuated`` is
  r / sqrt(rel_T rel_P).
- The judge draws its axis order and its 25-axis chunks from ``prompt_id|s``, so
  replies of two models with the same prompt and sample index share them. The
  within-cell halves never share a sample index, so they treat that shared order
  as noise, and ``r_disattenuated`` can exceed 1. ``r_name_effects`` removes it:
  it splits the sample indices into two halves shared by both models (100
  splits) and divides the cross-model covariance of disjoint halves by the
  geometric mean of each model's own half-half covariance
  (``swap_effects.name_effect_correlation``).

Writes ``correlation.json``, ``correlation_table.csv`` and ``reliability.json``.
"""

from __future__ import annotations

import csv
import hashlib
import json

import numpy as np

from script.analysis.baseline_free_20261115.proxy_swaps.run_swaps import split_rng, task_path
from script.analysis.baseline_free_20261115.proxy_swaps.swap_effects import (
    boot_effects, boot_interval, cell_effect, gap_grid, interval, moments,
    name_effect_correlation, s_half_effects)
from script.analysis.baseline_free_20261115.proxy_swaps.swap_secret_loyalty import (
    secret_loyalty_rows)
from script.analysis.baseline_free_20261115.proxy_swaps.swap_subjects import (
    CONTROLS, N_BOOT, N_SPLITS, OUT, PLACEBO_SUBJECTS, SERVED, SUBJECTS, SYNTH, load_table,
    planned_pairs, sample_index)
from src.compare.placebo_calibration import split_cell_indices, subset_table

CSV_COLUMNS = ["id", "type", "subtype", "target", "proxy", "n_cells", "r", "r_ci", "beta",
               "beta_ci", "var_ratio", "var_ratio_ci", "beta_above_half", "reliability_target",
               "reliability_proxy", "r_disattenuated", "r_name_effects", "shared_order_share"]


def n_sample_indices(name: str) -> int:
    return 4 if name in SERVED else 16


def reliability(name: str) -> dict:
    table = load_table(name)
    rh, shas = [], []
    for rep in range(N_SPLITS):
        a, b = split_cell_indices(table, split_rng(name, rep))
        shas.append(hashlib.sha256(np.sort(a).tobytes()).hexdigest())
        rh.append(float(moments(cell_effect(subset_table(table, a)).ravel(),
                                cell_effect(subset_table(table, b)).ravel())["r"]))
    rh = np.array(rh)
    sb = 2 * rh / (1 + rh)
    return {"subject": name, "n_splits": N_SPLITS, "split_half_r_mean": float(rh.mean()),
            "split_half_r_interval": interval(rh), "spearman_brown_mean": float(sb.mean()),
            "spearman_brown_interval": interval(sb),
            "spearman_brown_of_mean_r": float(2 * rh.mean() / (1 + rh.mean())),
            "half_a_sha256": shas}


def pair_rows(pairs: list[dict], rel: dict) -> list[dict]:
    names = [s.name for s in SUBJECTS]
    grids = {n: gap_grid(load_table(n)) for n in names}
    boots = {n: boot_effects(g) for n, g in grids.items()}
    halves = {n: s_half_effects(load_table(n), sample_index(n), n_sample_indices(n), N_SPLITS)
              for n in names}
    rows = []
    for p in pairs:
        t, q = p["target"], p["proxy"]
        with np.errstate(invalid="ignore"):
            point = moments(np.nanmean(grids[t], 1).ravel(), np.nanmean(grids[q], 1).ravel())
        boot = moments(boots[t], boots[q])
        bi = {k: boot_interval(boot[k], float(point[k])) for k in ("r", "beta", "var_ratio")}
        rt, rp = rel[t]["spearman_brown_mean"], rel[q]["spearman_brown_mean"]
        named = name_effect_correlation(halves[t], halves[q])
        rows.append({**p, "n_cells": int(point["n_cells"]), "r": float(point["r"]),
                     "r_ci": bi["r"]["ci"], "beta": float(point["beta"]), "beta_ci": bi["beta"]["ci"],
                     "var_ratio": float(point["var_ratio"]), "var_ratio_ci": bi["var_ratio"]["ci"],
                     "bootstrap": bi, "sd_target": float(point["sd_target"]),
                     "sd_proxy": float(point["sd_proxy"]),
                     "beta_above_half": bool(point["beta"] > 0.5),
                     "reliability_target": rt, "reliability_proxy": rp,
                     "r_disattenuated": float(point["r"] / np.sqrt(rt * rp)),
                     "r_name_effects": named["r_name_effects"],
                     "shared_order_share": named["shared_order_share"], "name_effect_split": named,
                     "n_bootstrap": N_BOOT})
    return rows


def correlation_pairs() -> list[dict]:
    """The swaps, plus each null target against every base draw of its own weights."""
    pairs = [p for p in planned_pairs() if p["type"] != "stored_base_pair_reproduce"]
    for t in CONTROLS + SYNTH:  # contextual_optimism against the bases is already planned
        for b in ("A", "B", "C1", "C2"):
            pairs.append({"id": f"{t}|{b}", "target": t, "proxy": b, "type": "null_vs_base_draw",
                          "subtype": "registered base" if b == "A" else "other base draw"})
    return pairs


def _cell(v):
    if isinstance(v, list):
        return f"{v[0]:.4f};{v[1]:.4f}"
    return f"{v:.4f}" if isinstance(v, float) else ("" if v is None else v)


def main() -> None:
    for path in (OUT / "correlation.json", OUT / "correlation_table.csv", OUT / "reliability.json"):
        if path.exists():
            raise SystemExit(f"refusing to overwrite {path}")
    rel = {s.name: reliability(s.name) for s in SUBJECTS}
    for name in PLACEBO_SUBJECTS:
        for rep in range(N_SPLITS):
            run = json.loads(task_path({"kind": "placebo", "id": f"{name}#{rep:03d}"}).read_text())
            if run["half_a_sha256"] != rel[name]["half_a_sha256"][rep]:
                raise SystemExit(f"split mismatch for {name} replicate {rep}")
    rows = pair_rows(correlation_pairs(), rel)
    sl = secret_loyalty_rows()
    (OUT / "reliability.json").write_text(json.dumps(
        {k: {kk: vv for kk, vv in v.items() if kk != "half_a_sha256"} for k, v in rel.items()},
        indent=1))
    (OUT / "correlation.json").write_text(json.dumps(
        {"pairs": rows, "secret_loyalty_descriptive": sl, "n_bootstrap": N_BOOT,
         "seed": 20260726, "n_splits": N_SPLITS,
         "placebo_splits_checked": list(PLACEBO_SUBJECTS)}, indent=1))
    with (OUT / "correlation_table.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(CSV_COLUMNS)
        for r in rows:
            w.writerow([_cell(r[c]) for c in CSV_COLUMNS])
    print(f"{len(rows)} correlation rows; reliabilities:",
          {k: round(v["spearman_brown_mean"], 3) for k, v in rel.items()})


if __name__ == "__main__":
    main()
