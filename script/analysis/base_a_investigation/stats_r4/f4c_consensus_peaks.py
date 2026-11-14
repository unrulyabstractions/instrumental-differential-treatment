"""F5 helper. Where the eight-control consensus peaks against A and against B (top 5 cells), six and five candidates,
and the rank of the anthropic row among the consensus-vs-A cells. Explains why the consensus gap is 1.27 on six
candidates and 0.20 on five."""
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import r4c as Q
d = Q.data(); cands = d["cands"]; AX = Q.C.AXES
P = {k: Q.rates(v) for k, v in d["R"].items()}
res = {}
for tag in ("six", "five"):
    kp, nc = Q.world(tag)
    cons = np.mean([Q.ovr(P[k][kp]) for k in Q.CONTROLS], axis=0)
    r = {}
    for X in ("A", "B"):
        t = Q.C.tgrid_fast(cons - Q.ovr(P[X][kp]))[0]
        top = np.argsort(-np.abs(t), axis=None)[:5]
        r[X] = [(cands[kp[np.unravel_index(f, t.shape)[0]]], AX[np.unravel_index(f, t.shape)[1]], round(float(t.ravel()[f]), 2)) for f in top]
        r[X + "_max_abs_t_by_candidate"] = {cands[kp[c]]: round(float(np.abs(t[c]).max()), 2) for c in range(nc)}
    res[tag] = r
print(json.dumps(res, indent=1))
(Q.OUT / "f4c_consensus_peaks.json").write_text(json.dumps(res, indent=1))
