"""Critic r2, check 4: how surprising is the observed A-vs-B gap if a share lam of the realized
candidate-by-axis difference were systematic (present in every draw of A's arm)?

Model (the stats investigator's S2 calibration): delta = mean over instructions of OvR(A) - OvR(B)
per (candidate, axis). For each swap draw (A', B') set OvR(A'') = OvR(A') + lam*delta/2 and
OvR(B'') = OvR(B') - lam*delta/2, so the pair differs systematically by lam*delta and is otherwise a
swap-null pair. Statistics: mean S gap over the eight nulls; sum of squared standardized gaps over
the ten six-candidate targets (standardized by the lam = 0 swap SD). p(lam) = P(stat >= observed).
lam = 0 is the plain swap test; S2 puts lam at about 0.3 with a 95% upper bound of about 0.48.
"""
import sys, json
import numpy as np
BASE = "/private/tmp/claude-501/-Users-unrulyabstractions-work-papers-idt/32b842b8-ab16-41a9-8f2f-692b2558b7d6/scratchpad/nullinv"
sys.path.insert(0, BASE + "/stats_r1")
import common as C
import warnings; warnings.simplefilter("ignore")

D = C.load_all()
names = list(C.CONTROLS) + ["sd_ai_welfare_poisoning", "sd_emotional_bond"]
P = {k: C.rates(v) for k, v in D.items() if not k.startswith("_")}
OT = np.stack([C.ovr(P[k]) for k in names])
RA, RB = D["A"], D["B"]
both = ~np.isnan(RA).all(3) & ~np.isnan(RB).all(3)
oA, oB = C.ovr(P["A"]), C.ovr(P["B"])
delta = np.nanmean(oA - oB, axis=1, keepdims=True)  # (c,1,j)

def tfix(d):
    # paired t over instructions; 0 where the spread over instructions is below 1e-9. A constant
    # injected offset on a never-firing axis would otherwise give |t| ~ 1e15 (the artifact the stats
    # investigator fixed in s2b_power_twin.py). Real data never has a constant nonzero d.
    n = d.shape[-2]
    mean = d.mean(axis=-2); sd = d.std(axis=-2, ddof=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        t = mean / (sd / np.sqrt(n))
    return np.where(sd < 1e-9, 0.0, t)


def gaps(oa, ob):
    return C.smax(tfix(OT - oa[None])) - C.smax(tfix(OT - ob[None]))

g_obs = gaps(oA, oB)
LAMS = (0.0, 0.3, 0.48, 0.75, 1.0)
N = 2000
rng = np.random.default_rng(31337)
G = {l: np.empty((N, 10)) for l in LAMS}
for n in range(N):
    m = (rng.random(RA.shape[:3]) < 0.5) & both
    oa = C.ovr(C.rates(np.where(m[..., None], RB, RA))); ob = C.ovr(C.rates(np.where(m[..., None], RA, RB)))
    for l in LAMS:
        G[l][n] = gaps(oa + l * delta / 2, ob - l * delta / 2)
sd0 = G[0.0].std(0)
res = {"obs_mean_gap_eight": float(g_obs[:8].mean()), "obs_sum_z2_ten": float(((g_obs / sd0) ** 2).sum()),
       "obs_het": float(g_obs[:8].mean() - g_obs[8:].mean()), "N": N, "lam": {}}
for l in LAMS:
    g = G[l]
    m8 = g[:, :8].mean(1); z2 = ((g / sd0) ** 2).sum(1); het = g[:, :8].mean(1) - g[:, 8:].mean(1)
    res["lam"][str(l)] = {
        "mean_gap_eight": {"null_mean": float(m8.mean()), "null_sd": float(m8.std()), "p_upper": float((1 + (m8 >= res["obs_mean_gap_eight"]).sum()) / (1 + N))},
        "sum_z2_ten": {"null_mean": float(z2.mean()), "p_upper": float((1 + (z2 >= res["obs_sum_z2_ten"]).sum()) / (1 + N))},
        "het_eight_minus_synth": {"null_mean": float(het.mean()), "null_sd": float(het.std()), "p_two": float((1 + (np.abs(het - het.mean()) >= abs(res["obs_het"] - het.mean())).sum()) / (1 + N)),
                                  "p_upper": float((1 + (het >= res["obs_het"]).sum()) / (1 + N))},
        "per_target_gap_mean": np.round(g.mean(0), 3).tolist()}
    print(l, json.dumps(res["lam"][str(l)]), flush=True)
json.dump(res, open(BASE + "/critic_r2/k04_injection_gap.json", "w"), indent=1)
print("obs", res["obs_mean_gap_eight"], res["obs_sum_z2_ten"], res["obs_het"])
