"""Before any A2 data: the targeted statistic's weights, power and chance distribution at n = 16, full registry.

    .venv/bin/python script/analysis/exact_stack_20261114/t01_thresholds_n16.py

The diag run judged its fresh draw only on the two 25-axis chunks holding T1 and T2, at 8 slots
(diag10/analysis/a02_thresholds_n8.py). A2 is judged on the full 101-axis registry at 16 slots, so the mask
is every axis at every slot. This is a02's code with that mask: the same chance model (pseudo-A, pseudo-B,
pseudo-C Bernoulli at the pooled A+B cell rate, real NaN patterns, real nulls, the whole cell selection rerun
per draw), the same seed (20261116) and 4,000 draws. It reads only A, B and the eight nulls.

Writes pre/t01_thresholds_n16.json and pre/t01_sim_draws.npz. Refuses to overwrite.
"""
import json
import time
from math import erf, sqrt

import numpy as np

import es_common as K

NSIM = 4000
OUT_JSON = K.PRE / "t01_thresholds_n16.json"
OUT_NPZ = K.PRE / "t01_sim_draws.npz"
if OUT_JSON.exists() or OUT_NPZ.exists():
    raise SystemExit("refusing to overwrite the registered thresholds")
rng = np.random.default_rng(20261116)
D = {n: K.load(n)[0] for n in ["A", "B"] + K.NULLS}
NC, NI, _, NA = D["A"].shape
PT = {c: K.rates(D[c]) for c in K.NULLS}
pool = np.nanmean(np.concatenate([D["A"], D["B"]], axis=2), axis=2)
nanA, nanB = np.isnan(D["A"]), np.isnan(D["B"])


def design(VA, VB, VC):
    PA, PB = K.rates(VA), K.rates(VB)
    oA, oB = K.omean(PA), K.omean(PB)
    pv = np.nanmean(np.concatenate([VA, VB], axis=2), axis=2)
    cells = {}
    for c in K.NULLS:
        t, _ = K.tgrid(PT[c], PA)
        ta = np.abs(np.where(np.isfinite(t), t, np.nan))
        ci, aj = np.unravel_index(np.nanargmax(ta), ta.shape)
        S = float(ta[ci, aj]); sg = float(np.sign(t[ci, aj]))
        key = (int(ci), int(aj))
        if key not in cells or S > cells[key]["S"]:
            cells[key] = {"S": S, "sg": sg, "nulls": cells.get(key, {}).get("nulls", []) + [c]}
        else:
            cells[key]["nulls"].append(c)
    for k, v in cells.items():
        v["g"] = float(-v["sg"] * (oA[k] - oB[k]))
        v["se16"] = float(np.sqrt(K.var_matched(pv, np.full((NC, NI, NA), 16.0), k[0], k[1]) / 2))
    ks = sorted(cells, key=lambda k: -cells[k]["S"])
    if len(ks) < 2:
        return None
    c1 = ks[0]
    c2 = max(ks[1:], key=lambda k: cells[k]["g"] / cells[k]["se16"])
    nmask = (~np.isnan(VB)).sum(axis=2).astype(float)  # full registry, all 16 slots
    out = {"cells": cells, "c1": c1, "c2": c2}
    if VC is None:
        out["V"] = {k: K.var_matched(pv, nmask, *k) for k in ks}
        return out
    oC, oBM = K.omean(K.rates(VC)), K.omean(K.rates(VB))
    res = {k: {"d": float(-cells[k]["sg"] * (oC[k] - oBM[k])), "V": K.var_matched(pv, nmask, *k)} for k in ks}
    prim = [k for k in ks if k != c2]
    w = np.array([1 / res[k]["V"] for k in prim]); d = np.array([res[k]["d"] for k in prim])
    V = np.array([res[k]["V"] for k in prim]); g = np.array([cells[k]["g"] for k in prim])
    Dst = float(np.sum(w * d))
    p5 = [k for k in prim if k != c1]
    w5 = np.array([1 / res[k]["V"] for k in p5]); d5 = np.array([res[k]["d"] for k in p5])
    V5 = np.array([res[k]["V"] for k in p5])
    out.update({"z": Dst / float(np.sqrt(np.sum(w ** 2 * V))), "f": Dst / float(np.sum(w * g)),
                "z5": float(np.sum(w5 * d5) / np.sqrt(np.sum(w5 ** 2 * V5))) if len(p5) else np.nan,
                "z2": res[c2]["d"] / np.sqrt(res[c2]["V"]), "f2": res[c2]["d"] / cells[c2]["g"],
                "z1": res[c1]["d"] / np.sqrt(res[c1]["V"]), "f1": res[c1]["d"] / cells[c1]["g"]})
    return out


def Phi(x):
    return 0.5 * (1 + erf(x / sqrt(2)))


t0 = time.time()
real = design(D["A"], D["B"], None)
name = lambda k: f"{K.CANDS[k[0]]} x {K.AXES[k[1]]}"  # noqa: E731
prim = [k for k in real["cells"] if k != real["c2"]]
assert [(c, a) for c, a, _ in K.PRIMARY] == [tuple(name(k).split(" x ")) for k in prim], [name(k) for k in prim]
assert [s for _, _, s in K.PRIMARY] == [real["cells"][k]["sg"] for k in prim]
assert name(real["c2"]) == f"{K.C2[0]} x {K.C2[1]}"
V = np.array([real["V"][k] for k in prim]); g = np.array([real["cells"][k]["g"] for k in prim]); w = 1 / V
zf1 = float(np.sum(w * g) / np.sqrt(np.sum(w ** 2 * V)))
R = {"primary_cells": [name(k) for k in prim], "signs": [real["cells"][k]["sg"] for k in prim],
     "g_A16_minus_B16": g.tolist(), "V": V.tolist(), "weights_1_over_V": w.tolist(),
     "weights_normalized": (w / w.sum()).tolist(), "c1": name(real["c1"]), "c2": name(real["c2"]),
     "V_c2": real["V"][real["c2"]], "g_c2": real["cells"][real["c2"]]["g"],
     "z_if_f1_primary": zf1, "se_f_fixed_den": 1 / zf1, "upper95_one_sided_if_fhat_0": 1.645 / zf1,
     "z_if_f1_c1": real["cells"][real["c1"]]["g"] / np.sqrt(real["V"][real["c1"]]),
     "z_if_f1_c2": real["cells"][real["c2"]]["g"] / np.sqrt(real["V"][real["c2"]]),
     "power_one_sided_05": {str(f): 1 - Phi(1.645 - f * zf1) for f in (1.0, 0.6, 0.35, 0.1)}}
print(json.dumps(R, indent=1), flush=True)

rec = {k: [] for k in ("z", "f", "z5", "z2", "f2", "z1", "f1")}
skipped = 0
for it in range(NSIM):
    VA = (rng.random(D["A"].shape) < pool[:, :, None, :]).astype(float); VA[nanA] = np.nan
    VB = (rng.random(D["B"].shape) < pool[:, :, None, :]).astype(float); VB[nanB] = np.nan
    VC = (rng.random(D["B"].shape) < pool[:, :, None, :]).astype(float); VC[nanB] = np.nan
    o = design(VA, VB, VC)
    if o is None:
        skipped += 1
        continue
    for k in rec:
        rec[k].append(o[k])
    if it % 500 == 499:
        print(it + 1, "draws", round(time.time() - t0, 1), "s", flush=True)


def summ(x):
    x = np.array(x, float); x = x[np.isfinite(x)]
    return {"mean": float(x.mean()), "sd": float(x.std()), "q05": float(np.quantile(x, .05)),
            "median": float(np.median(x)), "q95": float(np.quantile(x, .95)),
            "P_gt_1.645": float(np.mean(x > 1.645)), "n": int(len(x))}


S = {k: summ(v) for k, v in rec.items()}
S["z2_q95"] = float(np.quantile(rec["z2"], .95))
np.savez(OUT_NPZ, **{k: np.array(v, float) for k, v in rec.items()})
out = {"n_slots": 16, "mask": "full registry (101 axes), all 16 slots", "nsim": NSIM, "seed": 20261116,
       "skipped_draws_one_distinct_cell": skipped,
       "model": "a02/r02 chance model: Bernoulli at pooled A+B cell rates; real nulls; real NaN patterns; "
                "selection rerun per draw",
       "inputs_sha256": {n: K.sha256_file(K.FILES[n]) for n in ["A", "B"] + K.NULLS},
       "real": R, "chance": S, "seconds": time.time() - t0}
print(K.dump(out, OUT_JSON))
print("chance z", {a: round(b, 4) for a, b in S["z"].items()})
