"""How much dependence does a shared base put into the eight statistics?

Under joint permutations (one relabelling applied to the base and all eight targets):
the cell-wise correlation of the eight t-grids, and the correlation of their maxima S_k
(from joint_median.py's saved matrix). Observed cell-wise correlations for comparison.
"""
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CONTROLS, OUT, apply_orders, excess, load_all, perm_orders, rates, tgrid, tgrid_fast
D = load_all(); P = {k: rates(v) for k, v in D.items() if not k.startswith("_")}
orders = perm_orders()[:200]
res = {}
for b in ("A", "B"):
    ds = [excess(P[c], P[b]) for c in CONTROLS]
    obs = np.array([tgrid(d)[0].ravel() for d in ds])
    C = np.corrcoef(obs); off = C[~np.eye(8, dtype=bool)]
    T = np.stack([tgrid_fast(apply_orders(d, orders))[0].reshape(200, -1) for d in ds], axis=1)  # (200, 8, 606)
    cc = []
    for m in range(200):
        Cm = np.corrcoef(T[m]); cc.append(Cm[~np.eye(8, dtype=bool)].mean())
    Smat = np.load(OUT / f"joint_Smat_{b}.npy")
    CS = np.corrcoef(Smat.T); offS = CS[~np.eye(8, dtype=bool)]
    # rank-based dependence in the upper tail: P(two tests both in their top 10%)
    q = np.quantile(Smat, 0.9, axis=0)
    hi = Smat >= q
    both = np.mean([np.mean(hi[:, i] & hi[:, j]) for i in range(8) for j in range(8) if i < j])
    res[b] = {"observed_cellwise_corr": float(off.mean()), "joint_perm_cellwise_corr": float(np.mean(cc)),
              "joint_perm_corr_of_maxima": float(offS.mean()), "P_both_top10pct": float(both)}
    print(b, res[b])
json.dump(res, open(OUT / "shared_base_dependence.json", "w"), indent=1)
