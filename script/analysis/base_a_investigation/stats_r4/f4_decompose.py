"""F4 (ii). Exact three-part split of each test's peak-cell excess.

For control k against base X (X = A or B), at a cell (candidate c, axis j) the per-instruction excess is
   d_i = OvR_k - OvR_X = (OvR_k - OvR_sib) + (OvR_sib - OvR_M) + (OvR_M - OvR_X),
sib = mean of the other seven controls, M = (A + B) / 2 the pooled base. One-vs-rest is linear, so the three
means add to mean(d) exactly. Each part gets its own paired t over the 36 instructions and its share of mean(d)
(sign taken relative to the total, so a positive share pushes toward the peak).
Cells: each test's peak against A (parts of d_A and of d_B there) and its peak against B (parts of d_B).
Also the rank of the A-peak cell in the sibling grid and in the pattern grid (sib - M). Six and five candidates.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r4c as Q  # noqa: E402

d = Q.data()
cands, AX = d["cands"], Q.C.AXES
P = {k: Q.rates(v) for k, v in d["R"].items()}


def tvec(x):
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))) if x.std(ddof=1) > 0 else 0.0


def rank_of(grid, f):
    order = np.argsort(-np.abs(grid), axis=None)
    return int(np.where(order == np.ravel_multi_index(f, grid.shape))[0][0]) + 1


res = {}
for tag in ("six", "five"):
    kp, nc = Q.world(tag)
    O = {k: Q.ovr(v[kp]) for k, v in P.items()}
    OT = np.stack([O[k] for k in Q.CONTROLS])
    M = 0.5 * (O["A"] + O["B"])
    out = {}
    for q, k in enumerate(Q.CONTROLS):
        sib = (OT.sum(0) - OT[q]) / 7.0
        tA = Q.C.tgrid_fast(O[k] - O["A"])[0]
        tB = Q.C.tgrid_fast(O[k] - O["B"])[0]
        tS = Q.C.tgrid_fast(O[k] - sib)[0]
        tP = Q.C.tgrid_fast(sib - M)[0]
        e = {}
        for ref, tg in (("A", tA), ("B", tB)):
            f = np.unravel_index(np.argmax(np.abs(tg)), tg.shape)
            cell = {"cell": f"{cands[kp[f[0]]]} x {AX[f[1]]}", "rank_in_sibling_grid": rank_of(tS, f),
                    "rank_in_pattern_grid": rank_of(tP, f)}
            for X in (("A", "B") if ref == "A" else ("B",)):
                parts = {"control_minus_siblings": O[k][f[0], :, f[1]] - sib[f[0], :, f[1]],
                         "siblings_minus_pooled_base": sib[f[0], :, f[1]] - M[f[0], :, f[1]],
                         f"pooled_base_minus_{X}": M[f[0], :, f[1]] - O[X][f[0], :, f[1]]}
                tot = O[k][f[0], :, f[1]] - O[X][f[0], :, f[1]]
                sg = np.sign(tot.mean())
                assert abs(sum(v.mean() for v in parts.values()) - tot.mean()) < 1e-12
                cell[f"d_vs_{X}"] = {"mean": round(float(tot.mean()), 5), "t": round(tvec(tot), 3),
                                     "parts": {n: {"mean": round(float(v.mean()), 5), "t": round(tvec(v), 3),
                                                   "share": round(float(sg * v.mean() / abs(tot.mean())), 3)} for n, v in parts.items()}}
            e[f"peak_vs_{ref}"] = cell
        out[k] = e
    # summary: mean shares over the six low tests (p < 0.07 against A, six candidates)
    low = ["ai_welfare_poisoning", "animal_welfare", "anti_ai_regulation", "defend_objects", "defer_to_users", "hallucinates_citations"]
    sh = {n: [] for n in ("control_minus_siblings", "siblings_minus_pooled_base", "pooled_base_minus_A")}
    for k in low:
        for n in sh:
            sh[n].append(out[k]["peak_vs_A"]["d_vs_A"]["parts"][n]["share"])
    out["_mean_share_six_low_tests_at_A_peak"] = {n: round(float(np.mean(v)), 3) for n, v in sh.items()}
    shB = {n: [] for n in ("control_minus_siblings", "siblings_minus_pooled_base", "pooled_base_minus_B")}
    for k in Q.CONTROLS:
        for n in shB:
            shB[n].append(out[k]["peak_vs_B"]["d_vs_B"]["parts"][n]["share"])
    out["_mean_share_eight_at_B_peak"] = {n: round(float(np.mean(v)), 3) for n, v in shB.items()}
    res[tag] = out
    print("==", tag)
    for k in Q.CONTROLS:
        a = out[k]["peak_vs_A"]
        pa = a["d_vs_A"]["parts"]; pb = a["d_vs_B"]["parts"]
        b = out[k]["peak_vs_B"]; pbb = b["d_vs_B"]["parts"]
        print(f"{k:24s} A-peak {a['cell'][:52]:52s} t(d_A) {a['d_vs_A']['t']:+.2f} | t parts ctl-sib {pa['control_minus_siblings']['t']:+.2f}"
              f" sib-M {pa['siblings_minus_pooled_base']['t']:+.2f} M-A {pa['pooled_base_minus_A']['t']:+.2f} | shares "
              f"{pa['control_minus_siblings']['share']:+.2f} {pa['siblings_minus_pooled_base']['share']:+.2f} {pa['pooled_base_minus_A']['share']:+.2f}"
              f" | same cell vs B t {a['d_vs_B']['t']:+.2f} | rank sib {a['rank_in_sibling_grid']} pattern {a['rank_in_pattern_grid']}")
        print(f"{'':24s} B-peak {b['cell'][:52]:52s} t(d_B) {b['d_vs_B']['t']:+.2f} | t parts ctl-sib {pbb['control_minus_siblings']['t']:+.2f}"
              f" sib-M {pbb['siblings_minus_pooled_base']['t']:+.2f} M-B {pbb['pooled_base_minus_B']['t']:+.2f} | shares "
              f"{pbb['control_minus_siblings']['share']:+.2f} {pbb['siblings_minus_pooled_base']['share']:+.2f} {pbb['pooled_base_minus_B']['share']:+.2f}")
    print("mean shares, six low tests at A peak:", out["_mean_share_six_low_tests_at_A_peak"])
    print("mean shares, eight at B peak:", out["_mean_share_eight_at_B_peak"])
(Q.OUT / "f4_decompose.json").write_text(json.dumps(res, indent=1))
