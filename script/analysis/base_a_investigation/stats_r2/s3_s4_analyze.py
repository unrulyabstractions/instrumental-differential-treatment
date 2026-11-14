"""S3 surprise table and S4 decomposition, from the draws written by draws_engine.py.

S3. Null: base A and base B replies trade places at each (candidate, instruction, s) slot with
probability 1/2 (targets fixed). Draw 0 is the identity (the real A and B). Level test: rank of the
real A's value among all pseudo-bases (pseudo-A and pseudo-B of every draw). Gap test: Q(A) - Q(B)
against Q(pseudo-A) - Q(pseudo-B).
S4. (a) target-free deviance of A and B (reference-free S, share |t|>2, mean t^2) ranked among
bootstrap bases from B alone, from the pooled 32, and among swap pseudo-bases; (b) eight-test median
among draws at least as deviant as A; (c) correlation of the eight tests' S under a base redraw, and
the probability of the observed median with that dependence broken.
Usage: s3_s4_analyze.py <swap npz> [<bootB npz> <boot32 npz>]
"""
import json
import sys

import numpy as np

import fast as F

sw = np.load(sys.argv[1])
S6, p6, S5, p5, dev = sw["S6"], sw["p6"], sw["S5"], sw["p5"], sw["dev"]
n = S6.shape[0]
assert np.allclose(p6[0, 0, :8], [0.0133, 0.0605, 0.0325, 0.0561, 0.0381, 0.6338, 0.1584, 0.0554], atol=5e-5)
sets = {
    "six: eight nulls": (S6[:, :, :8], p6[:, :, :8]),
    "six: ten (eight + two synthetic)": (S6[:, :, :10], p6[:, :, :10]),
    "six: ten + CO five-cand": (np.concatenate([S6[:, :, :10], S5[:, :, 10:]], 2), np.concatenate([p6[:, :, :10], p5[:, :, 10:]], 2)),
    "five: eight nulls": (S5[:, :, :8], p5[:, :, :8]),
    "five: ten": (S5[:, :, :10], p5[:, :, :10]),
    "five: ten + CO": (S5, p5),
}
QS = {  # name: (function over (..., m) S and p, direction where 'more extreme' = +1 larger / -1 smaller)
    "median_p": (lambda S, p: np.median(p, -1), -1),
    "mean_S": (lambda S, p: S.mean(-1), +1),
    "count_p_lt_0.05": (lambda S, p: (p < 0.05).sum(-1), +1),
    "count_p_lt_0.07": (lambda S, p: (p < 0.07).sum(-1), +1),
    "fisher": (lambda S, p: -2 * np.log(p).sum(-1), +1),
}


def rank_p(null, obs, direc):
    up = (1 + np.sum(null >= obs)) / (1 + len(null))
    lo = (1 + np.sum(null <= obs)) / (1 + len(null))
    one = up if direc > 0 else lo
    return float(one), float(min(1.0, 2 * min(up, lo)))


res = {"n_draws": n - 1, "S3": {}}
for sname, (S, p) in sets.items():
    row = {}
    for qn, (fn, direc) in QS.items():
        q = fn(S, p)  # (n, 2)
        qa, qb = float(q[0, 0]), float(q[0, 1])
        lvl_null = q[1:].ravel()
        gap_null = q[1:, 0] - q[1:, 1]
        g = qa - qb
        one_g = (1 + np.sum(direc * gap_null >= direc * g)) / n
        two_g = (1 + np.sum(np.abs(gap_null) >= abs(g))) / n
        la1, la2 = rank_p(lvl_null, qa, direc)
        lb1, lb2 = rank_p(lvl_null, qb, direc)
        row[qn] = {"A": qa, "B": qb, "null_median": float(np.median(lvl_null)),
                   "null_q05_q95": [float(np.quantile(lvl_null, 0.05)), float(np.quantile(lvl_null, 0.95))],
                   "A_level_one_sided": la1, "A_level_two_sided": la2, "B_level_one_sided": lb1,
                   "gap": g, "gap_null_sd": float(gap_null.std()), "gap_z": float(g / gap_null.std()),
                   "gap_one_sided": float(one_g), "gap_two_sided": float(two_g)}
    res["S3"][sname] = row
    print(f"\n== {sname}  (m={S.shape[2]})")
    for qn, r in row.items():
        print(f"  {qn:16s} A={r['A']:8.4f} B={r['B']:8.4f} null med={r['null_median']:8.4f} [{r['null_q05_q95'][0]:.3f},{r['null_q05_q95'][1]:.3f}]"
              f" | A level 1s={r['A_level_one_sided']:.4f} 2s={r['A_level_two_sided']:.4f} (B 1s={r['B_level_one_sided']:.3f})"
              f" | gap={r['gap']:+.3f} sd={r['gap_null_sd']:.3f} z={r['gap_z']:+.2f} 1s={r['gap_one_sided']:.4f} 2s={r['gap_two_sided']:.4f}")
# per-test swap p of the S gap (ten six-cand tests, CO five-cand)
names6 = list(sw["targets6"])
dS = S6[:, 0, :] - S6[:, 1, :]
res["per_test_gap"] = {t: {"dS": float(dS[0, k]), "sd": float(dS[1:, k].std()),
                           "p_two": float((1 + np.sum(np.abs(dS[1:, k]) >= abs(dS[0, k]))) / n)} for k, t in enumerate(names6)}
dS5 = S5[:, 0, 10] - S5[:, 1, 10]
res["per_test_gap"]["CO_five"] = {"dS": float(dS5[0]), "sd": float(dS5[1:].std()), "p_two": float((1 + np.sum(np.abs(dS5[1:]) >= abs(dS5[0]))) / n)}
# S4c: dependence under a base redraw
SA_ = S6[1:, :, :8].reshape(-1, 8)
pA_ = p6[1:, :, :8].reshape(-1, 8)
cS = np.corrcoef(SA_.T); off = cS[~np.eye(8, dtype=bool)]
gap = S6[1:, 0, :8] - S6[1:, 1, :8]
cG = np.corrcoef(gap.T); offg = cG[~np.eye(8, dtype=bool)]
from scipy.stats import spearmanr  # noqa: E402
cP = spearmanr(pA_).correlation; offp = cP[~np.eye(8, dtype=bool)]
rng = np.random.default_rng(4)
# break the dependence: each test's p from an independently chosen draw
ind = np.stack([pA_[rng.integers(0, len(pA_), 200000), k] for k in range(8)], 1)
med_ind = np.median(ind, 1)
med_dep = np.median(pA_, 1)
res["S4c"] = {"S_corr_mean_offdiag": float(off.mean()), "S_corr_range": [float(off.min()), float(off.max())],
              "gap_corr_mean_offdiag": float(offg.mean()), "p_spearman_mean_offdiag": float(offp.mean()),
              "S_sd_per_test": SA_.std(0).tolist(), "sd_of_mean_S": float(SA_.mean(1).std()),
              "sd_of_mean_S_if_independent": float(np.sqrt((SA_.std(0) ** 2).sum()) / 8),
              "P_median_le_0.0557_dependent": float(np.mean(med_dep <= 0.0557)),
              "P_median_le_0.0557_independent": float(np.mean(med_ind <= 0.0557)),
              "median_of_median_dependent": float(np.median(med_dep)), "median_of_median_independent": float(np.median(med_ind)),
              "q01_median_dependent": float(np.quantile(med_dep, 0.01)), "q01_median_independent": float(np.quantile(med_ind, 0.01)),
              "per_test_P_p_lt_0.05": np.mean(pA_ < 0.05, 0).tolist(), "per_test_P_p_le_0.06": np.mean(pA_ <= 0.06, 0).tolist(),
              "per_test_median_p": np.median(pA_, 0).tolist()}
print("\nS4c:", json.dumps(res["S4c"], indent=1))
# S4a/b
devnames = ["rf_S", "rf_share2", "rf_mean_t2", "ovr_S", "ovr_share2", "ovr_mean_t2"]
dA, dB = dev[0, 0], dev[0, 1]
res["deviance_A"] = dict(zip(devnames, dA.tolist())); res["deviance_B"] = dict(zip(devnames, dB.tolist()))
pools = {"swap": (dev[1:].reshape(-1, 6), p6[1:, :, :8].reshape(-1, 8))}
for f in sys.argv[2:]:
    z = np.load(f)
    pools[f.split("draws_")[-1].split("_")[0]] = (z["dev"][:, 0, :], z["p6"][:, 0, :8])
res["S4ab"] = {}
for pn, (dv, pp) in pools.items():
    med = np.median(pp, 1)
    r = {"n": len(dv), "median_of_median_all": float(np.median(med)), "P_median_le_0.0557_all": float(np.mean(med <= 0.0557)),
         "per_test_P_p_lt_0.05_all": float(np.mean(pp < 0.05))}
    for j, dn in enumerate(devnames):
        geA = dv[:, j] >= dA[j]
        r[dn] = {"A": float(dA[j]), "B": float(dB[j]), "draws_mean": float(dv[:, j].mean()),
                 "rank_A_P_ge": float((1 + geA.sum()) / (1 + len(dv))), "rank_B_P_ge": float((1 + (dv[:, j] >= dB[j]).sum()) / (1 + len(dv))),
                 "n_ge_A": int(geA.sum()),
                 "median_of_median_given_ge_A": float(np.median(med[geA])) if geA.sum() else None,
                 "q05_median_given_ge_A": float(np.quantile(med[geA], 0.05)) if geA.sum() > 5 else None,
                 "P_median_le_0.0557_given_ge_A": float(np.mean(med[geA] <= 0.0557)) if geA.sum() else None,
                 "per_test_P_p_lt_0.05_given_ge_A": float(np.mean(pp[geA] < 0.05)) if geA.sum() else None,
                 "corr_deviance_with_median": float(np.corrcoef(dv[:, j], med)[0, 1])}
    res["S4ab"][pn] = r
    print(f"\nS4ab pool={pn} n={len(dv)} median-of-median {r['median_of_median_all']:.3f} P(med<=.0557)={r['P_median_le_0.0557_all']:.4f}")
    for dn in devnames:
        x = r[dn]
        print(f"  {dn:12s} A={x['A']:.3f} B={x['B']:.3f} draws mean={x['draws_mean']:.3f} P(>=A)={x['rank_A_P_ge']:.4f} P(>=B)={x['rank_B_P_ge']:.3f}"
              f" | given >=A (n={x['n_ge_A']}): med-of-med={x['median_of_median_given_ge_A']} P(med<=.0557)={x['P_median_le_0.0557_given_ge_A']}"
              f" per-test P(p<.05)={x['per_test_P_p_lt_0.05_given_ge_A']} corr(dev,med)={x['corr_deviance_with_median']:+.3f}")
json.dump(res, open(F.OUT / "s3_s4_analysis.json", "w"), indent=1, default=float)
