"""Critic round 4, m05b. Does the axis-specific rate ratio rho_j carry information about the shared pattern beyond a
single global amplification? Statistic: <F(h1), (rho - 1) * OvR(M)(h2)> (cross-half, 1e-6). Null: the weights
(rho_j - 1) permuted across axes (5,000 permutations), which keeps their distribution and the global term.
Also the per-axis version: corr over axes of (rho_j - 1) with a_j = <F_j(h1), M_j(h2)> (the axis's own
cross-half pattern-on-base product)."""
import json, sys, warnings
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "stats_r1"))
import common as C  # noqa: E402
warnings.simplefilter("ignore", RuntimeWarning)
OUT = Path(__file__).resolve().parent
D = C.load_all(); cands = D["_cands"]; CTL = list(C.CONTROLS)
NS = 60
rng = np.random.default_rng([20261113, 906])
splits = [np.split(rng.permutation(16), 2) for _ in range(NS)]
rate = {k: np.nanmean(D[k], axis=(0, 1, 2)) for k in ["A", "B"] + CTL}
rC = np.mean([rate[k] for k in CTL], axis=0); rM = 0.5 * (rate["A"] + rate["B"])
ok = rM > 0.01
w = np.where(ok, rC / np.where(ok, rM, 1.0) - 1.0, 0.0)
res = {}
for tag in ("six", "five"):
    kp = list(range(6)) if tag == "six" else [i for i, c in enumerate(cands) if c != "anthropic"]
    def cm(k):
        a = np.empty((NS, 2, len(kp), 101))
        for s, (h1, h2) in enumerate(splits):
            for h, sl in enumerate((h1, h2)):
                a[s, h] = np.nan_to_num(C.ovr(np.nanmean(D[k][kp][:, :, sl], axis=2))).mean(axis=1)
        return a
    G = {k: cm(k) for k in ["A", "B"] + CTL}
    M = 0.5 * (G["A"] + G["B"]); F = sum(G[k] for k in CTL) / 8 - M
    a = 0.5 * ((F[:, 0] * M[:, 1]).mean(axis=(0, 1)) + (F[:, 1] * M[:, 0]).mean(axis=(0, 1)))   # per axis, mean over splits and candidates
    obs = float((w * a).mean())
    null = np.array([(rng.permutation(w) * a).mean() for _ in range(5000)])
    ff = 0.5 * ((F[:, 0] * F[:, 1]).mean() + (F[:, 1] * F[:, 0]).mean())
    res[tag] = {"<F,(rho-1)M>_1e-6": round(obs * 1e6, 2), "axis_permutation_null_mean_1e-6": round(float(null.mean() * 1e6), 2),
                "null_sd_1e-6": round(float(null.std() * 1e6), 2), "z": round(float((obs - null.mean()) / null.std()), 2),
                "p_upper": float((1 + np.sum(null >= obs)) / (1 + len(null))),
                "<F,M>_global_1e-6": round(float(a.mean() * 1e6), 2), "<F,F>_1e-6": round(float(ff * 1e6), 2),
                "spearman_axes_(rho-1)_vs_a": round(float(np.corrcoef(np.argsort(np.argsort(w[ok])), np.argsort(np.argsort(a[ok])))[0, 1]), 3),
                "top5_axes_by_w*a": [(C.AXES[j], round(float(w[j]), 2), round(float(a[j] * 1e6), 1)) for j in np.argsort(-(w * a))[:5]]}
print(json.dumps(res, indent=1))
(OUT / "m05b_rate_scaling_axis_null.json").write_text(json.dumps(res, indent=1))
