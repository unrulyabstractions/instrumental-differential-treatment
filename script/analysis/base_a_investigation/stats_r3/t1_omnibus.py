"""T1. Reproduce the critic's omnibus and provenance contrasts from the stored swap draws, independently.

HEADLINE, NAMED BEFORE THIS SCRIPT WAS RUN: the direction-free sum of squared standardized S gaps over
all ten null fine-tunes on six candidates, z_k = (S(T_k|A') - S(T_k|B')) / sd_k, with sd_k and the
p-value from the 3,999 non-identity swap draws in stats_r2/out/draws_swap_4000.npz (draw 0 is the real
A and B). Its five-candidate twin (eleven targets, with contextual_optimism) is reported beside it.
Everything else in this file is secondary.

Source draws: at each (candidate, instruction, s) slot with both replies, A's and B's replies trade
places with probability 1/2; targets fixed; exact registered p (10,000 permutations, seed 20260726).
Three gap scales: S (largest |t|), probit of the exact p (Phi^-1(1 - p)), and a rank-normalized gap
(each target's gap mapped to its swap-null mid-rank percentile, then probit), which makes each z_k
exactly N(0, 1) under the null whatever the tails.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy import stats

HERE = Path(__file__).resolve().parent
DR = HERE.parent / "stats_r2" / "out" / "draws_swap_4000.npz"
z = np.load(DR)
S6, p6, S5, p5 = z["S6"], z["p6"], z["S5"], z["p5"]
T6 = [str(x) for x in z["targets6"]]
T5 = [str(x) for x in z["targets5"]]
N = S6.shape[0]
assert np.allclose(p6[0, 0, :8], [0.0133, 0.0605, 0.0325, 0.0561, 0.0381, 0.6338, 0.1584, 0.0554], atol=5e-5)


def probit(p):
    # Phi^-1(1 - p): large when p is small. p = 1 (every permutation at least as large) is clipped to
    # 1 - 1/(2 * 10001) so the transform stays finite; p never falls below 1/10001.
    return stats.norm.isf(np.clip(p, 1.0 / 10001, 1.0 - 0.5 / 10001))


def ptail(v_null, v_obs):
    return float((1 + np.sum(v_null >= v_obs)) / (1 + len(v_null)))


def p2(v_null, v_obs):
    return float((1 + np.sum(np.abs(v_null) >= abs(v_obs))) / (1 + len(v_null)))


def rank_norm(G):
    """Map each column to its mid-rank percentile among the null rows (1..), then probit."""
    out = np.empty_like(G)
    null = G[1:]
    for k in range(G.shape[1]):
        srt = np.sort(null[:, k])
        lo = np.searchsorted(srt, G[:, k], side="left")
        hi = np.searchsorted(srt, G[:, k], side="right")
        u = (lo + hi) / 2.0 + 0.5
        out[:, k] = stats.norm.ppf(u / (len(srt) + 1))
    return out


def analyse(G, names, label, contrasts):
    """G: (N, m) gaps, row 0 observed."""
    sd = G[1:].std(0)
    Z = G / sd
    r = {"names": names, "gap_obs": np.round(G[0], 4).tolist(), "null_sd": np.round(sd, 4).tolist(),
         "z_obs": np.round(Z[0], 3).tolist()}
    sz = (Z ** 2).sum(1)
    r["sum_z2"] = {"obs": float(sz[0]), "null_mean": float(sz[1:].mean()), "p": ptail(sz[1:], sz[0]),
                   "chi2_ref_p": float(stats.chi2.sf(sz[0], len(names)))}
    mz = np.abs(Z).max(1)
    r["max_abs_z"] = {"obs": float(mz[0]), "p": ptail(mz[1:], mz[0])}
    mg = G.mean(1)
    r["signed_mean_gap"] = {"obs": float(mg[0]), "null_sd": float(mg[1:].std()), "z": float(mg[0] / mg[1:].std()),
                            "p_one_upper": ptail(mg[1:], mg[0]), "p_two": p2(mg[1:] - mg[1:].mean(), mg[0] - mg[1:].mean())}
    loo = {}
    for k, nm in enumerate(names):
        keep = [j for j in range(len(names)) if j != k]
        s = (Z[:, keep] ** 2).sum(1)
        loo[nm] = {"sum_z2": round(float(s[0]), 2), "null_mean": round(float(s[1:].mean()), 2), "p": ptail(s[1:], s[0])}
    r["leave_one_out_sum_z2"] = loo
    for cl, (code, unit) in contrasts.items():
        code = np.asarray(code, float)
        msk = code != 0
        if unit == "S":
            # difference of family means in gap units (the critic's 'eight minus synthetic' contrast)
            pos, neg = code > 0, code < 0
            v = G[:, pos].mean(1) - (G[:, neg].mean(1) if neg.any() else 0.0)
        else:
            v = (Z[:, msk] * code[msk]).mean(1)
        r[cl] = {"obs": float(v[0]), "null_mean": float(v[1:].mean()), "null_sd": float(v[1:].std()),
                 "z": float((v[0] - v[1:].mean()) / v[1:].std()),
                 "p_two": p2(v[1:] - v[1:].mean(), v[0] - v[1:].mean()), "n_targets": int(msk.sum())}
    # pairwise correlation of the z under the null (how much the targets move together)
    cm = np.corrcoef(Z[1:].T)
    r["null_corr_mean_offdiag"] = float(cm[~np.eye(len(names), dtype=bool)].mean())
    return r


res = {"headline_named_in_advance": "sum z^2 over the ten null fine-tunes, six candidates, S-gap scale", "N_null": N - 1}
for scale in ("S", "probit_p", "rank_norm"):
    if scale == "S":
        G6, G5 = S6[:, 0] - S6[:, 1], S5[:, 0] - S5[:, 1]
    elif scale == "probit_p":
        G6 = probit(p6[:, 0]) - probit(p6[:, 1])
        G5 = probit(p5[:, 0]) - probit(p5[:, 1])
    else:
        G6 = rank_norm(S6[:, 0] - S6[:, 1])
        G5 = rank_norm(S5[:, 0] - S5[:, 1])
    six_con = {
        "eight_minus_synthetic_gap_units": ([1] * 8 + [-1] * 2, "S"),
        # six candidates has no contextual_optimism; engine version: nulls and SD arms both share 0.11.0 with B (+1)
        "prov_engine_version": ([+1] * 10, "z"),
        "prov_sampler_gpu_judge_month": ([-1] * 8 + [+1] * 2, "z"),
        "prov_engine_process": ([0] * 8 + [+1] * 2, "z"),
    }
    five_con = {
        "eight_minus_synthetic_gap_units": ([1] * 8 + [-1] * 2 + [0], "S"),
        "prov_engine_version": ([+1] * 10 + [-1], "z"),
        "prov_engine_version_outside_eight": ([0] * 8 + [+1, +1, -1], "z"),
        "prov_sampler_gpu_judge_month": ([-1] * 8 + [+1] * 2 + [-1], "z"),
        "prov_sampler_gpu_judge_month_outside_eight": ([0] * 8 + [+1] * 2 + [-1], "z"),
        "prov_engine_process": ([0] * 8 + [+1] * 2 + [-1], "z"),
    }
    res[f"{scale} | ten, six candidates"] = analyse(G6, T6, "ten6", six_con)
    res[f"{scale} | eight, six candidates"] = analyse(G6[:, :8], T6[:8], "eight6", {})
    res[f"{scale} | two synthetic arms, six candidates"] = analyse(G6[:, 8:], T6[8:], "sd6", {})
    res[f"{scale} | eleven, five candidates"] = analyse(G5, T5, "eleven5", five_con)
    res[f"{scale} | eight, five candidates"] = analyse(G5[:, :8], T5[:8], "eight5", {})
    res[f"{scale} | ten, five candidates"] = analyse(G5[:, :10], T5[:10], "ten5", {})
    res[f"{scale} | three outside the eight, five candidates"] = analyse(G5[:, 8:], T5[8:], "three5", {})

for k, v in res.items():
    if not isinstance(v, dict):
        print(k, v)
        continue
    line = f"{k:55s} sum z2 {v['sum_z2']['obs']:6.2f} (null {v['sum_z2']['null_mean']:5.2f}) p {v['sum_z2']['p']:.4f} chi2 {v['sum_z2']['chi2_ref_p']:.4f}"
    line += f" | max|z| {v['max_abs_z']['obs']:.2f} p {v['max_abs_z']['p']:.4f} | mean gap {v['signed_mean_gap']['obs']:+.3f} z {v['signed_mean_gap']['z']:+.2f} p1 {v['signed_mean_gap']['p_one_upper']:.4f} p2 {v['signed_mean_gap']['p_two']:.4f}"
    print(line)
    print("     z:", dict(zip(v["names"], v["z_obs"])), "null corr", round(v["null_corr_mean_offdiag"], 3))
    for c in [c for c in v if c.startswith("prov") or c.startswith("eight_minus")]:
        print(f"     {c:45s} obs {v[c]['obs']:+.3f} sd {v[c]['null_sd']:.3f} z {v[c]['z']:+.2f} p2 {v[c]['p_two']:.5f}")
    if "ten" in k or "eleven" in k:
        print("     LOO:", {n: (d["sum_z2"], d["p"]) for n, d in v["leave_one_out_sum_z2"].items()})
json.dump(res, open(HERE / "out" / "t1_omnibus.json", "w"), indent=1)
