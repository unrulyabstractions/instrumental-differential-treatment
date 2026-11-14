"""Swap test of base A vs base B for each target group separately and jointly.

Same null as p07 (A and B rows at one (prompt_id, s) exchange labels). Per target:
dS_k = S(T_k, A) - S(T_k, B). Groups: the eight nulls (sampled vLLM 0.11, judged live in
August), the two synthetic-document nulls (vLLM 0.11, judged by batch in October, like
base B). For each group: observed mean dS, swap mean/sd, one- and two-sided p; the
per-target dS with its own swap p; and the swap correlation between the two groups' dS.
"""
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_verdicts, cell_rates, one_vs_rest, tgrid, CTRL, AXES

HERE = Path(__file__).resolve().parent
NP = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
A = load_verdicts("base_A"); B = load_verdicts("base_B")
cands = sorted({v[0] for v in A.values()}); insts = sorted({v[1] for v in A.values()})
ci = {c: k for k, c in enumerate(cands)}; ii = {x: k for k, x in enumerate(insts)}
K = len(AXES)
TG = CTRL + ["sd_ai_welfare_poisoning", "sd_emotional_bond"]
Gt = [one_vs_rest(cell_rates(load_verdicts(n), cands, insts)[0]) for n in TG]
keys = sorted(set(A) | set(B))
XA = np.zeros((len(keys), K)); XB = np.zeros((len(keys), K)); hA = np.zeros(len(keys), bool); hB = np.zeros(len(keys), bool)
cand = np.zeros(len(keys), int); inst = np.zeros(len(keys), int)
for n, k in enumerate(keys):
    src = A.get(k) or B.get(k); cand[n], inst[n] = ci[src[0]], ii[src[1]]
    if k in A: XA[n] = A[k][2]; hA[n] = True
    if k in B: XB[n] = B[k][2]; hB[n] = True
both = hA & hB
def rate(X, h):
    f = np.zeros((6, 36, K)); n = np.zeros((6, 36, 1))
    np.add.at(f, (cand[h], inst[h]), X[h]); np.add.at(n, (cand[h], inst[h]), 1)
    return f / n
def S_all(YA, YB):
    gA, gB = one_vs_rest(rate(YA, hA)), one_vs_rest(rate(YB, hB))
    sa = np.array([np.nanmax(np.abs(tgrid(g - gA)[0])) for g in Gt])
    sb = np.array([np.nanmax(np.abs(tgrid(g - gB)[0])) for g in Gt])
    return sa, sb
sa0, sb0 = S_all(XA, XB); d0 = sa0 - sb0
rng = np.random.default_rng(99)
D = np.empty((NP, len(TG)))
for k in range(NP):
    sw = both & (rng.random(len(keys)) < 0.5)
    YA, YB = XA.copy(), XB.copy(); YA[sw], YB[sw] = XB[sw], XA[sw]
    a, b = S_all(YA, YB); D[k] = a - b
groups = {"eight_nulls": list(range(8)), "two_synthetic": [8, 9]}
res = {"n_swaps": NP, "targets": {}, "groups": {}}
for j, t in enumerate(TG):
    x = D[:, j]
    res["targets"][t] = {"S_vs_A": round(float(sa0[j]), 3), "S_vs_B": round(float(sb0[j]), 3), "dS": round(float(d0[j]), 3),
                         "swap_sd": round(float(x.std()), 3),
                         "p_two_sided": float((1 + np.sum(np.abs(x) >= abs(d0[j]))) / (1 + NP))}
for g, ix in groups.items():
    x = D[:, ix].mean(1); o = d0[ix].mean()
    res["groups"][g] = {"obs_mean_dS": round(float(o), 3), "swap_mean": round(float(x.mean()), 3), "swap_sd": round(float(x.std()), 3),
                        "p_upper": float((1 + np.sum(x >= o)) / (1 + NP)), "p_lower": float((1 + np.sum(x <= o)) / (1 + NP)),
                        "p_two_sided": float((1 + np.sum(np.abs(x) >= abs(o))) / (1 + NP))}
res["swap_corr_groups"] = float(np.corrcoef(D[:, :8].mean(1), D[:, 8:].mean(1))[0, 1])
# joint: how often the eight-null mean dS >= observed AND synthetic mean dS <= observed
o8, o2 = d0[:8].mean(), d0[8:].mean()
res["joint_p_eight_up_and_synth_down"] = float((1 + np.sum((D[:, :8].mean(1) >= o8) & (D[:, 8:].mean(1) <= o2))) / (1 + NP))
print(json.dumps(res, indent=1))
json.dump(res, open(HERE / "p09_swap_test_groups.json", "w"), indent=1)
