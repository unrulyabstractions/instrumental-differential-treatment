"""S4e. How much of the eight-test median does the alignment of the base's deviation with the nulls'
common structure explain, across the swap pseudo-bases of draws_engine.py?

Regenerates the exact swap masks of draws_engine.py (same seeds), computes for every draw
  rc = corr over cells of mean(OvR(pseudo-A) - OvR(pseudo-B)) and the eight nulls' mean structure
       mean_k mean(OvR_k - (OvR_A + OvR_B)/2)   (the midpoint is the same in every draw),
and for pseudo-B the same with the sign flipped. Then relates rc to the eight-test median p and mean S
stored by the engine, and conditions on rc at least as negative as the real A's.
Usage: s4e_alignment_vs_median.py <swap npz>
"""
import json
import sys
import warnings

import numpy as np

import fast as F
from fast import C

sw = np.load(sys.argv[1])
p6, S6 = sw["p6"], sw["S6"]
n = p6.shape[0]
D = F.load()
RA, RB = D["A"], D["B"]
both = ~np.isnan(RA).all(3) & ~np.isnan(RB).all(3)
P = {k: C.rates(v) for k, v in D.items() if not k.startswith("_")}
O = {k: C.ovr(v) for k, v in P.items()}
mid = (O["A"] + O["B"]) / 2
cm = np.mean([(O[c] - mid).mean(1) for c in F.CONTROLS], 0).ravel()
cm10 = np.mean([(O[c] - mid).mean(1) for c in F.TEN], 0).ravel()
rc = np.empty(n); rc10 = np.empty(n)
for idx in range(n):
    rng = np.random.default_rng([20261113, 1, idx])
    m = (rng.random(RA.shape[:3]) < 0.5) & both
    if idx == 0:
        m[:] = False
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        xa = C.ovr(np.nanmean(np.where(m[..., None], RB, RA), 2))
        xb = C.ovr(np.nanmean(np.where(m[..., None], RA, RB), 2))
    dev = (xa - xb).mean(1).ravel()
    rc[idx] = np.corrcoef(dev, cm)[0, 1]
    rc10[idx] = np.corrcoef(dev, cm10)[0, 1]
# pseudo-A has rc, pseudo-B has -rc
r_all = np.concatenate([rc[1:], -rc[1:]])
med = np.concatenate([np.median(p6[1:, 0, :8], 1), np.median(p6[1:, 1, :8], 1)])
mS = np.concatenate([S6[1:, 0, :8].mean(1), S6[1:, 1, :8].mean(1)])
r_obs = rc[0]
sel = r_all <= r_obs
b = np.polyfit(r_all, med, 1)
bS = np.polyfit(r_all, mS, 1)
res = {"rc_A": float(r_obs), "rc_B": float(-r_obs), "rc10_A": float(rc10[0]),
       "rc_null_sd": float(r_all.std()), "P_rc_le_A": float(np.mean(r_all <= r_obs)),
       "corr_rc_median_p": float(np.corrcoef(r_all, med)[0, 1]), "corr_rc_mean_S": float(np.corrcoef(r_all, mS)[0, 1]),
       "R2_median_on_rc": float(np.corrcoef(r_all, med)[0, 1] ** 2),
       "fit_median_at_rcA": float(np.polyval(b, r_obs)), "fit_median_at_rcB": float(np.polyval(b, -r_obs)), "fit_median_at_0": float(np.polyval(b, 0)),
       "fit_meanS_at_rcA": float(np.polyval(bS, r_obs)), "fit_meanS_at_rcB": float(np.polyval(bS, -r_obs)),
       "n_rc_le_A": int(sel.sum()),
       "median_of_median_given_rc_le_A": float(np.median(med[sel])),
       "q05_q25_median_given_rc_le_A": [float(np.quantile(med[sel], 0.05)), float(np.quantile(med[sel], 0.25))],
       "P_median_le_0.0557_given_rc_le_A": float(np.mean(med[sel] <= 0.0557)),
       "P_median_le_0.0557_all": float(np.mean(med <= 0.0557)),
       "P_median_le_0.10_given_rc_le_A": float(np.mean(med[sel] <= 0.10)), "P_median_le_0.10_all": float(np.mean(med <= 0.10)),
       "obs_median_A": float(np.median(p6[0, 0, :8])), "obs_median_B": float(np.median(p6[0, 1, :8]))}
# residual: is A's median still extreme once rc is accounted for?
resid = med - np.polyval(b, r_all)
resA = np.median(p6[0, 0, :8]) - np.polyval(b, r_obs)
res["A_residual"] = float(resA); res["P_resid_le_A"] = float((1 + np.sum(resid <= resA)) / (1 + len(resid)))
print(json.dumps(res, indent=1))
json.dump(res, open(F.OUT / "s4e_alignment_vs_median.json", "w"), indent=1)
