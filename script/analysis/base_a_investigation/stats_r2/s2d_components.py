"""S2d. Where does the replicating part of A - B live? ANOVA split of the half-sample differences.

d_h = A_h - B_h on raw cell rates (matched slots), h = 1, 2. Each d_h is split into
  axis (j)              : mean over candidates and instructions
  instruction x axis    : mean over candidates, minus the axis part          (cancels in one-vs-rest)
  candidate x axis      : mean over instructions, minus the axis part       (what the test's mean sees)
  residual (c, i, j)    : the rest                                           (enters the test's spread only)
For each part, the replication is the mean over cells of part_1 * part_2 (a covariance; 0 under iid
replies and no arm difference). Swap null as in s2c (A and B replies trade places per slot).
Per candidate for the candidate x axis part too.
"""
import json
import warnings

import numpy as np

import fast as F

D = F.load()
cands = D["_cands"]
RA, RB = D["A"], D["B"]
both = ~np.isnan(RA).all(3) & ~np.isnan(RB).all(3)
rng = np.random.default_rng(717)


def hr(R, sl):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(R[:, :, sl], axis=2)


def parts(d):
    j = d.mean(axis=(0, 1), keepdims=True)
    ij = d.mean(axis=0, keepdims=True) - j
    cj = d.mean(axis=1, keepdims=True) - j
    res = d - j - ij - cj
    return j, ij, cj, res


def stat(X, Y, n):
    acc = np.zeros(4 + 6)
    for _ in range(n):
        p = rng.permutation(16)
        P1 = parts(hr(X, p[:8]) - hr(Y, p[:8])); P2 = parts(hr(X, p[8:]) - hr(Y, p[8:]))
        for k in range(4):
            acc[k] += float(np.mean(P1[k] * P2[k]))
        for c in range(6):
            acc[4 + c] += float(np.mean(P1[2][c] * P2[2][c]))
    return acc / n


obs = stat(RA, RB, 200)
nul = []
for _ in range(300):
    m = ((rng.random(RA.shape[:3]) < 0.5) & both)[..., None]
    nul.append(stat(np.where(m, RB, RA), np.where(m, RA, RB), 20))
nul = np.array(nul)
labels = ["axis", "instruction x axis", "candidate x axis", "residual (c,i,j)"] + [f"candidate x axis, {c}" for c in cands]
res = {}
for k, lab in enumerate(labels):
    res[lab] = {"obs": float(obs[k]), "null_mean": float(nul[:, k].mean()), "null_sd": float(nul[:, k].std()),
                "z": float((obs[k] - nul[:, k].mean()) / nul[:, k].std()),
                "p_upper": float((1 + np.sum(nul[:, k] >= obs[k])) / (1 + len(nul)))}
    print(f"{lab:36s} obs {obs[k]:+.3e} null {nul[:, k].mean():+.3e} +/- {nul[:, k].std():.3e} z={res[lab]['z']:+.2f} p_up={res[lab]['p_upper']:.3f}")
json.dump(res, open(F.OUT / "s2d_components.json", "w"), indent=1)
