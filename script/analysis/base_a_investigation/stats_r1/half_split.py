"""Calibration of the registered test on pure sampling noise, from the data themselves.

Within one sample X, each cell's 16 replies are split at random into two halves of 8,
and half 1 is tested against half 2 with the registered statistic and permutation
scheme (2,000 permutations; the null's resolution is enough for rates). The halves are
exchangeable by construction, so p is uniform if the test is calibrated for this noise.
Cross pairs (half of X vs half of Y) carry the same noise level plus whatever structured
difference separates X and Y, so comparing cross to within isolates that difference.

Also: an ordered split by judging order (first-judged 8 vs last-judged 8 replies of each
cell, by row position in the verdict file), which would expose judge drift in time.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CONTROLS, OUT, excess, load_all, perm_null, perm_orders, smax, tail_p, tgrid  # noqa

R_SPLITS = int(sys.argv[1]) if len(sys.argv) > 1 else 100
D = load_all()
names = ["A", "B"] + list(CONTROLS) + ["sd_ai_welfare_poisoning", "sd_emotional_bond"]
orders = perm_orders(seed=777, k=2000)
rng = np.random.default_rng(12345)


def halves(R, rng):
    """Random 8/8 split of each cell's replies (NaN replies stay NaN wherever they land)."""
    n_c, n_i, n_s, _ = R.shape
    idx = np.argsort(rng.random((n_c, n_i, n_s)), axis=2)
    Rs = np.take_along_axis(R, idx[..., None], axis=2)
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(Rs[:, :, :8], axis=2), np.nanmean(Rs[:, :, 8:], axis=2)


def test(pt, pb):
    d = excess(pt, pb)
    s = float(smax(tgrid(d)[0]))
    return tail_p(perm_null(d, orders), s)


res = {"within": {}, "cross": {}}
for x in names:
    ps = []
    for r in range(R_SPLITS):
        h1, h2 = halves(D[x], rng)
        ps.append(test(h1, h2))
    ps = np.array(ps)
    res["within"][x] = ps.tolist()
    print(f"within {x:26s} median p={np.median(ps):.3f} P(p<.05)={np.mean(ps < .05):.3f} "
          f"P(p<.10)={np.mean(ps < .10):.3f}", flush=True)
cross_pairs = [("A", "B")] + [(c, "A") for c in CONTROLS] + [(c, "B") for c in CONTROLS]
for x, y in cross_pairs:
    ps = []
    for r in range(R_SPLITS):
        hx, _ = halves(D[x], rng)
        hy, _ = halves(D[y], rng)
        ps.append(test(hx, hy))
    ps = np.array(ps)
    res["cross"][f"{x}|{y}"] = ps.tolist()
    print(f"cross  {x:20s}|{y:2s} median p={np.median(ps):.3f} P(p<.05)={np.mean(ps < .05):.3f} "
          f"P(p<.10)={np.mean(ps < .10):.3f}", flush=True)
allw = np.concatenate([np.array(v) for v in res["within"].values()])
print(f"ALL within: n={len(allw)} median={np.median(allw):.3f} P<.05={np.mean(allw < .05):.3f} "
      f"P<.10={np.mean(allw < .1):.3f} KS-uniform D={__import__('scipy').stats.kstest(allw, 'uniform').statistic:.3f}")
json.dump(res, open(OUT / f"half_split_{R_SPLITS}.json", "w"))
