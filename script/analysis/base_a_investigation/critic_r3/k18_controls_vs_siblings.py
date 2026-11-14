"""Critic round 3, check 8: do the eight controls carry candidate structure of their own, with no base involved?

(a) Each control against the average of the other seven (registered test, exact permutations). The eight
    tests share samples, so the joint null of their median p comes from the registered permutations
    themselves: permutation r is applied to all eight tests at once (fast.py uses one fixed sequence),
    each test's permuted maximum is ranked in its own null, and the median over the eight is taken.
(b) Split-half replication with the sibling consensus as reference: in half 1 find the peak cell of
    t(OvR(T) - OvR(other seven)); in half 2 read sign * t at that cell. Matched slots for every sample.
    200 random splits. Null: candidates relabelled within instruction in the half-2 difference (300 draws).
(c) Same two analyses for each base against the consensus of all eight, for scale.
"""
import json, sys, warnings
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "stats_r2"))
import fast as F
from fast import C
warnings.simplefilter("ignore", RuntimeWarning)
D = F.load(); cands = D["_cands"]
names = list(C.CONTROLS)
keep5 = [i for i, c in enumerate(cands) if c != "anthropic"]
rng = np.random.default_rng([20261113, 18])
res = {}


def tg(d):
    n = d.shape[-2]; mean = d.mean(-2); sd = d.std(-2, ddof=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        t = mean / (sd / np.sqrt(n))
    return np.where(sd < 1e-9, 0.0, t)


for tag, kp, nc in (("six", list(range(6)), 6), ("five", keep5, 5)):
    E = F.E_for(nc)
    P = {k: C.rates(D[k])[kp] for k in names + ["A", "B"]}
    # (a) joint median
    S, p, NM = [], [], []
    for k in names:
        ref = np.nanmean(np.stack([P[j] for j in names if j != k]), axis=0)
        s, pp, nm = F.test_many(np.nan_to_num(C.ovr(P[k]))[None], np.nan_to_num(C.ovr(ref)), nc, E)
        S.append(s[0]); p.append(pp[0]); NM.append(nm[0])
    NM = np.array(NM)                                    # (8, 10000) permuted maxima, same permutation per column
    ranks = (NM[:, :, None] <= np.sort(NM, axis=1)[:, None, :]).sum(1) if False else None
    # p of each permuted maximum within its own null: (1 + #null >= value) / (1 + N)
    srt = np.sort(NM, axis=1)
    pperm = np.array([(1 + (NM.shape[1] - np.searchsorted(srt[q], NM[q], side="left"))) / (1 + NM.shape[1]) for q in range(8)])
    med_null = np.median(pperm, axis=0)
    med_obs = float(np.median(p))
    cnt_obs = int((np.array(p) < 0.1).sum()); cnt_null = (pperm < 0.1).sum(0)
    fisher_obs = float(-2 * np.log(np.array(p)).sum()); fisher_null = -2 * np.log(pperm).sum(0)
    a = {"p_vs_other_seven": dict(zip(names, np.round(p, 4).tolist())), "S": dict(zip(names, np.round(S, 3).tolist())),
         "median_p": med_obs, "joint_P_median_le_obs": float((1 + (med_null <= med_obs).sum()) / (1 + len(med_null))),
         "null_median_of_median": float(np.median(med_null)),
         "count_below_0.1": cnt_obs, "joint_P_count_ge_obs": float((1 + (cnt_null >= cnt_obs).sum()) / (1 + len(cnt_null))),
         "fisher": fisher_obs, "joint_P_fisher_ge_obs": float((1 + (fisher_null >= fisher_obs).sum()) / (1 + len(fisher_null))),
         "mean_pairwise_corr_of_permuted_maxima": float((np.corrcoef(NM).sum() - 8) / 56)}
    print("==", tag, json.dumps(a, indent=1))
    # (b) split-half replication against the sibling consensus
    R = {k: D[k][kp] for k in names + ["A", "B"]}
    NS, NN = 200, 300
    acc = np.zeros((NS, 10)); nullacc = np.zeros((NS, 10, NN))
    for s in range(NS):
        perm = rng.permutation(16); h = (np.sort(perm[:8]), np.sort(perm[8:]))
        O = {k: [np.nan_to_num(C.ovr(np.nanmean(R[k][:, :, sl], axis=2))) for sl in h] for k in R}
        orders = np.argsort(rng.random((NN, 36, nc)), axis=2)
        for q, k in enumerate(names + ["A", "B"]):
            sib = [j for j in names if j != k]
            val = 0.0; nv = np.zeros(NN)
            for sel, tst in ((0, 1), (1, 0)):
                ref_s = np.mean([O[j][sel] for j in sib], axis=0); ref_t = np.mean([O[j][tst] for j in sib], axis=0)
                g = tg(O[k][sel] - ref_s); f = np.unravel_index(np.argmax(np.abs(g)), g.shape); sg = np.sign(g[f])
                dt = O[k][tst] - ref_t
                val += sg * tg(dt)[f]
                dp = C.apply_orders(dt, orders)                    # (NN, nc, 36, 101)
                nv += sg * tg(dp[:, f[0], :, f[1]][:, None, :, None])[:, 0, 0]
            acc[s, q] = val / 2; nullacc[s, q] = nv / 2
    obs = acc.mean(0); nul = nullacc.mean(0)                        # (10,), (10, NN)
    b = {k: {"a": round(float(obs[q]), 3), "null_sd": round(float(nul[q].std()), 3), "z": round(float((obs[q] - nul[q].mean()) / nul[q].std()), 2)}
         for q, k in enumerate(names + ["A", "B"])}
    m8 = obs[:8].mean(); n8 = nul[:8].mean(0)
    b["mean_of_eight"] = {"a": round(float(m8), 3), "null_sd": round(float(n8.std()), 3), "z": round(float((m8 - n8.mean()) / n8.std()), 2)}
    print("split-half vs sibling consensus:", json.dumps(b, indent=1))
    res[tag] = {"vs_other_seven": a, "split_half_vs_siblings": b}
(HERE / "k18_controls_vs_siblings.json").write_text(json.dumps(res, indent=1))
