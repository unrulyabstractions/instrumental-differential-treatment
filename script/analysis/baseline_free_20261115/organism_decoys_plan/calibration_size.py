"""Size of the decoy test's p values when every name is null, by simulation (B72).

    .venv/bin/python script/analysis/baseline_free_20261115/organism_decoys_plan/calibration_size.py

The decoy test reports three p values for a pre-registered target among n_ref
reference names: the conformal rank p, a normal fit to the reference names
(empirical calibration), and the deleted-residual (predictive) t. Only the rank
p is exact under exchangeability. This module measures the realized size of
the other two, and of a Gumbel fit by moments, at the plan's own n_ref, axis
count and instruction count.

Model. Each name's statistic is its peak |t| over A axes, with each t a
Student t on I - 1 degrees of freedom. Names are independent and identically
distributed, so nothing is planted. Axes are independent, or share one
equicorrelated normal factor (rho 0.5) as a sensitivity check. The model leaves
out the dependence the median-of-others contrast puts between names. Each
configuration draws 100,000 null data sets, seeded SeedSequence([20260726,
configuration index]). Nothing here reads a model or calls an API.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from scipy import stats

SEED = 20260726
N_DRAWS = 100_000
ALPHAS = (0.05, 0.01)
EULER = 0.5772156649015329


def null_peaks(rng: np.random.Generator, n: int, n_axes: int, df: int, rho: float) -> np.ndarray:
    out = np.empty(n)
    chunk = max(1, 3_000_000 // n_axes)
    for s in range(0, n, chunk):
        e = min(n, s + chunk)
        b = e - s
        if rho == 0.0:
            t = rng.standard_t(df, size=(b, n_axes))
        else:
            z = (math.sqrt(rho) * rng.standard_normal((b, 1))
                 + math.sqrt(1.0 - rho) * rng.standard_normal((b, n_axes)))
            t = z / np.sqrt(rng.chisquare(df, size=(b, n_axes)) / df)
        out[s:e] = np.abs(t).max(axis=1)
    return out


def _pvalues(tgt: np.ndarray, ref: np.ndarray) -> dict[str, np.ndarray]:
    n = ref.shape[1]
    mu, sd = ref.mean(axis=1), ref.std(axis=1, ddof=1)
    beta = sd * math.sqrt(6.0) / math.pi
    loc = mu - EULER * beta
    return {
        "normal_fit": stats.norm.sf((tgt - mu) / sd),
        "deleted_residual_t": stats.t.sf((tgt - mu) / (sd * math.sqrt(1.0 + 1.0 / n)), n - 1),
        "gumbel_moments": -np.expm1(-np.exp(-(tgt - loc) / beta)),
    }


def one_config(index: int, n_ref: int, n_axes: int, df: int, rho: float, k: int) -> dict:
    rng = np.random.default_rng(np.random.SeedSequence([SEED, index]))
    x = null_peaks(rng, N_DRAWS * (n_ref + 1), n_axes, df, rho).reshape(N_DRAWS, n_ref + 1)
    tgt, ref = x[:, 0], x[:, 1:]
    p_conf = (1.0 + (ref >= tgt[:, None]).sum(axis=1)) / (n_ref + 1)
    sizes: dict[str, dict] = {"conformal": {}}
    for a in ALPHAS:
        s = float(np.mean(p_conf <= a))
        sizes["conformal"][str(a)] = {"size": s, "mc_se": math.sqrt(s * (1 - s) / N_DRAWS)}
    for scale, fn in (("raw", lambda v: v), ("log", np.log)):
        for name, p in _pvalues(fn(tgt), fn(ref)).items():
            key = f"{name}_{scale}"
            sizes[key] = {}
            for a in ALPHAS:
                s = float(np.mean(p <= a))
                sizes[key][str(a)] = {"size": s, "mc_se": math.sqrt(s * (1 - s) / N_DRAWS)}
    # The audited maximum referred as if it were registered: k of the n_ref + 1 names are
    # audited, the largest of them is the target, and the rest are its reference.
    m = n_ref + 1 - k
    srt = np.sort(x[:, :k], axis=1)
    top = srt[:, -1]
    naive_ref = np.concatenate([srt[:, :-1], x[:, k:]], axis=1)
    p_naive = (1.0 + (naive_ref >= top[:, None]).sum(axis=1)) / (n_ref + 1)
    naive = float(np.mean(p_naive <= 0.05))
    # p <= 0.05 allows r_max reference names at or above the target; the audited maximum
    # passes when at most r_max decoys reach it: 1 - C(m, r_max + 1) / C(m + k, r_max + 1).
    r_max = int(math.floor(0.05 * (n_ref + 1) + 1e-9)) - 1
    exact = 1.0 - math.comb(m, r_max + 1) / math.comb(m + k, r_max + 1)
    return {"index": index, "n_ref": n_ref, "n_axes": n_axes, "df": df, "rho": rho,
            "k": k, "m": m, "n_draws": N_DRAWS, "sizes": sizes,
            "audited_maximum_as_if_registered": {
                "size_at_0.05": naive, "mc_se": math.sqrt(naive * (1 - naive) / N_DRAWS),
                "exact": exact, "exact_formula": "1 - C(m, r + 1) / C(m + k, r + 1), r = "
                                                 f"{r_max} reference names allowed at or above"},
            "skewness_of_one_peak": float(stats.skew(x[:, 0]))}


def configs_from_sets(sets: dict, n_axes_by_set: dict) -> list[dict]:
    """One configuration per distinct (n_ref, axes, df) of the plan, plus two sensitivity rows."""
    seen, out = {}, []
    for key, s in sets.items():
        cfg = (s["m_plan"] + s["k_min"] - 1, n_axes_by_set[key], s["n_instructions"] - 1, 0.0,
               s["k_min"])
        seen.setdefault(cfg, []).append(key)
    ab = sets["auditbench_ai_organizations"]
    a_axes, a_df, a_k = n_axes_by_set["auditbench_ai_organizations"], ab["n_instructions"] - 1, ab["k_min"]
    extra = [((ab["m_plan"] + a_k - 1, a_axes, a_df, 0.5, a_k), "plan m, correlated axes"),
             ((ab["m_slack1"] + a_k - 1, a_axes, a_df, 0.0, a_k), "one-exceedance m")]
    for cfg, keys in seen.items():
        out.append({"cfg": cfg, "sets": keys, "label": "plan m"})
    for cfg, label in extra:
        out.append({"cfg": cfg, "sets": ["auditbench_ai_organizations"], "label": label})
    return out


def run(sets: dict, n_axes_by_set: dict) -> dict:
    rows = []
    for i, c in enumerate(configs_from_sets(sets, n_axes_by_set)):
        n_ref, a, df, rho, k = c["cfg"]
        r = one_config(i, n_ref, a, df, rho, k)
        r.update(sets=c["sets"], label=c["label"])
        rows.append(r)
    return {"what": "realized size of each decoy p value with every name null",
            "model": __doc__.split("Model.", 1)[1].strip().split("\n\n")[0].replace("\n", " "),
            "seed": SEED, "n_draws_per_config": N_DRAWS, "alphas": list(ALPHAS),
            "configs": rows}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True, help="a new JSON file to write")
    args = ap.parse_args()
    demo = {"auditbench_ai_organizations": {"m_plan": 15, "k_min": 6, "n_instructions": 36,
                                            "m_slack1": 34}}
    res = run(demo, {"auditbench_ai_organizations": 101})
    if args.out.exists():
        raise SystemExit(f"refusing to overwrite {args.out}")
    args.out.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
