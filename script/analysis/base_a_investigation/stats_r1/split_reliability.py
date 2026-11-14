"""Is base A's deviation reproducible inside A (systematic) or does it vanish across A's own halves (noise)?

Split each cell of base X (A or B) into two random halves of 8 replies. A systematic
deviation of X (engine, judge period, anything that touches every reply of X) shows in
both halves, so the deviation measured from half 1 against one set of other samples
correlates with the deviation measured from half 2 against a disjoint set. Sampling noise
does not: the halves' noises are independent.

  G1 = t-grid of (consensus of the 8 nulls - X_half1)
  G2 = t-grid of (consensus of the other base and the 2 synth-doc arms - X_half2)
  r_X = corr over the 606 cells of G1 and G2, averaged over 100 random splits.
Null for r: the same with G2's input relabelled within instruction (200 relabellings on
one split), which keeps every marginal and breaks only the cell alignment.
Also the split-half reliability of X's own deviation from the full 11-sample consensus:
corr( t(cons11 - X_h1), t(cons11 - X_h2) ) where cons11 excludes X.
"""
import json
import sys
import warnings
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CONTROLS, OUT, apply_orders, load_all, ovr, perm_orders, rates, tgrid  # noqa

D = load_all()
O = {k: ovr(rates(v)) for k, v in D.items() if not k.startswith("_")}
SD = ["sd_ai_welfare_poisoning", "sd_emotional_bond"]
rng = np.random.default_rng(31)
orders = perm_orders(seed=4242, k=200)


def halves(R):
    idx = np.argsort(rng.random(R.shape[:3]), axis=2)
    Rs = np.take_along_axis(R, idx[..., None], axis=2)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return ovr(np.nanmean(Rs[:, :, :8], 2)), ovr(np.nanmean(Rs[:, :, 8:], 2))


def corr(a, b):
    return float(np.corrcoef(np.nan_to_num(a).ravel(), np.nan_to_num(b).ravel())[0, 1])


res = {}
for X, other in (("A", "B"), ("B", "A")):
    consN = np.mean([O[c] for c in CONTROLS], axis=0)
    consS = np.mean([O[other]] + [O[s] for s in SD], axis=0)
    cons11 = np.mean([O[k] for k in ["A", "B"] + list(CONTROLS) + SD if k != X], axis=0)
    rs, rel = [], []
    for _ in range(100):
        h1, h2 = halves(D[X])
        rs.append(corr(tgrid(consN - h1)[0], tgrid(consS - h2)[0]))
        rel.append(corr(tgrid(cons11 - h1)[0], tgrid(cons11 - h2)[0]))
    h1, h2 = halves(D[X])
    g1 = tgrid(consN - h1)[0]
    dperm = apply_orders(consS - h2, orders)
    null = np.array([corr(g1, tgrid(dp)[0]) for dp in dperm])
    # null for 'rel': cons11 noise is shared by both halves, so relabel half 2's own deviation
    dperm2 = apply_orders(cons11 - h2, orders)
    g1b = tgrid(cons11 - h1)[0]
    null2 = np.array([corr(g1b, tgrid(dp)[0]) for dp in dperm2])
    res[X] = {"r_disjoint_mean": float(np.mean(rs)), "r_disjoint_sd_over_splits": float(np.std(rs)),
              "r_disjoint_null_mean": float(null.mean()), "r_disjoint_null_sd": float(null.std()),
              "reliability_vs_cons11_mean": float(np.mean(rel)),
              "reliability_null_mean": float(null2.mean()), "reliability_null_sd": float(null2.std())}
    print(X, json.dumps(res[X], indent=1), flush=True)
json.dump(res, open(OUT / "split_reliability.json", "w"), indent=1)
