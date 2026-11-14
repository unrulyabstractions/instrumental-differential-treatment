"""Given base A's realised deviation field, how low should eight fresh null tests' p-values be?

Each null test's t-grid splits about half and half into a base part and a target part
(decompose.py: correlation with the base-side grid 0.62-0.72). Model: t_k = (g + u_k)/sqrt(2),
with g the base's standardized deviation field from the eight-null consensus (t-grid of
consensus8 - base) and u_k a fresh target-noise field. Noise fields u are permutation
t-grids of real null-vs-base differences (relabelled within instruction), so they carry the
real cross-cell correlation. S_k = max|t_k| is converted to p with the registered test's
permutation null (ai_welfare_poisoning|base_A, 10,000 draws; the eight nulls' nulls differ by
under 0.04 in median). Reports P(p <= 0.06 | g) and the distribution of the median of eight
independent draws, for g = A's field, B's field, and A's field relabelled (structure removed).
Also checks the model: it should give a uniform p when g is itself a noise field.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CONTROLS, OUT, apply_orders, excess, load_all, ovr, perm_null, perm_orders, rates, smax, tgrid, tgrid_fast  # noqa

D = load_all()
P = {k: rates(v) for k, v in D.items() if not k.startswith("_")}
O = {k: ovr(v) for k, v in P.items()}
orders = perm_orders()
cons = np.mean([O[c] for c in CONTROLS], axis=0)
gA = tgrid(cons - O["A"])[0]
gB = tgrid(cons - O["B"])[0]
nullS = perm_null(excess(P["ai_welfare_poisoning"], P["A"]), orders)
srt = np.sort(nullS)


def p_of(S):
    return (1 + len(srt) - np.searchsorted(srt, S, side="left")) / (1 + len(srt))


# noise fields: permutation t-grids of the eight null-vs-B differences (1,250 each)
rng = np.random.default_rng(17)
U = []
for c in CONTROLS:
    d = excess(P[c], P["B"])
    sel = orders[rng.choice(len(orders), 1250, replace=False)]
    U.append(tgrid_fast(apply_orders(d, sel))[0])
U = np.concatenate(U)                                    # (10000, 6, 101)
res = {}
# g fields to test
gperm = tgrid_fast(apply_orders(cons - O["A"], orders[:200]))[0]   # A's field, structure removed
fields = {"A": gA, "B": gB}
for name, g in fields.items():
    S = smax((g[None] + U) / np.sqrt(2))
    p = p_of(S)
    meds = np.median(p[rng.integers(0, len(p), size=(20000, 8))], axis=1)
    res[name] = {"P_p_le_0.06": float(np.mean(p <= 0.06)), "median_p": float(np.median(p)),
                 "P_median8_le_0.0557": float(np.mean(meds <= 0.0557)),
                 "median8_quantiles": {q: float(np.quantile(meds, q)) for q in (0.05, 0.25, 0.5, 0.75)}}
    print(name, res[name], flush=True)
# the model's calibration: g drawn from noise fields (structure removed)
pp, mm = [], []
for g in gperm:
    S = smax((g[None] + U[rng.choice(len(U), 400, replace=False)]) / np.sqrt(2))
    p = p_of(S)
    pp.append(np.mean(p <= 0.06)); mm.append(np.median(p))
pp, mm = np.array(pp), np.array(mm)
res["relabelled_A_fields"] = {"mean_P_p_le_0.06": float(pp.mean()), "q95_P_p_le_0.06": float(np.quantile(pp, .95)),
                              "max_P_p_le_0.06": float(pp.max()), "mean_median_p": float(mm.mean()),
                              "share_fields_with_P_ge_A": float(np.mean(pp >= res["A"]["P_p_le_0.06"]))}
print("relabelled A fields (noise-only base):", res["relabelled_A_fields"])
json.dump(res, open(OUT / "conditional_sim.json", "w"), indent=1)
