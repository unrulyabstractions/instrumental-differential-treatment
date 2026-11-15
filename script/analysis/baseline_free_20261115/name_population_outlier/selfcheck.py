"""Check the outlier machinery on simulated data before it touches any verdict.

    PYTHONPATH=. .venv/bin/python \\
        script/analysis/baseline_free_20261115/name_population_outlier/selfcheck.py

Checks, all on simulated data:

1. The G-D identity G^2 = ((k-1)^3/k^2) D^2 / ((k-2) + ((k-1)/k) D^2) on 200,000
   rows of k i.i.d. normals for every k = 3..11, against Grubbs's G computed
   directly from the mean and SD of all k values.
2. The t-relation: t_G from G equals the leader's deleted residual, checked as
   the difference of the two bound p values (t_G from G cancels near G's ceiling
   at k = 3, so the relative error in t itself is reported, not gated).
3. The t_{k-2} law of a fixed candidate's deleted residual on 200,000 rows per k
   (Kolmogorov-Smirnov, and the 0.9, 0.95, 0.99 quantiles).
4. The Monte Carlo null of G against the t-relation bound in the tail, and the
   operating points of the research report's table at k = 5, 7, 11.
5. The shared-stream engine reproduces ``candidate_detachment_test`` and
   ``reference_free_max_test`` exactly on a simulated verdict table, and the
   shuffle p of G equals the shuffle p of D.

Writes ``selfcheck.json`` (refuses to overwrite) with ``passed`` true only if
every check holds.
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
    OUT, outlier_test)
from src.compare.behavior_count_table import build_behavior_table  # noqa: E402
from src.compare.candidate_detachment_statistic import candidate_detachment_test  # noqa: E402
from src.compare.reference_free_max_statistic import reference_free_max_test  # noqa: E402

SEED = 20260726
N_ROWS = 200_000
#: The research report's operating points (its notes' Monte Carlo of 200,000 draws).
REPORT = {5: {"G_max": 1.789, "G_05": 1.671, "D_05_top": 5.08, "D_05_pre": 2.63},
          7: {"G_max": 2.268, "G_05": 1.939, "D_05_top": 3.98, "D_05_pre": 2.18},
          11: {"G_max": 3.015, "G_05": 2.232, "D_05_top": 3.47, "D_05_pre": 1.92}}


def check_identities(rng) -> dict:
    out, ok = {}, True
    for k in range(3, 12):
        z = rng.standard_normal((N_ROWS, k))
        lead = np.argmax(z, axis=1)
        top = z[np.arange(N_ROWS), lead]
        mask = np.ones_like(z, dtype=bool)
        mask[np.arange(N_ROWS), lead] = False
        rest = z[mask].reshape(N_ROWS, k - 1)
        D = (top - rest.mean(axis=1)) / rest.std(axis=1, ddof=1)
        G_formula = gb.G_from_D(D, k)
        G_direct = (top - z.mean(axis=1)) / z.std(axis=1, ddof=1)
        err_gd = float(np.max(np.abs(G_formula - G_direct)))
        # t-relation: t_G equals the leader's deleted residual.
        r_lead = D / np.sqrt(1 + 1 / (k - 1))
        tG = np.sqrt(k * (k - 2) * G_direct ** 2 / ((k - 1) ** 2 - k * G_direct ** 2))
        err_tr = float(np.max(np.abs(tG - r_lead) / np.maximum(1.0, np.abs(r_lead))))
        # The bound read from G and from the leader's deleted residual agree in p.
        p_from_G = np.minimum(1.0, k * stats.t.sf(tG, k - 2))
        p_from_r = np.minimum(1.0, k * stats.t.sf(r_lead, k - 2))
        err_bound_p = float(np.max(np.abs(p_from_G - p_from_r)))
        # The deleted residual of a fixed candidate (index 0) follows t_{k-2}.
        r0 = (z[:, 0] - z[:, 1:].mean(axis=1)) / (z[:, 1:].std(axis=1, ddof=1) * np.sqrt(1 + 1 / (k - 1)))
        ks = stats.kstest(r0, stats.t(df=k - 2).cdf)
        qs = {str(q): [float(np.quantile(r0, q)), float(stats.t.ppf(q, k - 2))] for q in (0.9, 0.95, 0.99)}
        # Quantile tolerance from the sampling SD of an order statistic.
        tol = {str(q): 4 * np.sqrt(q * (1 - q) / N_ROWS) / stats.t.pdf(stats.t.ppf(q, k - 2), k - 2)
               for q in (0.9, 0.95, 0.99)}
        q_ok = all(abs(qs[q][0] - qs[q][1]) <= tol[q] for q in qs)
        # The engine's per-row function agrees with the vectorised forms.
        sub = z[:500]
        eng = np.array([gb.grubbs_top(row)[:2] for row in sub])
        eng_r = np.array([gb.deleted_residuals(row)[0] for row in sub])
        err_eng = float(max(np.max(np.abs(eng[:, 0] - D[:500])), np.max(np.abs(eng[:, 1] - G_direct[:500])),
                            np.max(np.abs(eng_r - r0[:500]))))
        passed = (err_gd < 1e-12 and err_bound_p < 1e-9 and ks.pvalue > 1e-3 and q_ok
                  and err_eng < 1e-12)
        ok &= passed
        out[str(k)] = {"max_abs_err_G_formula_vs_direct": err_gd,
                       "max_rel_err_tG_vs_leader_deleted_residual": err_tr,
                       "max_abs_err_bound_p_from_G_vs_from_r": err_bound_p,
                       "deleted_residual_ks_vs_t": {"statistic": float(ks.statistic), "p": float(ks.pvalue)},
                       "deleted_residual_quantiles_[sim, t]": qs,
                       "quantile_tolerance": {q: float(v) for q, v in tol.items()},
                       "max_abs_err_engine_vs_vectorised": err_eng, "passed": bool(passed)}
    return {"passed": bool(ok), "rows_per_k": N_ROWS, "by_k": out}


def check_null_and_report() -> dict:
    mc = gb.grubbs_null(range(3, 12), N_ROWS, SEED + 1)
    out, ok = {}, True
    for k in range(3, 12):
        G = mc[k]["G"]
        rec = {"G_max": gb.G_MAX(k), "mc_max_G": float(G[-1])}
        for a in (0.05, 0.01):
            g_q = float(np.quantile(G, 1 - a))
            rec[f"mc_G_{a}"] = g_q
            rec[f"bound_p_at_mc_G_{a}"] = gb.grubbs_bound_p(g_q, k)
        ok &= rec["mc_max_G"] <= rec["G_max"] + 1e-12
        # The bound is an upper bound and is tight in the tail.
        ok &= rec["bound_p_at_mc_G_0.01"] >= 0.01 * 0.9 and rec["bound_p_at_mc_G_0.01"] <= 0.012
        out[str(k)] = rec
    rep = {}
    for k, want in REPORT.items():
        G, D = mc[k]["G"], mc[k]["D"]
        got = {"G_max": gb.G_MAX(k), "G_05": float(np.quantile(G, 0.95)),
               "D_05_top": float(np.quantile(D, 0.95)),
               "D_05_pre": float(stats.t.ppf(0.95, k - 2) * np.sqrt(1 + 1 / (k - 1)))}
        tol = {"G_max": 0.001, "G_05": 0.01, "D_05_top": 0.1, "D_05_pre": 0.01}
        match = {f: abs(got[f] - want[f]) <= tol[f] for f in want}
        ok &= all(match.values())
        rep[str(k)] = {"report": want, "got": got, "tolerance": tol, "match": match}
    return {"passed": bool(ok), "mc_rows_per_k": N_ROWS, "mc_seed": SEED + 1, "by_k": out,
            "report_table": rep}


def _sim_rows(rng, k=5, n_instr=12, samples=4, axes=8, shift=0.25):
    rows = []
    base = rng.uniform(0.1, 0.6, size=(n_instr, axes))
    for c in range(k):
        name_effect = rng.normal(0, 0.05, size=axes)
        for i in range(n_instr):
            p = np.clip(base[i] + name_effect + (shift if c == 0 else 0.0) * (np.arange(axes) < 2), 0, 1)
            for s in range(samples):
                fired = rng.random(axes) < p
                rows.append({"principal": f"cand{c}", "instruction_id": f"x::i{i:02d}", "s": s,
                             "level": 2, "verdicts": {f"ax{j}": bool(fired[j]) for j in range(axes)}})
    return rows, [f"ax{j}" for j in range(axes)]


def check_engine(rng) -> dict:
    out, ok = {}, True
    for label, kw in (("k5_shift", {"k": 5, "shift": 0.3}), ("k7_null", {"k": 7, "shift": 0.0}),
                      ("k3_shift", {"k": 3, "shift": 0.2})):
        rows, axes = _sim_rows(rng, **kw)
        table = build_behavior_table(rows, axes)
        n = 999
        mine = outlier_test(table, n_permutations=n, seed=SEED)
        det = candidate_detachment_test(table, n_permutations=n, seed=SEED)
        rf = reference_free_max_test(table, n_permutations=n, seed=SEED)
        m = mine["scalars"]["peak"]["mad_detachment"]
        g = mine["scalars"]["peak"]["grubbs"]
        fields = {
            "detachment.statistic": (det["statistic"], m["statistic"]),
            "detachment.p_family_wise": (det["p_family_wise"], m["p_family_wise"]),
            "detachment.null_mean": (det["null_mean"], m["null_mean"]),
            "detachment.null_p95": (det["null_p95"], m["null_p95"]),
            "detachment.bulk_median_peak": (det["bulk_median_peak"], m["bulk_median"]),
            "max.statistic": (rf["statistic"], mine["target_only_max"]["statistic"]),
            "max.p_family_wise": (rf["p_family_wise"], mine["target_only_max"]["p_family_wise"]),
            "max.null_mean": (rf["null_mean"], mine["target_only_max"]["null_mean"]),
            "max.null_p95": (rf["null_p95"], mine["target_only_max"]["null_p95"]),
        }
        exact = {f: a == b for f, (a, b) in fields.items()}
        peaks_same = all(det["peaks"][c] == mine["scalars"]["peak"]["values"][c] for c in det["peaks"])
        loo_same = all(det["leave_one_out"][c] == m["leave_one_out"][c] for c in det["leave_one_out"])
        lead_same = det["leading"] == m["leading"]
        gd_same = g["p_shuffle_G"] == g["p_shuffle_D"]
        passed = all(exact.values()) and peaks_same and loo_same and lead_same and gd_same
        ok &= passed
        out[label] = {"n_permutations": n, "fields_exact": exact, "peaks_exact": peaks_same,
                      "leave_one_out_exact": loo_same, "leading_same": lead_same,
                      "shuffle_p_G_equals_D": gd_same,
                      "values": {f: [a, b] for f, (a, b) in fields.items()},
                      "grubbs_peak": {"D": g["D"], "G": g["G"], "p_shuffle": g["p_shuffle_G"],
                                      "p_bound": g["p_bound"], "leading": g["leading"]},
                      "passed": bool(passed)}
    return {"passed": bool(ok), "cases": out}


def check_conventions() -> dict:
    """Infinite and tied scalars follow the stated conventions."""
    cases = {
        "leader_inf": (np.array([np.inf, 1.0, 2.0, 1.5]), lambda D, G, k: D == np.inf and G == gb.G_MAX(k)),
        "crowd_inf": (np.array([np.inf, np.inf, 2.0, 1.5]), lambda D, G, k: D == 0.0 and G == 0.0),
        "ties_above": (np.array([3.0, 1.0, 1.0, 1.0]), lambda D, G, k: D == np.inf and G == gb.G_MAX(k)),
        "all_equal": (np.array([1.0, 1.0, 1.0, 1.0]), lambda D, G, k: D == 0.0 and G == 0.0),
    }
    out, ok = {}, True
    for name, (x, want) in cases.items():
        D, G, lead, k = gb.grubbs_top(x)
        r = gb.deleted_residuals(x)
        passed = bool(want(D, G, k))
        ok &= passed
        out[name] = {"x": x.tolist(), "D": D, "G": G, "lead": lead,
                     "deleted_residuals": r.tolist(), "rank_p": gb.rank_p(x).tolist(), "passed": passed}
    hol = gb.holm({"a": 0.004, "b": 0.03})
    ok &= abs(hol["a"] - 0.008) < 1e-15 and abs(hol["b"] - 0.03) < 1e-15
    out["holm"] = hol
    return {"passed": bool(ok), "cases": out}


def main() -> None:
    path = OUT / "selfcheck.json"
    if path.exists():
        raise SystemExit(f"refusing to overwrite {path}")
    rng = np.random.default_rng(SEED)
    rec = {"seed": SEED,
           "identities_and_t_law": check_identities(rng),
           "null_and_report_table": check_null_and_report(),
           "engine_reproduces_stored_tests": check_engine(rng),
           "conventions": check_conventions()}
    rec["passed"] = all(v["passed"] for v in rec.values() if isinstance(v, dict))
    OUT.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, indent=1, default=float))
    for k, v in rec.items():
        if isinstance(v, dict):
            print(f"{k}: {'PASS' if v['passed'] else 'FAIL'}")
    print("selfcheck", "PASSED" if rec["passed"] else "FAILED")
    if not rec["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
