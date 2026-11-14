"""Critic r2, check 3.

(a) Direction-free omnibus over all targets under the A/B reply swap: per-target standardized S gap
    z_k = (S(T_k|A') - S(T_k|B')) / sd_k (sd_k from the swap draws); statistics sum z^2 and max |z|,
    for the ten six-candidate targets and for the eleven five-candidate targets (ten + CO).
    Also the heterogeneity contrast: gap(eight nulls) - gap(two synthetic arms).
(b) Dose-response without luck: base cell rates (1-lam)*pB + lam*pA, exact registered p for the
    eight nulls (uses stats_r2/fast.py, which reproduces 22 of 22 stored pairings).
(c) Mixture bootstrap: each of 16 replies per cell drawn with replacement from A's replies with
    probability lam, else B's. P(eight-test median <= 0.0557) for lam in {0.25, 0.75, 1.0}
    (stats_r2 has lam = 0 and 0.5 as bootB and boot32).
"""
import sys, json, time
import numpy as np
BASE = "/private/tmp/claude-501/-Users-unrulyabstractions-work-papers-idt/32b842b8-ab16-41a9-8f2f-692b2558b7d6/scratchpad/nullinv"
sys.path.insert(0, BASE + "/stats_r2")
import fast as F
from fast import C
import warnings; warnings.simplefilter("ignore")

D = F.load()
cands = D["_cands"]
keep = [i for i, c in enumerate(cands) if c != "anthropic"]
names = list(C.CONTROLS) + ["sd_ai_welfare_poisoning", "sd_emotional_bond"]
P = {k: C.rates(v) for k, v in D.items() if not k.startswith("_")}
OT = np.stack([C.ovr(P[k]) for k in names])
OT5 = np.stack([C.ovr(P[k][keep]) for k in names + ["CO"]])
RA, RB = D["A"], D["B"]
both = ~np.isnan(RA).all(3) & ~np.isnan(RB).all(3)
res = {}

# ---------- (a) omnibus
def S_all(XA, XB):
    pa, pb = C.rates(XA), C.rates(XB)
    sa = C.smax(C.tgrid(OT - C.ovr(pa)[None])[0]); sb = C.smax(C.tgrid(OT - C.ovr(pb)[None])[0])
    sa5 = C.smax(C.tgrid(OT5 - C.ovr(pa[keep])[None])[0]); sb5 = C.smax(C.tgrid(OT5 - C.ovr(pb[keep])[None])[0])
    return sa - sb, sa5 - sb5

g6o, g5o = S_all(RA, RB)
N = 4000
rng = np.random.default_rng(4242)
G6 = np.empty((N, 10)); G5 = np.empty((N, 11))
for n in range(N):
    m = (rng.random(RA.shape[:3]) < 0.5) & both
    G6[n], G5[n] = S_all(np.where(m[..., None], RB, RA), np.where(m[..., None], RA, RB))
def omni(go, G, label):
    sd = G.std(0)
    zo = go / sd; Z = G / sd
    out = {"per_target_z": dict(zip((names + ["CO"])[:len(go)], np.round(zo, 2).tolist()))}
    for nm, fn in (("sum_z2", lambda z: (z ** 2).sum(-1)), ("max_abs_z", lambda z: np.abs(z).max(-1)),
                   ("abs_mean_gap", lambda z: np.abs(z.mean(-1)))):
        o = fn(zo); nl = fn(Z)
        out[nm] = {"obs": float(o), "null_mean": float(nl.mean()), "p": float((1 + (nl >= o).sum()) / (1 + N))}
    print(label, json.dumps(out)); return out
res["omnibus_ten_six"] = omni(g6o, G6, "ten six-cand")
res["omnibus_eight_six"] = omni(g6o[:8], G6[:, :8], "eight six-cand")
res["omnibus_eleven_five"] = omni(g5o, G5, "eleven five-cand")
h_o = g6o[:8].mean() - g6o[8:].mean(); h = G6[:, :8].mean(1) - G6[:, 8:].mean(1)
res["heterogeneity_eight_minus_synth"] = {"obs": float(h_o), "sd": float(h.std()), "p_two": float((1 + (np.abs(h) >= abs(h_o)).sum()) / (1 + N))}
print("heterogeneity", res["heterogeneity_eight_minus_synth"])

# ---------- (b) deterministic interpolation
E6 = F.E_for(6)
pA, pB = P["A"], P["B"]
# cells where A has NaN rate (none expected) -> use B
pA_ = np.where(np.isnan(pA), pB, pA)
curve = {}
for lam in (0.0, 0.1, 0.25, 0.3, 0.4, 0.48, 0.5, 0.6, 0.75, 0.9, 1.0):
    pb = (1 - lam) * pB + lam * pA_
    S, p, _ = F.test_many(OT[:8], C.ovr(pb), 6, E6)
    curve[str(lam)] = {"median_p": float(np.median(p)), "p": np.round(p, 4).tolist(), "mean_S": float(S.mean())}
    print(f"lam={lam:4.2f} median p={np.median(p):.4f} mean S={S.mean():.3f} p={np.round(p,3).tolist()}", flush=True)
res["interpolation"] = curve

# ---------- (c) mixture bootstrap
rng = np.random.default_rng(99)
pool = np.concatenate([RA, RB], axis=2)  # (c,i,32,j)
t0 = time.time()
mb = {}
for lam in (0.25, 0.75, 1.0):
    meds = []; ps = []
    for n in range(300):
        fromA = rng.random(RA.shape[:3]) < lam
        ix = rng.integers(0, 16, size=RA.shape[:3]) + np.where(fromA, 0, 16)
        X = np.take_along_axis(pool, ix[..., None], axis=2)
        pb = F.rates_of(X)
        if np.isnan(pb).any():
            pb = np.where(np.isnan(pb), pB, pb)
        S, p, _ = F.test_many(OT[:8], C.ovr(pb), 6, E6)
        meds.append(np.median(p)); ps.append(p)
    meds = np.array(meds); ps = np.array(ps)
    mb[str(lam)] = {"n": 300, "median_of_median": float(np.median(meds)), "P_median_le_0.0557": float(np.mean(meds <= 0.0557)),
                    "q05_q95": [float(np.quantile(meds, .05)), float(np.quantile(meds, .95))],
                    "per_test_P_p_lt_0.05": np.mean(ps < 0.05, 0).round(3).tolist()}
    print(f"mixture bootstrap lam={lam}: {mb[str(lam)]}  ({time.time()-t0:.0f}s)", flush=True)
res["mixture_bootstrap"] = mb
json.dump(res, open(BASE + "/critic_r2/k03_omnibus_and_dose.json", "w"), indent=1)
