"""T4b. Is the adverse base the odd sample at its targets' peak cells, and is it as odd as base A was?

For each target-base pair (eight nulls | A, two synthetic arms | B) at the test's full-sample peak cell:
  t of (adverse base minus the mean of the eleven other samples) and minus the eight-null consensus
  (excluding the target), and the rank of that |t| among the adverse base's 606 cells.
'Other samples' = the other base, contextual_optimism, the eight nulls and the two synthetic arms,
minus the target itself. Six candidates. Descriptive: the peak was chosen with this base.
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
O = {k: C.ovr(C.rates(v)) for k, v in D.items() if not k.startswith("_")}
ALL = ["A", "B", "CO"] + list(F.CONTROLS) + F.SD


def tg(d):
    t = C.tgrid(d)[0]
    return np.where(np.isfinite(t), t, 0.0)


out = {}
for fam, X, targets in (("nulls|A", "A", list(F.CONTROLS)), ("synthetic|B", "B", F.SD)):
    for name in targets:
        tt = tg(O[name] - O[X])
        c, j = np.unravel_index(np.argmax(np.abs(tt)), tt.shape)
        s = np.sign(tt[c, j])
        others = [k for k in ALL if k not in (X, name)]
        ref11 = np.mean([O[k] for k in others], axis=0)
        cons = np.mean([O[k] for k in F.CONTROLS if k != name], axis=0)
        g11 = tg(O[X] - ref11)
        g8 = tg(O[X] - cons)
        rank = int((np.abs(g11) > abs(g11[c, j])).sum()) + 1
        out[f"{name}|{X}"] = {"cell": f"{cands[c]} x {C.AXES[j]}", "t_target_minus_base": float(tt[c, j]),
                              "signed_t_others11_minus_base": float(-s * g11[c, j]), "signed_t_cons8_minus_base": float(-s * g8[c, j]),
                              "rank_of_base_departure_among_606": rank}
        print(f"{fam:12s} {name:24s} {out[f'{name}|{X}']['cell'][:60]:60s} t(T-X) {tt[c, j]:+.2f}  "
              f"signed t(others11 - X) {-s * g11[c, j]:+.2f} (rank {rank}/606)  signed t(cons8 - X) {-s * g8[c, j]:+.2f}")
json.dump(out, open(HERE / "out" / "t4b_odd_base_at_peaks.json", "w"), indent=1)
