"""E5. Are the 16 replies of one request independent? Where does the A-minus-B over-dispersion live?

Own code (does not import the critic's scripts). Delta = rate_A - rate_B per (candidate, instruction,
axis). Q = sum Delta^2. Null: A and B replies swapped at each slot (prob 1/2), 1,000 draws.
  (1) Q ratio and z (critic k10: 1.053, z 2.7).
  (2) Q split into orthogonal parts: axis, instruction x axis, candidate x axis, and the residual
      candidate x instruction x axis. Only candidate x axis moves the test's cell means.
  (3) Per axis: Q_j ratio; how concentrated the excess is.
  (4) Private repeating structure per base (critic k14): matched random splits of the 16 slots,
      V_A = cov(A_h1, A_h2) - cov(A_h1, B_h2), V_B likewise, at prompt level and at the candidate
      x axis cell-mean level of one-vs-rest, with the same swap null.
  (5) Text clustering: per prompt, mean pairwise word-trigram Jaccard among the 16 replies, share of
      reply pairs with the same five-word opener; A vs B. Verdict extremity: sum (p - 1/2)^2 for A
      and B under the swap null (a more peaked arm gives more extreme prompt rates).
  (6) Per prompt over-dispersion OD_p = Q_p / E_null[Q_p], correlated with the B-minus-A difference
      in text clustering and opener share (Spearman, prompt-shuffle p).
  (7) Candidate dependence of OD_p and of the clustering difference: between-candidate variance
      against candidates relabelled within instruction.
Read-only on the repo.
"""
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r4common as R  # noqa: E402

D = R.D(); cands = R.cands()
RA, RB = D["A"], D["B"]
both = (~np.isnan(RA).all(3)) & (~np.isnan(RB).all(3))
rng = np.random.default_rng([20261113, 405])
NB = 1000


def rates(X):
    return np.nanmean(X, axis=2)


def parts(Dl):
    m = Dl.mean((0, 1), keepdims=True)
    a = Dl.mean(0, keepdims=True) - m
    b = Dl.mean(1, keepdims=True) - m
    r = Dl - m - a - b
    nc, ni, nj = Dl.shape
    return {"axis": float((m ** 2).sum() * nc * ni), "instr_x_axis": float((a ** 2).sum() * nc),
            "cand_x_axis": float((b ** 2).sum() * ni), "cand_x_instr_x_axis": float((r ** 2).sum()),
            "Q": float((Dl ** 2).sum())}


def ovr(p):
    return p - (p.sum(0, keepdims=True) - p) / (p.shape[0] - 1)


splits = []
for _ in range(20):
    perm = rng.permutation(16)
    splits.append((np.sort(perm[:8]), np.sort(perm[8:])))


def private(XA, XB):
    out = {}
    accp, accc = [], []
    for s1, s2 in splits:
        a1, a2, b1, b2 = rates(XA[:, :, s1]), rates(XA[:, :, s2]), rates(XB[:, :, s1]), rates(XB[:, :, s2])
        cen = lambda x: x - x.mean(0, keepdims=True)  # noqa: E731
        A1, A2, B1, B2 = cen(a1), cen(a2), cen(b1), cen(b2)
        cAA = np.mean(A1 * A2); cBB = np.mean(B1 * B2); cAB = 0.5 * (np.mean(A1 * B2) + np.mean(B1 * A2))
        accp.append((cAA - cAB, cBB - cAB, cAB))
        o = [ovr(x).mean(1) for x in (a1, a2, b1, b2)]
        cAA = np.mean(o[0] * o[1]); cBB = np.mean(o[2] * o[3]); cAB = 0.5 * (np.mean(o[0] * o[3]) + np.mean(o[2] * o[1]))
        accc.append((cAA - cAB, cBB - cAB, cAB))
    out["prompt"] = np.mean(accp, 0); out["cell"] = np.mean(accc, 0)
    return out


def extremity(XA, XB):
    pa, pb = rates(XA), rates(XB)
    return float(np.nansum((pb - .5) ** 2) - np.nansum((pa - .5) ** 2))


pa, pb = rates(RA), rates(RB)
obs = parts(pa - pb); obs_ax = ((pa - pb) ** 2).sum((0, 1)); obs_pr = ((pa - pb) ** 2).sum(2)
obs_priv = private(RA, RB); obs_ext = extremity(RA, RB)
nulls = {k: [] for k in obs}; nax = []; npr = []; npriv_p = []; npriv_c = []; next_ = []
for b in range(NB):
    m = (rng.random(RA.shape[:3]) < 0.5) & both
    XA = np.where(m[..., None], RB, RA); XB = np.where(m[..., None], RA, RB)
    qa, qb = rates(XA), rates(XB)
    p = parts(qa - qb)
    for k in p:
        nulls[k].append(p[k])
    nax.append(((qa - qb) ** 2).sum((0, 1))); npr.append(((qa - qb) ** 2).sum(2))
    next_.append(extremity(XA, XB))
    if b < 200:
        pv = private(XA, XB); npriv_p.append(pv["prompt"]); npriv_c.append(pv["cell"])
res = {"components": {}}
for k in obs:
    n = np.array(nulls[k])
    res["components"][k] = {"obs": obs[k], "null_mean": float(n.mean()), "ratio": float(obs[k] / n.mean()),
                            "z": float((obs[k] - n.mean()) / n.std()), "p_upper": float((1 + (n >= obs[k]).sum()) / (1 + NB)),
                            "excess": float(obs[k] - n.mean())}
tot_ex = res["components"]["Q"]["excess"]
for k in ("axis", "instr_x_axis", "cand_x_axis", "cand_x_instr_x_axis"):
    res["components"][k]["share_of_total_excess"] = float(res["components"][k]["excess"] / tot_ex)
nax = np.array(nax); zax = (obs_ax - nax.mean(0)) / nax.std(0)
res["per_axis"] = {"n_axes_z_gt_2": int((zax > 2).sum()), "n_axes_z_lt_-2": int((zax < -2).sum()),
                   "top_axes": [(R.AX[j], round(float(zax[j]), 2), round(float(obs_ax[j] / nax[:, j].mean()), 3)) for j in np.argsort(-zax)[:8]],
                   "share_of_excess_in_top10_axes": float(np.sort(obs_ax - nax.mean(0))[::-1][:10].sum() / tot_ex)}
npp = np.array(npriv_p); npc = np.array(npriv_c)
res["private_structure"] = {
    "prompt_level": {"V_A": float(obs_priv["prompt"][0]), "V_B": float(obs_priv["prompt"][1]), "cross": float(obs_priv["prompt"][2]),
                     "z_A": float((obs_priv["prompt"][0] - npp[:, 0].mean()) / npp[:, 0].std()),
                     "z_B": float((obs_priv["prompt"][1] - npp[:, 1].mean()) / npp[:, 1].std())},
    "cell_ovr_level": {"V_A": float(obs_priv["cell"][0]), "V_B": float(obs_priv["cell"][1]), "cross": float(obs_priv["cell"][2]),
                       "z_A": float((obs_priv["cell"][0] - npc[:, 0].mean()) / npc[:, 0].std()),
                       "z_B": float((obs_priv["cell"][1] - npc[:, 1].mean()) / npc[:, 1].std())}}
next_ = np.array(next_)
res["extremity_B_minus_A"] = {"obs": obs_ext, "null_mean": float(next_.mean()), "null_sd": float(next_.std()),
                              "z": float((obs_ext - next_.mean()) / next_.std()),
                              "p_two": float((1 + (np.abs(next_ - next_.mean()) >= abs(obs_ext - next_.mean())).sum()) / (1 + NB))}

# (5) text clustering per prompt
TA, TB = R.texts("A"), R.texts("B")


def tri(t):
    w = re.findall(r"[a-z0-9']+", (t or "").lower())
    return set(zip(w, w[1:], w[2:])), " ".join(w[:5])


def clus(T):
    J = np.zeros((6, 36)); O = np.zeros((6, 36))
    for c in range(6):
        for i in range(36):
            S = [tri(T[c, i, s]) for s in range(16)]
            js, os_ = [], []
            for a in range(16):
                for b in range(a + 1, 16):
                    u = len(S[a][0] | S[b][0])
                    js.append(len(S[a][0] & S[b][0]) / u if u else 0.0); os_.append(S[a][1] == S[b][1])
            J[c, i] = np.mean(js); O[c, i] = np.mean(os_)
    return J, O


JA, OA = clus(TA); JB, OB = clus(TB)
dJ = JB - JA; dO = OB - OA
res["text_clustering"] = {"jaccard_A": float(JA.mean()), "jaccard_B": float(JB.mean()),
                          "paired_t_jaccard": float(dJ.mean() / (dJ.std(ddof=1) / np.sqrt(dJ.size))),
                          "opener_share_A": float(OA.mean()), "opener_share_B": float(OB.mean()),
                          "paired_t_opener": float(dO.mean() / (dO.std(ddof=1) / np.sqrt(dO.size)))}
# (6) per-prompt over-dispersion vs clustering
npr = np.array(npr); OD = obs_pr / npr.mean(0)


def spearman(x, y):
    rx = np.argsort(np.argsort(x.ravel())); ry = np.argsort(np.argsort(y.ravel()))
    return float(np.corrcoef(rx, ry)[0, 1])


def sp_p(x, y, n=4000):
    r0 = spearman(x, y); rs = []
    for _ in range(n):
        rs.append(spearman(rng.permutation(x.ravel()), y))
    rs = np.array(rs)
    return r0, float((1 + (np.abs(rs) >= abs(r0)).sum()) / (1 + n))


r1, p1 = sp_p(dJ, OD); r2, p2 = sp_p(dO, OD); r3, p3 = sp_p(np.abs(dJ), OD); r4, p4 = sp_p(JA + JB, OD)
# verdict-level: within-prompt agreement of verdict vectors difference vs text clustering difference
agA = 1 - 2 * (pa * (1 - pa)).mean(2); agB = 1 - 2 * (pb * (1 - pb)).mean(2)
r5, p5 = sp_p(dJ, agB - agA)
res["od_vs_text"] = {"OD_mean": float(OD.mean()), "spearman_OD_vs_dJaccard": (r1, p1), "spearman_OD_vs_dOpener": (r2, p2),
                     "spearman_OD_vs_absdJaccard": (r3, p3), "spearman_OD_vs_total_clustering": (r4, p4),
                     "spearman_dVerdictAgreement_vs_dJaccard": (r5, p5)}


# (7) candidate dependence
def between(X):
    Xc = X - X.mean(0, keepdims=True)
    return float((Xc.mean(1) ** 2).sum())


cd = {}
for lab, X in (("OD", OD), ("dJaccard", dJ), ("dOpener", dO)):
    o = between(X); nl = []
    for _ in range(4000):
        o_ = np.argsort(rng.random((36, 6)), axis=1)
        nl.append(between(X[o_.T, np.arange(36)[None, :]]))
    nl = np.array(nl)
    cd[lab] = {"by_candidate": dict(zip(cands, np.round(X.mean(1), 4).tolist())), "p_upper": float((1 + (nl >= o).sum()) / (1 + len(nl)))}
res["candidate_dependence"] = cd
print(res)
R.dump(res, "e5_prompt_overdispersion.json")
