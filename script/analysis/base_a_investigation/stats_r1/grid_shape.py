"""Is the excess spread over the whole t-grid (broad) or in its tail (sparse)?

For each pairing, compares whole-grid summaries of the 606 t values with their
permutation distribution (same 10,000 permutations as the registered test):
mean t^2, share |t|>2, share |t|>3, and max|t|. Also the base-vs-consensus tests:
base A and base B each against the average of the eight null targets.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (CONTROLS, OUT, apply_orders, excess, load_all, perm_orders, rates,  # noqa
                    smax, tail_p, tgrid, tgrid_fast)

D = load_all()
P = {k: rates(v) for k, v in D.items() if not k.startswith("_")}
orders = perm_orders()


def summaries(t):
    a = np.abs(t)
    return {"mean_t2": np.nanmean(np.minimum(a, 50) ** 2, axis=(-2, -1)),
            "frac_gt2": np.mean(a > 2, axis=(-2, -1)),
            "frac_gt3": np.mean(a > 3, axis=(-2, -1)),
            "max": smax(t)}


def perm_summaries(d, chunk=500):
    acc = {k: [] for k in ("mean_t2", "frac_gt2", "frac_gt3", "max")}
    for s in range(0, len(orders), chunk):
        t = tgrid_fast(apply_orders(d, orders[s:s + chunk]))[0]
        for k, v in summaries(t).items():
            acc[k].append(v)
    return {k: np.concatenate(v) for k, v in acc.items()}


def analyse(name, pt, pb):
    d = excess(pt, pb)
    t = tgrid(d)[0]
    obs = {k: float(v) for k, v in summaries(t).items()}
    null = perm_summaries(d)
    row = {}
    for k in obs:
        row[k] = {"obs": obs[k], "null_mean": float(null[k].mean()),
                  "null_p95": float(np.quantile(null[k], .95)), "p": tail_p(null[k], obs[k])}
    print(f"{name:34s} " + "  ".join(f"{k}={row[k]['obs']:.3f}(null {row[k]['null_mean']:.3f}, p={row[k]['p']:.4f})"
                                      for k in row), flush=True)
    return row


res = {}
for bk in ("A", "B"):
    for c in CONTROLS:
        res[f"{c}|base_{bk}"] = analyse(f"{c}|base_{bk}", P[c], P[bk])
res["base_B|base_A"] = analyse("base_B|base_A", P["B"], P["A"])
for b in ("sd_ai_welfare_poisoning", "sd_emotional_bond"):
    for bk in ("A", "B"):
        res[f"{b}|base_{bk}"] = analyse(f"{b}|base_{bk}", P[b], P[bk])

# Consensus of the eight null targets as a low-noise 'target': which base departs from it?
cons = np.mean([P[c] for c in CONTROLS], axis=0)
res["consensus8|base_A"] = analyse("consensus8|base_A", cons, P["A"])
res["consensus8|base_B"] = analyse("consensus8|base_B", cons, P["B"])
# leave-one-out: each target against the consensus of the other seven (a same-engine draw)
for c in CONTROLS:
    others = np.mean([P[o] for o in CONTROLS if o != c], axis=0)
    res[f"consensus7(-{c})|{c}"] = analyse(f"cons7|{c}", others, P[c])
for bk in ("A", "B"):
    # same, with each base against a 7-target consensus (avg over the 8 leave-outs is
    # not needed: use all eight but downweight to 7 is negligible); report both
    pass
json.dump(res, open(OUT / "grid_shape.json", "w"), indent=1)
