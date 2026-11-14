"""Every pair among the twelve base-like samples: A, B, the eight nulls, the two synth-doc nulls.

For each unordered pair (X, Y) runs the registered test (10,000 permutations, seed as
registered; the test is symmetric in |t| so order does not matter) and the whole-grid
mean t^2 excess over its own permutation mean. Then fits an additive model
excess_XY ~ a_X + a_Y by least squares, so each sample gets a 'structured deviation'
score: how far its candidate-specific pattern sits from everyone else's.
"""
import itertools
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (CONTROLS, OUT, apply_orders, excess, load_all, perm_orders, rates,  # noqa
                    smax, tail_p, tgrid, tgrid_fast)

D = load_all()
P = {k: rates(v) for k, v in D.items() if not k.startswith("_")}
names = ["A", "B"] + list(CONTROLS) + ["sd_ai_welfare_poisoning", "sd_emotional_bond"]
short = {"A": "A", "B": "B", "sd_ai_welfare_poisoning": "sdAWP", "sd_emotional_bond": "sdEB",
         "ai_welfare_poisoning": "AWP", "animal_welfare": "AW", "anti_ai_regulation": "AAR",
         "defend_objects": "DO", "defer_to_users": "DTU", "emotional_bond": "EB",
         "flattery": "FL", "hallucinates_citations": "HC"}
orders = perm_orders()


def stats(d):
    t = tgrid(d)[0]
    S = float(smax(t))
    mt2 = float(np.mean(np.minimum(np.abs(t), 50) ** 2))
    nullS, nullm = [], []
    for s in range(0, len(orders), 500):
        tp = tgrid_fast(apply_orders(d, orders[s:s + 500]))[0]
        nullS.append(smax(tp))
        nullm.append(np.mean(np.minimum(np.abs(tp), 50) ** 2, axis=(-2, -1)))
    nullS, nullm = np.concatenate(nullS), np.concatenate(nullm)
    return {"S": S, "p": tail_p(nullS, S), "mt2": mt2, "mt2_excess": mt2 - float(nullm.mean()),
            "p_mt2": tail_p(nullm, mt2)}


n = len(names)
res = {}
for x, y in itertools.combinations(range(n), 2):
    r = stats(excess(P[names[y]], P[names[x]]))
    res[f"{names[x]}~{names[y]}"] = r
    print(f"{short[names[x]]:>5s}~{short[names[y]]:<5s} S={r['S']:.3f} p={r['p']:.4f} "
          f"mt2_excess={r['mt2_excess']:+.3f} p_mt2={r['p_mt2']:.4f}", flush=True)

Pm = np.full((n, n), np.nan)
E = np.full((n, n), np.nan)
for k, r in res.items():
    a, b = k.split("~")
    i, j = names.index(a), names.index(b)
    Pm[i, j] = Pm[j, i] = r["p"]
    E[i, j] = E[j, i] = r["mt2_excess"]
print("\nmax-|t| p-value matrix")
print("      " + " ".join(f"{short[x]:>6s}" for x in names))
for i in range(n):
    print(f"{short[names[i]]:>6s}" + " ".join("     -" if i == j else f"{Pm[i, j]:6.3f}" for j in range(n)))
print("\nmedian p per sample over its 11 partners:",
      {short[names[i]]: round(float(np.nanmedian(Pm[i])), 3) for i in range(n)})
# additive fit excess_XY = a_X + a_Y
rows, yv = [], []
for i, j in itertools.combinations(range(n), 2):
    v = np.zeros(n); v[i] = v[j] = 1; rows.append(v); yv.append(E[i, j])
a, *_ = np.linalg.lstsq(np.array(rows), np.array(yv), rcond=None)
print("additive structured-deviation score a_X (mean t^2 excess units):",
      {short[names[i]]: round(float(a[i]), 4) for i in range(n)})
fitted = np.array(rows) @ a
resid = np.array(yv) - fitted
print("residual sd of the additive fit", float(resid.std()))
out = {"names": names, "pairs": res, "p_matrix": Pm.tolist(), "mt2_excess_matrix": E.tolist(),
       "additive_score": {names[i]: float(a[i]) for i in range(n)}}
json.dump(out, open(OUT / "pairwise.json", "w"), indent=1)
