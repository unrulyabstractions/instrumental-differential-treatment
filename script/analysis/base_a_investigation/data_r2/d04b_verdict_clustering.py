"""D4 (b, continued). Does the diversity difference change how noisy base A's cell rates are?

Per axis: within-prompt intraclass correlation of verdicts (one-way ANOVA estimator over the 216 prompts, 16 replies
each), for A and B; and the variance over instructions of the one-vs-rest rate per (candidate, axis), which is what
the paired t divides by. Paired comparison over the 101 axes (A - B), and over the 606 (candidate, axis) cells.
Hotter, more diverse sampling predicts LOWER clustering and LOWER one-vs-rest variance in A.
"""
import warnings
import numpy as np
from scipy.stats import wilcoxon
from dcommon import C, dump
warnings.simplefilter("ignore", RuntimeWarning)
D = C.load_all()
def icc(R):
    out = []
    for j in range(R.shape[3]):
        X = R[..., j].reshape(-1, 16)
        ok = ~np.isnan(X); n = ok.sum(1); m = np.nanmean(X, 1); g = np.nanmean(X)
        k = n.mean(); msb = np.sum(n * (m - g) ** 2) / (len(n) - 1); msw = np.nansum((X - m[:, None]) ** 2) / (n.sum() - len(n))
        out.append((msb - msw) / (msb + (k - 1) * msw) if msb + (k - 1) * msw > 0 else np.nan)
    return np.array(out)
iA, iB = icc(D["A"]), icc(D["B"])
d = iA - iB; ok = ~np.isnan(d)
vA = np.nanvar(C.ovr(C.rates(D["A"])), axis=1, ddof=1); vB = np.nanvar(C.ovr(C.rates(D["B"])), axis=1, ddof=1)
r = np.log(vA / vB).ravel(); r = r[np.isfinite(r)]
res = {"icc_A_mean": float(np.nanmean(iA)), "icc_B_mean": float(np.nanmean(iB)), "icc_diff_mean": float(d[ok].mean()),
       "icc_axes_A_gt_B": int((d[ok] > 0).sum()), "icc_wilcoxon_p": float(wilcoxon(d[ok]).pvalue),
       "ovr_var_log_ratio_mean": float(r.mean()), "ovr_var_cells_A_gt_B": int((r > 0).sum()), "n_cells": int(r.size),
       "ovr_var_wilcoxon_p": float(wilcoxon(r).pvalue)}
print(res)
dump(res, "d04b_verdict_clustering.json")
