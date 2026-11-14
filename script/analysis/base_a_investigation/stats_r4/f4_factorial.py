"""F4 (iii) and F1 (k19, k21 at 1,000 shuffles). Target side x base side factorial for the eight-test median.

Target side
  real     the eight controls as observed
  pseudo   per-slot shuffle of the eight controls' replies among the labels (shared pattern kept, own structure gone)
  tboot    each control's replies resampled within cell (its realized structure treated as truth, fresh noise)
Base side
  A, B     the real bases
  swap     a pseudo-base from an A/B reply swap (A's particular draw removed; exchangeable bases)
Cells: median over draws of the eight-test median, P(eight-test median <= 0.0557), share of p < 0.05, mean S.
Sibling calibration (k19): pseudo-control against the mean of the other seven pseudo-controls.
Inputs: out/draws_shuf_1000.npz, out/draws_tboot_500.npz, stats_r2/out/draws_swap_4000.npz.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r4c as Q  # noqa: E402

SH = np.load(Q.OUT / "draws_shuf_1000.npz")
TB = np.load(Q.OUT / "draws_tboot_500.npz") if (Q.OUT / "draws_tboot_500.npz").exists() else None
SW = np.load(Q.ROOT / "stats_r2" / "out" / "draws_swap_4000.npz")
SIB = json.loads((Q.OUT / "f1b_siblings.json").read_text())
OBSMED = {"six": {"A": 0.0557, "B": 0.4146}, "five": {"A": 0.0782, "B": 0.4553}}


def cell(p, S=None, thr=0.0557):
    med = np.median(p, axis=1)
    r = {"n": int(len(p)), "median_of_median": round(float(np.median(med)), 4), "q05_q95": np.quantile(med, [.05, .95]).round(4).tolist(),
         "P_median_le_thr": Q.tail_le(med, thr), "share_p_lt_0.05": round(float((p < 0.05).mean()), 4),
         "share_p_le_0.06": round(float((p <= 0.06).mean()), 4)}
    if S is not None:
        r["mean_S"] = round(float(S.mean()), 3)
    return r


res = {}
for w, n in (("six", "6"), ("five", "5")):
    thr = OBSMED[w]["A"]
    pA_real, pB_real = SW[f"p{n}"][0, 0, :8], SW[f"p{n}"][0, 1, :8]
    sw = SW[f"p{n}"][1:, :, :8].reshape(-1, 8)                         # both halves of every swap draw
    swS = SW[f"S{n}"][1:, :, :8].reshape(-1, 8)
    f = {"threshold_median": thr,
         "real|A": {"median": float(np.median(pA_real)), "share_p_lt_0.05": float((pA_real < 0.05).mean())},
         "real|B": {"median": float(np.median(pB_real)), "share_p_lt_0.05": float((pB_real < 0.05).mean())},
         "real|swap": cell(sw, swS, thr),
         "pseudo|A": cell(SH[f"p_{w}_A"], SH[f"S_{w}_A"], thr), "pseudo|B": cell(SH[f"p_{w}_B"], SH[f"S_{w}_B"], thr),
         "pseudo|swap": cell(np.concatenate([SH[f"p_{w}_A2"], SH[f"p_{w}_B2"]]), np.concatenate([SH[f"S_{w}_A2"], SH[f"S_{w}_B2"]]), thr)}
    if TB is not None:
        f["tboot|A"] = cell(TB[f"p_{w}_A"], TB[f"S_{w}_A"], thr)
        f["tboot|B"] = cell(TB[f"p_{w}_B"], TB[f"S_{w}_B"], thr)
        f["tboot|sib"] = cell(TB[f"p_{w}_sib"], TB[f"S_{w}_sib"], SIB[w]["median_p"])
    # pseudo-control mean S gap, real A minus real B (k21)
    g = (SH[f"S_{w}_A"] - SH[f"S_{w}_B"]).mean(1)
    gobs = float((SW[f"S{n}"][0, 0, :8] - SW[f"S{n}"][0, 1, :8]).mean())
    f["pseudo_gap_A_minus_B"] = {"mean": round(float(g.mean()), 4), "sd_over_shuffles": round(float(g.std()), 4), "real_controls_gap": round(gobs, 4),
                                 "P_pseudo_gap_ge_real": Q.tail_ge(g, gobs)}
    # sibling calibration (k19)
    ps = SH[f"p_{w}_sib"]
    meds = np.median(ps, 1)
    so = SIB[w]
    f["sibling_calibration"] = {"n_shuffles": int(len(ps)), "share_p_lt_0.05": round(float((ps < 0.05).mean()), 4),
                                "share_p_lt_0.10": round(float((ps < 0.10).mean()), 4), "median_of_all_p": round(float(np.median(ps)), 4),
                                "median_of_eight_test_median": round(float(np.median(meds)), 4), "q05_q95": np.quantile(meds, [.05, .95]).round(4).tolist(),
                                "observed_median": so["median_p"], "P_median_le_observed": Q.tail_le(meds, so["median_p"]),
                                "observed_count_below_0.10": so["count_below_0.10"],
                                "P_count_ge_observed": Q.tail_ge((ps < 0.10).sum(1), so["count_below_0.10"]),
                                "observed_fisher": so["fisher"], "P_fisher_ge_observed": Q.tail_ge(-2 * np.log(ps).sum(1), so["fisher"]),
                                "per_label_share_p_lt_0.05": dict(zip(Q.CONTROLS, np.round((ps < 0.05).mean(0), 3).tolist()))}
    # joint: how often does one shuffle give BOTH a sibling median as low as observed AND a median against A as low as observed?
    mA = np.median(SH[f"p_{w}_A"], 1)
    f["pseudo_corr_sibling_median_vs_A_median"] = round(float(np.corrcoef(meds, mA)[0, 1]), 3)
    # is 'the controls that stand out against their siblings are the ones low against A' beyond what shared noise gives?
    def spearman(a, b):
        ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
        return float(np.corrcoef(ra, rb)[0, 1])
    rho_obs = spearman(np.array([so["p_vs_siblings"][k] for k in Q.CONTROLS]), SW[f"p{n}"][0, 0, :8])
    rho_null = np.array([spearman(ps[i], SH[f"p_{w}_A"][i]) for i in range(len(ps))])
    f["spearman_sibling_p_vs_A_p_across_eight"] = {"observed": round(rho_obs, 3), "pseudo_null_mean": round(float(rho_null.mean()), 3),
                                                   "pseudo_null_sd": round(float(rho_null.std()), 3), "P_ge_obs": Q.tail_ge(rho_null, rho_obs)}
    res[w] = f
    print("==", w)
    print(json.dumps(f, indent=1))
(Q.OUT / "f4_factorial.json").write_text(json.dumps(res, indent=1))
