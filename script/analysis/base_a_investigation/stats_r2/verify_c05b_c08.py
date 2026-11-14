"""Independent re-implementation of the critic's matched-slot split-half replication (c05b, c08b).

For samples X, R and a split of the 16 slots into halves (one split for both samples when matched,
independent splits when unmatched): G1 = t-grid of OvR(X_h1) - OvR(R_h1), G2 the same on the other
halves; r = corr(G1, G2) over cells; hot12 = mean over the top-12 cells of |G1| of sign(G1)*G2,
symmetrised. Null: swap X and R replies at each slot. Checks: the observed values for A vs B (six and
five candidates), their swap-null mean and sd, and the claim that UNMATCHED slots bias the null mean
of r to about -0.068.
"""
import json
import warnings

import numpy as np

import fast as F
from fast import C

D = F.load()
keep5 = [i for i, c in enumerate(D["_cands"]) if c != "anthropic"]
rng = np.random.default_rng(8080)


def hr(R, sl):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(R[:, :, sl], axis=2)


def tg(d):
    t = C.tgrid_fast(d)[0]
    return np.where(np.isfinite(t), t, 0.0).ravel()


def stat(X, R, matched):
    p = rng.permutation(16)
    q = p if matched else rng.permutation(16)
    g1 = tg(C.ovr(hr(X, p[:8])) - C.ovr(hr(R, q[:8])))
    g2 = tg(C.ovr(hr(X, p[8:])) - C.ovr(hr(R, q[8:])))
    r = np.corrcoef(g1, g2)[0, 1]
    t1, t2 = np.argsort(-np.abs(g1))[:12], np.argsort(-np.abs(g2))[:12]
    h = 0.5 * (np.mean(np.sign(g1[t1]) * g2[t1]) + np.mean(np.sign(g2[t2]) * g1[t2]))
    return r, h


def avg(X, R, n, matched=True):
    return np.mean([stat(X, R, matched) for _ in range(n)], axis=0)


def swap(X, R):
    m = (rng.random(X.shape[:3]) < 0.5)[..., None]
    return np.where(m, R, X), np.where(m, X, R)


res = {}
for lab, X, R in (("six", D["A"], D["B"]), ("five", D["A"][keep5], D["B"][keep5])):
    obs = avg(X, R, 200)
    nul = np.array([avg(*swap(X, R), 12) for _ in range(150)])
    res[lab] = {"r": float(obs[0]), "hot12": float(obs[1]), "null_mean": nul.mean(0).tolist(), "null_sd": nul.std(0).tolist(),
                "z": ((obs - nul.mean(0)) / nul.std(0)).tolist()}
    print(lab, json.dumps(res[lab]), flush=True)
un = np.array([avg(*swap(D["A"], D["B"]), 12, matched=False) for _ in range(60)])
res["unmatched_null_six"] = {"mean": un.mean(0).tolist(), "sd": un.std(0).tolist(), "se_of_mean": (un.std(0) / np.sqrt(len(un))).tolist()}
print("unmatched swap-null mean (r, hot12):", un.mean(0).round(4), "se", (un.std(0) / np.sqrt(len(un))).round(4))
json.dump(res, open(F.OUT / "verify_c05b_c08.json", "w"), indent=1)
