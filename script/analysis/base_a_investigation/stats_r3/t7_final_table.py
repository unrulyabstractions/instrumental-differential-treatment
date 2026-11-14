"""T7. One table for the paper authors.

Rows: mean-S gap (A minus B), sum z^2, median level (median p against A), count p < 0.05 against A,
and the eight-minus-synthetic contrast. Columns: eight nulls (six candidates); ten = eight + two
synthetic arms (six candidates); eleven = ten + contextual_optimism (five candidates).
Each cell: the observed value, then P(at least as extreme) under
  (1) exchangeability (A/B reply swap, 3,999 draws, stats_r2),
  (2) the mixture-bootstrap share model at the T3 point estimate and 95% upper bound of the
      systematic share (linear interpolation in lam between grid points 0, 0.3, 0.48, 0.7, 1.0),
  (3) the partial-swap model at the same two shares (grid 0 = swap, 0.15, 0.3, 0.48, 0.7).
The share estimate comes from out/t3_t4_split_half_200_64.json (six candidates; five beside it).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
R = json.load(open(HERE / "out" / "t2_t5_t7.json"))
T3 = json.load(open(HERE / "out" / "t3_t4_split_half_200_64.json"))


def share_estimates(world):
    blk = T3[f"T3 power {world}"]
    ob = blk["obs_b"]
    lams = sorted(float(k) for k in blk["mboot"])
    means = np.array([blk["mboot"][str(l) if str(l) in blk["mboot"] else repr(l)]["mean"] for l in lams])
    P = np.array([blk["mboot"][str(l)]["P_le_obs_normal"] for l in lams])
    # point estimate: E[b | lam] = observed (means increase with lam)
    lam_hat = float(np.interp(ob, means, lams)) if means[0] <= ob <= means[-1] else (0.0 if ob < means[0] else 1.0)
    # 95% upper bound: largest lam with P(b <= obs | lam) >= 0.05 (P decreases with lam)
    lam_up = float(np.interp(0.05, P[::-1], np.array(lams)[::-1])) if P[-1] < 0.05 < P[0] else (1.0 if P[-1] >= 0.05 else 0.0)
    return {"obs_b": ob, "lams": lams, "E_b": means.round(3).tolist(), "P_le_obs": P.round(4).tolist(),
            "lam_hat": lam_hat, "lam_up95": lam_up}


SH = {w: share_estimates(w) for w in ("six", "five")}
print(json.dumps(SH, indent=1))

STAT = {"mean_gap": ("mean_gap", "P_ge_obs"), "sum_z2": ("sum_z2", "P_ge_obs"),
        "median_p": ("median_p", "P_le_obs"), "count_lt_05": ("count_lt_05", "P_ge_obs")}


def P_at(mode, fam, stat, lam):
    grid = {"mboot": [0.0, 0.3, 0.48, 0.7, 1.0], "pswap": [0.0, 0.15, 0.3, 0.48, 0.7]}[mode]
    xs, ys = [], []
    for g in grid:
        key = "swap 0.0" if (mode == "pswap" and g == 0.0) else f"{mode} {g}"
        if key not in R:
            continue
        xs.append(g)
        if fam == "eight_minus_synth":
            ys.append(R[key]["eight_minus_synth"]["P_ge_obs"])
        else:
            ys.append(R[key][fam][STAT[stat][0]][STAT[stat][1]])
    if not xs or lam > xs[-1] + 1e-9:
        return None
    return float(np.interp(lam, xs, ys))


lh, lu = SH["six"]["lam_hat"], SH["six"]["lam_up95"]
table = {"share_six": SH["six"], "share_five": SH["five"], "rows": {}}
for stat in ("mean_gap", "sum_z2", "median_p", "count_lt_05"):
    for fam in ("eight", "ten", "eleven5"):
        ex = R["swap 0.0"][fam][STAT[stat][0]]
        cell = {"obs": ex["obs"], "P_exchangeable_swap": ex[STAT[stat][1]],
                "P_mboot_lam0_fresh_noise": P_at("mboot", fam, stat, 0.0),
                "P_mboot_at_lam_hat": P_at("mboot", fam, stat, lh), "P_mboot_at_lam_up": P_at("mboot", fam, stat, lu),
                "P_pswap_at_lam_hat": P_at("pswap", fam, stat, lh), "P_pswap_at_lam_up": P_at("pswap", fam, stat, lu),
                "P_mboot_lam1_all_systematic": P_at("mboot", fam, stat, 1.0)}
        table["rows"][f"{stat} | {fam}"] = cell
        print(f"{stat:12s} {fam:8s} obs {cell['obs']:8.4f} | swap {cell['P_exchangeable_swap']:.4f} | mboot0 {cell['P_mboot_lam0_fresh_noise']}"
              f" | mboot@{lh:.2f} {cell['P_mboot_at_lam_hat']} @{lu:.2f} {cell['P_mboot_at_lam_up']} | pswap@{lh:.2f} {cell['P_pswap_at_lam_hat']}"
              f" @{lu:.2f} {cell['P_pswap_at_lam_up']} | mboot1 {cell['P_mboot_lam1_all_systematic']}")
e = R["swap 0.0"]["eight_minus_synth"]
table["rows"]["eight_minus_synth"] = {"obs": e["obs"], "P_exchangeable_swap": e["P_ge_obs"],
                                      "P_mboot_at_lam_hat": P_at("mboot", "eight_minus_synth", None, lh),
                                      "P_mboot_at_lam_up": P_at("mboot", "eight_minus_synth", None, lu),
                                      "P_pswap_at_lam_hat": P_at("pswap", "eight_minus_synth", None, lh),
                                      "P_pswap_at_lam_up": P_at("pswap", "eight_minus_synth", None, lu),
                                      "P_mboot_lam1_all_systematic": P_at("mboot", "eight_minus_synth", None, 1.0)}
print("eight_minus_synth", json.dumps(table["rows"]["eight_minus_synth"]))
json.dump(table, open(HERE / "out" / "t7_final_table.json", "w"), indent=1)
