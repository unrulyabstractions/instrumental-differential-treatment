"""Check the size and reference-set machinery on simulated data before any verdict.

    PYTHONPATH=. .venv/bin/python \\
        script/analysis/baseline_free_20261115/name_population_outlier/selfcheck_revision.py

Checks, all on simulated i.i.d. normal scalars (seed 20260726):

1. ``reference_residuals`` against a fixed reference of m values follows t with
   m - 1 degrees of freedom (m = 5 and 6, 200,000 rows each; Kolmogorov-Smirnov
   and the 0.95 and 0.99 quantiles), and with the reference set to all other
   candidates it equals ``deleted_residuals`` exactly.
2. ``mc_tail_p_many`` equals ``mc_tail_p`` value by value.
3. ``run_outlier.attach_calibration`` reports the nominal size when the shuffled
   scalars are i.i.d. normal: G, every deleted residual, and Holm over two
   independent scalars, each within four binomial standard errors of alpha.

Writes ``selfcheck_revision.json`` (refuses to overwrite) with ``passed`` true
only if every check holds. ``run_outlier.py`` refuses to run without it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy import stats

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from script.analysis.baseline_free_20261115.name_population_outlier import grubbs as gb  # noqa: E402
from script.analysis.baseline_free_20261115.name_population_outlier.run_outlier import (  # noqa: E402
    OUT, attach_calibration)

SEED = 20260726
N_ROWS = 200_000


def check_reference_t(rng) -> dict:
    out, ok = {}, True
    for m in (5, 6):
        z = rng.standard_normal((N_ROWS, m + 1))
        r = gb.reference_residuals(z, 0, range(1, m + 1))
        ks = stats.kstest(r, stats.t(m - 1).cdf)
        q = {str(a): [float(np.quantile(r, a)), float(stats.t.ppf(a, m - 1))] for a in (0.95, 0.99)}
        good = ks.pvalue > 1e-3 and all(abs(a - b) / b < 0.03 for a, b in q.values())
        out[f"m{m}"] = {"ks_p": float(ks.pvalue), "quantiles_got_vs_t": q, "passed": bool(good)}
        ok &= good
    for k in (3, 6, 10):
        z = rng.standard_normal((2000, k))
        a = np.array([gb.deleted_residuals(row) for row in z])
        b = np.stack([gb.reference_residuals(z, c, [j for j in range(k) if j != c]) for c in range(k)], axis=1)
        err = float(np.max(np.abs(a - b)))
        out[f"equals_deleted_residuals_k{k}"] = {"max_abs_err": err, "passed": bool(err < 1e-12)}
        ok &= err < 1e-12
    out["passed"] = bool(ok)
    return out


def check_mc_tail(rng) -> dict:
    null = np.sort(rng.standard_normal(100_000))
    vals = np.concatenate([rng.standard_normal(5000) * 2, null[:50], [np.nan, np.inf, -np.inf]])
    a = np.array([gb.mc_tail_p(null, v) for v in vals])
    b = gb.mc_tail_p_many(null, vals)
    same = bool(np.array_equal(np.isnan(a), np.isnan(b)) and np.allclose(a[~np.isnan(a)], b[~np.isnan(b)],
                                                                          rtol=0, atol=0))
    return {"n_values": int(vals.size), "passed": same}


def check_size(rng) -> dict:
    out, ok = {}, True
    mc = gb.grubbs_null(range(3, 12), 400_000, SEED)
    B = 40_000
    for k in (4, 6, 10):
        res = {"candidates": [f"c{i}" for i in range(k)], "scalars": {}, "_nulls": {}}
        for n in ("peak", "rms"):
            x = rng.standard_normal((B, k))
            G = np.array([gb.grubbs_top(row)[1] for row in x])
            r = np.array([gb.deleted_residuals(row) for row in x])
            res["scalars"][n] = {"grubbs": {"k_used": k}, "df": k - 2}
            res["_nulls"][n] = {"x": x, "G": G, "D": G, "r": r}
        attach_calibration(res, mc)
        cal = res["normal_theory_calibration"]["unsigned"]
        got = {}
        for a in ("0.01", "0.05"):
            al = float(a)
            se = np.sqrt(al * (1 - al) / B)
            vals = {"G_peak": cal["grubbs_normal_size"]["peak"][a],
                    "G_rms": cal["grubbs_normal_size"]["rms"][a],
                    "deleted_residual_peak": cal["deleted_residual_size"]["peak"][a],
                    "deleted_residual_rms": cal["deleted_residual_size"]["rms"][a]}
            # Holm over two independent scalars: 1 - (1 - alpha/2)^2.
            holm_expect = 1 - (1 - al / 2) ** 2
            vals_holm = {"G_holm": cal["grubbs_normal_holm_size"][a],
                         "deleted_residual_holm": cal["deleted_residual_holm_size"][a]["mean_over_candidates"]}
            good = all(abs(v - al) <= 4 * se for v in vals.values()) and all(
                abs(v - holm_expect) <= 4 * se for v in vals_holm.values())
            got[a] = {**vals, **vals_holm, "holm_expected": holm_expect, "se": float(se), "passed": bool(good)}
            ok &= good
        out[f"k{k}"] = got
    out["passed"] = bool(ok)
    return out


def main() -> None:
    path = OUT / "selfcheck_revision.json"
    if path.exists():
        raise SystemExit(f"refusing to overwrite {path}")
    rng = np.random.default_rng(SEED)
    rec = {"seed": SEED,
           "reference_residual_t_law": check_reference_t(rng),
           "mc_tail_p_many": check_mc_tail(rng),
           "size_under_iid_normal": check_size(rng)}
    rec["passed"] = all(v["passed"] for v in rec.values() if isinstance(v, dict))
    path.write_text(json.dumps(rec, indent=1))
    print(json.dumps({k: (v["passed"] if isinstance(v, dict) else v) for k, v in rec.items()}))
    if not rec["passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
