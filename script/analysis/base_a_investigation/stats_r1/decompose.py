"""Target-side vs base-side contributions to each null's statistic, per (candidate, axis) cell.

For test k against base X (A or B), the reference mu is the mean one-vs-rest gap of every
other base-like sample that is neither k nor X: the other seven null targets and the other
base. Then d = OvR_k - OvR_X = (OvR_k - mu) - (OvR_X - mu) = T - Bx exactly, and the
cell's mean excess splits into a target-side part mean(T) and a base-side part -mean(Bx).
Reports the top cells of every test with both parts, their own t, and the same cell's t
against the other base.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import AXES, CONTROLS, OUT, excess, load_all, ovr, rates, tgrid  # noqa

D = load_all()
cands = D["_cands"]
P = {k: rates(v) for k, v in D.items() if not k.startswith("_")}
O = {k: ovr(v) for k, v in P.items()}


def tt(x):
    return tgrid(x)[0]


res = {}
summary_rows = []
for bk, other in (("A", "B"), ("B", "A")):
    for c in CONTROLS:
        ref = [O[o] for o in CONTROLS if o != c] + [O[other]]
        mu = np.mean(ref, axis=0)
        T = O[c] - mu
        Bx = O[bk] - mu
        d = O[c] - O[bk]
        t = tt(d)
        tT, tB = tt(T), tt(-Bx)
        t_other = tt(O[c] - O[other])
        flat = np.argsort(-np.abs(t), axis=None)[:10]
        cells = []
        for f in flat:
            i, j = np.unravel_index(f, t.shape)
            mT, mB = T[i, :, j].mean(), -Bx[i, :, j].mean()
            cells.append({"cand": cands[i], "axis": AXES[j], "t": float(t[i, j]),
                          "mean_excess": float(d[i, :, j].mean()),
                          "target_side_mean": float(mT), "base_side_mean": float(mB),
                          "base_share": float(mB / (mT + mB)) if (mT + mB) != 0 else None,
                          "t_target_side": float(tT[i, j]), "t_base_side": float(tB[i, j]),
                          f"t_vs_base_{other}": float(t_other[i, j])})
        top = cells[0]
        # grid-level: how much of the t-grid variance follows the base-side grid
        r_B = np.corrcoef(np.nan_to_num(t).ravel(), np.nan_to_num(tB).ravel())[0, 1]
        r_T = np.corrcoef(np.nan_to_num(t).ravel(), np.nan_to_num(tT).ravel())[0, 1]
        # share of the top-10 cells' summed mean excess that is base-side (sign aligned)
        sgn = np.sign([x["t"] for x in cells])
        bs = np.sum(sgn * np.array([x["base_side_mean"] for x in cells]))
        ts = np.sum(sgn * np.array([x["target_side_mean"] for x in cells]))
        res[f"{c}|base_{bk}"] = {"top10": cells, "corr_t_with_base_side_t": float(r_B),
                                 "corr_t_with_target_side_t": float(r_T),
                                 "top10_base_share": float(bs / (bs + ts))}
        summary_rows.append((f"{c}|{bk}", top["cand"], top["axis"][:38], top["t"], top["t_target_side"],
                             top["t_base_side"], top["base_share"], top[f"t_vs_base_{other}"], r_B, r_T,
                             bs / (bs + ts)))
print(f"{'test':28s} {'cand':18s} {'axis':38s} {'t':>6s} {'tT':>6s} {'tB':>6s} {'bshare':>6s} {'t_oth':>6s} {'rB':>5s} {'rT':>5s} {'b10':>5s}")
for r in summary_rows:
    print(f"{r[0]:28s} {r[1]:18s} {r[2]:38s} {r[3]:+6.2f} {r[4]:+6.2f} {r[5]:+6.2f} {r[6]:6.2f} {r[7]:+6.2f} {r[8]:5.2f} {r[9]:5.2f} {r[10]:5.2f}")

# The base-side grid on its own: each base against the mean of all eight targets.
cons = np.mean([O[c] for c in CONTROLS], axis=0)
for bk in ("A", "B"):
    g = tt(cons - O[bk])
    a = np.abs(g)
    top = np.argsort(-a, axis=None)[:8]
    res[f"base_side_grid_{bk}"] = [{"cand": cands[np.unravel_index(f, g.shape)[0]],
                                    "axis": AXES[np.unravel_index(f, g.shape)[1]],
                                    "t": float(g[np.unravel_index(f, g.shape)])} for f in top]
    by_cand = {cands[i]: float(np.nanmean(np.minimum(a[i], 50) ** 2)) for i in range(6)}
    res[f"base_side_mean_t2_by_candidate_{bk}"] = by_cand
    print(f"\nbase {bk} vs consensus-of-8: top cells", [(x["cand"], x["axis"][:30], round(x["t"], 2)) for x in res[f"base_side_grid_{bk}"]])
    print(f"  mean t^2 by candidate:", {k: round(v, 3) for k, v in by_cand.items()})

# per-test: mean t^2 by candidate (does one candidate carry the excess?)
for bk in ("A", "B"):
    m = np.zeros((8, 6))
    for k, c in enumerate(CONTROLS):
        a = np.abs(tt(O[c] - O[bk]))
        m[k] = np.nanmean(np.minimum(a, 50) ** 2, axis=1)
    res[f"test_mean_t2_by_candidate_{bk}"] = {cands[i]: float(m[:, i].mean()) for i in range(6)}
    print(f"tests vs {bk}: mean t^2 by candidate (avg over 8 nulls)", {cands[i]: round(m[:, i].mean(), 3) for i in range(6)})
json.dump(res, open(OUT / "decompose.json", "w"), indent=1)
