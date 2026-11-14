"""Does base A's deviation follow the order in which its candidates were judged?

Base A (and the eight nulls) were judged online in candidate blocks: anthropic first,
stanford last (row order of the verdict file). A judge whose behaviour drifts in time
would leave a deviation that is a smooth (here: linear) function of block order on each
axis. For each sample X, dev_X = mean over instructions of (OvR_X - consensus of the
other base-like samples), a (6 x 101) array. The share of sum(dev^2) captured by a
per-axis linear trend in candidate order is compared with the same share under all 720
relabellings of the candidate order (an exact null for 'order does not matter').
Also: within-block drift in A, i.e. does a reply's position inside its candidate block
predict its verdicts once each cell's mean is removed (permutation over positions).
"""
import itertools
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BASE_A, CONTROLS, OUT, AXES, load_all, ovr, rates, null_target  # noqa

D = load_all()
cands = D["_cands"]
P = {k: rates(v) for k, v in D.items() if not k.startswith("_")}
O = {k: ovr(v) for k, v in P.items()}
pool = ["A", "B"] + list(CONTROLS) + ["sd_ai_welfare_poisoning", "sd_emotional_bond"]


def linear_share(dev, order):
    x = np.array(order, float); x = x - x.mean()
    beta = (x[:, None] * dev).sum(0) / (x ** 2).sum()
    fit = x[:, None] * beta[None, :]
    return float((fit ** 2).sum() / (dev ** 2).sum())


res = {}
perms = list(itertools.permutations(range(6)))
for X in pool:
    ref = np.mean([O[o] for o in pool if o != X], axis=0)
    dev = (O[X] - ref).mean(axis=1)                       # (6, 101)
    # standardise each cell by its across-instruction se so the share is in t units
    se = (O[X] - ref).std(axis=1, ddof=1) / 6.0
    z = dev / se
    obs = linear_share(z, range(6))
    null = np.array([linear_share(z, p) for p in perms])
    res[X] = {"share_linear_in_judging_order": obs, "rank_p": float(np.mean(null >= obs)),
              "null_mean": float(null.mean())}
    print(f"{X:26s} linear-in-order share {obs:.3f} (null mean {null.mean():.3f}, exact p={np.mean(null >= obs):.3f})")

# within-block drift in base A
rows = [json.loads(l) for l in open(BASE_A)]
ci = {c: i for i, c in enumerate(cands)}
pos = {}
for n, r in enumerate(rows):
    pos[(r["principal"], r["instruction_id"], int(r["s"]))] = n
instr = D["_instr"]
RA = D["A"]
# relative position inside the candidate's block
posarr = np.full(RA.shape[:3], np.nan)
for (c, i, s), n in pos.items():
    posarr[ci[c], instr.index(i), s] = n
for c in range(6):
    v = posarr[c]; lo, hi = np.nanmin(v), np.nanmax(v)
    posarr[c] = (v - lo) / (hi - lo)
resid = RA - np.nanmean(RA, axis=2, keepdims=True)
pc = posarr - np.nanmean(posarr, axis=2, keepdims=True)


def slope_stat(pc):
    num = np.nansum(resid * pc[..., None], axis=(0, 1, 2))
    den = np.nansum((pc ** 2)[..., None] * ~np.isnan(resid), axis=(0, 1, 2))
    b = num / den
    return float(np.sum(b ** 2)), b


obs, b = slope_stat(pc)
rng = np.random.default_rng(5)
null = []
for _ in range(500):
    idx = np.argsort(rng.random(pc.shape), axis=2)
    null.append(slope_stat(np.take_along_axis(pc, idx, axis=2))[0])
null = np.array(null)
res["A_within_block_drift"] = {"sum_sq_slopes": obs, "null_mean": float(null.mean()),
                               "p": float((1 + np.sum(null >= obs)) / 501)}
print("A within-block drift: sum of squared per-axis slopes", obs, "null mean", null.mean(),
      "p", res["A_within_block_drift"]["p"])
json.dump(res, open(OUT / "order_drift.json", "w"), indent=1)
