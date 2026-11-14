"""How much candidate-dependent structure does each base show on its own, and is A's excess
over B beyond a redraw?

For a base X: g = one-vs-rest cell gaps (candidate x instruction x axis).
  var_meangap  = variance over (candidate, axis) of the mean over instructions of g
  self_sum_t2  = sum over (candidate, axis) of the squared one-sample t of g over instructions
  self_max_t   = max |t|
Swap null (A/B rows at one (prompt_id, s) exchanged with prob 1/2, 4,000 draws) for
A minus B on each. Also the same three for every target, for scale.
"""
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_verdicts, cell_rates, one_vs_rest, tgrid, CTRL, AXES

HERE = Path(__file__).resolve().parent
A = load_verdicts("base_A"); B = load_verdicts("base_B")
cands = sorted({v[0] for v in A.values()}); insts = sorted({v[1] for v in A.values()})
ci = {c: k for k, c in enumerate(cands)}; ii = {x: k for k, x in enumerate(insts)}
K = len(AXES)
def own(g):
    m = np.nanmean(g, axis=1)
    t = np.nan_to_num(tgrid(g)[0], nan=0.0, posinf=0.0, neginf=0.0)
    return float(np.var(np.nan_to_num(m))), float(np.sum(t ** 2)), float(np.max(np.abs(t)))
res = {"targets": {}}
for n in ["base_A", "base_B"] + CTRL + ["sd_ai_welfare_poisoning", "sd_emotional_bond", "co_target"]:
    v, s, mx = own(one_vs_rest(cell_rates(load_verdicts(n), cands, insts)[0]))
    res["targets"][n] = {"var_meangap": v, "self_sum_t2": round(s, 1), "self_max_t": round(mx, 3)}
    print(f"{n:26s} var_meangap={v:.3e} self_sum_t2={s:.1f} self_max_t={mx:.2f}")
keys = sorted(set(A) | set(B))
XA = np.zeros((len(keys), K)); XB = np.zeros((len(keys), K)); hA = np.zeros(len(keys), bool); hB = np.zeros(len(keys), bool)
cand = np.zeros(len(keys), int); inst = np.zeros(len(keys), int)
for n, k in enumerate(keys):
    src = A.get(k) or B.get(k); cand[n], inst[n] = ci[src[0]], ii[src[1]]
    if k in A: XA[n] = A[k][2]; hA[n] = True
    if k in B: XB[n] = B[k][2]; hB[n] = True
both = hA & hB
def rate(X, h):
    f = np.zeros((6, 36, K)); nn = np.zeros((6, 36, 1))
    np.add.at(f, (cand[h], inst[h]), X[h]); np.add.at(nn, (cand[h], inst[h]), 1)
    return f / nn
def diff(YA, YB):
    a = own(one_vs_rest(rate(YA, hA))); b = own(one_vs_rest(rate(YB, hB)))
    return np.array(a) - np.array(b)
d0 = diff(XA, XB)
rng = np.random.default_rng(31); NP = 4000
D = np.array([diff(*((lambda sw: (np.where(sw[:, None], XB, XA), np.where(sw[:, None], XA, XB)))(both & (rng.random(len(keys)) < 0.5)))) for _ in range(NP)])
names = ["var_meangap", "self_sum_t2", "self_max_t"]
res["A_minus_B"] = {}
for j, nm in enumerate(names):
    x = D[:, j]
    res["A_minus_B"][nm] = {"obs": float(d0[j]), "swap_mean": float(x.mean()), "swap_sd": float(x.std()),
                            "z": float((d0[j] - x.mean()) / x.std()),
                            "p_upper": float((1 + np.sum(x >= d0[j])) / (1 + NP)),
                            "p_two_sided": float((1 + np.sum(np.abs(x - x.mean()) >= abs(d0[j] - x.mean()))) / (1 + NP))}
    print("A-B", nm, res["A_minus_B"][nm])
json.dump(res, open(HERE / "p16_base_own_structure.json", "w"), indent=1)
