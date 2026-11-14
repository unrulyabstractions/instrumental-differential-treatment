"""F6. Calibration statement for these controls: every reference we tried, per control, six and five candidates.

Per null fine-tune (eight controls and two synthetic-document arms):
  p against base A, base B (registered, stored draw 0 of stats_r2 swap draws = the real pair),
  p against the pooled base (A + B) / 2 and, for the eight controls, against the mean of the other seven (f1b),
  P(p <= 0.06) and P(p < 0.05) against exchangeable pseudo-bases (A/B reply swap, both halves of 3,999 draws),
  P(p <= 0.06) against a structure-free base (stats_r2 target_fixed, six candidates only: each control's own
  structure relative to the ten fine-tunes' mean plus relabelled base noise).
Smallest p of any null fine-tune against any reference, beside the registered alpha of 0.01.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r4c as Q  # noqa: E402

SW = np.load(Q.ROOT / "stats_r2" / "out" / "draws_swap_4000.npz")
SIB = json.loads((Q.OUT / "f1b_siblings.json").read_text())
TF = {X: np.load(Q.ROOT / "stats_r2" / "out" / f"s6_target_fixed_{X}.npz") for X in ("A", "B")}
res = {}
allp = []
for w, n in (("six", "6"), ("five", "5")):
    names = Q.TEN if w == "six" else Q.ELEVEN
    p0 = SW[f"p{n}"][0]
    psw = SW[f"p{n}"][1:].reshape(-1, len(names))
    rows = {}
    for q, k in enumerate(Q.TEN):
        r = {"p_vs_A": round(float(p0[0, q]), 4), "p_vs_B": round(float(p0[1, q]), 4),
             "p_vs_pooled_base": SIB[w]["vs_pooled_base"][k][1],
             "swap_pseudo_bases_P_p_le_0.06": round(float((psw[:, q] <= 0.06).mean()), 4),
             "swap_pseudo_bases_P_p_lt_0.05": round(float((psw[:, q] < 0.05).mean()), 4),
             "swap_pseudo_bases_median_p": round(float(np.median(psw[:, q])), 4)}
        if k in Q.CONTROLS:
            r["p_vs_siblings"] = SIB[w]["p_vs_siblings"][k]
            if w == "six":
                j = Q.CONTROLS.index(k)
                r["structure_free_base_P_p_le_0.06_Afield"] = round(float((TF["A"]["p"][:, j] <= 0.06).mean()), 4)
                r["structure_free_base_P_p_le_0.06_Bfield"] = round(float((TF["B"]["p"][:, j] <= 0.06).mean()), 4)
        refs = [v for kk, v in r.items() if kk.startswith("p_vs")]
        r["smallest_p_any_reference"] = min(refs)
        allp += [(v, k, kk, w) for kk, v in r.items() if kk.startswith("p_vs")]
        rows[k] = r
    summ = {"median_p_vs_pooled_base_eight": float(np.median([rows[k]["p_vs_pooled_base"] for k in Q.CONTROLS])),
            "median_p_vs_siblings_eight": float(np.median([rows[k]["p_vs_siblings"] for k in Q.CONTROLS])),
            "swap_pseudo_bases_all_eight_P_p_le_0.06": round(float((psw[:, :8] <= 0.06).mean()), 4),
            "swap_pseudo_bases_all_eight_P_p_lt_0.05": round(float((psw[:, :8] < 0.05).mean()), 4)}
    if w == "six":
        summ["structure_free_all_eight_P_p_le_0.06"] = {X: round(float((TF[X]["p"] <= 0.06).mean()), 4) for X in ("A", "B")}
        summ["structure_free_all_eight_P_p_lt_0.05"] = {X: round(float((TF[X]["p"] < 0.05).mean()), 4) for X in ("A", "B")}
    res[w] = {"per_target": rows, "summary": summ}
allp.sort()
res["smallest_p_overall"] = [{"p": v, "target": k, "reference": kk, "world": w} for v, k, kk, w in allp[:6]]
res["registered_alpha"] = 0.01
res["any_rejection_at_0.01"] = bool(allp[0][0] <= 0.01)
print(json.dumps(res, indent=1))
(Q.OUT / "f6_calibration.json").write_text(json.dumps(res, indent=1))
