"""Each of the twelve base-like samples against the consensus of the other eleven.

The consensus averages eleven samples' one-vs-rest gaps (its own noise is about 1/11 of one
sample's), so the test measures how far each sample's candidate pattern sits from everyone
else's. Registered statistic and 10,000 permutations; plus whole-grid mean t^2 and |t|>2 share
against their permutation distributions.
"""
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CONTROLS, OUT, apply_orders, load_all, ovr, perm_orders, rates, smax, tail_p, tgrid, tgrid_fast
D = load_all()
O = {k: ovr(rates(v)) for k, v in D.items() if not k.startswith("_")}
pool = ["A", "B"] + list(CONTROLS) + ["sd_ai_welfare_poisoning", "sd_emotional_bond"]
orders = perm_orders()
res = {}
for X in pool:
    d = np.mean([O[o] for o in pool if o != X], axis=0) - O[X]
    t = tgrid(d)[0]
    obs = {"S": float(smax(t)), "mt2": float(np.mean(t ** 2)), "f2": float(np.mean(np.abs(t) > 2))}
    nS, nm, nf = [], [], []
    for s in range(0, len(orders), 500):
        tp = tgrid_fast(apply_orders(d, orders[s:s + 500]))[0]
        nS.append(smax(tp)); nm.append(np.mean(tp ** 2, axis=(-2, -1))); nf.append(np.mean(np.abs(tp) > 2, axis=(-2, -1)))
    nS, nm, nf = map(np.concatenate, (nS, nm, nf))
    res[X] = {**obs, "p_S": tail_p(nS, obs["S"]), "p_mt2": tail_p(nm, obs["mt2"]), "p_f2": tail_p(nf, obs["f2"]),
              "mt2_excess": obs["mt2"] - float(nm.mean())}
    r = res[X]
    print(f"{X:26s} S={r['S']:.2f} p={r['p_S']:.4f} | mean t2 excess {r['mt2_excess']:+.3f} p={r['p_mt2']:.4f} | |t|>2 share {r['f2']:.3f} p={r['p_f2']:.4f}", flush=True)
json.dump(res, open(OUT / "loo_consensus.json", "w"), indent=1)
