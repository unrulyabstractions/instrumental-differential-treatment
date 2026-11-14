"""How surprising is a median p of 0.056 over eight tests that share one base?

Joint-permutation null: one within-instruction candidate relabelling pi is applied to
the base AND all eight targets at once. Under H0 for all eight (every target has the
base's candidate effects) the joint law of (d_1..d_8) is invariant under a common pi,
so the vector of eight p-values computed from pi(d_1..d_8) is a draw from their joint
null, with the dependence the shared base induces kept intact. The p of each pi is its
rank within the same 10,000 permutations (leave-self-out). The observed vector is pi=id.

Reports for base A and base B: P(median <= observed), P(#p<0.07 >= observed count),
P(Fisher combination >= observed), the correlation of S_k across tests under the joint
null, and the same tail probabilities if the eight tests were independent.
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CONTROLS, OUT, excess, load_all, perm_null, perm_orders, rates, smax, tgrid  # noqa

D = load_all()
P = {k: rates(v) for k, v in D.items() if not k.startswith("_")}
orders = perm_orders()
M = len(orders)


def pvals_from_null(Smat, s_obs):
    """Smat: (M, K) null stats under joint perms; s_obs: (K,).
    Returns observed p (K,) and the per-permutation p matrix (M, K) using leave-self-out ranks."""
    K = Smat.shape[1]
    p_obs = np.array([(1 + np.sum(Smat[:, k] >= s_obs[k])) / (1 + M) for k in range(K)])
    pm = np.empty_like(Smat)
    for k in range(K):
        col = Smat[:, k]
        srt = np.sort(col)
        # count of others >= value, (including the observed identity as one more draw)
        ge = M - np.searchsorted(srt, col, side="left")  # includes itself
        ge_id = (s_obs[k] >= col).astype(int)            # the identity permutation counts too
        pm[:, k] = (ge - 1 + ge_id + 1) / (1 + M)
    return p_obs, pm


def fisher(p):
    return -2 * np.sum(np.log(p), axis=-1)


res = {}
for bk in ("A", "B"):
    s_obs = np.empty(8)
    Smat = np.empty((M, 8))
    for k, c in enumerate(CONTROLS):
        d = excess(P[c], P[bk])
        s_obs[k] = smax(tgrid(d)[0])
        Smat[:, k] = perm_null(d, orders)
    p_obs, pm = pvals_from_null(Smat, s_obs)
    med_obs = np.median(p_obs)
    med_null = np.median(pm, axis=1)
    n07_obs = int(np.sum(p_obs < 0.07))
    n07_null = np.sum(pm < 0.07, axis=1)
    f_obs = fisher(p_obs)
    f_null = fisher(pm)
    C = np.corrcoef(Smat.T)
    off = C[~np.eye(8, dtype=bool)]
    Cp = np.corrcoef(pm.T)
    offp = Cp[~np.eye(8, dtype=bool)]
    # independent-tests reference
    rng = np.random.default_rng(1)
    U = rng.uniform(size=(200000, 8))
    r = {
        "p_obs": p_obs.tolist(), "median_obs": float(med_obs),
        "P_median_le_obs_joint": float((1 + np.sum(med_null <= med_obs)) / (1 + M)),
        "P_median_ge_obs_joint": float((1 + np.sum(med_null >= med_obs)) / (1 + M)),
        "P_median_le_obs_indep": float(np.mean(np.median(U, 1) <= med_obs)),
        "n_lt_0.07_obs": n07_obs,
        "P_n07_ge_obs_joint": float((1 + np.sum(n07_null >= n07_obs)) / (1 + M)),
        "P_n07_ge_obs_indep": float(stats.binom.sf(n07_obs - 1, 8, 0.07)),
        "fisher_obs": float(f_obs),
        "P_fisher_ge_obs_joint": float((1 + np.sum(f_null >= f_obs)) / (1 + M)),
        "P_fisher_ge_obs_indep": float(stats.chi2.sf(f_obs, 16)),
        "mean_corr_S_joint": float(off.mean()), "mean_corr_p_joint": float(offp.mean()),
        "joint_null_median_quantiles": {q: float(np.quantile(med_null, q)) for q in (.01, .05, .1, .25, .5)},
        "joint_null_sd_of_median": float(med_null.std()),
    }
    res[bk] = r
    print(bk, json.dumps(r, indent=1), flush=True)
    np.save(OUT / f"joint_Smat_{bk}.npy", Smat)
json.dump(res, open(OUT / "joint_median.json", "w"), indent=1)
