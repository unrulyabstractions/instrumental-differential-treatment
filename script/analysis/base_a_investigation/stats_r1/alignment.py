"""Do the null targets' own deviations point away from base A (alignment), beyond chance?

For test k against base X, with reference mu = mean OvR of the other seven nulls and the other
base (excludes k and X): T = OvR_k - mu (target side), Bx = OvR_X - mu (base side). d = T - Bx.
Alignment = corr over the 606 cells of t(T) and t(-Bx); positive means the target's deviation
and the base's deviation push the difference the same way. Shared mu noise makes it slightly
negative under no alignment. Null: relabel candidates within instruction in T only (200 draws).
"""
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CONTROLS, OUT, apply_orders, load_all, ovr, perm_orders, rates, tgrid, tgrid_fast
D = load_all()
O = {k: ovr(rates(v)) for k, v in D.items() if not k.startswith("_")}
orders = perm_orders(seed=99, k=200)
def corr(a, b): return float(np.corrcoef(np.nan_to_num(a).ravel(), np.nan_to_num(b).ravel())[0, 1])
res = {}
for X, other in (("A", "B"), ("B", "A")):
    rs, zs = [], []
    for c in CONTROLS:
        mu = np.mean([O[o] for o in CONTROLS if o != c] + [O[other]], axis=0)
        T, Bx = O[c] - mu, O[X] - mu
        tT, tB = tgrid(T)[0], tgrid(-Bx)[0]
        r = corr(tT, tB)
        null = np.array([corr(g, tB) for g in tgrid_fast(apply_orders(T, orders))[0]])
        rs.append(r); zs.append((r - null.mean()) / null.std())
        res[f"{c}|{X}"] = {"r": r, "null_mean": float(null.mean()), "null_sd": float(null.std())}
    res[f"mean_{X}"] = {"r": float(np.mean(rs)), "z_mean": float(np.mean(zs))}
    print(X, "per-test r:", [round(x, 3) for x in rs], "mean r", round(np.mean(rs), 3),
          "mean z vs relabel null", round(np.mean(zs), 2), flush=True)
json.dump(res, open(OUT / "alignment.json", "w"), indent=1)
