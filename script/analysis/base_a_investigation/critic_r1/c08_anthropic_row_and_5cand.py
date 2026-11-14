"""Critic checks:
(a) Does base A carry a fraction of the contextual_optimism (CO) adapter's anthropic effect (adapter leakage into the base arm,
    which was sampled in the engine holding that adapter), or a judge-session effect on the anthropic rows?
    lambda = regression slope, over the 101 axes of the anthropic row, of mean OvR(A) - OvR(B) on mean OvR(CO) - OvR(nulls' consensus).
    Noise sources of the two sides are disjoint (A,B vs CO,nulls). Null: swap A/B replies (2,000 swaps). Same for the other five rows.
(b) Five-candidate world (anthropic dropped before one-vs-rest): matched-slot split-half replication of T-A vs T-B for the eight nulls,
    with the A/B swap null, and injection power for A-B.
"""
import sys, json, warnings
import numpy as np
sys.path.insert(0, "/private/tmp/claude-501/-Users-unrulyabstractions-work-papers-idt/32b842b8-ab16-41a9-8f2f-692b2558b7d6/scratchpad/nullinv/stats_r1")
import common as C
D = C.load_all(); cands = D["_cands"]
rng = np.random.default_rng(41)
RA, RB = D["A"], D["B"]
O = {k: C.ovr(C.rates(v)) for k, v in D.items() if not k.startswith("_")}
cons = np.mean([O[c] for c in C.CONTROLS], axis=0)
x = np.nanmean(O["CO"] - cons, axis=1)          # (6, 101) CO's mean excess over the nulls
def lam(oa, ob):
    y = np.nanmean(oa - ob, axis=1)
    return np.array([float(np.dot(x[c], y[c]) / np.dot(x[c], x[c])) for c in range(6)]), np.array([float(np.corrcoef(x[c], y[c])[0, 1]) for c in range(6)])
l0, r0 = lam(O["A"], O["B"])
L = []; Rr = []
for k in range(2000):
    m = rng.random(RA.shape[:3]) < 0.5
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        ya = C.ovr(np.nanmean(np.where(m[..., None], RA, RB), 2)); yb = C.ovr(np.nanmean(np.where(m[..., None], RB, RA), 2))
    l, r = lam(ya, yb); L.append(l); Rr.append(r)
L, Rr = np.array(L), np.array(Rr)
res = {"leak": {}}
print("(a) slope of (A - B) on (CO - nulls) per candidate row; CO's own effect size |x| (rms over axes):")
for c, cn in enumerate(cands):
    p2 = float((1 + np.sum(np.abs(L[:, c]) >= abs(l0[c]))) / (1 + len(L)))
    res["leak"][cn] = {"lambda": float(l0[c]), "swap_sd": float(L[:, c].std()), "p_two_sided": p2, "corr": float(r0[c]), "rms_CO_excess": float(np.sqrt(np.mean(x[c] ** 2)))}
    print(f"   {cn:20s} lambda={l0[c]:+.4f} (swap sd {L[:, c].std():.4f}, z={l0[c]/L[:, c].std():+.2f}, p2={p2:.4f})  corr={r0[c]:+.3f}  rms CO excess {np.sqrt(np.mean(x[c]**2)):.4f}")
# (b) five-candidate matched split-half
keep5 = [i for i, c in enumerate(cands) if c != "anthropic"]
def hrate(R, sl):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(R[:, :, sl], axis=2)
def stat(RX, RR, sl1, sl2, inject=None):
    d1 = C.ovr(hrate(RX, sl1)) - C.ovr(hrate(RR, sl1)); d2 = C.ovr(hrate(RX, sl2)) - C.ovr(hrate(RR, sl2))
    if inject is not None: d1 = d1 + inject; d2 = d2 + inject
    g1 = np.nan_to_num(C.tgrid(d1)[0]).ravel(); g2 = np.nan_to_num(C.tgrid(d2)[0]).ravel()
    out = {"r": float(np.corrcoef(g1, g2)[0, 1])}
    for K in (6, 12, 20):
        t1 = np.argsort(-np.abs(g1))[:K]; t2 = np.argsort(-np.abs(g2))[:K]
        out[f"hot{K}"] = float(0.5 * (np.mean(np.sign(g1[t1]) * g2[t1]) + np.mean(np.sign(g2[t2]) * g1[t2])))
    return out
def avg(RX, RR, n, inject=None):
    acc = {}
    for _ in range(n):
        perm = rng.permutation(16); s = stat(RX, RR, perm[:8], perm[8:], inject)
        for k, v in s.items(): acc.setdefault(k, []).append(v)
    return {k: float(np.mean(v)) for k, v in acc.items()}
A5, B5 = RA[keep5], RB[keep5]
obs = avg(A5, B5, 200)
TA = {c: avg(D[c][keep5], A5, 100) for c in C.CONTROLS}; TB = {c: avg(D[c][keep5], B5, 100) for c in C.CONTROLS}
dobs = {k: float(np.mean([TA[c][k] - TB[c][k] for c in C.CONTROLS])) for k in obs}
nulAB = {k: [] for k in obs}; nulD = {k: [] for k in obs}
for it in range(150):
    m = rng.random(A5.shape[:3]) < 0.5
    YA = np.where(m[..., None], A5, B5); YB = np.where(m[..., None], B5, A5)
    s = avg(YA, YB, 10)
    for k, v in s.items(): nulAB[k].append(v)
    if it < 60:
        ta = [avg(D[c][keep5], YA, 6) for c in C.CONTROLS]; tb = [avg(D[c][keep5], YB, 6) for c in C.CONTROLS]
        for k in obs: nulD[k].append(float(np.mean([a[k] - b[k] for a, b in zip(ta, tb)])))
print("\n(b) five candidates. A-B replication:", {k: f"{obs[k]:+.3f} (z={(obs[k]-np.mean(nulAB[k]))/np.std(nulAB[k]):+.2f})" for k in obs})
print("    eight nulls, mean replication of (T-A) minus (T-B):", {k: f"{dobs[k]:+.3f} (swap sd {np.std(nulD[k]):.3f}, z={(dobs[k]-np.mean(nulD[k]))/np.std(nulD[k]):+.2f})" for k in obs})
print("    per null (T-A | T-B) hot12:", {c[:8]: (round(TA[c]['hot12'], 2), round(TB[c]['hot12'], 2)) for c in C.CONTROLS})
dfull = C.ovr(C.rates(A5)) - C.ovr(C.rates(B5)); tfull = np.nan_to_num(C.tgrid(dfull)[0])
top = np.argsort(-np.abs(tfull), axis=None)[:12]; inj = np.zeros_like(dfull); ii, jj = np.unravel_index(top, tfull.shape)
for i, j in zip(ii, jj): inj[i, :, j] = np.nanmean(dfull[i, :, j])
pw = {k: [] for k in obs}
for it in range(80):
    m = rng.random(A5.shape[:3]) < 0.5
    s = avg(np.where(m[..., None], A5, B5), np.where(m[..., None], B5, A5), 10, inject=inj)
    for k, v in s.items(): pw[k].append(v)
print("    if the top-12 full-sample A-B differences were entirely systematic:", {k: f"{np.mean(v):+.3f}±{np.std(v):.3f}" for k, v in pw.items()})
res["five_cand"] = {"A_B": obs, "A_B_null_sd": {k: float(np.std(v)) for k, v in nulAB.items()}, "nulls_TA_minus_TB": dobs,
                    "nulls_TA_minus_TB_null_sd": {k: float(np.std(v)) for k, v in nulD.items()}, "inject_top12": {k: [float(np.mean(v)), float(np.std(v))] for k, v in pw.items()},
                    "TA": TA, "TB": TB}
json.dump(res, open("/private/tmp/claude-501/-Users-unrulyabstractions-work-papers-idt/32b842b8-ab16-41a9-8f2f-692b2558b7d6/scratchpad/nullinv/critic_r1/c08_anthropic_row_and_5cand.json", "w"), indent=1)
