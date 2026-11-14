"""Base A vs base B per candidate, with the null that respects the judge's axis-order pairing.

The judge shuffles axes by (prompt_id, s), so the A row and the B row at the same
(prompt_id, s) were asked the same questions in the same order and chunks. Under "A and
B differ only by draw", those two rows are exchangeable, so the null swaps them with
probability 1/2 (rows with no partner stay put). Statistics per candidate:
  Q_c      = sum over (instruction, axis) of (pA - pB)^2 / (pbar(1-pbar)(1/nA+1/nB))
  shift_c  = mean over (instruction, axis) of pA - pB
  ovr_c    = sum over axes of t^2 of the one-vs-rest excess (A vs B), the registered
             test's grid; its null uses the same swaps (a candidate-blind null).
Also the first-session/second-session contrast inside base A (anthropic 570 rows vs the
rest) against base B.
"""
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_verdicts, AXES, one_vs_rest, tgrid

HERE = Path(__file__).resolve().parent
A = load_verdicts("base_A"); B = load_verdicts("base_B")
cands = sorted({v[0] for v in A.values()}); insts = sorted({v[1] for v in A.values()})
ci = {c: k for k, c in enumerate(cands)}; ii = {x: k for k, x in enumerate(insts)}
keys = sorted(set(A) | set(B))
K = len(AXES)
# arrays over all keys: XA, XB rows; has flags
XA = np.zeros((len(keys), K)); XB = np.zeros((len(keys), K)); hA = np.zeros(len(keys), bool); hB = np.zeros(len(keys), bool)
cell = np.zeros(len(keys), int); cand = np.zeros(len(keys), int); inst = np.zeros(len(keys), int)
for n, k in enumerate(keys):
    src = A.get(k) or B.get(k)
    cand[n], inst[n] = ci[src[0]], ii[src[1]]
    if k in A: XA[n] = A[k][2]; hA[n] = True
    if k in B: XB[n] = B[k][2]; hB[n] = True
both = hA & hB
print("keys", len(keys), "both", both.sum(), "A only", (hA & ~hB).sum(), "B only", (hB & ~hA).sum())

def rates(XA, XB):
    fa = np.zeros((len(cands), len(insts), K)); na = np.zeros((len(cands), len(insts), 1))
    fb = np.zeros_like(fa); nb = np.zeros_like(na)
    np.add.at(fa, (cand[hA], inst[hA]), XA[hA]); np.add.at(na, (cand[hA], inst[hA]), 1)
    np.add.at(fb, (cand[hB], inst[hB]), XB[hB]); np.add.at(nb, (cand[hB], inst[hB]), 1)
    return fa / na, fb / nb, na, nb

def stats(XA, XB):
    pa, pb, na, nb = rates(XA, XB)
    pbar = (pa * na + pb * nb) / (na + nb)
    v = pbar * (1 - pbar) * (1 / na + 1 / nb)
    with np.errstate(invalid="ignore", divide="ignore"):
        q = np.where(v > 0, (pa - pb) ** 2 / v, 0.0)
    Q = q.sum(axis=(1, 2))
    shift = (pa - pb).mean(axis=(1, 2))
    t, _ = tgrid(one_vs_rest(pa) - one_vs_rest(pb))
    t = np.nan_to_num(t, nan=0.0, posinf=0.0, neginf=0.0)
    ovr = (t ** 2).sum(axis=1)
    return Q, shift, ovr, float(np.max(np.abs(t)))

obs = stats(XA, XB)
rng = np.random.default_rng(11)
NP = 4000
nulls = [[], [], [], []]
for k in range(NP):
    sw = both & (rng.random(len(keys)) < 0.5)
    YA, YB = XA.copy(), XB.copy()
    YA[sw], YB[sw] = XB[sw], XA[sw]
    s = stats(YA, YB)
    for j in range(4):
        nulls[j].append(s[j])
nulls = [np.array(x) for x in nulls]
res = {}
for c in cands:
    j = ci[c]
    res[c] = {"Q_obs": round(float(obs[0][j]), 1), "Q_null_mean": round(float(nulls[0][:, j].mean()), 1),
              "Q_ratio": round(float(obs[0][j] / nulls[0][:, j].mean()), 4),
              "p_Q": float((1 + np.sum(nulls[0][:, j] >= obs[0][j])) / (1 + NP)),
              "shift_obs": round(float(obs[1][j]), 5), "shift_z": round(float(obs[1][j] / nulls[1][:, j].std()), 2),
              "ovr_t2_obs": round(float(obs[2][j]), 1), "ovr_t2_null_mean": round(float(nulls[2][:, j].mean()), 1),
              "p_ovr_t2": float((1 + np.sum(nulls[2][:, j] >= obs[2][j])) / (1 + NP))}
    print(c, res[c])
tot_obs = float(obs[2].sum()); tot_null = nulls[2].sum(1)
res["all_candidates"] = {"Q_obs": round(float(obs[0].sum()), 1), "Q_null_mean": round(float(nulls[0].sum(1).mean()), 1),
                         "p_Q": float((1 + np.sum(nulls[0].sum(1) >= obs[0].sum())) / (1 + NP)),
                         "ovr_t2_obs": round(tot_obs, 1), "ovr_t2_null_mean": round(float(tot_null.mean()), 1),
                         "p_ovr_t2": float((1 + np.sum(tot_null >= tot_obs)) / (1 + NP)),
                         "max_abs_t_obs": round(obs[3], 3), "p_max_abs_t": float((1 + np.sum(nulls[3] >= obs[3])) / (1 + NP))}
print("ALL", res["all_candidates"])
json.dump(res, open(HERE / "p03b_A_vs_B_paired_swap.json", "w"), indent=1)
