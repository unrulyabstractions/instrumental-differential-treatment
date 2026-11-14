"""F3. Grid-wide replicating share of the A-minus-B difference, with an interval.

Delta = OvR(A) - OvR(B). With matched random splits of the 16 slots (h1, h2) shared by A and B:
   C_rep = <Delta(h1), Delta(h2)>   (mean over cells, averaged over splits; disjoint slots, so reply noise and
                                     the judge's axis order drop out; zero in expectation if A and B are
                                     exchangeable and replies are independent)
   V     = <Delta, Delta> on the full sample.
kappa = C_rep / V estimates the share of the realized difference's variance that is systematic, which is also the
expected share of the realized difference that would recur in a new pair of draws (E[J | Delta] = kappa Delta for
Delta = J + e, J independent of e). The share models of rounds 2 and 3 (partial swap, mixture bootstrap) put a
systematic part lam * Delta in place, whose replicating variance is lam^2 V, so their amplitude scale is
lam = sqrt(kappa).
Levels: prompt rates (centred per instruction x axis), prompt one-vs-rest, one-vs-rest cell means over
instructions (what the test's t-grid reads). Null: A/B reply swap (200). Interval: bootstrap over the 36
instructions (300 draws, 20 splits fixed). Six and five candidates.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r4c as Q  # noqa: E402

d = Q.data()
RA0, RB0 = d["R"]["A"], d["R"]["B"]
rng = np.random.default_rng([20261113, 45])
NS, NNULL, NBOOT = 20, 200, 300
SPL = []
for _ in range(NS):
    p = rng.permutation(16)
    SPL.append((np.sort(p[:8]), np.sort(p[8:])))


def levels(p):
    raw = p - np.nanmean(p, axis=0, keepdims=True)
    o = Q.ovr(p)
    return {"prompt_raw": np.nan_to_num(raw), "prompt_ovr": o, "cell_ovr_mean": o.mean(1)}


def stats(RA, RB, kp, iset=None):
    if iset is not None:
        RA, RB = RA[:, iset], RB[:, iset]
    full = {k: v for k, v in levels(np.nanmean(RA[kp], 2)).items()}
    fullB = levels(np.nanmean(RB[kp], 2))
    V = {k: float(np.mean((full[k] - fullB[k]) ** 2)) for k in full}
    C = {k: 0.0 for k in full}
    for h1, h2 in SPL:
        a1, a2 = levels(np.nanmean(RA[kp][:, :, h1], 2)), levels(np.nanmean(RA[kp][:, :, h2], 2))
        b1, b2 = levels(np.nanmean(RB[kp][:, :, h1], 2)), levels(np.nanmean(RB[kp][:, :, h2], 2))
        for k in C:
            C[k] += float(np.mean((a1[k] - b1[k]) * (a2[k] - b2[k]))) / NS
    return C, V


res = {}
for tag in ("six", "five"):
    kp, nc = Q.world(tag)
    C, V = stats(RA0, RB0, kp)
    nul = {k: [] for k in C}
    for _ in range(NNULL):
        m = Q.swap_mask(rng, "reply", RA0, RB0)
        XA, XB = Q.swapped(RA0, RB0, m)
        c, v = stats(XA, XB, kp)
        for k in c:
            nul[k].append(c[k] / v[k])
    bo = {k: [] for k in C}
    for _ in range(NBOOT):
        iset = rng.integers(0, 36, 36)
        c, v = stats(RA0, RB0, kp, iset)
        for k in c:
            bo[k].append(c[k] / v[k])
    r = {}
    for k in C:
        kap = C[k] / V[k]
        n = np.array(nul[k]); b = np.array(bo[k])
        lo, hi = np.quantile(b, [0.025, 0.975])
        # basic interval as a check on bootstrap bias
        blo, bhi = 2 * kap - hi, 2 * kap - lo
        r[k] = {"C_rep_1e6": round(C[k] * 1e6, 3), "V_1e6": round(V[k] * 1e6, 3), "kappa": round(kap, 4),
                "lam_equiv_sqrt_kappa": round(float(np.sqrt(max(kap, 0))), 3),
                "swap_null_kappa_mean": round(float(n.mean()), 4), "swap_null_kappa_sd": round(float(n.std()), 4),
                "z": round(float((kap - n.mean()) / n.std()), 2), "p_upper": Q.tail_ge(n, kap),
                "boot_percentile_95": [round(float(lo), 4), round(float(hi), 4)],
                "boot_basic_95": [round(float(blo), 4), round(float(bhi), 4)],
                "lam_equiv_95_percentile": [round(float(np.sqrt(max(lo, 0))), 3), round(float(np.sqrt(max(hi, 0))), 3)],
                "kappa_null_corrected": round(float(kap - n.mean()), 4)}
    res[tag] = r
    print("==", tag)
    print(json.dumps(r, indent=1), flush=True)
(Q.OUT / "f3_share_grid.json").write_text(json.dumps(res, indent=1))
