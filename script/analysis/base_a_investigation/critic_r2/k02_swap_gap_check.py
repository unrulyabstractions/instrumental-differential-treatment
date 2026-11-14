"""Critic r2, check 2: independent re-run of the A/B reply-swap test on the mean-S gap.

Statistic: mean over targets of S(T vs A') - S(T vs B'), where A', B' swap replies at each
(candidate, instruction, s) slot with probability 1/2. Families: eight nulls; two synthetic arms; all ten;
ten + CO on five candidates. Also the sign pattern: how many of the targets have S higher against A.
Own swap code and RNG; cell rates / OvR / t via the validated loaders (22 of 22 stored pairings).
"""
import sys, json
import numpy as np
sys.path.insert(0, "/private/tmp/claude-501/-Users-unrulyabstractions-work-papers-idt/32b842b8-ab16-41a9-8f2f-692b2558b7d6/scratchpad/nullinv/stats_r1")
import common as C
import warnings; warnings.simplefilter("ignore")

D = C.load_all()
cands = D["_cands"]
keep = [i for i, c in enumerate(cands) if c != "anthropic"]
names = list(C.CONTROLS) + ["sd_ai_welfare_poisoning", "sd_emotional_bond"]
OT = np.stack([C.ovr(C.rates(D[k])) for k in names])
OT5 = np.stack([C.ovr(C.rates(D[k])[keep]) for k in names + ["CO"]])
RA, RB = D["A"], D["B"]
both = ~np.isnan(RA).all(3) & ~np.isnan(RB).all(3)

def S_all(XA, XB):
    pa, pb = C.rates(XA), C.rates(XB)
    oa, ob = C.ovr(pa), C.ovr(pb)
    sa = C.smax(C.tgrid(OT - oa[None])[0]); sb = C.smax(C.tgrid(OT - ob[None])[0])
    oa5, ob5 = C.ovr(pa[keep]), C.ovr(pb[keep])
    sa5 = C.smax(C.tgrid(OT5 - oa5[None])[0]); sb5 = C.smax(C.tgrid(OT5 - ob5[None])[0])
    return sa, sb, sa5, sb5

sa, sb, sa5, sb5 = S_all(RA, RB)
print("S vs A:", np.round(sa, 3)); print("S vs B:", np.round(sb, 3))
print("5-cand S vs A:", np.round(sa5, 3)); print("5-cand S vs B:", np.round(sb5, 3))
obs = {"eight": (sa[:8] - sb[:8]).mean(), "synth2": (sa[8:] - sb[8:]).mean(), "ten": (sa - sb).mean(),
       "eight_5c": (sa5[:8] - sb5[:8]).mean(), "ten_5c": (sa5[:10] - sb5[:10]).mean(), "eleven_5c": (sa5 - sb5).mean(),
       "n_higher_vs_A_ten": int((sa > sb).sum()), "n_higher_vs_A_eleven5": int((sa5 > sb5).sum())}
N = 3000
rng = np.random.default_rng(777)
G = {k: np.empty(N) for k in ["eight", "synth2", "ten", "eight_5c", "ten_5c", "eleven_5c"]}
cnt = np.empty(N)
for n in range(N):
    m = (rng.random(RA.shape[:3]) < 0.5) & both
    XA = np.where(m[..., None], RB, RA); XB = np.where(m[..., None], RA, RB)
    a, b, a5, b5 = S_all(XA, XB)
    G["eight"][n] = (a[:8] - b[:8]).mean(); G["synth2"][n] = (a[8:] - b[8:]).mean(); G["ten"][n] = (a - b).mean()
    G["eight_5c"][n] = (a5[:8] - b5[:8]).mean(); G["ten_5c"][n] = (a5[:10] - b5[:10]).mean(); G["eleven_5c"][n] = (a5 - b5).mean()
    cnt[n] = max((a > b).sum(), (a < b).sum())
res = {"obs": {k: float(v) for k, v in obs.items()}, "N": N}
for k, g in G.items():
    o = obs[k]
    res[k] = {"obs": float(o), "sd": float(g.std()), "z": float(o / g.std()),
              "p_upper": float((1 + (g >= o).sum()) / (1 + N)), "p_lower": float((1 + (g <= o).sum()) / (1 + N)),
              "p_two": float((1 + (np.abs(g) >= abs(o)).sum()) / (1 + N))}
    print(k, res[k])
# omnibus over the ten that ignores direction: mean of squared per-target standardized gaps would need per-target sd; use max(|eight gap|,|synth gap|) style
res["sign_split_ten"] = {"obs_max_same_sign": int(max(obs["n_higher_vs_A_ten"], 10 - obs["n_higher_vs_A_ten"])),
                         "P_ge": float(np.mean(cnt >= max(obs["n_higher_vs_A_ten"], 10 - obs["n_higher_vs_A_ten"])))}
print(res["sign_split_ten"])
json.dump(res, open("/private/tmp/claude-501/-Users-unrulyabstractions-work-papers-idt/32b842b8-ab16-41a9-8f2f-692b2558b7d6/scratchpad/nullinv/critic_r2/k02_swap_gap_check.json", "w"), indent=1)
