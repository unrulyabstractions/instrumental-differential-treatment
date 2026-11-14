"""Critic round 4, m02. Summarize the stats investigator's 1,000 pseudo-control draws with my own code.
Pseudo-controls: the eight controls' replies shuffled among the eight labels per slot (keeps the shared pattern,
drops own structure). Tests against siblings, real A, real B, and a swap pseudo-base pair (A2, B2)."""
import json
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent
z = np.load(ROOT / "stats_r4/out/draws_shuf_1000.npz")
sw = np.load(ROOT / "stats_r2/out/draws_swap_4000.npz")
OBS = {"six": {"medA": 0.0557, "medB": 0.4146, "gap": 0.597, "sib": [0.0472, 0.0201, 0.1916, 0.1557, 0.0914, 0.6119, 0.9600, 0.0442]},
       "five": {"medA": 0.0782, "medB": 0.4553, "gap": 0.600, "sib": None}}
res = {}
for tag in ("six", "five"):
    r = {}
    for fam in ("sib", "A", "B", "A2", "B2"):
        p = z[f"p_{tag}_{fam}"]; S = z[f"S_{tag}_{fam}"]
        med = np.median(p, axis=1)
        r[fam] = {"share_p_below_0.05": round(float((p < 0.05).mean()), 4), "share_p_below_0.10": round(float((p < 0.10).mean()), 4),
                  "median_of_medians": round(float(np.median(med)), 3), "q05_q95_of_median": np.round(np.quantile(med, [0.05, 0.95]), 3).tolist(),
                  "P_median_le_obsA": float((1 + np.sum(med <= OBS[tag]["medA"])) / (1 + len(med))), "mean_S": round(float(S.mean()), 3)}
    gap = z[f"S_{tag}_A"].mean(1) - z[f"S_{tag}_B"].mean(1)
    r["pseudo_gap_A_minus_B"] = {"mean": round(float(gap.mean()), 3), "sd_over_shuffles": round(float(gap.std()), 3),
                                 "P_ge_obs_gap": float((1 + np.sum(gap >= OBS[tag]["gap"])) / (1 + len(gap)))}
    if OBS[tag]["sib"]:
        o = np.array(OBS[tag]["sib"]); med = np.median(z[f"p_{tag}_sib"], axis=1)
        r["sibling_observed"] = {"median": round(float(np.median(o)), 4), "P_median_le_obs": float((1 + np.sum(med <= np.median(o))) / (1 + len(med))),
                                 "count_below_0.10_obs": int((o < 0.10).sum()),
                                 "P_count_ge_obs": float((1 + np.sum((z[f"p_{tag}_sib"] < 0.10).sum(1) >= (o < 0.10).sum())) / (1 + len(med)))}
    res[tag] = r
# real controls against swap pseudo-bases (7,998), for the factorial's other margin
p6 = np.concatenate([sw["p6"][1:, 0, :8], sw["p6"][1:, 1, :8]])
res["real_controls_vs_swap_pseudobase_six"] = {"median_of_medians": round(float(np.median(np.median(p6, 1))), 3),
                                               "share_p_below_0.05": round(float((p6 < 0.05).mean()), 4),
                                               "share_p_le_0.06": round(float((p6 <= 0.06).mean()), 4),
                                               "per_control_share_p_le_0.06": np.round((p6 <= 0.06).mean(0), 3).tolist()}
print(json.dumps(res, indent=1))
(OUT / "m02_pseudo_controls_from_draws.json").write_text(json.dumps(res, indent=1))
