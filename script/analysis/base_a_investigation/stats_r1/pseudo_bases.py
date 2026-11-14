"""How unlikely is a median p of 0.056 for the eight nulls against one fresh base?

Pseudo-bases built from the two real base samples, with the eight null targets held
fixed as observed. Under H0 that base A and base B are exchangeable draws of the same
base model (same prompts, independent sampling), every scheme below yields valid base
draws, and the all-A assignment is one of them; its rank is a conditional p-value.

  instr : each of the 36 instructions' (6 x 101) block from A or B, fair coin
  cell  : each of the 216 (candidate, instruction) cells from A or B, fair coin
  reply : each of the 16 reply slots of each cell from A or B, fair coin
  boot16: 16 replies drawn with replacement from the pooled 32 of each cell
          (random part the size of one fresh base's noise; the pool centre is fixed)

2,000 permutations per test (seed 777) to keep 8 x N tests affordable.
Usage: pseudo_bases.py <scheme> <n_draws>
"""
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CONTROLS, OUT, excess, load_all, perm_null, perm_orders, rates, smax, tail_p, tgrid  # noqa

scheme, N = sys.argv[1], int(sys.argv[2])
D = load_all()
P = {k: rates(v) for k, v in D.items() if not k.startswith("_")}
RA, RB = D["A"], D["B"]
orders = perm_orders(seed=777, k=2000)
rng = np.random.default_rng({"instr": 1, "cell": 2, "reply": 3, "boot16": 4}[scheme])
OT = {c: P[c] for c in CONTROLS}


def eight(pb):
    out = []
    for c in CONTROLS:
        d = excess(OT[c], pb)
        out.append(tail_p(perm_null(d, orders), float(smax(tgrid(d)[0]))))
    return out


def draw():
    if scheme == "instr":
        m = rng.random(36) < 0.5
        pb = P["B"].copy(); pb[:, m] = P["A"][:, m]; return pb, float(m.mean())
    if scheme == "cell":
        m = rng.random((6, 36)) < 0.5
        pb = P["B"].copy(); pb[m] = P["A"][m]; return pb, float(m.mean())
    if scheme == "reply":
        m = rng.random(RA.shape[:3]) < 0.5
        R = np.where(m[..., None], RA, RB)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            return np.nanmean(R, axis=2), float(m.mean())
    if scheme == "boot16":
        pool = np.concatenate([RA, RB], axis=2)          # (6, 36, 32, 101)
        idx = rng.integers(0, 32, size=(6, 36, 16))
        R = np.take_along_axis(pool, idx[..., None], axis=2)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            return np.nanmean(R, axis=2), float(np.mean(idx < 16))
    raise SystemExit(scheme)


t0 = time.time()
ref = {"A": eight(P["A"]), "B": eight(P["B"])}
meds, fracA, allp = [], [], []
for n in range(N):
    pb, fa = draw()
    ps = eight(pb)
    allp.append(ps); meds.append(float(np.median(ps))); fracA.append(fa)
meds, fracA, allp = np.array(meds), np.array(fracA), np.array(allp)
mA, mB = float(np.median(ref["A"])), float(np.median(ref["B"]))
r = {"scheme": scheme, "n_draws": N, "n_perm": 2000,
     "median_A_2000perm": mA, "median_B_2000perm": mB,
     "P_median_le_A": float((1 + np.sum(meds <= mA)) / (1 + N)),
     "P_median_le_0.0557": float(np.mean(meds <= 0.0557)),
     "P_median_le_0.10": float(np.mean(meds <= 0.10)),
     "quantiles": {q: float(np.quantile(meds, q)) for q in (0.01, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9)},
     "min": float(meds.min()),
     "corr_median_with_share_A": float(np.corrcoef(meds, fracA)[0, 1]),
     "mean_frac_p_lt_0.05": float(np.mean(allp < 0.05)),
     "median_per_test": [float(x) for x in np.median(allp, axis=0)],
     "seconds": time.time() - t0}
print(json.dumps(r, indent=1))
json.dump({**r, "medians": meds.tolist(), "fracA": fracA.tolist()},
          open(OUT / f"pseudo_bases_{scheme}_{N}.json", "w"))
