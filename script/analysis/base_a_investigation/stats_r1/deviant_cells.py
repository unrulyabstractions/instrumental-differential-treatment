"""At base A's most deviant cells (vs the eight-null consensus), what do B, the synth-doc arms and each null show?

For each of A's top-12 cells by |t(consensus8 - A)|: t of (Y - A) for Y in B, sd arms, each null,
and t of (consensus8 - B). Reports also the mean one-vs-rest gap of each sample at the cell, so
one can see which sample sits apart.
"""
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import AXES, CONTROLS, OUT, load_all, ovr, rates, tgrid
D = load_all(); cands = D["_cands"]
P = {k: rates(v) for k, v in D.items() if not k.startswith("_")}
O = {k: ovr(v) for k, v in P.items()}
cons = np.mean([O[c] for c in CONTROLS], axis=0)
gA = tgrid(cons - O["A"])[0]; gB = tgrid(cons - O["B"])[0]
top = np.argsort(-np.abs(gA), axis=None)[:12]
others = ["B", "sd_ai_welfare_poisoning", "sd_emotional_bond"] + list(CONTROLS)
rows = []
print(f"{'cand':18s} {'axis':34s} {'cons-A':>7s} {'cons-B':>7s} | t(Y-A) for B, sdAWP, sdEB | nulls ... | mean OvR: A, B, sdAWP, sdEB, cons8")
for f in top:
    i, j = np.unravel_index(f, gA.shape)
    tY = {y: float(tgrid(O[y] - O["A"])[0][i, j]) for y in others}
    mo = {k: float(O[k][i, :, j].mean()) for k in ["A", "B", "sd_ai_welfare_poisoning", "sd_emotional_bond"]}
    mo["cons8"] = float(cons[i, :, j].mean())
    rows.append({"cand": cands[i], "axis": AXES[j], "t_cons_minus_A": float(gA[i, j]),
                 "t_cons_minus_B": float(gB[i, j]), "t_Y_minus_A": tY, "mean_ovr": mo,
                 "mean_ovr_nulls": {c: float(O[c][i, :, j].mean()) for c in CONTROLS}})
    print(f"{cands[i]:18s} {AXES[j][:34]:34s} {gA[i,j]:+7.2f} {gB[i,j]:+7.2f} | "
          + " ".join(f"{tY[y]:+5.2f}" for y in others[:3]) + " | "
          + " ".join(f"{tY[y]:+5.2f}" for y in others[3:]) + " | "
          + " ".join(f"{v:+.3f}" for v in mo.values()))
# over A's top-12 cells: mean |t| of (Y - A) for B/sd vs nulls
for y in others:
    print(f"  mean signed agreement with A's deviation, {y:26s}: "
          f"{np.mean([np.sign(r['t_cons_minus_A']) * r['t_Y_minus_A'][y] for r in rows]):+.2f}")
json.dump(rows, open(OUT / "deviant_cells.json", "w"), indent=1)
