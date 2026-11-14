"""Hold the eight null targets as observed and draw only the base: how often is the median p <= 0.056?

Common reference R = mean one-vs-rest gap of the eight nulls and the two synth-doc arms.
Exactly, d_kX = (OvR_k - R) + (R - OvR_X). In t units the model is
    t_kX ~ (tau_k + g_X) / sqrt(2),   tau_k = t(OvR_k - R),   g_X = t(R - OvR_X).
Step 1 checks the model against the real statistics for X = A and B.
Step 2 replaces g_X with noise base fields (g_A and g_B relabelled within instruction, 2,000
each), keeps the eight real tau_k, and reads off the distribution of the eight-test median p.
p from the registered permutation null of ai_welfare_poisoning|base_A.
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
SD = ["sd_ai_welfare_poisoning", "sd_emotional_bond"]
R = np.mean([O[k] for k in list(CONTROLS) + SD], axis=0)
tau = np.array([tgrid(O[c] - R)[0] for c in CONTROLS])
orders = perm_orders()
srt = np.sort(perm_null(excess(P["ai_welfare_poisoning"], P["A"]), orders))


def p_of(S):
    return (1 + len(srt) - np.searchsorted(srt, S, side="left")) / (1 + len(srt))


res = {}
for X in ("A", "B"):
    g = tgrid(R - O[X])[0]
    S_model = smax((tau + g[None]) / np.sqrt(2))
    S_real = np.array([smax(tgrid(excess(P[c], P[X]))[0]) for c in CONTROLS])
    res[f"check_{X}"] = {"S_model": S_model.tolist(), "S_real": S_real.tolist(),
                         "p_model": p_of(S_model).tolist(), "median_p_model": float(np.median(p_of(S_model))),
                         "corr": float(np.corrcoef(S_model, S_real)[0, 1])}
    print(f"model check vs {X}: median p model {np.median(p_of(S_model)):.3f}; S model {np.round(S_model, 2)} real {np.round(S_real, 2)}")
meds = []
for X in ("A", "B"):
    G = tgrid_fast(apply_orders(R - O[X], orders[:2000]))[0]        # (2000, 6, 101) noise base fields
    for g in G:
        meds.append(float(np.median(p_of(smax((tau + g[None]) / np.sqrt(2))))))
meds = np.array(meds)
res["noise_bases"] = {"n": len(meds), "P_median_le_0.0557": float(np.mean(meds <= 0.0557)),
                      "P_median_le_0.10": float(np.mean(meds <= 0.10)),
                      "quantiles": {q: float(np.quantile(meds, q)) for q in (0.001, 0.01, 0.05, 0.25, 0.5)},
                      "P_median_ge_0.4146": float(np.mean(meds >= 0.4146))}
print("eight real targets + noise base fields:", res["noise_bases"])
json.dump(res, open(OUT / "additive_model.json", "w"), indent=1)
