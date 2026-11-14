"""D1 (b, refined). Restrict the second-judge comparison to cells where gpt-4.1-nano actually fires.

nano says yes on 7.8% of verdicts against gpt-5-mini's 19.4%, and on some axes almost never. A cell where nano
returned (almost) no yes verdicts for that candidate in A and CO carries no information about text vs judge.
Informative cell: nano yes count, A + CO at that candidate, >= 20 of 1,152 replies.
(a) A's top-K deviant cells (five candidates, cons8 - A), informative cells only: mini and nano signed t(CO - A),
    null N2 (same axes, random candidate row, random sign) restricted to informative cells.
(b) The eight tests' peak cells (six candidates): which are informative, and the signed t there.
"""
import numpy as np
from dcommon import C, dump, load_nano
D = C.load_all(); cands = D["_cands"]; N = load_nano()
keep = [i for i, c in enumerate(cands) if c != "anthropic"]
O5 = lambda R: C.ovr(C.rates(R)[keep]); O6 = lambda R: C.ovr(C.rates(R))
T = lambda x: np.nan_to_num(C.tgrid(x)[0])
yes6 = np.nansum(N["A"], axis=(1, 2)) + np.nansum(N["CO"], axis=(1, 2))     # (6, 101)
inf6 = yes6 >= 20; inf5 = inf6[keep]
print(f"informative (candidate, axis) cells: {inf6.sum()} of {inf6.size} (six candidates); {inf5.sum()} of {inf5.size} (five)")
m5 = {k: O5(D[k]) for k in ["A", "CO"] + list(C.CONTROLS)}; n5 = {"A": O5(N["A"]), "CO": O5(N["CO"])}
cons = np.mean([m5[c] for c in C.CONTROLS], 0)
g = T(cons - m5["A"]); g_inf = np.where(inf5, np.abs(g), -1).ravel()
vm = T(m5["CO"] - m5["A"]).ravel(); vn = T(n5["CO"] - n5["A"]).ravel()
gc = T(cons - m5["CO"]); gc_inf = np.where(inf5, np.abs(gc), -1).ravel()
vm2 = T(m5["A"] - m5["CO"]).ravel(); vn2 = T(n5["A"] - n5["CO"]).ravel()
rng = np.random.default_rng(8); res = {"n_informative_five": int(inf5.sum())}
infl = np.flatnonzero(inf5.ravel())
for K in (6, 12, 20, 40):
    top = np.argsort(-g_inf)[:K]; s = np.sign(g.ravel()[top])
    xm, xn = float(np.mean(s * vm[top])), float(np.mean(s * vn[top]))
    nul = np.array([np.mean(rng.choice([-1, 1], K) * vn[rng.choice(infl, K, replace=False)]) for _ in range(20000)])
    topc = np.argsort(-gc_inf)[:K]; sc = np.sign(gc.ravel()[topc])
    cm, cn = float(np.mean(sc * vm2[topc])), float(np.mean(sc * vn2[topc]))
    res[f"K{K}"] = {"A_cells_mini": xm, "A_cells_nano": xn, "ratio": xn / xm, "null_sd": float(nul.std()),
                    "p_upper": float((1 + np.sum(nul >= xn)) / 20001), "CO_mirror_mini": cm, "CO_mirror_nano": cn, "CO_ratio": cn / cm}
    print(f"K={K:2d} A's informative top cells: mini {xm:+.2f} nano {xn:+.2f} ratio {xn/xm:.2f} (random informative-cell null sd {nul.std():.2f}, p_upper {res[f'K{K}']['p_upper']:.4f}) | CO mirror: mini {cm:+.2f} nano {cn:+.2f} ratio {cn/cm:.2f}")
m6 = {k: O6(D[k]) for k in ["A", "CO"] + list(C.CONTROLS)}; n6 = {"A": O6(N["A"]), "CO": O6(N["CO"])}
um6 = T(m6["CO"] - m6["A"]); un6 = T(n6["CO"] - n6["A"]); peaks = []
for k in C.CONTROLS:
    t = np.nan_to_num(C.tgrid(m6[k] - m6["A"])[0]); i, j = np.unravel_index(np.argmax(np.abs(t)), t.shape); s = np.sign(t[i, j])
    peaks.append({"test": k, "cell": [cands[i], C.AXES[j]], "nano_yes_A_plus_CO": int(yes6[i, j]), "informative": bool(inf6[i, j]),
                  "mini": float(s * um6[i, j]), "nano": float(s * un6[i, j])})
    print(f"  {k:24s} {cands[i]:18s} {C.AXES[j][:44]:44s} nano yes {int(yes6[i,j]):4d} informative={bool(inf6[i,j])} | mini {s*um6[i,j]:+.2f} nano {s*un6[i,j]:+.2f}")
inf_p = [p for p in peaks if p["informative"]]
print(f"  informative peaks: {len(inf_p)}; mean mini {np.mean([p['mini'] for p in inf_p]):+.2f}, nano {np.mean([p['nano'] for p in inf_p]):+.2f}")
res["peaks"] = peaks
dump(res, "d01b_nano_informative_cells.json")
