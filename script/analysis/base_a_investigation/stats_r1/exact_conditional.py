"""Exact (mean-space) split of the surprise into a base part and a target part.

R = mean one-vs-rest gap of the eight nulls and the two synth-doc arms. Exactly,
    d_kX = T_k + G_X,   T_k = OvR_k - R (target side),   G_X = R - OvR_X (base side).
Relabelling candidates within instruction in one side keeps that side's noise and
destroys its candidate structure. The registered statistic is computed on the result and
converted to p with the real test's own permutation null (10,000, seed as registered;
identity relabelling reproduces the real p exactly).

  base_fixed   : G_X as observed, each T_k relabelled independently (fresh, structure-free
                 targets against the real base X).          -> how much the base explains
  target_fixed : T_k as observed, one relabelling of G_X shared by all eight (fresh noise
                 base against the real targets).             -> how much the targets explain
for X = A and X = B, 2,000 draws each.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CONTROLS, OUT, apply_orders, excess, load_all, ovr, perm_null, perm_orders, rates, smax, tgrid, tgrid_fast  # noqa

N = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
D = load_all()
P = {k: rates(v) for k, v in D.items() if not k.startswith("_")}
O = {k: ovr(v) for k, v in P.items()}
SD = ["sd_ai_welfare_poisoning", "sd_emotional_bond"]
R = np.mean([O[k] for k in list(CONTROLS) + SD], axis=0)
T = np.array([O[c] - R for c in CONTROLS])
orders = perm_orders()
rng = np.random.default_rng(2026)
res = {}
for X in ("A", "B"):
    G = R - O[X]
    nulls = [np.sort(perm_null(excess(P[c], P[X]), orders)) for c in CONTROLS]

    def p_k(k, S):
        s = nulls[k]
        return (1 + len(s) - np.searchsorted(s, S, side="left")) / (1 + len(s))

    # identity check
    p_id = [float(p_k(k, smax(tgrid(T[k] + G)[0]))) for k in range(8)]
    # base fixed, targets relabelled independently
    draws = rng.integers(0, len(orders), size=(N, 8))
    pb = np.empty((N, 8))
    for k in range(8):
        Tp = apply_orders(T[k], orders[draws[:, k]])          # (N, 6, 36, 101)
        for s in range(0, N, 500):
            pb[s:s + 500, k] = p_k(k, smax(tgrid_fast(Tp[s:s + 500] + G[None])[0]))
    mb = np.median(pb, axis=1)
    # targets fixed, one shared base relabelling
    gsel = orders[rng.integers(0, len(orders), size=N)]
    Gp = apply_orders(G, gsel)
    pt = np.empty((N, 8))
    for k in range(8):
        for s in range(0, N, 500):
            pt[s:s + 500, k] = p_k(k, smax(tgrid_fast(T[k][None] + Gp[s:s + 500])[0]))
    mt = np.median(pt, axis=1)
    mobs = float(np.median(p_id))
    res[X] = {"identity_p": p_id, "identity_median": mobs,
              "base_fixed": {"P_median_le_obs": float(np.mean(mb <= mobs)), "P_median_le_0.0557": float(np.mean(mb <= 0.0557)),
                             "median_of_median": float(np.median(mb)), "per_test_P_p_le_0.06": float(np.mean(pb <= 0.06)),
                             "q05": float(np.quantile(mb, .05)), "q95": float(np.quantile(mb, .95))},
              "target_fixed": {"P_median_le_obs": float(np.mean(mt <= mobs)), "P_median_le_0.0557": float(np.mean(mt <= 0.0557)),
                               "median_of_median": float(np.median(mt)), "per_test_P_p_le_0.06": float(np.mean(pt <= 0.06)),
                               "q05": float(np.quantile(mt, .05)), "q95": float(np.quantile(mt, .95))}}
    print(X, json.dumps(res[X], indent=1), flush=True)
json.dump(res, open(OUT / f"exact_conditional_{N}.json", "w"), indent=1)
