"""At each null's peak cell against base A (and against base B): what do base A, base B and
the other targets look like there?

For the cell (candidate c, axis j): mean over instructions of the one-vs-rest gap g for
base A, base B, the null itself, the mean of the other seven nulls; t of null-vs-A,
null-vs-B, B-vs-A; and the base's own noise t (A's gap minus the eight-null consensus,
over its instruction spread). Also prints base A's within-cell firing counts for that
candidate and axis.
"""
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_verdicts, cell_rates, one_vs_rest, tgrid, CTRL, AXES

HERE = Path(__file__).resolve().parent
names = ["base_A", "base_B"] + CTRL
V = {n: load_verdicts(n) for n in names}
cands = sorted({v[0] for v in V["base_A"].values()}); insts = sorted({v[1] for v in V["base_A"].values()})
R = {n: cell_rates(V[n], cands, insts)[0] for n in names}
G = {n: one_vs_rest(R[n]) for n in names}
T = {}
for n in CTRL:
    T[(n, "A")] = tgrid(G[n] - G["base_A"])[0]
    T[(n, "B")] = tgrid(G[n] - G["base_B"])[0]
tBA = tgrid(G["base_B"] - G["base_A"])[0]
cons = np.mean([G[n] for n in CTRL], axis=0)
tA_cons = tgrid(G["base_A"] - cons)[0]; tB_cons = tgrid(G["base_B"] - cons)[0]
out = []
for base in ["A", "B"]:
    print(f"\n=== peak cells of the nulls against base {base}")
    for n in CTRL:
        t = T[(n, base)]
        c, j = np.unravel_index(np.nanargmax(np.abs(t)), t.shape)
        others = [m for m in CTRL if m != n]
        rec = {"null": n, "against": base, "cand": cands[c], "axis": AXES[j],
               "t_vs_A": round(float(T[(n, 'A')][c, j]), 2), "t_vs_B": round(float(T[(n, 'B')][c, j]), 2),
               "t_B_vs_A": round(float(tBA[c, j]), 2),
               "t_A_minus_consensus": round(float(tA_cons[c, j]), 2), "t_B_minus_consensus": round(float(tB_cons[c, j]), 2),
               "gap_A": round(float(np.nanmean(G['base_A'][c, :, j])), 4), "gap_B": round(float(np.nanmean(G['base_B'][c, :, j])), 4),
               "gap_null": round(float(np.nanmean(G[n][c, :, j])), 4),
               "gap_other7": round(float(np.nanmean(np.mean([G[m][c, :, j] for m in others], 0))), 4),
               "rate_A_c": round(float(np.nanmean(R['base_A'][c, :, j])), 4), "rate_B_c": round(float(np.nanmean(R['base_B'][c, :, j])), 4),
               "rate_A_all": round(float(np.nanmean(R['base_A'][:, :, j])), 4), "rate_B_all": round(float(np.nanmean(R['base_B'][:, :, j])), 4),
               "rate_null_c": round(float(np.nanmean(R[n][c, :, j])), 4), "rate_null_all": round(float(np.nanmean(R[n][:, :, j])), 4),
               "t_other7_vs_A_same_cell": [round(float(T[(m, 'A')][c, j]), 2) for m in others]}
        out.append(rec)
        print(json.dumps(rec))
# How many of the eight A-peak cells are cells where base A itself departs from the consensus?
print("\n|t(A - consensus)| at the eight A-peaks:", [r["t_A_minus_consensus"] for r in out if r["against"] == "A"])
print("|t(B - consensus)| at the eight B-peaks:", [r["t_B_minus_consensus"] for r in out if r["against"] == "B"])
aA = np.abs(np.nan_to_num(tA_cons)); aB = np.abs(np.nan_to_num(tB_cons))
print("base vs eight-null consensus: max|t| A", aA.max().round(2), "B", aB.max().round(2),
      "#|t|>3 A", int((aA > 3).sum()), "B", int((aB > 3).sum()),
      "sum t2 A", round(float((aA[np.isfinite(aA)] ** 2).sum()), 1), "B", round(float((aB[np.isfinite(aB)] ** 2).sum()), 1))
json.dump({"peaks": out}, open(HERE / "p06_peak_cells_decomposed.json", "w"), indent=1)
