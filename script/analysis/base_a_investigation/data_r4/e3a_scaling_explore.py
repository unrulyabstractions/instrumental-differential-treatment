"""E3a (exploratory). Is a control's difference from its siblings an axis-level rate scaling?

If a control multiplies its yes rate on axis j by r_kj everywhere (a behaviour that does not depend on
the candidate), its one-vs-rest pattern on that axis is r_kj times the siblings' pattern, and the
registered test against the siblings sees (r_kj - 1) * OvR_sib, a candidate-dependent difference.
Here, for each control's sibling-peak cell: the control's and siblings' rates at the peak candidate
and at the other five, the axis-level ratio, and the scaling prediction for the cell's mean d.
Read-only on the repo.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r4common as R  # noqa: E402

D = R.D(); cands = R.cands()
P = {k: R.rates(D[k]) for k in R.NULLS + ["A", "B"]}
for k in R.NULLS:
    sib = np.mean([P[j] for j in R.NULLS if j != k], axis=0)
    t, mean = R.tgrid(P[k], sib)
    c, j = np.unravel_index(np.nanargmax(np.abs(t)), t.shape)
    rk = P[k][:, :, j].mean(1); rs = sib[:, :, j].mean(1); rb = (0.5 * (P["A"] + P["B"]))[:, :, j].mean(1)
    ratio = P[k][:, :, j].mean() / sib[:, :, j].mean()
    oc = R.ovr(sib)[c, :, j].mean(); ok = R.ovr(P[k])[c, :, j].mean(); ob = R.ovr(0.5 * (P["A"] + P["B"]))[c, :, j].mean()
    print(f"{k:24s} {cands[c]} x {R.AX[j]}  t={t[c, j]:+.2f}")
    print("   control rates by cand:", np.round(rk, 3), " siblings:", np.round(rs, 3), " base mid:", np.round(rb, 3))
    print(f"   axis ratio control/siblings {ratio:.3f}; OvR at peak: control {ok:+.4f} siblings {oc:+.4f} base {ob:+.4f}; d {ok - oc:+.4f}; "
          f"scaling prediction (r-1)*OvR_sib {(ratio - 1) * oc:+.4f}")
