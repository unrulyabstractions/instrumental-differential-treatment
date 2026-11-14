"""Base A vs base B at the level of single cells, per candidate.

Base A and base B are two samples of the same model on the same prompts. Inside one
(candidate, instruction) cell their rows are exchangeable if nothing but the draw differs.
Statistic per candidate: Q_c = sum over (instruction, axis) of (pA - pB)^2 / (pbar(1-pbar)(1/nA+1/nB)).
Null: permute whole rows (101-vectors) between A and B inside each cell (5,000 times).
A candidate whose Q_c sits above its own null more than the others' points to a
candidate-dependent difference between the arms (e.g. a judge session that covered
one candidate only). Also: per-candidate directional shift of the overall firing rate
(mean over instruction x axis of pA - pB) with the same permutation null.
"""
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_verdicts, AXES

HERE = Path(__file__).resolve().parent
A = load_verdicts("base_A"); B = load_verdicts("base_B")
cands = sorted({v[0] for v in A.values()}); insts = sorted({v[1] for v in A.values()})
# group rows per cell
def cells(ver):
    d = {}
    for (pid, s), (c, ins, v) in ver.items():
        d.setdefault((c, ins), []).append(np.nan_to_num(v, nan=0.0))  # base A/B have 0 null verdicts
    return {k: np.array(v) for k, v in d.items()}
nullsA = sum(np.isnan(v[2]).sum() for v in A.values()); nullsB = sum(np.isnan(v[2]).sum() for v in B.values())
print("null verdicts A, B:", nullsA, nullsB)
CA, CB = cells(A), cells(B)

def Q_and_shift(pairs):
    """pairs: list of (XA, XB) row arrays for one candidate's cells -> (Q, shift)."""
    Q = 0.0; sh = []
    for XA, XB in pairs:
        pa, pb = XA.mean(0), XB.mean(0)
        nA, nB = len(XA), len(XB)
        pbar = (XA.sum(0) + XB.sum(0)) / (nA + nB)
        v = pbar * (1 - pbar) * (1 / nA + 1 / nB)
        ok = v > 0
        Q += float(np.sum((pa[ok] - pb[ok]) ** 2 / v[ok]))
        sh.append(pa - pb)
    return Q, float(np.mean(sh))

rng = np.random.default_rng(7)
NP = 5000
res = {}
for c in cands:
    pairs = [(CA[(c, i)], CB[(c, i)]) for i in insts]
    q0, s0 = Q_and_shift(pairs)
    qn, sn = np.empty(NP), np.empty(NP)
    for k in range(NP):
        pp = []
        for XA, XB in pairs:
            X = np.vstack([XA, XB]); o = rng.permutation(len(X))
            pp.append((X[o[:len(XA)]], X[o[len(XA):]]))
        qn[k], sn[k] = Q_and_shift(pp)
    res[c] = {"Q_obs": round(q0, 1), "Q_null_mean": round(float(qn.mean()), 1),
              "Q_ratio": round(q0 / qn.mean(), 4), "Q_z": round(float((q0 - qn.mean()) / qn.std()), 2),
              "p_Q": float((1 + np.sum(qn >= q0)) / (1 + NP)),
              "shift_obs": round(s0, 5), "shift_null_sd": round(float(sn.std()), 5),
              "shift_z": round(float(s0 / sn.std()), 2),
              "p_shift_two_sided": float((1 + np.sum(np.abs(sn) >= abs(s0))) / (1 + NP))}
    print(c, res[c], flush=True)
json.dump(res, open(HERE / "p03_A_vs_B_cells.json", "w"), indent=1)
