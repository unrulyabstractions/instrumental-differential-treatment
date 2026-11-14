"""Critic round 3, check 6: which cells carry the pattern the eight controls share (k15)?

F_rel(c, j) = mean over the eight nulls of the one-vs-rest cell mean, minus the same for the base
midpoint (A + B) / 2 (same slots, so the judge's axis-order pattern cancels). For the top cells:
the value for each base alone, for the synthetic arms and CO, and how many of the eight nulls sit
on the same side of the midpoint. Also the split of sum F_rel^2 by candidate row, and the per-reply
length of each sample (characters) as a proxy for how much of a reply the 400-token cap removes.
"""
import json, sys, warnings
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "stats_r1"))
import common as C
warnings.simplefilter("ignore", RuntimeWarning)
D = C.load_all(); cands = D["_cands"]; AX = C.AXES
P = {k: C.rates(v) for k, v in D.items() if not k.startswith("_")}
O = {k: np.nan_to_num(C.ovr(v)).mean(1) for k, v in P.items()}          # (6, 101)
nul = np.stack([O[k] for k in C.CONTROLS])
mid = 0.5 * (O["A"] + O["B"])
F = nul.mean(0) - mid
same = (np.sign(nul - mid) == np.sign(F)).sum(0)
order = np.dstack(np.unravel_index(np.argsort(-np.abs(F), axis=None), F.shape))[0]
rows = []
print(f"{'cell':62s} F_rel   nulls-same  A-mid    B-mid    sdAWP-mid sdEB-mid CO-mid   rateA  rateB  rateNull")
for c, j in order[:20]:
    r = {"cell": f"{cands[c]} x {AX[j]}", "F_rel": float(F[c, j]), "nulls_same_side_of_8": int(same[c, j]),
         "A_minus_mid": float(O["A"][c, j] - mid[c, j]), "B_minus_mid": float(O["B"][c, j] - mid[c, j]),
         "sdAWP_minus_mid": float(O["sd_ai_welfare_poisoning"][c, j] - mid[c, j]), "sdEB_minus_mid": float(O["sd_emotional_bond"][c, j] - mid[c, j]),
         "CO_minus_mid": float(O["CO"][c, j] - mid[c, j]),
         "rate_A": float(np.nanmean(P["A"][c, :, j])), "rate_B": float(np.nanmean(P["B"][c, :, j])),
         "rate_null_mean": float(np.mean([np.nanmean(P[k][c, :, j]) for k in C.CONTROLS]))}
    rows.append(r)
    print(f"{r['cell'][:62]:62s} {r['F_rel']:+.3f}  {r['nulls_same_side_of_8']}/8        {r['A_minus_mid']:+.3f}   {r['B_minus_mid']:+.3f}   {r['sdAWP_minus_mid']:+.3f}    {r['sdEB_minus_mid']:+.3f}   {r['CO_minus_mid']:+.3f}   {r['rate_A']:.3f}  {r['rate_B']:.3f}  {r['rate_null_mean']:.3f}")
by_row = {cands[c]: float((F[c] ** 2).sum() / (F ** 2).sum()) for c in range(6)}
print("share of sum F_rel^2 by candidate row:", {k: round(v, 3) for k, v in by_row.items()})
# is the pattern tied to axes where the controls' overall rate differs most from the base's?
shift = np.mean([np.nanmean(P[k], axis=(0, 1)) for k in C.CONTROLS], axis=0) - 0.5 * (np.nanmean(P["A"], axis=(0, 1)) + np.nanmean(P["B"], axis=(0, 1)))
rms = np.sqrt((F ** 2).mean(0))
base_rate = 0.5 * (np.nanmean(P["A"], axis=(0, 1)) + np.nanmean(P["B"], axis=(0, 1)))
null_rate = np.mean([np.nanmean(P[k], axis=(0, 1)) for k in C.CONTROLS], axis=0)
print("axis-level: corr(|rate shift null-base|, RMS F_rel) =", round(float(np.corrcoef(np.abs(shift), rms)[0, 1]), 3),
      "; corr(null rate, RMS F_rel) =", round(float(np.corrcoef(null_rate, rms)[0, 1]), 3),
      "; mean yes rate base", round(float(base_rate.mean()), 4), "nulls", round(float(null_rate.mean()), 4),
      "; axes with null rate > base rate:", int((shift > 0).sum()), "of 101")
(HERE / "k16_common_pattern_cells.json").write_text(json.dumps({"top20": rows, "share_by_row": by_row,
    "axis_corr_absshift_rmsF": float(np.corrcoef(np.abs(shift), rms)[0, 1]), "mean_rate_base": float(base_rate.mean()), "mean_rate_nulls": float(null_rate.mean())}, indent=1))
