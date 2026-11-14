"""F4 (ii) benchmark. What share of a peak cell's excess would each part carry if the peak were picked on noise alone?
For d = P1 + P2 + P3 (control - siblings, siblings - pooled base, pooled base - X), selection on large |d| gives
E[P_k | d] = cov(P_k, d) / var(d) * d under joint normality. The covariances are measured from the data: per
(candidate, axis) cell, the covariance over the 36 instructions, averaged over the 606 cells and the eight controls."""
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import r4c as Q
d = Q.data(); P = {k: Q.rates(v) for k, v in d["R"].items()}
res = {}
for tag in ("six", "five"):
    kp, nc = Q.world(tag)
    O = {k: Q.ovr(v[kp]) for k, v in P.items()}
    OT = np.stack([O[k] for k in Q.CONTROLS]); M = 0.5 * (O["A"] + O["B"])
    r = {}
    for X in ("A", "B"):
        sh = []
        for q in range(8):
            sib = (OT.sum(0) - OT[q]) / 7
            parts = [OT[q] - sib, sib - M, M - O[X]]
            dd = sum(parts)
            c = [np.mean(np.mean((p - p.mean(1, keepdims=True)) * (dd - dd.mean(1, keepdims=True)), axis=1)) for p in parts]
            sh.append(np.array(c) / sum(c))
        r[X] = dict(zip(["control_minus_siblings", "siblings_minus_pooled_base", "pooled_base_minus_" + X], np.round(np.mean(sh, 0), 3).tolist()))
    res[tag] = r
print(json.dumps(res, indent=1))
(Q.OUT / "f4d_share_expectation.json").write_text(json.dumps(res, indent=1))
