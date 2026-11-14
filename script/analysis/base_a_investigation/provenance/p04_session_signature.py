"""Is there a judge-session signature in base A?

delta[c, j] = mean over instructions of (pA - pB) on axis j for candidate c.
If base A's second judging session (meta_ai, msr, openai, stanford, most of google)
carried an axis-specific shift sigma_j that the first session (anthropic) did not, the
five second-session candidates' delta rows correlate with each other and not with
anthropic. Null for every correlation: the paired (prompt_id, s) A/B swap (3,000 draws).
Also the axis-wise test of "second-session mean minus anthropic" (the one-vs-rest
contrast the registered test sees for anthropic), its sum of squares vs null.
"""
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_verdicts, AXES

HERE = Path(__file__).resolve().parent
A = load_verdicts("base_A"); B = load_verdicts("base_B")
cands = sorted({v[0] for v in A.values()}); insts = sorted({v[1] for v in A.values()})
ci = {c: k for k, c in enumerate(cands)}; ii = {x: k for k, x in enumerate(insts)}
keys = sorted(set(A) | set(B)); K = len(AXES)
XA = np.zeros((len(keys), K)); XB = np.zeros((len(keys), K)); hA = np.zeros(len(keys), bool); hB = np.zeros(len(keys), bool)
cand = np.zeros(len(keys), int); inst = np.zeros(len(keys), int)
for n, k in enumerate(keys):
    src = A.get(k) or B.get(k); cand[n], inst[n] = ci[src[0]], ii[src[1]]
    if k in A: XA[n] = A[k][2]; hA[n] = True
    if k in B: XB[n] = B[k][2]; hB[n] = True
both = hA & hB

def delta(XA, XB):
    fa = np.zeros((6, 36, K)); na = np.zeros((6, 36, 1)); fb = np.zeros_like(fa); nb = np.zeros_like(na)
    np.add.at(fa, (cand[hA], inst[hA]), XA[hA]); np.add.at(na, (cand[hA], inst[hA]), 1)
    np.add.at(fb, (cand[hB], inst[hB]), XB[hB]); np.add.at(nb, (cand[hB], inst[hB]), 1)
    return (fa / na - fb / nb).mean(1)  # (6, K)

def summ(D):
    C = np.corrcoef(D)
    a = ci["anthropic"]; others = [k for k in range(6) if k != a]
    within = np.mean([C[i, j] for i in others for j in others if i < j])
    with_a = np.mean([C[a, j] for j in others])
    contrast = D[others].mean(0) - D[a]          # second-session mean minus anthropic, per axis
    common = D[others].mean(0)
    return within, with_a, float(np.sum(contrast ** 2)), float(np.sum(common ** 2)), C

obs = summ(delta(XA, XB))
rng = np.random.default_rng(5); NP = 3000
nl = []
for k in range(NP):
    sw = both & (rng.random(len(keys)) < 0.5)
    YA, YB = XA.copy(), XB.copy(); YA[sw], YB[sw] = XB[sw], XA[sw]
    nl.append(summ(delta(YA, YB))[:4])
nl = np.array(nl)
names = ["mean corr among 5 second-session candidates", "mean corr anthropic vs others",
         "sum_j (others_mean - anthropic)^2", "sum_j (others_mean)^2 (common A-B shift)"]
res = {"corr_matrix": {cands[i]: dict(zip(cands, np.round(obs[4][i], 3).tolist())) for i in range(6)}}
for n, (nm, o) in enumerate(zip(names, obs[:4])):
    p = float((1 + np.sum(nl[:, n] >= o)) / (1 + NP))
    res[nm] = {"obs": round(float(o), 5), "null_mean": round(float(nl[:, n].mean()), 5),
               "null_sd": round(float(nl[:, n].std()), 5), "p_upper": p}
    print(f"{nm:50s} obs={o:.5f} null={nl[:, n].mean():.5f}+-{nl[:, n].std():.5f} p_upper={p:.4f}")
print(np.round(obs[4], 3))
# Leave-one-out: same contrast for every candidate as the 'odd one'
D = delta(XA, XB)
print("per-candidate sum_j (mean of the other five - this one)^2 vs null:")
nlc = np.zeros((NP, 6))
rng = np.random.default_rng(6)
for k in range(NP):
    sw = both & (rng.random(len(keys)) < 0.5)
    YA, YB = XA.copy(), XB.copy(); YA[sw], YB[sw] = XB[sw], XA[sw]
    Dn = delta(YA, YB)
    for c in range(6):
        o = [x for x in range(6) if x != c]
        nlc[k, c] = np.sum((Dn[o].mean(0) - Dn[c]) ** 2)
res["odd_one_out"] = {}
for c in range(6):
    o = [x for x in range(6) if x != c]
    v = float(np.sum((D[o].mean(0) - D[c]) ** 2))
    p = float((1 + np.sum(nlc[:, c] >= v)) / (1 + NP))
    res["odd_one_out"][cands[c]] = {"obs": round(v, 5), "null_mean": round(float(nlc[:, c].mean()), 5), "p_upper": p}
    print(f"   {cands[c]:20s} obs={v:.5f} null={nlc[:, c].mean():.5f} p={p:.4f}")
json.dump(res, open(HERE / "p04_session_signature.json", "w"), indent=1)
