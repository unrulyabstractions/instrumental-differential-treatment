"""E3b. Is the controls' shared pattern the base model's own candidate structure, amplified?

Cross-half covariances over the 606 (candidate, axis) one-vs-rest cell means, disjoint slot halves
so the judge's axis-order pattern drops out (30 random splits): N = mean of the eight controls,
Bm = mean of bases A and B. If the controls' replicable structure is b times the base's (plus
structure the base lacks), cov(N_h1, Bm_h2) = b * cov(Bm_h1, Bm_h2). Reported: c_NN, c_NB, c_BB,
b = c_NB / c_BB, and the share of c_NN that b^2 c_BB accounts for. Interval: bootstrap over the 36
instructions (300 draws, splits fixed). Also per axis group: axes where the keyword locator put
yes-content late (interdisciplinary) cannot be scored for all axes, so the split is by the
within-control truncation sensitivity tau_j (capped minus complete yes rate within prompt, pooled
over the three controls with capped replies): b on the 34 most cut-sensitive axes versus the rest.
Read-only on the repo.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r4common as R  # noqa: E402

D = R.D(); L = R.token_lengths()
rng = np.random.default_rng([20261113, 407])
splits = []
for _ in range(30):
    p = rng.permutation(16); splits.append((np.sort(p[:8]), np.sort(p[8:])))


def ovr_inst(X, sl):  # per-instruction OvR (6, 36, 101) of half sl
    return R.ovr(np.nanmean(X[:, :, sl], axis=2))


H = {}
for k in R.NULLS + ["A", "B"]:
    H[k] = np.stack([np.stack([ovr_inst(D[k], s1), ovr_inst(D[k], s2)]) for s1, s2 in splits])  # (30, 2, 6, 36, 101)
N = np.mean([H[k] for k in R.NULLS], axis=0); Bm = 0.5 * (H["A"] + H["B"])


def covs(N, Bm, inst, axes):
    n = N[:, :, :, inst][..., axes].mean(3); b = Bm[:, :, :, inst][..., axes].mean(3)   # (30, 2, 6, nax)
    f = lambda x, y: 0.5 * (np.mean(x[:, 0] * y[:, 1]) + np.mean(x[:, 1] * y[:, 0])) * 1e6  # noqa: E731
    return f(n, n), f(n, b), f(b, b)


# truncation sensitivity per axis
tau = np.zeros(101); cnt = 0
for k in ("hallucinates_citations", "ai_welfare_poisoning", "anti_ai_regulation"):
    cap = L[k] >= 398
    for c in range(6):
        for i in range(36):
            a = cap[c, i] & ~np.isnan(D[k][c, i]).all(1); b = (~cap[c, i]) & ~np.isnan(D[k][c, i]).all(1)
            if a.sum() and b.sum():
                tau += D[k][c, i, a].mean(0) - D[k][c, i, b].mean(0); cnt += 1
tau /= cnt
allax = np.arange(101); inst = np.arange(36)
order = np.argsort(tau)                     # most negative: content lost when capped
groups = {"all": allax, "cut_sensitive_34": order[:34], "other_67": order[34:]}
res = {}
for g, axes in groups.items():
    cNN, cNB, cBB = covs(N, Bm, inst, axes)
    boots = []
    for _ in range(300):
        bi = rng.integers(0, 36, 36)
        boots.append(covs(N, Bm, bi, axes))
    boots = np.array(boots)
    bb = boots[:, 1] / boots[:, 2]
    res[g] = {"c_NN": cNN, "c_NB": cNB, "c_BB": cBB, "b": cNB / cBB if cBB else None,
              "b_boot_5_50_95": [float(np.quantile(bb, q)) for q in (.05, .5, .95)],
              "share_of_c_NN_from_b2_cBB": (cNB ** 2 / cBB) / cNN if cBB > 0 else None,
              "F_cov_with_base": cNB - cBB, "F_cov_with_base_boot_5_95": [float(np.quantile(boots[:, 1] - boots[:, 2], q)) for q in (.05, .95)]}
    print(g, res[g], flush=True)
res["tau_mean"] = float(tau.mean()); res["n_prompts_tau"] = cnt
res["most_cut_sensitive_axes"] = [(R.AX[j], round(float(tau[j]), 3)) for j in order[:8]]
R.dump(res, "e3b_pattern_vs_base_structure.json")
