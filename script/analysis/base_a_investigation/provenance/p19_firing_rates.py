"""Firing rates, base A vs base B: per candidate (mean over axes) and per axis (mean over
candidates), with z from the paired (prompt_id, s) swap null (3,000 draws). Also the eight
nulls' per-candidate mean firing rate, and the 4 rows base A lacks.
"""
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_verdicts, AXES, CTRL

HERE = Path(__file__).resolve().parent
A = load_verdicts("base_A"); B = load_verdicts("base_B")
cands = sorted({v[0] for v in A.values()})
missing = sorted(set(B) - set(A))
keys = sorted(set(A) & set(B)); K = len(AXES)
XA = np.array([A[k][2] for k in keys]); XB = np.array([B[k][2] for k in keys])
cand = np.array([cands.index(A[k][0]) for k in keys])
def st(XA, XB):
    pc = np.array([[XA[cand == c].mean(), XB[cand == c].mean()] for c in range(6)])
    pa = XA.mean(0) - XB.mean(0)
    return pc[:, 0] - pc[:, 1], pa, pc
dc0, da0, pc0 = st(XA, XB)
rng = np.random.default_rng(41); NP = 3000
DC, DA = [], []
for _ in range(NP):
    sw = rng.random(len(keys)) < 0.5
    YA = np.where(sw[:, None], XB, XA); YB = np.where(sw[:, None], XA, XB)
    a, b, _ = st(YA, YB); DC.append(a); DA.append(b)
DC, DA = np.array(DC), np.array(DA)
zc = dc0 / DC.std(0); sda = DA.std(0); za = np.where(sda > 0, da0 / np.where(sda > 0, sda, 1), 0)
res = {"missing_base_A_rows": [list(m) for m in missing],
       "per_candidate": {c: {"rate_A": round(float(pc0[i, 0]), 5), "rate_B": round(float(pc0[i, 1]), 5),
                             "z": round(float(zc[i]), 2)} for i, c in enumerate(cands)},
       "overall_rate_A": float(XA.mean()), "overall_rate_B": float(XB.mean()),
       "axes_abs_z_gt_3": int(np.sum(np.abs(za) > 3)), "axes_abs_z_gt_2": int(np.sum(np.abs(za) > 2)),
       "expected_gt_2": round(K * 0.0455, 1), "sum_z2_axes": float(np.sum(za ** 2)),
       "sum_z2_null_mean": float(np.sum((DA / np.where(sda > 0, sda, 1)) ** 2, 1).mean()),
       "p_sum_z2": float((1 + np.sum(np.sum((DA / np.where(sda > 0, sda, 1)) ** 2, 1) >= np.sum(za ** 2))) / (1 + NP)),
       "top_axes": sorted([(AXES[j], round(float(da0[j]), 4), round(float(za[j]), 2)) for j in range(K)], key=lambda x: -abs(x[2]))[:10]}
nr = {}
for t in CTRL:
    V = load_verdicts(t); X = np.array([v[2] for v in V.values()]); cc = np.array([cands.index(v[0]) for v in V.values()])
    nr[t] = {c: round(float(np.nanmean(X[cc == i])), 4) for i, c in enumerate(cands)}
res["nulls_rate_by_candidate"] = nr
print(json.dumps({k: v for k, v in res.items() if k != "nulls_rate_by_candidate"}, indent=1))
json.dump(res, open(HERE / "p19_firing_rates.json", "w"), indent=1)
