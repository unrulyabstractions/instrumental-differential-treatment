"""Critic round 4, m01. Recompute the surprise table from the stats investigator's stored draws with my own code.
Reads only: stats_r2/out/draws_swap_4000.npz (reply swap), stats_r4/out/draws_prompt_1000.npz (whole-prompt swap),
stats_r4/out/draws_instructionS_2000.npz (whole-instruction swap, S only). Draw 0 is the identity (real A, B)."""
import json
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent
EIGHT = slice(0, 8)


def tail_ge(null, x): return float((1 + np.sum(null >= x - 1e-12)) / (1 + len(null)))
def tail_le(null, x): return float((1 + np.sum(null <= x + 1e-12)) / (1 + len(null)))


def table(SA, SB, pA=None, names=None):
    """SA, SB (n_draws, m). Row 0 observed. Null rows 1..; a swap draw gives a pseudo pair, so both orders are null draws."""
    g = SA - SB
    obs, null = g[0], g[1:]
    sd = null.std(axis=0)
    z_obs, z_null = obs / sd, null / sd
    m = g.shape[1]
    r = {"n_null": int(len(null)), "z": dict(zip(names, np.round(z_obs, 2).tolist()))}
    r["sum_z2_all"] = {"obs": round(float((z_obs ** 2).sum()), 2), "null_mean": round(float((z_null ** 2).sum(1).mean()), 2),
                       "P": tail_ge((z_null ** 2).sum(1), (z_obs ** 2).sum())}
    r["sum_z2_eight"] = {"obs": round(float((z_obs[EIGHT] ** 2).sum()), 2), "P": tail_ge((z_null[:, EIGHT] ** 2).sum(1), (z_obs[EIGHT] ** 2).sum())}
    loo = {}
    for j in range(m):
        keep = [i for i in range(m) if i != j]
        loo[names[j]] = tail_ge((z_null[:, keep] ** 2).sum(1), (z_obs[keep] ** 2).sum())
    r["sum_z2_leave_one_out_P"] = {k: round(v, 4) for k, v in loo.items()}
    mg = null[:, EIGHT].mean(1)
    r["eight_mean_gap"] = {"obs": round(float(obs[EIGHT].mean()), 3), "null_sd": round(float(mg.std()), 3),
                           "P_one": tail_ge(mg, obs[EIGHT].mean()), "P_two": tail_ge(np.abs(mg), abs(obs[EIGHT].mean()))}
    if m >= 10:
        c_obs = obs[EIGHT].mean() - obs[8:10].mean()
        c_null = null[:, EIGHT].mean(1) - null[:, 8:10].mean(1)
        r["eight_minus_synthetic"] = {"obs": round(float(c_obs), 3), "null_sd": round(float(c_null.std()), 3), "P_two": tail_ge(np.abs(c_null), abs(c_obs))}
        ag = null.mean(1)
        r["all_mean_gap"] = {"obs": round(float(obs.mean()), 3), "P_one": tail_ge(ag, obs.mean())}
    if pA is not None:
        med = np.median(pA[:, EIGHT], axis=1)
        r["eight_median_p_level"] = {"obs": round(float(med[0]), 4), "null_median": round(float(np.median(med[1:])), 3),
                                     "P": tail_le(med[1:], med[0])}
    return r


res = {}
z = np.load(ROOT / "stats_r2/out/draws_swap_4000.npz")
n6, n5 = [str(x) for x in z["targets6"]], [str(x) for x in z["targets5"]]
res["reply_swap_six"] = table(z["S6"][:, 0], z["S6"][:, 1], np.concatenate([z["p6"][:, 0], z["p6"][1:, 1]]) if False else z["p6"][:, 0], n6)
# level test over both members of each swap pair (7,998 pseudo-bases)
med_all = np.median(np.concatenate([z["p6"][1:, 0, :8], z["p6"][1:, 1, :8]]), axis=1)
res["reply_swap_six"]["eight_median_p_level_both_members"] = {"P": tail_le(med_all, float(np.median(z["p6"][0, 0, :8]))), "null_median": round(float(np.median(med_all)), 3)}
res["reply_swap_five"] = table(z["S5"][:, 0], z["S5"][:, 1], z["p5"][:, 0], n5)
q = np.load(ROOT / "stats_r4/out/draws_prompt_1000.npz")
res["prompt_swap_six"] = table(q["S_six_A2"], q["S_six_B2"], q["p_six_A2"], n6)
res["prompt_swap_five"] = table(q["S_five_A2"], q["S_five_B2"], q["p_five_A2"], n5)
s = np.load(ROOT / "stats_r4/out/draws_instructionS_2000.npz")
res["instruction_swap_six"] = table(s["S_six_A2"], s["S_six_B2"], None, n6)
res["instruction_swap_five"] = table(s["S_five_A2"], s["S_five_B2"], None, n5)
# identity checks
res["identity_check"] = {"prompt_draw0_pA": np.round(q["p_six_A2"][0, :8], 4).tolist(), "prompt_draw0_pB": np.round(q["p_six_B2"][0, :8], 4).tolist()}
print(json.dumps(res, indent=1))
(OUT / "m01_headline_from_draws.json").write_text(json.dumps(res, indent=1))
