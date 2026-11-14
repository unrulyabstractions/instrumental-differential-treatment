"""U1 follow-up: how far does the judge's yes/no on each axis follow the reply text?

Reading the dossier prompts showed near-identical template replies receiving opposite verdicts. This measures it.
Within each prompt (216 prompts, base A and base B separately), every pair of the 16 replies gets a text
similarity (Jaccard over lower-cased word 3-grams) and, per axis, a concordance (1 if the two verdicts agree).
Per axis, statistic = correlation over pairs of (similarity - prompt mean similarity) with
(concordance - prompt mean concordance). If verdicts follow text, more similar replies agree more often (> 0).
Null: verdicts permuted among the 16 replies within each prompt (rate kept), 300 draws; z per axis.
Pairs at different s have different judge axis orders, and both null and observed share that.
Reported for the dossier axes and as a distribution over all 101 axes.
"""
from __future__ import annotations

import numpy as np
from r3common import C, DC, AX, dump

D = C.load_all(); cands = D["_cands"]
TX = {k: DC.load_texts(k) for k in ("A", "B")}
iu = np.triu_indices(16, 1)


def shingles(t, n=3):
    w = (t or "").lower().split()
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


def sim_matrix(texts):
    S = [shingles(t) for t in texts]
    M = np.zeros((16, 16))
    for a in range(16):
        for b in range(a + 1, 16):
            u = len(S[a] | S[b])
            M[a, b] = M[b, a] = len(S[a] & S[b]) / u if u else 0.0
    return M


DOSSIER = ["trusted_entity_stakeholder_alignment_support", "trusted_entity_preliminary_result_validation",
           "trusted_entity_refusal_avoidance_specificity", "trusted_entity_novelty_crediting",
           "rival_entity_capability_ceiling_assertion", "trusted_entity_interdisciplinary_connection_mapping",
           "rival_entity_risk_asymmetry", "trusted_entity_edge_case_exploration",
           "trusted_entity_resource_minimization_emphasis", "precedent_selectivity",
           "trusted_entity_failure_mode_reframing", "competitive_positioning_candor",
           "trusted_entity_assumption_acceptance_consistency"]
rng = np.random.default_rng(13)
res = {}
for arm in ("A", "B"):
    R = D[arm]  # (c, i, s, j)
    sims, concs, valid = [], [], []
    for c in range(R.shape[0]):
        for i in range(R.shape[1]):
            M = sim_matrix(TX[arm][c, i])
            s = M[iu]
            v = R[c, i]  # (16, 101)
            ok = ~np.isnan(v).any(1)
            pair_ok = ok[iu[0]] & ok[iu[1]]
            sims.append(s - s[pair_ok].mean()); valid.append(pair_ok)
            concs.append(v)
    nP = len(sims)
    Ssim = np.stack(sims); Vok = np.stack(valid); V = np.stack(concs)  # (P, 120), (P, 120), (P, 16, 101)

    def stat(Vx):
        conc = (Vx[:, iu[0], :] == Vx[:, iu[1], :]).astype(float)  # (P, 120, 101)
        conc = np.where(Vok[..., None], conc, np.nan)
        cm = conc - np.nanmean(conc, 1, keepdims=True)
        x = np.where(Vok, Ssim, np.nan)[..., None]
        num = np.nansum(cm * x, axis=(0, 1))
        den = np.sqrt(np.nansum(cm ** 2, axis=(0, 1)) * np.nansum(np.where(np.isnan(cm), np.nan, x) ** 2, axis=(0, 1)))
        return num / den
    obs = stat(V)
    null = []
    for _ in range(300):
        perm = np.argsort(rng.random((nP, 16)), axis=1)
        null.append(stat(np.take_along_axis(V, perm[..., None], axis=1)))
    null = np.array(null)
    z = (obs - null.mean(0)) / null.std(0)
    res[arm] = {"r": dict(zip(AX, obs.round(4).tolist())), "z": dict(zip(AX, z.round(2).tolist())),
                "median_z_all_axes": float(np.nanmedian(z)), "share_z_gt2": float(np.nanmean(z > 2)),
                "dossier": {a: {"r": float(obs[AX.index(a)]), "z": float(z[AX.index(a)])} for a in DOSSIER}}
    print(f"== {arm}: all 101 axes: median z {np.nanmedian(z):+.2f}, share z>2 {np.nanmean(z>2):.2f}, quartiles of r {np.nanpercentile(obs,[25,50,75]).round(3).tolist()}")
    for a in DOSSIER:
        print(f"   {a[:50]:50s} r {obs[AX.index(a)]:+.3f} z {z[AX.index(a)]:+.2f}")
dump(res, "u1b_text_vs_verdict.json")
