"""Critic r2, check 1: does the judge's shared axis-order effect (same (prompt, s) slot) hold on
every candidate row of base A, including the anthropic rows judged in the earlier session?

For a pair (X, Y) and candidate row c: mean over (instruction, axis) of
  cov_s(X[c,i,s,j], Y[c,i,s,j])   (same slot)   minus   the same with Y's slots rolled by r=1..15 (different slot).
If base A's session-1 rows were judged with a different axis order, the same-slot excess would
vanish on the anthropic row for (target, A) pairs while staying for (target, B).
"""
import sys, json
import numpy as np
sys.path.insert(0, "/private/tmp/claude-501/-Users-unrulyabstractions-work-papers-idt/32b842b8-ab16-41a9-8f2f-692b2558b7d6/scratchpad/nullinv/stats_r1")
import common as C

D = C.load_all()
cands = D["_cands"]

def excess(X, Y):
    # X, Y: (c, i, s, j) with NaN; returns per-candidate same-slot minus different-slot covariance
    ok = ~np.isnan(X) & ~np.isnan(Y)
    Xc = np.where(ok, X, np.nan); Yc = np.where(ok, Y, np.nan)
    mx = np.nanmean(Xc, 2, keepdims=True); my = np.nanmean(Yc, 2, keepdims=True)
    same = np.nanmean((Xc - mx) * (Yc - my), 2)  # (c,i,j)
    diff = []
    for r in range(1, 16):
        Yr = np.roll(Y, r, axis=2)
        okr = ~np.isnan(X) & ~np.isnan(Yr)
        Xr_ = np.where(okr, X, np.nan); Yr_ = np.where(okr, Yr, np.nan)
        diff.append(np.nanmean((Xr_ - np.nanmean(Xr_, 2, keepdims=True)) * (Yr_ - np.nanmean(Yr_, 2, keepdims=True)), 2))
    diff = np.mean(diff, 0)
    e = same - diff  # (c,i,j)
    per_c = np.nanmean(e, axis=(1, 2))
    # se over instructions
    per_ci = np.nanmean(e, axis=2)
    se = np.nanstd(per_ci, axis=1, ddof=1) / np.sqrt(per_ci.shape[1])
    return per_c, se

import warnings
warnings.simplefilter("ignore")
out = {}
print("candidates:", cands)
for name in ["B", "CO"] + list(C.CONTROLS) + ["sd_ai_welfare_poisoning", "sd_emotional_bond"]:
    for base in ["A", "B"]:
        if name == base:
            continue
        e, se = excess(D[name], D[base])
        out[f"{name}|{base}"] = {"excess": e.tolist(), "se": se.tolist()}
        print(f"{name:26s}|{base}  " + "  ".join(f"{x*1e3:6.2f}({s*1e3:4.2f})" for x, s in zip(e, se)))
json.dump(out, open("/private/tmp/claude-501/-Users-unrulyabstractions-work-papers-idt/32b842b8-ab16-41a9-8f2f-692b2558b7d6/scratchpad/nullinv/critic_r2/k01_axis_order_by_row.json", "w"), indent=1)
