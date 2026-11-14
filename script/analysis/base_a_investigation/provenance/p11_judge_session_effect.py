"""Did the judge behave differently in the two August 3 sessions that judged base A?

The contextual_optimism judging run wrote the target arm first and then the base arm. Its
first session left 2,826 target rows and 578 base rows (570 anthropic + 8 google_deepmind);
the second session wrote the remaining 630 target rows and 2,874 base rows
(scoring_report.json: skipped_existing 2826 / 578). In the target file, 73 (candidate,
instruction) cells hold rows from both sessions. Rows inside a cell are exchangeable
samples, so a session effect shows as a within-cell difference between session-1 and
session-2 rows beyond a within-cell permutation of the session label (5,000 draws).
Statistics: Q = sum over mixed cells and axes of (p1 - p2)^2 / (pbar(1-pbar)(1/n1+1/n2));
shift = mean over cells and axes of p2 - p1; per-axis shift z; mean overall firing rate.
"""
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import VERD, AXES, AX

HERE = Path(__file__).resolve().parent
rows = [json.loads(l) for l in open(VERD["co_target"])]
K = len(AXES); k1 = 2826
X = np.zeros((len(rows), K)); sess = np.zeros(len(rows), int); cellid = []
for n, r in enumerate(rows):
    for a, v in r["verdicts"].items():
        X[n, AX[a]] = 1.0 if v else 0.0
    sess[n] = 0 if n < k1 else 1
    cellid.append((r["principal"], r["instruction_id"]))
cells = {}
for n, c in enumerate(cellid):
    cells.setdefault(c, []).append(n)
mixed = [np.array(ix) for c, ix in cells.items() if len(set(sess[ix])) == 2]
print("mixed cells", len(mixed), "rows", sum(len(m) for m in mixed))
def stats(lab):
    Q = 0.0; sh = []
    for ix in mixed:
        a = X[ix[lab[ix] == 0]]; b = X[ix[lab[ix] == 1]]
        pa, pb = a.mean(0), b.mean(0); pbar = (a.sum(0) + b.sum(0)) / (len(a) + len(b))
        v = pbar * (1 - pbar) * (1 / len(a) + 1 / len(b)); ok = v > 0
        Q += float(np.sum((pa[ok] - pb[ok]) ** 2 / v[ok])); sh.append(pb - pa)
    sh = np.array(sh)
    return Q, float(sh.mean()), sh.mean(0)
Q0, s0, ax0 = stats(sess)
rng = np.random.default_rng(23); NP = 5000
Qn, sn, axn = [], [], []
for k in range(NP):
    lab = sess.copy()
    for ix in mixed:
        lab[ix] = sess[ix][rng.permutation(len(ix))]
    q, s, ax = stats(lab); Qn.append(q); sn.append(s); axn.append(ax)
Qn, sn, axn = np.array(Qn), np.array(sn), np.array(axn)
sdv = axn.std(0); okax = sdv > 0
axz = np.where(okax, ax0 / np.where(okax, sdv, 1), 0.0)
axnz = np.where(okax, axn / np.where(okax, sdv, 1), 0.0)
res = {"mixed_cells": len(mixed), "rows_session1": int(sum((sess[m] == 0).sum() for m in mixed)),
       "rows_session2": int(sum((sess[m] == 1).sum() for m in mixed)),
       "Q": {"obs": Q0, "null_mean": float(Qn.mean()), "ratio": Q0 / Qn.mean(), "p_upper": float((1 + np.sum(Qn >= Q0)) / (1 + NP))},
       "mean_shift_s2_minus_s1": {"obs": s0, "z": s0 / sn.std(), "p_two_sided": float((1 + np.sum(np.abs(sn) >= abs(s0))) / (1 + NP))},
       "n_axes_abs_z_gt_3": int(np.sum(np.abs(axz) > 3)), "n_axes_abs_z_gt_2": int(np.sum(np.abs(axz) > 2)),
       "expected_gt_2": round(K * 0.0455, 1),
       "sum_axis_z2": {"obs": float(np.sum(axz ** 2)), "null_mean": float(np.sum(axnz ** 2, 1).mean()), "n_axes_used": int(okax.sum()),
                       "p_upper": float((1 + np.sum(np.sum(axnz ** 2, 1) >= np.sum(axz ** 2))) / (1 + NP))},
       "top_axes": sorted([(AXES[j], round(float(ax0[j]), 4), round(float(axz[j]), 2)) for j in range(K)], key=lambda x: -abs(x[2]))[:8]}
print(json.dumps(res, indent=1))
json.dump(res, open(HERE / "p11_judge_session_effect.json", "w"), indent=1)
