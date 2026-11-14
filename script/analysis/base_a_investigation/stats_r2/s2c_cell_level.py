"""S2c. Does A - B replicate at the level of single prompts (candidate x instruction x axis)?

Base A and base B are the same model on the same prompts, so their true per-prompt rates are equal and
A_h - B_h (half-sample rates, matched slots) is pure noise unless (a) the two arms differ systematically
or (b) the 16 replies of one prompt share something beyond the prompt (one vLLM request with n=16,
one judging session), in either arm. Statistic: correlation over all (c, i, j) of (A_h1 - B_h1) and
(A_h2 - B_h2), on raw cell rates and on one-vs-rest gaps; averaged over 200 random matched splits.
Swap null: A and B replies trade places at each slot (300 swaps x 20 splits). Also per candidate,
and restricted to the eight tests' full-sample peak axes.
"""
import json
import warnings

import numpy as np

import fast as F
from fast import C

D = F.load()
cands = D["_cands"]
RA, RB = D["A"], D["B"]
both = ~np.isnan(RA).all(3) & ~np.isnan(RB).all(3)
rng = np.random.default_rng(616)


def hr(R, sl):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(R[:, :, sl], axis=2)


def stat(X, Y, n):
    acc = np.zeros(2 + 6)
    for _ in range(n):
        p = rng.permutation(16)
        d1 = hr(X, p[:8]) - hr(Y, p[:8]); d2 = hr(X, p[8:]) - hr(Y, p[8:])
        o1, o2 = C.ovr(hr(X, p[:8])) - C.ovr(hr(Y, p[:8])), C.ovr(hr(X, p[8:])) - C.ovr(hr(Y, p[8:]))
        ok = np.isfinite(d1) & np.isfinite(d2)
        acc[0] += np.corrcoef(d1[ok], d2[ok])[0, 1]
        acc[1] += np.corrcoef(o1[ok], o2[ok])[0, 1]
        for c in range(6):
            okc = ok[c]
            acc[2 + c] += np.corrcoef(d1[c][okc], d2[c][okc])[0, 1]
    return acc / n


obs = stat(RA, RB, 200)
nul = []
for _ in range(300):
    m = ((rng.random(RA.shape[:3]) < 0.5) & both)[..., None]
    nul.append(stat(np.where(m, RB, RA), np.where(m, RA, RB), 20))
nul = np.array(nul)
labels = ["raw rates", "one-vs-rest"] + [f"raw, {c}" for c in cands]
res = {}
for k, lab in enumerate(labels):
    res[lab] = {"obs": float(obs[k]), "null_mean": float(nul[:, k].mean()), "null_sd": float(nul[:, k].std()),
                "z": float((obs[k] - nul[:, k].mean()) / nul[:, k].std()),
                "p_upper": float((1 + np.sum(nul[:, k] >= obs[k])) / (1 + len(nul)))}
    print(f"{lab:28s} obs {obs[k]:+.4f}  null {nul[:, k].mean():+.4f} +/- {nul[:, k].std():.4f}  z={res[lab]['z']:+.2f} p_up={res[lab]['p_upper']:.3f}")
json.dump(res, open(F.OUT / "s2c_cell_level.json", "w"), indent=1)
