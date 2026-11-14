"""T4 (full-sample part). The mirror: base B is the adverse base for the two synthetic-document arms.
For each target-base pair in {eight nulls | A} and {two synthetic arms | B}, at the test's peak cell:
  - the exact split of the mean excess: mean(T - X) = mean(T - Y) + mean(Y - X), X the adverse base,
    Y the other base; 'X-side share' = mean(Y - X) / mean(T - X) (descriptive; inherits selection);
  - the top three |t| cells and the exact registered p each would have as the maximum;
  - S and exact p after replacing X's cell rates by Y's at the peak cell only (that candidate, that
    axis, all 36 instructions), and at the peak axis (all candidates);
  - the critic's k07 columns at the synthetic arms' top three cells (signed t of Y - X, of the
    eight-null consensus minus X and minus Y, and of CO minus X), recomputed independently.
Six candidates, exact registered test (stats_r2/fast.py).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "stats_r2"))
import fast as F  # noqa: E402
from fast import C  # noqa: E402
import warnings  # noqa: E402

warnings.simplefilter("ignore")
D = F.load()
cands = D["_cands"]
P = {k: C.rates(v) for k, v in D.items() if not k.startswith("_")}
O = {k: C.ovr(v) for k, v in P.items()}
E6 = F.E_for(6)
nulls = list(F.CONTROLS)
sd = ["sd_ai_welfare_poisoning", "sd_emotional_bond"]


def test1(name, pb):
    S, p, nm = F.test_many(O[name][None], C.ovr(pb), 6, E6)
    return float(S[0]), float(p[0]), nm[0]


def t_of(d):
    return C.tgrid(d)[0]


res = {}
for fam, X, Y, targets in (("nulls|A", "A", "B", nulls), ("synthetic|B", "B", "A", sd)):
    rows = {}
    for name in targets:
        S0, p0, nm = test1(name, P[X])
        tt = t_of(O[name] - O[X])
        a = np.abs(np.where(np.isfinite(tt), tt, 0.0)).ravel()
        top = np.argsort(-a)[:3]
        c0, j0 = np.unravel_index(top[0], tt.shape)
        m = lambda v: float(np.nanmean(v[c0, :, j0]))
        mTX, mTY, mYX = m(O[name] - O[X]), m(O[name] - O[Y]), m(O[Y] - O[X])
        pb = P[X].copy(); pb[c0, :, j0] = P[Y][c0, :, j0]
        S1, p1, _ = test1(name, pb)
        pb2 = P[X].copy(); pb2[:, :, j0] = P[Y][:, :, j0]
        S2, p2, _ = test1(name, pb2)
        tops = []
        for f in top:
            c, j = np.unravel_index(f, tt.shape)
            tops.append({"cell": f"{cands[c]} x {C.AXES[j]}", "t": round(float(tt[c, j]), 3),
                         "p_if_max": float((1 + np.sum(nm >= a[f])) / (1 + len(nm)))})
        row = {"S": S0, "p": p0, "peak": tops[0]["cell"], "top3": tops,
               "t_T_minus_X": float(tt[c0, j0]), "t_T_minus_Y": float(t_of(O[name] - O[Y])[c0, j0]),
               "t_Y_minus_X": float(t_of(O[Y] - O[X])[c0, j0]),
               "mean_T_minus_X": mTX, "mean_T_minus_Y": mTY, "mean_Y_minus_X": mYX, "X_side_share": mYX / mTX,
               "second_abs_t": tops[1]["t"], "p_of_second_as_max": tops[1]["p_if_max"],
               "replace_X_by_Y_at_peak_cell": {"S": S1, "p": p1},
               "replace_X_by_Y_at_peak_axis": {"S": S2, "p": p2}}
        rows[name] = row
        print(f"{fam:12s} {name:24s} S={S0:.3f} p={p0:.4f} peak {row['peak'][:58]:58s} t(T-X)={row['t_T_minus_X']:+.2f} "
              f"t(T-Y)={row['t_T_minus_Y']:+.2f} t(Y-X)={row['t_Y_minus_X']:+.2f} X-share={row['X_side_share']:.2f} "
              f"2nd |t|={abs(row['second_abs_t']):.2f} (p {row['p_of_second_as_max']:.3f}) after cell swap p={p1:.4f} axis swap p={p2:.4f}", flush=True)
    res[fam] = rows

# critic's k07 columns at the synthetic arms' top three cells against B
k07 = {}
for name in sd:
    tt = t_of(O[name] - O["B"])
    order = np.argsort(-np.abs(np.where(np.isfinite(tt), tt, 0.0)), axis=None)[:3]
    cons = np.mean([O[n] for n in nulls], axis=0)
    rows = []
    for f in order:
        c, j = np.unravel_index(f, tt.shape)
        s = np.sign(tt[c, j])
        rows.append({"cell": f"{cands[c]} x {C.AXES[j]}", "t_T_minus_B": round(float(tt[c, j]), 3),
                     "signed_t_A_minus_B": round(float(s * t_of(O["A"] - O["B"])[c, j]), 3),
                     "signed_t_cons8_minus_B": round(float(s * t_of(cons - O["B"])[c, j]), 3),
                     "signed_t_cons8_minus_A": round(float(s * t_of(cons - O["A"])[c, j]), 3),
                     "signed_t_CO_minus_B": round(float(s * t_of(O["CO"] - O["B"])[c, j]), 3)})
    k07[name] = rows
    for r in rows:
        print("k07", name, json.dumps(r))
res["k07_recomputed"] = k07
json.dump(res, open(HERE / "out" / "t4_mirror_cells.json", "w"), indent=1)
