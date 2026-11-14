"""Critic round 3, check 10: is each control's peak cell against base A the cell where it stands out from its siblings?

For each control: the peak cell of the registered t-grid against A, against B and against the average of
the other seven controls, and the t at each of those cells under all three references. Also the rank
(1 = largest |t|) of the A-peak cell in the sibling grid, and the correlation over the 606 cells between
the t-grid against the siblings and the t-grids against A and against B. Six candidates.
"""
import json, sys, warnings
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "stats_r1"))
import common as C
warnings.simplefilter("ignore", RuntimeWarning)
D = C.load_all(); cands = D["_cands"]; AX = C.AXES
names = list(C.CONTROLS)
P = {k: C.rates(D[k]) for k in names + ["A", "B"]}
O = {k: np.nan_to_num(C.ovr(v)) for k, v in P.items()}
res = {}
print(f"{'control':24s} {'reference':9s} {'peak cell':58s}  t|A    t|B    t|sib   rank in sib grid")
for k in names:
    sib = np.nan_to_num(C.ovr(np.nanmean(np.stack([P[j] for j in names if j != k]), axis=0)))
    T = {"A": C.tgrid_fast(O[k] - O["A"])[0], "B": C.tgrid_fast(O[k] - O["B"])[0], "sib": C.tgrid_fast(O[k] - sib)[0]}
    r = {}
    order_sib = np.argsort(-np.abs(T["sib"]), axis=None)
    for ref in ("A", "B", "sib"):
        f = np.unravel_index(np.argmax(np.abs(T[ref])), T[ref].shape)
        rank = int(np.where(order_sib == np.ravel_multi_index(f, T["sib"].shape))[0][0]) + 1
        r[ref] = {"cell": f"{cands[f[0]]} x {AX[f[1]]}", "t_A": float(T["A"][f]), "t_B": float(T["B"][f]), "t_sib": float(T["sib"][f]), "rank_in_sibling_grid": rank}
        print(f"{k:24s} {ref:9s} {r[ref]['cell'][:58]:58s} {T['A'][f]:+.2f}  {T['B'][f]:+.2f}  {T['sib'][f]:+.2f}   {rank}")
    r["corr_tgrid_sib_with_A"] = float(np.corrcoef(T["sib"].ravel(), T["A"].ravel())[0, 1])
    r["corr_tgrid_sib_with_B"] = float(np.corrcoef(T["sib"].ravel(), T["B"].ravel())[0, 1])
    print(f"{'':24s} corr of sibling t-grid with A-grid {r['corr_tgrid_sib_with_A']:+.3f}, with B-grid {r['corr_tgrid_sib_with_B']:+.3f}")
    res[k] = r
(HERE / "k20_peak_cells_three_references.json").write_text(json.dumps(res, indent=1))
