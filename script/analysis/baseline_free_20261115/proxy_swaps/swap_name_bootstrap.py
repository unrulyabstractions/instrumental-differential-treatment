"""Instruction bootstrap of the name-effect correlation, per pair and pooled per pair type.

    uv run --no-sync python -m script.analysis.baseline_free_20261115.proxy_swaps.swap_name_bootstrap --workers 4

For every correlation pair (``swap_correlation.correlation_pairs``) and for the
two narrow-secret-loyalty within-run pairs, this recomputes the four
covariances of ``swap_effects.name_effect_correlation`` on the same 100
sample-index splits (``SeedSequence([20260726, 1000, replicate])``):

- once with every instruction weighted once, which is the point estimate and is
  checked against ``correlation.json`` before anything is written;
- once per instruction resample of ``boot_effects`` (2,000, seed 20260726), the
  resamples the observed r and beta already use. A resample's covariances are
  averaged over the 100 splits exactly as the point's are.

Pooled per pair type (``swap_effects.corr_group``), as ``correlation_by_type``
pools the point: the mean cross covariance over the geometric mean of the mean
within-model covariances, the stable slope (mean cross over mean proxy within)
and the stable variance ratio. The contrast of pooled r between sibling
AuditBench nulls and synthetic-document nulls against AuditBench nulls is
bootstrapped on the same resamples.

Intervals are 95% percentile intervals over the resamples where the quantity is
defined (``swap_effects.percentile_summary``); the bias and the undefined count
are kept beside each.

Writes ``name_effect_bootstrap.json`` and ``name_effect_table.csv``; refuses to overwrite.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache

import numpy as np

from script.analysis.baseline_free_20261115.proxy_swaps.swap_correlation import (
    correlation_pairs, n_sample_indices)
from script.analysis.baseline_free_20261115.proxy_swaps.swap_effects import (
    boot_weights, corr_group, masked_cov, name_moments, percentile_summary, s_half_grids,
    weighted_effects)
from script.analysis.baseline_free_20261115.proxy_swaps.swap_secret_loyalty import RUNS, _table
from script.analysis.baseline_free_20261115.proxy_swaps.swap_subjects import (
    N_BOOT, N_SPLITS, OUT, SEED, load_table, sample_index)

POINT_TOL = 1e-10
CONTRASTS = ((("sibling_auditbench_null", ""), ("synthetic_vs_auditbench_null", "synthetic target")),)


def secret_key(run: str, seat: str) -> str:
    return f"secret:{run}:{seat}"


SECRET_PAIRS = [{"id": f"{run}: target|own base", "target": secret_key(run, "target"),
                 "proxy": secret_key(run, "base"), "type": "secret_loyalty_within_run",
                 "subtype": run} for run in RUNS]


@lru_cache(maxsize=None)
def _subject(name: str):
    """(table, sample index, n_s) of a swap subject or a secret-loyalty seat."""
    if name.startswith("secret:"):
        _, run, seat = name.split(":")
        table, s = _table(run, seat)
        return table, s, 4
    return load_table(name), sample_index(name), n_sample_indices(name)


@lru_cache(maxsize=None)
def _weights(n_i: int) -> np.ndarray:
    """The point row (every instruction once) on top of the ``boot_effects`` resamples."""
    return np.vstack([np.ones((1, n_i)), boot_weights(n_i)])


def one_split(args: tuple) -> dict:
    """The four covariances of every subject and pair on one sample-index split."""
    rep, subjects, pairs = args
    eff = {}
    for name in subjects:
        table, s, n_s = _subject(name)
        g1, g2 = s_half_grids(table, s, n_s, rep)
        w = _weights(g1.shape[1])
        eff[name] = (weighted_effects(g1, w), weighted_effects(g2, w))
    within = {n: masked_cov(*eff[n]) for n in subjects}
    cross, same = {}, {}
    for t, p in pairs:
        (t1, t2), (p1, p2) = eff[t], eff[p]
        cross[(t, p)] = (masked_cov(t1, p2) + masked_cov(t2, p1)) / 2
        same[(t, p)] = (masked_cov(t1, p1) + masked_cov(t2, p2)) / 2
    return {"rep": rep, "within": within, "cross": cross, "same": same}


def unordered(rows: list[dict]) -> list[tuple[str, str]]:
    seen, out = set(), []
    for r in rows:
        key = tuple(sorted((r["target"], r["proxy"])))
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def covariances(rows: list[dict], workers: int) -> tuple[dict, dict, dict]:
    """Mean over the 100 splits of each covariance, as (1 + N_BOOT,) arrays (row 0 the point)."""
    pairs = unordered(rows)
    subjects = sorted({n for pr in pairs for n in pr})
    tasks = [(rep, subjects, pairs) for rep in range(N_SPLITS)]
    within = {n: 0.0 for n in subjects}
    cross = {pr: 0.0 for pr in pairs}
    same = {pr: 0.0 for pr in pairs}
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for k, res in enumerate(pool.map(one_split, tasks), 1):
            for n in subjects:
                within[n] = within[n] + res["within"][n] / N_SPLITS
            for pr in pairs:
                cross[pr] = cross[pr] + res["cross"][pr] / N_SPLITS
                same[pr] = same[pr] + res["same"][pr] / N_SPLITS
            print(f"[split {k}/{N_SPLITS} {time.time() - t0:.0f}s]", flush=True)
    return within, cross, same


def four(row: dict, within, cross, same) -> tuple:
    key = tuple(sorted((row["target"], row["proxy"])))
    return within[row["target"]], within[row["proxy"]], cross[key], same[key]


def summarise(c_tt, c_pp, c_x, c_s) -> dict:
    m = name_moments(c_tt, c_pp, c_x, c_s)
    return {k: percentile_summary(v[1:], float(v[0]),
                                  above=0.5 if k in ("r_name_effects", "stable_slope") else
                                  (1.0 if k == "stable_var_ratio" else None))
            for k, v in m.items()}


def pooled(rows: list[dict], within, cross, same) -> tuple:
    c = np.array([four(r, within, cross, same) for r in rows])  # (pairs, 4, 1 + N_BOOT)
    return tuple(c.mean(axis=0))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    for name in ("name_effect_bootstrap.json", "name_effect_table.csv"):
        if (OUT / name).exists():
            raise SystemExit(f"refusing to overwrite {OUT / name}")
    rows = correlation_pairs()
    stored = {r["id"]: r for r in json.loads((OUT / "correlation.json").read_text())["pairs"]}
    secret_stored = {f"{w['run']}: target|own base": w for w in json.loads(
        (OUT / "correlation.json").read_text())["secret_loyalty_descriptive"]["within_run_target_vs_base"]}
    within, cross, same = covariances(rows + SECRET_PAIRS, args.workers)

    # The point row must reproduce the stored name-effect split exactly.
    worst = 0.0
    for r in rows + SECRET_PAIRS:
        st = (stored.get(r["id"]) or secret_stored[r["id"]])["name_effect_split"]
        got = [float(v[0]) for v in four(r, within, cross, same)]
        want = [st["cov_within_target"], st["cov_within_proxy"], st["cov_cross_disjoint_s"],
                st["cov_cross_same_s"]]
        worst = max(worst, max(abs(a - b) / max(abs(b), 1e-12) for a, b in zip(got, want)))
    if worst > POINT_TOL:
        raise SystemExit(f"point covariances differ from correlation.json (relative {worst:.2e})")

    per_pair = []
    for r in rows + SECRET_PAIRS:
        c = four(r, within, cross, same)
        per_pair.append({k: r[k] for k in ("id", "type", "subtype", "target", "proxy")}
                        | {"group": list(corr_group(r)), **summarise(*c)})
    groups: dict = {}
    for r in rows:
        groups.setdefault(corr_group(r), []).append(r)
    by_type = [{"type": t, "subtype": sub, "n_pairs": len(rs),
                **summarise(*pooled(rs, within, cross, same))} for (t, sub), rs in groups.items()]
    contrasts = []
    for a, b in CONTRASTS:
        ra = name_moments(*pooled(groups[a], within, cross, same))["r_name_effects"]
        rb = name_moments(*pooled(groups[b], within, cross, same))["r_name_effects"]
        d = ra - rb
        contrasts.append({"minuend": list(a), "subtrahend": list(b), "quantity": "pooled r_name_effects",
                          **percentile_summary(d[1:], float(d[0]), above=0.0)})
    record = {"settings": {"n_bootstrap": N_BOOT, "bootstrap_seed": SEED,
                           "bootstrap_unit": "instruction (the boot_effects resamples)",
                           "n_sample_index_splits": N_SPLITS,
                           "split_seed": "SeedSequence([20260726, 1000, replicate])",
                           "interval": "95% percentile over resamples where defined",
                           "point_check_max_relative_diff": worst, "point_check_tolerance": POINT_TOL},
              "pairs": per_pair, "by_type": by_type, "contrasts": contrasts}
    (OUT / "name_effect_bootstrap.json").write_text(json.dumps(record, indent=1))
    cols = ["id", "type", "subtype", "r_name_effects", "r_name_effects_ci", "r_name_share_above_0.5",
            "stable_slope", "stable_slope_ci", "stable_slope_share_above_0.5", "stable_var_ratio",
            "stable_var_ratio_ci", "shared_order_share", "n_defined_r"]
    with (OUT / "name_effect_table.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for p in per_pair:
            def f(x):
                return "" if x is None else f"{x:.4f}"

            def ci(x):
                return "" if x is None else f"{x[0]:.4f};{x[1]:.4f}"
            rn, sl, vr = p["r_name_effects"], p["stable_slope"], p["stable_var_ratio"]
            w.writerow([p["id"], p["type"], p["subtype"], f(rn["point"]), ci(rn["ci"]),
                        f(rn["share_above_0.5"]), f(sl["point"]), ci(sl["ci"]),
                        f(sl["share_above_0.5"]), f(vr["point"]), ci(vr["ci"]),
                        f(p["shared_order_share"]["point"]), rn["n_defined"]])
    print(f"{len(per_pair)} pairs, {len(by_type)} types; point check {worst:.2e}")


if __name__ == "__main__":
    main()
