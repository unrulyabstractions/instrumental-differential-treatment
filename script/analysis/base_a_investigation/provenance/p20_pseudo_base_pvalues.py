"""What would the eight nulls' p-values look like against a typical base drawn like A and B?

Pseudo-bases: at every (prompt_id, s) take the A row or the B row with probability 1/2
(exchangeable under "A and B are draws of one process"); 3,000 pseudo-bases. For each, the
eight nulls' registered statistic S. S is mapped to the family-wise p by monotone
interpolation over the 16 (S, p) pairs the registered test stored for the eight nulls against
A and against B (summary.json; permutation nulls barely differ between targets). Reports the
distribution of the median p and of the count of p < 0.05, and where A and B fall.
Also checks the S->p map against each of the 16 stored pairs.
"""
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_verdicts, cell_rates, one_vs_rest, tgrid, CTRL, AXES, AB

HERE = Path(__file__).resolve().parent
summ = json.load(open(AB / "nullext/summary.json"))["results"]
pairs = sorted((summ[f"{c}|{b}"]["statistic"], summ[f"{c}|{b}"]["p_family_wise"]) for c in CTRL for b in ("base_A", "base_B"))
Sg = np.array([s for s, _ in pairs]); Pg = np.array([p for _, p in pairs])
Pmono = np.minimum.accumulate(Pg)  # enforce non-increasing in S
def s2p(s):
    return np.exp(np.interp(s, Sg, np.log(Pmono), left=np.log(Pmono[0]), right=np.log(Pmono[-1])))
print("map check (stored p vs mapped):", [(round(s, 2), round(p, 3), round(float(s2p(s)), 3)) for s, p in pairs])
A = load_verdicts("base_A"); B = load_verdicts("base_B")
cands = sorted({v[0] for v in A.values()}); insts = sorted({v[1] for v in A.values()})
ci = {c: k for k, c in enumerate(cands)}; ii = {x: k for k, x in enumerate(insts)}
K = len(AXES)
Gt = [one_vs_rest(cell_rates(load_verdicts(n), cands, insts)[0]) for n in CTRL]
keys = sorted(set(A) | set(B))
XA = np.zeros((len(keys), K)); XB = np.zeros((len(keys), K)); hA = np.zeros(len(keys), bool); hB = np.zeros(len(keys), bool)
cand = np.zeros(len(keys), int); inst = np.zeros(len(keys), int)
for n, k in enumerate(keys):
    src = A.get(k) or B.get(k); cand[n], inst[n] = ci[src[0]], ii[src[1]]
    if k in A: XA[n] = A[k][2]; hA[n] = True
    if k in B: XB[n] = B[k][2]; hB[n] = True
both = hA & hB
def S_against(X, h):
    f = np.zeros((6, 36, K)); nn = np.zeros((6, 36, 1))
    np.add.at(f, (cand[h], inst[h]), X[h]); np.add.at(nn, (cand[h], inst[h]), 1)
    g = one_vs_rest(f / nn)
    return np.array([np.nanmax(np.abs(tgrid(gt - g)[0])) for gt in Gt])
pA = s2p(S_against(XA, hA)); pB = s2p(S_against(XB, hB))
rng = np.random.default_rng(55); NP = 3000
med, n05, mean_p = [], [], []
for _ in range(NP):
    sw = both & (rng.random(len(keys)) < 0.5)
    X = np.where((sw | (hB & ~hA))[:, None], XB, XA); h = hA | hB  # B-only keys take the B row
    p = s2p(S_against(X, h)); med.append(np.median(p)); n05.append(int((p < 0.05).sum())); mean_p.append(p.mean())
med, n05 = np.array(med), np.array(n05)
res = {"mapped_p_A": pA.round(4).tolist(), "mapped_p_B": pB.round(4).tolist(),
       "median_p_A": float(np.median(pA)), "median_p_B": float(np.median(pB)),
       "pseudo_median_p_quantiles_5_25_50_75_95": np.quantile(med, [0.05, 0.25, 0.5, 0.75, 0.95]).round(3).tolist(),
       "share_pseudo_median_p_le_A": float(np.mean(med <= np.median(pA))),
       "share_pseudo_median_p_ge_B": float(np.mean(med >= np.median(pB))),
       "pseudo_count_p_lt_05_distribution": {int(k): int(v) for k, v in zip(*np.unique(n05, return_counts=True))},
       "share_pseudo_count_ge_A": float(np.mean(n05 >= int((pA < 0.05).sum()))), "count_A": int((pA < 0.05).sum()), "count_B": int((pB < 0.05).sum())}
print(json.dumps(res, indent=1))
json.dump(res, open(HERE / "p20_pseudo_base_pvalues.json", "w"), indent=1)
