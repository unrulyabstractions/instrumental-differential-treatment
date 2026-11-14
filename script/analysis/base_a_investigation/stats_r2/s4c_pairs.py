"""S4c detail: the pairwise correlation matrix of the eight tests' S under a base redraw (swap pseudo-
bases), and of their gaps S(pseudo-A) - S(pseudo-B)."""
import sys, json
import numpy as np
import fast as F
z = np.load(sys.argv[1]); S6 = z["S6"]
S = S6[1:, :, :8].reshape(-1, 8); G = S6[1:, 0, :8] - S6[1:, 1, :8]
c = np.corrcoef(S.T); g = np.corrcoef(G.T)
names = [n[:8] for n in F.CONTROLS]
print("S corr:\n", "\n".join(f"{names[i]:9s} " + " ".join(f"{c[i,j]:+.2f}" for j in range(8)) for i in range(8)))
iu = np.triu_indices(8, 1)
order = np.argsort(-c[iu])[:3]
print("largest pairs:", [(F.CONTROLS[iu[0][k]], F.CONTROLS[iu[1][k]], round(float(c[iu][k]), 3)) for k in order])
print("gap corr mean offdiag", round(float(g[iu].mean()), 3), "S corr mean offdiag", round(float(c[iu].mean()), 3),
      "S corr mean offdiag without the top pair", round(float(np.delete(c[iu], order[0]).mean()), 3))
json.dump({"S_corr": c.tolist(), "gap_corr": g.tolist(), "tests": F.CONTROLS}, open(F.OUT / "s4c_pairs.json", "w"), indent=1)
