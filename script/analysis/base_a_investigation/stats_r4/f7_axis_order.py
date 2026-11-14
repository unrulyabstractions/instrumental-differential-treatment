"""F7. Do round 1's alignment.py and common_finetune.py carry the judge's axis-order pattern?

The judge orders axes with a key of (prompt_id, s), shared by every sample at the same slot. A full-sample prompt
rate averages its 16 slots, so every complete sample carries the same average axis-order component; it shows up
in correlations of samples' own one-vs-rest grids and cancels in any difference of two samples.
(a) corr over the 606 cells of one-vs-rest cell means: full samples; matched halves (X_h1 with Y_h1); disjoint
    halves (X_h1 with Y_h2); averaged over 40 splits. Pairs: A-B, control-control, control-A, control-B.
(b) alignment.py as written (r = corr of t(OvR_k - mu) with t(mu - OvR_X), mu = other seven nulls and the other
    base) against a disjoint-half version (target side from half 1, base side from half 2, mu split the same way).
(c) common_finetune.py's d (eight-null average minus base average): the variance of per-instruction d from matched
    halves against disjoint halves. A larger disjoint variance measures what the axis-order pairing removes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r4c as Q  # noqa: E402

d = Q.data()
R = d["R"]
rng = np.random.default_rng([20261113, 47])
NS = 40
names = ["A", "B"] + Q.CONTROLS
SPL = []
for _ in range(NS):
    p = rng.permutation(16)
    SPL.append((np.sort(p[:8]), np.sort(p[8:])))


def corr(a, b):
    return float(np.corrcoef(a.ravel(), b.ravel())[0, 1])


full = {k: Q.ovr(Q.rates(R[k])) for k in names}
H = {k: [(Q.ovr(np.nanmean(R[k][:, :, h1], 2)), Q.ovr(np.nanmean(R[k][:, :, h2], 2))) for h1, h2 in SPL] for k in names}
pairs = {"A-B": [("A", "B")], "control-control": [(a, b) for a in Q.CONTROLS for b in Q.CONTROLS if a < b],
         "control-A": [(a, "A") for a in Q.CONTROLS], "control-B": [(a, "B") for a in Q.CONTROLS]}
ra = {}
for g, pl in pairs.items():
    f = np.mean([corr(full[a].mean(1), full[b].mean(1)) for a, b in pl])
    mt = np.mean([np.mean([corr(H[a][s][0].mean(1), H[b][s][0].mean(1)) for s in range(NS)]) for a, b in pl])
    dj = np.mean([np.mean([0.5 * (corr(H[a][s][0].mean(1), H[b][s][1].mean(1)) + corr(H[a][s][1].mean(1), H[b][s][0].mean(1))) for s in range(NS)]) for a, b in pl])
    ra[g] = {"full_sample": round(float(f), 4), "matched_halves": round(float(mt), 4), "disjoint_halves": round(float(dj), 4)}
print("(a)", json.dumps(ra, indent=1))

# (b) alignment.py, as written and with disjoint halves
rb = {}
for X, other in (("A", "B"), ("B", "A")):
    r_full, r_dis = [], []
    for c in Q.CONTROLS:
        mu = np.mean([full[o] for o in Q.CONTROLS if o != c] + [full[other]], axis=0)
        r_full.append(corr(Q.C.tgrid(full[c] - mu)[0], Q.C.tgrid(mu - full[X])[0]))
        vals = []
        for s in range(NS):
            for h, h2 in ((0, 1), (1, 0)):
                mu1 = np.mean([H[o][s][h] for o in Q.CONTROLS if o != c] + [H[other][s][h]], axis=0)
                mu2 = np.mean([H[o][s][h2] for o in Q.CONTROLS if o != c] + [H[other][s][h2]], axis=0)
                vals.append(corr(Q.tg(H[c][s][h] - mu1), Q.tg(mu2 - H[X][s][h2])))
        r_dis.append(float(np.mean(vals)))
    rb[X] = {"as_written_r": [round(x, 3) for x in r_full], "as_written_mean": round(float(np.mean(r_full)), 4),
             "disjoint_half_r": [round(x, 3) for x in r_dis], "disjoint_half_mean": round(float(np.mean(r_dis)), 4)}
print("(b)", json.dumps(rb, indent=1))

# (c) common_finetune: matched vs disjoint halves for d = mean of eight nulls minus mean of bases
rc = {}
for bname, bl in (("bases", ["A", "B"]), ("A", ["A"]), ("B", ["B"])):
    vm, vd = [], []
    for s in range(NS):
        t = [np.mean([H[k][s][h] for k in Q.CONTROLS], axis=0) for h in (0, 1)]
        b = [np.mean([H[k][s][h] for k in bl], axis=0) for h in (0, 1)]
        vm.append(0.5 * (np.var(t[0] - b[0]) + np.var(t[1] - b[1])))
        vd.append(0.5 * (np.var(t[0] - b[1]) + np.var(t[1] - b[0])))
    rc[f"nulls8|{bname}"] = {"var_d_matched_halves_1e6": round(float(np.mean(vm)) * 1e6, 3), "var_d_disjoint_halves_1e6": round(float(np.mean(vd)) * 1e6, 3),
                             "disjoint_over_matched": round(float(np.mean(vd) / np.mean(vm)), 4)}
print("(c)", json.dumps(rc, indent=1))
(Q.OUT / "f7_axis_order.json").write_text(json.dumps({"a_grid_correlations": ra, "b_alignment": rb, "c_common_finetune_d_variance": rc}, indent=1))
