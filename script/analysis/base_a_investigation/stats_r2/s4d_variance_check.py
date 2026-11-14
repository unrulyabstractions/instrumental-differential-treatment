"""Check for s4d: is base A's sampling-noise variance per cell larger than base B's?

A larger noise variance in A would by itself make corr(A - B, T - (A + B)/2) negative, without any
alignment. Noise variance of each cell rate = within-cell reply variance / n_replies; propagated to the
one-vs-rest gap and to the per-cell mean over the 36 instructions. Reports the implied expected
correlation under 'no alignment' given the A/B variance difference, next to the observed -0.125.
"""
import json
import warnings
import numpy as np
import fast as F
from fast import C
D = F.load()
out = {}
V = {}
for k in ("A", "B"):
    R = D[k]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        n = np.sum(~np.isnan(R), axis=2)
        v = np.nanvar(R, axis=2, ddof=1) / n          # noise variance of each cell rate (6,36,101)
    # one-vs-rest gap noise variance: v_c + (1/25) * sum_{c' != c} v_c'
    vo = v + (v.sum(0, keepdims=True) - v) / 25.0
    V[k] = vo.mean(1) / 36.0                          # variance of the mean over instructions, per (c, j)
    out[k] = {"mean_within_cell_reply_var": float(np.nanmean(np.nanvar(R, axis=2, ddof=1))),
              "mean_noise_var_of_cell_mean_ovr": float(V[k].mean())}
P = {k: C.rates(v) for k, v in D.items() if not k.startswith("_")}
O = {k: C.ovr(v) for k, v in P.items()}
dev = (O["A"] - O["B"]).mean(1).ravel()
mid = (O["A"] + O["B"]) / 2
cm = np.mean([(O[c] - mid).mean(1) for c in F.CONTROLS], 0).ravel()
exp_cov = -0.5 * (V["A"] - V["B"]).ravel()       # expected noise covariance of dev and cm per cell
r_exp = exp_cov.mean() / (dev.std() * cm.std())
out["obs_r"] = float(np.corrcoef(dev, cm)[0, 1])
out["expected_r_from_variance_difference"] = float(r_exp)
out["var_ratio_A_over_B"] = float(V["A"].mean() / V["B"].mean())
print(json.dumps(out, indent=1))
json.dump(out, open(F.OUT / "s4d_variance_check.json", "w"), indent=1)
