"""Critic round 3, check 5: shared candidate structure between samples, free of the judge's axis order.

The judge shuffles axes with a key of (prompt_id, s), so two samples read at the same slots share an
axis-order pattern. Full-sample correlations between samples' one-vs-rest cell means include it
(k12: corr(A, B) = 0.158). Here every covariance pairs half 1 of one sample with half 2 of the other
(disjoint slots, 60 random splits), so the order pattern drops out and only structure in the replies
remains. Unit: covariance of one-vs-rest cell means over the (candidate, axis) cells, times 1e6.
Groups: bases A, B; the eight nulls; the two synthetic-document arms; CO (five candidates only).
Null for 'is this covariance zero': candidates relabelled within instruction in one member (500 draws).
"""
import json, sys, warnings
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "stats_r1"))
import common as C
warnings.simplefilter("ignore", RuntimeWarning)
D = C.load_all(); cands = D["_cands"]
names = ["A", "B", "CO"] + list(C.CONTROLS) + ["sd_ai_welfare_poisoning", "sd_emotional_bond"]
rng = np.random.default_rng([20261113, 15])
NS = 60


def halves(keep):
    """(n_samples, n_splits, 2, n_c, n_i, n_j) one-vs-rest per instruction for both halves."""
    out = np.empty((len(names), NS, 2, len(keep), 36, 101))
    splits = [rng.permutation(16) for _ in range(NS)]
    for q, k in enumerate(names):
        R = D[k][keep]
        for s, perm in enumerate(splits):
            for h, sl in enumerate((np.sort(perm[:8]), np.sort(perm[8:]))):
                out[q, s, h] = np.nan_to_num(C.ovr(np.nanmean(R[:, :, sl], axis=2)))
    return out


def run(keep, tag):
    H = halves(keep)                       # per-instruction OvR
    M = H.mean(axis=4)                     # cell means (n, NS, 2, n_c, n_j)
    Mf = M.reshape(len(names), NS, 2, -1)
    n = len(names)
    cov = np.zeros((n, n))
    for a in range(n):
        for b in range(n):
            cov[a, b] = 0.5 * (np.mean(Mf[a, :, 0] * Mf[b, :, 1]) + np.mean(Mf[a, :, 1] * Mf[b, :, 0]))
    cov *= 1e6
    ix = {k: i for i, k in enumerate(names)}
    nul = [ix[k] for k in C.CONTROLS]; sd = [ix["sd_ai_welfare_poisoning"], ix["sd_emotional_bond"]]
    var_half = float(np.mean([np.mean(Mf[a] ** 2) for a in range(n) if names[a] != "CO"]) * 1e6)
    res = {"unit": "1e-6", "mean_variance_of_half_sample_cell_means": var_half,
           "A_with_B": float(cov[0, 1]), "A_with_A": float(cov[0, 0]), "B_with_B": float(cov[1, 1]),
           "null_with_itself_mean": float(np.mean([cov[i, i] for i in nul])),
           "null_with_other_null_mean": float(np.mean([cov[i, j] for i in nul for j in nul if i != j])),
           "null_with_A_mean": float(cov[nul, 0].mean()), "null_with_B_mean": float(cov[nul, 1].mean()),
           "null_with_A": dict(zip(C.CONTROLS, cov[nul, 0].round(2).tolist())), "null_with_B": dict(zip(C.CONTROLS, cov[nul, 1].round(2).tolist())),
           "null_with_itself": dict(zip(C.CONTROLS, [round(float(cov[i, i]), 2) for i in nul])),
           "sd_with_sd": float(cov[sd[0], sd[1]]), "sd_with_itself": [round(float(cov[i, i]), 2) for i in sd],
           "sd_with_null_mean": float(cov[np.ix_(sd, nul)].mean()), "sd_with_A": cov[sd, 0].round(2).tolist(), "sd_with_B": cov[sd, 1].round(2).tolist(),
           "CO_with_itself": float(cov[2, 2]), "CO_with_null_mean": float(cov[2, nul].mean()), "CO_with_A": float(cov[2, 0]), "CO_with_B": float(cov[2, 1])}
    # significance of group means by relabelling candidates within instruction in the first member
    n_c = len(keep)
    def group_stat(Hx):
        Mx = Hx.mean(axis=4).reshape(len(names), NS, 2, -1)
        def cv(a, b):
            return 0.5 * (np.mean(Mx[a, :, 0] * Mf[b, :, 1]) + np.mean(Mx[a, :, 1] * Mf[b, :, 0])) * 1e6
        return np.array([np.mean([cv(i, j) for i in nul for j in nul if i != j]), np.mean([cv(i, 0) for i in nul]),
                         np.mean([cv(i, 1) for i in nul]), cv(0, 1), cv(sd[0], sd[1]), np.mean([cv(s, j) for s in sd for j in nul])])
    obs = group_stat(H)
    null = []
    for _ in range(300):
        o = np.argsort(rng.random((36, n_c)), axis=1)            # one relabelling per instruction, applied to every sample's first member
        Hp = H[:, :, :, o.T, np.arange(36)[None, :], :]            # (n, NS, 2, n_c, n_i, n_j) relabelled
        null.append(group_stat(Hp))
    null = np.array(null)
    labs = ["null-null", "null-A", "null-B", "A-B", "sd-sd", "sd-null"]
    res["z_vs_relabel_null"] = {l: round(float((obs[q] - null[:, q].mean()) / null[:, q].std()), 2) for q, l in enumerate(labs)}
    res["null_sd_of_group_means"] = {l: round(float(null[:, q].std()), 3) for q, l in enumerate(labs)}
    print("==", tag); print(json.dumps(res, indent=1))
    return res


out = {"six": run(list(range(6)), "six"), "five": run([i for i, c in enumerate(cands) if c != "anthropic"], "five")}
(HERE / "k15_cross_half_structure.json").write_text(json.dumps(out, indent=1))
