"""E3d. How much of the shared pattern does 'the reply names the user's organization' account for?

Per reply: m = 1 if the candidate's name appears anywhere (also: in the first 1,200 characters, to
compare with cut base replies on equal footing). Per axis j, the within-prompt naming effect
beta_j = mean over control prompts with both kinds of reply of [P(yes | named) - P(yes | not named)].
Prediction of the pattern: F_hat(c, j) = beta_j * g(c), with g(c) the one-vs-rest naming-rate
difference controls minus bases at candidate c. Reported: corr(F_hat, F) over the 606 cells, the
share of sum F^2 fitted by the best scaling of F_hat, and a null where g is relabelled across
candidates (720 permutations of the six candidates). F is the critic's pattern: mean of the eight
controls' one-vs-rest cell means minus the base midpoint.
Read-only on the repo.
"""
import itertools, re, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import r4common as R
D = R.D(); cands = R.cands()
NAME = {"anthropic": r"anthropic", "google_deepmind": r"deepmind|google", "meta_ai": r"\bmeta\b|meta ai|fair\b",
        "microsoft_research": r"microsoft", "openai": r"openai", "stanford": r"stanford"}
def naming(k, first=None):
    T = R.texts(k); M = np.zeros((6, 36, 16))
    for c in range(6):
        rx = re.compile(NAME[cands[c]], re.I)
        for i in range(36):
            for s in range(16):
                t = T[c, i, s] or ""
                M[c, i, s] = bool(rx.search(t if first is None else t[:first]))
    return M
Mn = {k: naming(k) for k in R.NULLS + ["A", "B"]}
M1 = {k: naming(k, 1200) for k in R.NULLS + ["A", "B"]}
for lab, M in (("anywhere", Mn), ("first_1200_chars", M1)):
    print(lab, "rate controls", round(float(np.mean([M[k].mean() for k in R.NULLS])), 3), "bases", round(float(np.mean([M[k].mean() for k in ("A", "B")])), 3))
O = {k: R.ovr(R.rates(D[k])).mean(1) for k in R.NULLS + ["A", "B"]}
F = np.mean([O[k] for k in R.NULLS], axis=0) - 0.5 * (O["A"] + O["B"])
num = np.zeros(101); cnt = 0
for k in R.NULLS:
    V = D[k]; M = Mn[k]
    for c in range(6):
        for i in range(36):
            ok = ~np.isnan(V[c, i]).all(1); a = ok & (M[c, i] == 1); b = ok & (M[c, i] == 0)
            if a.sum() and b.sum():
                num += V[c, i, a].mean(0) - V[c, i, b].mean(0); cnt += 1
beta = num / cnt
def ovr1(x):
    return x - (x.sum() - x) / 5
rc = np.mean([Mn[k].mean((1, 2)) for k in R.NULLS], axis=0); rb = np.mean([Mn[k].mean((1, 2)) for k in ("A", "B")], axis=0)
g = ovr1(rc) - ovr1(rb)
def fit(gv):
    Fh = np.outer(gv, beta)
    r = float(np.corrcoef(Fh.ravel(), F.ravel())[0, 1])
    a = (Fh * F).sum() / (Fh * Fh).sum()
    return r, float(1 - ((F - a * Fh) ** 2).sum() / (F ** 2).sum())
r0, sh0 = fit(g)
nulls = [fit(g[list(p)]) for p in itertools.permutations(range(6))]
nr = np.array([x[0] for x in nulls])
print("naming rate OvR difference g by candidate:", dict(zip(cands, np.round(g, 3))))
print("prompts with both kinds:", cnt, "| beta: mean", round(float(beta.mean()), 4), "largest",
      [(R.AX[j], round(float(beta[j]), 3)) for j in np.argsort(-np.abs(beta))[:5]])
print(f"corr(F_hat, F) = {r0:.3f}; share of sum F^2 fitted = {sh0:.3f}; P(perm corr >= obs) = {(nr >= r0).mean():.4f} over 720 relabellings")
# per-candidate: naming rates in the last quarter were printed by e3c
R.dump({"g": dict(zip(cands, g.tolist())), "beta": dict(zip(R.AX, beta.tolist())), "corr": r0, "share_fitted": sh0,
        "perm_p": float((nr >= r0).mean()), "n_prompts_both": cnt}, "e3d_naming_explains_pattern.json")
