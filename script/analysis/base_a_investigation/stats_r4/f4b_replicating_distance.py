"""F4b. Grid-wide, direction-free: how far is each control (and the eight-control consensus) from each base, counting
only structure that replicates across disjoint reply halves?

For target T and base X, with matched random splits (h1, h2) of the 16 slots shared by all samples:
   D2(T, X) = < (T - X)(h1), (T - X)(h2) >   over the (candidate, axis) one-vs-rest cell means, in 1e-6,
averaged over splits and both orders. Reply noise does not replicate across disjoint halves, so D2 estimates the
squared size of the systematic candidate-dependent difference between T and X (the quantity the test's t-grid
reads, before standardization). Statistic: D2(T, A) - D2(T, B). Null: A and B trade replies per slot, targets
fixed (300 draws, same splits). Targets: the consensus of the eight controls, each control, each synthetic arm,
and their family means. Six and five candidates.
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
rng = np.random.default_rng([20261113, 48])
NS, NNULL = 30, 300
SPL = []
for _ in range(NS):
    p = rng.permutation(16)
    SPL.append((np.sort(p[:8]), np.sort(p[8:])))
TG = Q.CONTROLS + Q.SD


def halves(Rx, kp):
    return np.stack([np.stack([Q.ovr(np.nanmean(Rx[kp][:, :, h], 2)).mean(1) for h in sp]) for sp in SPL])   # (NS, 2, nc, 101)


res = {}
for tag in ("six", "five"):
    kp, nc = Q.world(tag)
    H = {k: halves(R[k], kp) for k in TG}
    H["cons8"] = np.mean([H[k] for k in Q.CONTROLS], axis=0)
    names = TG + ["cons8"]

    def D2(Ht, Hx):
        a = Ht - Hx
        return 0.5e6 * (np.mean(a[:, 0] * a[:, 1]) + np.mean(a[:, 1] * a[:, 0]))

    def all_stats(HA, HB):
        dA = np.array([D2(H[k], HA) for k in names]); dB = np.array([D2(H[k], HB) for k in names])
        return dA, dB

    oA, oB = all_stats(halves(R["A"], kp), halves(R["B"], kp))
    nul = []
    for _ in range(NNULL):
        m = Q.swap_mask(rng, "reply", R["A"], R["B"])
        XA, XB = Q.swapped(R["A"], R["B"], m)
        a, b = all_stats(halves(XA, kp), halves(XB, kp))
        nul.append(a - b)
    nul = np.array(nul)
    og = oA - oB
    out = {}
    for q, k in enumerate(names):
        out[k] = {"D2_vs_A": round(float(oA[q]), 2), "D2_vs_B": round(float(oB[q]), 2), "diff": round(float(og[q]), 2),
                  "null_sd": round(float(nul[:, q].std()), 2), "z": round(float((og[q] - nul[:, q].mean()) / nul[:, q].std()), 2),
                  "p_two": float((1 + np.sum(np.abs(nul[:, q] - nul[:, q].mean()) >= abs(og[q] - nul[:, q].mean()))) / (1 + NNULL))}
    for fam, idx in (("mean_of_eight_controls", list(range(8))), ("mean_of_two_synthetic", [8, 9])):
        g = og[idx].mean(); n = nul[:, idx].mean(1)
        out[fam] = {"diff": round(float(g), 2), "null_sd": round(float(n.std()), 2), "z": round(float((g - n.mean()) / n.std()), 2),
                    "p_two": float((1 + np.sum(np.abs(n - n.mean()) >= abs(g - n.mean()))) / (1 + NNULL))}
    c = og[:8].mean() - og[8:10].mean(); cn = nul[:, :8].mean(1) - nul[:, 8:10].mean(1)
    out["eight_minus_synthetic"] = {"diff": round(float(c), 2), "null_sd": round(float(cn.std()), 2), "z": round(float((c - cn.mean()) / cn.std()), 2),
                                    "p_two": float((1 + np.sum(np.abs(cn - cn.mean()) >= abs(c - cn.mean()))) / (1 + NNULL))}
    res[tag] = out
    print("==", tag)
    for k, v in out.items():
        print(f"  {k:26s} {v}")
(Q.OUT / "f4b_replicating_distance.json").write_text(json.dumps(res, indent=1))
