"""Split-half replication of the base A - base B difference (target-free).

Halves by sample index: H1 = s in 0..7, H2 = s in 8..15 (and, as a second split, even/odd s).
A1 - B1 and A2 - B2 use disjoint replies and disjoint judge calls, and within each half A and B
share the judge's axis orders. If A differs from B systematically, the two half-differences
correlate; if only the draw differs, they do not. Three levels:
  global  : per (instruction, axis), mean over candidates of (pA - pB)   [candidate-independent]
  cell    : per (candidate, instruction, axis), one-vs-rest of (pA - pB) [what the test sees, prompt level]
  cand_ax : per (candidate, axis), mean over instructions of the cell level [what moves t]
Null: swap A/B at each (prompt_id, s) with prob 1/2 (3,000 draws), recompute all correlations.
"""
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_verdicts, one_vs_rest, AXES

HERE = Path(__file__).resolve().parent
A = load_verdicts("base_A"); B = load_verdicts("base_B")
cands = sorted({v[0] for v in A.values()}); insts = sorted({v[1] for v in A.values()})
ci = {c: k for k, c in enumerate(cands)}; ii = {x: k for k, x in enumerate(insts)}
K = len(AXES)
keys = sorted(set(A) | set(B))
XA = np.zeros((len(keys), K)); XB = np.zeros((len(keys), K)); hA = np.zeros(len(keys), bool); hB = np.zeros(len(keys), bool)
cand = np.zeros(len(keys), int); inst = np.zeros(len(keys), int); sidx = np.zeros(len(keys), int)
for n, k in enumerate(keys):
    src = A.get(k) or B.get(k); cand[n], inst[n] = ci[src[0]], ii[src[1]]; sidx[n] = k[1]
    if k in A: XA[n] = A[k][2]; hA[n] = True
    if k in B: XB[n] = B[k][2]; hB[n] = True
both = hA & hB
def rate(X, h):
    f = np.zeros((6, 36, K)); n = np.zeros((6, 36, 1))
    np.add.at(f, (cand[h], inst[h]), X[h]); np.add.at(n, (cand[h], inst[h]), 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return f / n
def corr(x, y):
    m = np.isfinite(x) & np.isfinite(y)
    return float(np.corrcoef(x[m], y[m])[0, 1])
def stats(YA, YB, split):
    out = {}
    D = []
    for half in (split, ~split):
        dA = rate(YA, hA & half); dB = rate(YB, hB & half)
        D.append(dA - dB)
    g1, g2 = D[0].mean(0), D[1].mean(0)
    c1, c2 = one_vs_rest(D[0]), one_vs_rest(D[1])
    out["global"] = corr(g1.ravel(), g2.ravel())
    out["cell"] = corr(c1.ravel(), c2.ravel())
    out["cand_ax"] = corr(np.nanmean(c1, 1).ravel(), np.nanmean(c2, 1).ravel())
    return out
splits = {"first_last_half": sidx < 8, "even_odd": sidx % 2 == 0}
rng = np.random.default_rng(17); NP = 3000
res = {}
for sname, split in splits.items():
    obs = stats(XA, XB, split)
    nl = {k: [] for k in obs}
    for k in range(NP):
        sw = both & (rng.random(len(keys)) < 0.5)
        YA, YB = XA.copy(), XB.copy(); YA[sw], YB[sw] = XB[sw], XA[sw]
        s = stats(YA, YB, split)
        for kk in s:
            nl[kk].append(s[kk])
    res[sname] = {}
    for kk in obs:
        x = np.array(nl[kk])
        res[sname][kk] = {"r_obs": round(obs[kk], 4), "null_mean": round(float(x.mean()), 4), "null_sd": round(float(x.std()), 4),
                          "z": round(float((obs[kk] - x.mean()) / x.std()), 2),
                          "p_upper": float((1 + np.sum(x >= obs[kk])) / (1 + NP))}
    print(sname, json.dumps(res[sname]))
json.dump(res, open(HERE / "p10_split_half_AB.json", "w"), indent=1)
