"""F1b. Each control against the mean of its seven siblings, no base involved (reproduces critic k17, k18a).

Registered test, exact (10,000 permutations, seed 20260726). Reference rates = mean of the other seven
controls' cell rates (one-vs-rest is linear, so this equals the mean of their one-vs-rest gaps).
Joint null of the eight-test summaries under the registered relabelling applied to all eight tests at once:
permutation r of the fixed sequence relabels every test's d; each permuted maximum is ranked in its own
test's null, and the eight resulting p are summarized (median, count below 0.10, Fisher).
Also: each base against the consensus of the eight; each control and synthetic arm against the pooled
base (A + B) / 2; the consensus of eight against A, B and the pooled base. Six and five candidates.
The reply-level shuffle null (pseudo-controls, 1,000 shuffles) comes from f_engine.py shuf.
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
cands = d["cands"]
AX = Q.C.AXES
P = {k: Q.rates(v) for k, v in R.items()}
res = {}
for tag in ("six", "five"):
    kp, nc = Q.world(tag)
    O = {k: Q.ovr(v[kp]) for k, v in P.items()}
    OT = np.stack([O[k] for k in Q.CONTROLS])
    sib = (OT.sum(0, keepdims=True) - OT) / 7.0
    S, p, NM = Q.test(OT, sib, nc)
    srt = np.sort(NM, axis=1)
    N = NM.shape[1]
    pperm = np.stack([(1 + N - np.searchsorted(srt[q], NM[q], side="left")) / (1 + N) for q in range(8)])
    med_obs, cnt_obs, fis_obs = float(np.median(p)), int((p < 0.10).sum()), float(-2 * np.log(p).sum())
    med_n, cnt_n, fis_n = np.median(pperm, 0), (pperm < 0.10).sum(0), -2 * np.log(pperm).sum(0)
    peaks = {}
    for q, k in enumerate(Q.CONTROLS):
        t = Q.C.tgrid_fast(OT[q] - sib[q])[0]
        f = np.unravel_index(np.nanargmax(np.abs(t)), t.shape)
        peaks[k] = {"cell": f"{cands[kp[f[0]]]} x {AX[f[1]]}", "t": round(float(t[f]), 3)}
    r = {"p_vs_siblings": dict(zip(Q.CONTROLS, np.round(p, 4).tolist())),
         "S_vs_siblings": dict(zip(Q.CONTROLS, np.round(S, 3).tolist())), "peak_vs_siblings": peaks,
         "median_p": med_obs, "count_below_0.10": cnt_obs, "fisher": fis_obs,
         "joint_registered_null": {"P_median_le_obs": Q.tail_le(med_n, med_obs), "median_of_null_median": float(np.median(med_n)),
                                   "P_count_ge_obs": Q.tail_ge(cnt_n, cnt_obs), "P_fisher_ge_obs": Q.tail_ge(fis_n, fis_obs),
                                   "mean_pairwise_corr_of_permuted_maxima": float((np.corrcoef(NM).sum() - 8) / 56)}}
    cons = OT.mean(0)
    mid = 0.5 * (O["A"] + O["B"])
    extra = {}
    for name, ot, ob in (("A | consensus of eight", O["A"], cons), ("B | consensus of eight", O["B"], cons),
                         ("consensus of eight | A", cons, O["A"]), ("consensus of eight | B", cons, O["B"]),
                         ("consensus of eight | pooled base", cons, mid)):
        s1, p1, _ = Q.test(ot[None], ob, nc)
        extra[name] = [round(float(s1[0]), 3), round(float(p1[0]), 4)]
    names = Q.TEN + (["CO"] if tag == "five" else [])
    s2, p2, _ = Q.test(np.stack([O[k] for k in names]), mid, nc)
    r["vs_pooled_base"] = {k: [round(float(a), 3), round(float(b), 4)] for k, a, b in zip(names, s2, p2)}
    r["vs_pooled_base_median_eight"] = float(np.median(p2[:8]))
    r["other"] = extra
    res[tag] = r
    print("==", tag)
    print(json.dumps(r, indent=1))
(Q.OUT / "f1b_siblings.json").write_text(json.dumps(res, indent=1))
