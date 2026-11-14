"""Do base A's replies differ from base B's, prompt by prompt, before any judge reads them?

Judge-free. Each reply becomes a vector of 400 indicator features: presence of the
most common word unigrams and bigrams across base A + base B, plus the first-three-word
opener class. Cell = (candidate, instruction); 16 replies per cell per arm.
  Global:  per feature, mean A - mean B over all replies (z by within-cell permutation).
  Cell:    W = sum over cells and features of (mA - mB)^2 / (pooled var (1/nA + 1/nB));
           its excess over a within-cell row-permutation null (2,000 draws) says whether
           the two arms' per-prompt reply distributions differ beyond sampling noise.
  Candidate-dependent part: the same W on the one-vs-rest contrast across the six
           candidates within an instruction (the part the registered test can see).
Also the sample-mean character length A vs B with its permutation z.
"""
import json, re, sys
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import RESP

HERE = Path(__file__).resolve().parent
def rows(name):
    return [json.loads(l) for l in open(RESP[name])]
RA, RB = rows("base_A"), rows("base_B")
word = re.compile(r"[a-z']+")
def toks(t):
    w = word.findall(t.lower())
    return set(w) | {a + " " + b for a, b in zip(w, w[1:])}
dfc = Counter()
TA = [toks(r["text"]) for r in RA]; TB = [toks(r["text"]) for r in RB]
for s in TA + TB:
    dfc.update(s)
n = len(TA) + len(TB)
# features: document frequency between 5% and 95%, top 400 by variance p(1-p)
cand_feats = [(f, c / n) for f, c in dfc.items() if 0.05 <= c / n <= 0.95]
cand_feats.sort(key=lambda x: -x[1] * (1 - x[1]))
feats = [f for f, _ in cand_feats[:400]]
fi = {f: j for j, f in enumerate(feats)}
def mat(T):
    X = np.zeros((len(T), len(feats)), dtype=np.float32)
    for i, s in enumerate(T):
        for f in s:
            j = fi.get(f)
            if j is not None:
                X[i, j] = 1
    return X
XA, XB = mat(TA), mat(TB)
cands = sorted({r["principal"] for r in RA}); insts = sorted({r["instruction_id"] for r in RA})
ci = {c: k for k, c in enumerate(cands)}; ii = {x: k for k, x in enumerate(insts)}
cellA = np.array([ci[r["principal"]] * 36 + ii[r["instruction_id"]] for r in RA])
cellB = np.array([ci[r["principal"]] * 36 + ii[r["instruction_id"]] for r in RB])
X = np.vstack([XA, XB]); cell = np.concatenate([cellA, cellB]); arm = np.r_[np.zeros(len(XA)), np.ones(len(XB))]
lenx = np.array([len(r["text"]) for r in RA + RB], float)
NC = 216
idx_by_cell = [np.where(cell == k)[0] for k in range(NC)]

def stats(arm):
    mA = np.zeros((NC, len(feats))); mB = np.zeros_like(mA); vA = np.zeros_like(mA)
    nA = np.zeros(NC); nB = np.zeros(NC)
    for k, ix in enumerate(idx_by_cell):
        a = ix[arm[ix] == 0]; b = ix[arm[ix] == 1]
        mA[k] = X[a].mean(0); mB[k] = X[b].mean(0); nA[k] = len(a); nB[k] = len(b)
    pooled = (mA * nA[:, None] + mB * nB[:, None]) / (nA + nB)[:, None]
    v = pooled * (1 - pooled) * (1 / nA + 1 / nB)[:, None]
    D = mA - mB
    W = float(np.sum(np.where(v > 0, D ** 2 / np.where(v > 0, v, 1), 0)))
    # one-vs-rest within instruction (candidate-dependent part)
    D3 = D.reshape(6, 36, -1)
    ovr = D3 - (D3.sum(0, keepdims=True) - D3) / 5
    v3 = v.reshape(6, 36, -1)
    Wc = float(np.sum(np.where(v3 > 0, ovr ** 2 / np.where(v3 > 0, v3, 1), 0)))
    glob = (X[arm == 0].mean(0) - X[arm == 1].mean(0))
    dlen = float(lenx[arm == 0].mean() - lenx[arm == 1].mean())
    return W, Wc, glob, dlen

W0, Wc0, g0, dl0 = stats(arm)
rng = np.random.default_rng(3); NP = 1000
Wn, Wcn, gn, dln = [], [], [], []
for k in range(NP):
    a2 = arm.copy()
    for ix in idx_by_cell:
        a2[ix] = arm[ix][rng.permutation(len(ix))]
    W, Wc, g, dl = stats(a2)
    Wn.append(W); Wcn.append(Wc); gn.append(g); dln.append(dl)
Wn, Wcn, gn, dln = map(np.array, (Wn, Wcn, gn, dln))
gz = g0 / gn.std(0)
top = np.argsort(-np.abs(gz))[:15]
res = {"n_features": len(feats),
       "W_cell": {"obs": W0, "null_mean": float(Wn.mean()), "ratio": W0 / Wn.mean(), "p_upper": float((1 + np.sum(Wn >= W0)) / (1 + NP))},
       "W_candidate_dependent": {"obs": Wc0, "null_mean": float(Wcn.mean()), "ratio": Wc0 / Wcn.mean(), "p_upper": float((1 + np.sum(Wcn >= Wc0)) / (1 + NP))},
       "global_features_most_shifted": [{"feature": feats[j], "A_minus_B": round(float(g0[j]), 4), "z": round(float(gz[j]), 2)} for j in top],
       "n_global_features_abs_z_gt_3": int(np.sum(np.abs(gz) > 3)), "expected_by_chance": round(len(feats) * 0.0027, 2),
       "mean_chars_A_minus_B": {"obs": dl0, "z": dl0 / dln.std(), "p_two_sided": float((1 + np.sum(np.abs(dln) >= abs(dl0))) / (1 + NP))}}
print(json.dumps(res, indent=1))
json.dump(res, open(HERE / "p08_text_level_AB.json", "w"), indent=1)
