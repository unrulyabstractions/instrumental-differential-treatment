"""D1. Is base A's deviation in the reply TEXT or in gpt-5-mini's VERDICTS on A's rows?

gpt-4.1-nano judged base A's replies and contextual_optimism's (CO) replies on the same 101 axes
(out/main/auditbench/contextual_optimism/responses/verdicts_{base,target}.jsonl, Aug 3). Same texts, a second judge.

(a) A's top-K deviant cells under mini (t of cons8 - A; five candidates, anthropic dropped before one-vs-rest).
    Statistic X(K) = mean over the K cells of sign(t_mini(cons8 - A)) * t_nano(CO - A).
    Nulls: N1 random cells with random signs; N2 the same AXES with a random candidate row and random sign
    (controls for axis-specific nano variance); N3 cells matched on mini |t(CO - A)| (same decile), signed by
    mini's sign of t(CO - A) times the selected cell's sign -> the nano value a GENERIC mini difference of that size
    carries (what nano should show if A's cells behave like any cell with the same mini CO-A difference).
    Mirror benchmark: CO's own top-K deviant cells (cons8 - CO, mini), statistic sign * t_nano(A - CO), and its
    replication ratio. Same selection procedure on another sample's ordinary draw: if A's deviation were judge
    noise specific to A's rows, A's ratio would sit well below CO's.
(b) The eight tests' peak cells against A (six candidates as registered), cells on the anthropic row excluded.
    sign(t_mini(T - A)) * t(CO - A) under mini and nano.
(c) Benchmarks: CO's anthropic row (six candidates, real effect) and generic top cells of mini |t(CO - A)|.
(d) Registered test CO vs A on five candidates, mini vs nano (registered seed; five-candidate permutations).
"""
import numpy as np

from dcommon import C, dump, load_nano

D = C.load_all(); cands = D["_cands"]
N = load_nano()
keep = [i for i, c in enumerate(cands) if c != "anthropic"]; c5 = [cands[i] for i in keep]
O5 = lambda R: C.ovr(C.rates(R)[keep])
O6 = lambda R: C.ovr(C.rates(R))
m5 = {k: O5(D[k]) for k in ["A", "B", "CO"] + list(C.CONTROLS)}
n5 = {"A": O5(N["A"]), "CO": O5(N["CO"])}
cons5 = np.mean([m5[c] for c in C.CONTROLS], axis=0)
T = lambda x: np.nan_to_num(C.tgrid(x)[0])
res = {}
rng = np.random.default_rng(20261113)

# mini-vs-nano agreement on A's and CO's replies
for k in ("A", "CO"):
    a, b = D[k], N[k]; both = ~np.isnan(a) & ~np.isnan(b)
    kap = []
    for j in range(len(C.AXES)):
        x, y = a[..., j][both[..., j]], b[..., j][both[..., j]]
        po = (x == y).mean(); pe = x.mean() * y.mean() + (1 - x.mean()) * (1 - y.mean())
        kap.append((po - pe) / (1 - pe) if pe < 1 else np.nan)
    res[f"agreement_{k}"] = {"raw": float((a[both] == b[both]).mean()), "median_kappa": float(np.nanmedian(kap)),
                             "yes_mini": float(np.nanmean(a)), "yes_nano": float(np.nanmean(b))}
print("agreement:", res["agreement_A"], res["agreement_CO"])

uM = T(m5["CO"] - m5["A"]).ravel()      # mini t(CO - A), 505 cells
uN = T(n5["CO"] - n5["A"]).ravel()      # nano t(CO - A)
shape5 = m5["A"].shape[0], m5["A"].shape[2]
dec = np.digitize(np.abs(uM), np.quantile(np.abs(uM), np.linspace(0, 1, 11)[1:-1]))


def block(dev_name, other_name, Ks=(6, 12, 20, 40), nnull=20000):
    """Top-K cells of cons8 - dev (mini). Statistic: sign * t(other - dev) under mini and nano."""
    g = T(cons5 - m5[dev_name]).ravel()
    vm = T(m5[other_name] - m5[dev_name]).ravel(); vn = T(n5[other_name] - n5[dev_name]).ravel()
    out = {}
    for K in Ks:
        top = np.argsort(-np.abs(g))[:K]; sg = np.sign(g[top])
        xm, xn = float(np.mean(sg * vm[top])), float(np.mean(sg * vn[top]))
        # N1: random cells, random signs
        n1 = np.array([np.mean(rng.choice([-1, 1], K) * vn[rng.choice(vn.size, K, replace=False)]) for _ in range(nnull)])
        # N2: same axes, random candidate row (any of 5), random sign
        jj = top % shape5[1]
        n2 = np.array([np.mean(rng.choice([-1, 1], K) * vn[rng.integers(0, shape5[0], K) * shape5[1] + jj]) for _ in range(nnull)])
        # N3: cells matched on decile of mini |t(other - dev)|, signed so that mini's value has the selected cell's sign
        smsel = np.sign(sg * vm[top]); smsel[smsel == 0] = 1
        pools = [np.flatnonzero(dec == dec[f]) for f in top]
        n3 = np.empty(nnull)
        for r in range(nnull):
            pick = np.array([rng.choice(p) for p in pools])
            n3[r] = np.mean(smsel * np.sign(vm[pick]) * vn[pick])
        n3m = np.array([rng.choice(p) for p in pools for _ in range(1)])
        out[K] = {"mean_abs_t_sel": float(np.mean(np.abs(g[top]))), "mini": xm, "nano": xn, "ratio": xn / xm if xm else np.nan,
                  "N1_sd": float(n1.std()), "N1_z": xn / n1.std(), "N1_p_upper": float((1 + np.sum(n1 >= xn)) / (1 + nnull)),
                  "N2_mean": float(n2.mean()), "N2_sd": float(n2.std()), "N2_p_upper": float((1 + np.sum(n2 >= xn)) / (1 + nnull)),
                  "N3_mean": float(n3.mean()), "N3_sd": float(n3.std()), "N3_p_lower": float((1 + np.sum(n3 <= xn)) / (1 + nnull)),
                  "N3_p_upper": float((1 + np.sum(n3 >= xn)) / (1 + nnull))}
        o = out[K]
        print(f"  dev={dev_name} other={other_name} K={K:2d} |t_sel|={o['mean_abs_t_sel']:.2f}  mini {xm:+.2f}  nano {xn:+.2f}  ratio {o['ratio']:.2f} | "
              f"N1 z={o['N1_z']:.2f} p={o['N1_p_upper']:.4f} | N2 mean {o['N2_mean']:+.2f} sd {o['N2_sd']:.2f} p={o['N2_p_upper']:.4f} | "
              f"N3 (generic replication) mean {o['N3_mean']:+.2f} sd {o['N3_sd']:.2f} p_lower={o['N3_p_lower']:.3f}")
    return out


print("(a) A's top-K deviant cells (five candidates); mirror: CO's own top-K deviant cells")
res["a_A_cells"] = block("A", "CO")
res["a_mirror_CO_cells"] = block("CO", "A")

# Bootstrap over instructions for the ratio difference A-cells vs CO-mirror (selection redone in each draw)
def boot_ratio(nboot=400, K=12):
    ni = m5["A"].shape[1]; out = []
    for b in range(nboot):
        ii = rng.integers(0, ni, ni)
        mm = {k: v[:, ii] for k, v in m5.items()}; nn = {k: v[:, ii] for k, v in n5.items()}
        cs = np.mean([mm[c] for c in C.CONTROLS], axis=0)
        row = []
        for dev, oth in (("A", "CO"), ("CO", "A")):
            g = T(cs - mm[dev]).ravel(); top = np.argsort(-np.abs(g))[:K]; sg = np.sign(g[top])
            xm = np.mean(sg * T(mm[oth] - mm[dev]).ravel()[top]); xn = np.mean(sg * T(nn[oth] - nn[dev]).ravel()[top])
            row += [xm, xn]
        out.append(row)
    return np.array(out)
bt = boot_ratio()
res["a_boot_K12"] = {"A_mini": np.percentile(bt[:, 0], [2.5, 50, 97.5]).tolist(), "A_nano": np.percentile(bt[:, 1], [2.5, 50, 97.5]).tolist(),
                     "CO_mini": np.percentile(bt[:, 2], [2.5, 50, 97.5]).tolist(), "CO_nano": np.percentile(bt[:, 3], [2.5, 50, 97.5]).tolist(),
                     "nano_A_minus_CO": np.percentile(bt[:, 1] - bt[:, 3], [2.5, 50, 97.5]).tolist(),
                     "ratio_A": np.percentile(bt[:, 1] / bt[:, 0], [2.5, 50, 97.5]).tolist(),
                     "ratio_CO": np.percentile(bt[:, 3] / bt[:, 2], [2.5, 50, 97.5]).tolist()}
print("    bootstrap over instructions (K=12, selection redone):", {k: [round(x, 2) for x in v] for k, v in res["a_boot_K12"].items()})

# (b) eight tests' peak cells vs A, six candidates, anthropic row excluded
print("\n(b) the eight tests' top cells against A (six candidates), anthropic row excluded")
m6 = {k: O6(D[k]) for k in ["A", "CO"] + list(C.CONTROLS)}; n6 = {"A": O6(N["A"]), "CO": O6(N["CO"])}
um6 = T(m6["CO"] - m6["A"]); un6 = T(n6["CO"] - n6["A"])
ia = cands.index("anthropic")
rows = []; sm = []; sn = []
for k in C.CONTROLS:
    t = C.tgrid(m6[k] - m6["A"])[0]; ta = np.abs(np.nan_to_num(t)); ta[ia] = -1
    i, j = np.unravel_index(np.argmax(ta), ta.shape); s = np.sign(t[i, j])
    rows.append({"test": k, "cand": cands[i], "axis": C.AXES[j], "t_test": float(t[i, j]),
                 "is_global_peak": bool(np.nanargmax(np.abs(np.nan_to_num(t))) == np.ravel_multi_index((i, j), t.shape)),
                 "mini_signed_t_CO_minus_A": float(s * um6[i, j]), "nano_signed_t_CO_minus_A": float(s * un6[i, j])})
    sm.append(s * um6[i, j]); sn.append(s * un6[i, j])
    print(f"  {k:24s} {cands[i]:18s} {C.AXES[j][:46]:46s} t={t[i,j]:+.2f} global_peak={rows[-1]['is_global_peak']} | mini {s*um6[i,j]:+.2f} nano {s*un6[i,j]:+.2f}")
# top-5 cells per test (non-anthropic) pooled
pm, pn = [], []
for k in C.CONTROLS:
    t = np.nan_to_num(C.tgrid(m6[k] - m6["A"])[0]); ta = np.abs(t).copy(); ta[ia] = -1
    for f in np.argsort(-ta, axis=None)[:5]:
        i, j = np.unravel_index(f, ta.shape); s = np.sign(t[i, j]); pm.append(s * um6[i, j]); pn.append(s * un6[i, j])
vn6 = un6.copy(); vn6[ia] = np.nan; flat = vn6.ravel()[~np.isnan(vn6.ravel())]
nul = np.array([np.mean(rng.choice([-1, 1], 8) * rng.choice(flat, 8, replace=False)) for _ in range(20000)])
nul40 = np.array([np.mean(rng.choice([-1, 1], 40) * rng.choice(flat, 40, replace=False)) for _ in range(20000)])
res["b_peaks"] = {"cells": rows, "mean_mini": float(np.mean(sm)), "mean_nano": float(np.mean(sn)),
                  "nano_null_sd_8": float(nul.std()), "nano_p_upper_8": float((1 + np.sum(nul >= np.mean(sn))) / 20001),
                  "top5_each_mean_mini": float(np.mean(pm)), "top5_each_mean_nano": float(np.mean(pn)),
                  "nano_null_sd_40": float(nul40.std()), "nano_p_upper_40": float((1 + np.sum(nul40 >= np.mean(pn))) / 20001)}
print(f"  mean over 8 peaks: mini {np.mean(sm):+.2f}  nano {np.mean(sn):+.2f} (random-cell null sd {nul.std():.2f}, p_upper {res['b_peaks']['nano_p_upper_8']:.4f})")
print(f"  top-5 cells of each test (40): mini {np.mean(pm):+.2f}  nano {np.mean(pn):+.2f} (null sd {nul40.std():.2f}, p_upper {res['b_peaks']['nano_p_upper_40']:.4f})")

# (c) benchmarks
print("\n(c) benchmarks")
bench = {}
for K in (6, 12, 20):
    top = np.argsort(-np.abs(um6[ia]))[:K]; s = np.sign(um6[ia][top])
    bench[f"CO_anthropic_row_K{K}"] = [float(np.mean(np.abs(um6[ia][top]))), float(np.mean(s * un6[ia][top]))]
    top = np.argsort(-np.abs(uM))[:K]; s = np.sign(uM[top])
    bench[f"generic_top_CO_minus_A_5cand_K{K}"] = [float(np.mean(np.abs(uM[top]))), float(np.mean(s * uN[top]))]
for k, v in bench.items():
    print(f"  {k:36s} mini {v[0]:.2f} -> nano {v[1]:+.2f}  ratio {v[1]/v[0]:.2f}")
res["c_bench"] = bench

# (d) registered test CO vs A on five candidates, mini vs nano
print("\n(d) registered test, CO vs A, five candidates")
orders5 = C.perm_orders(n_c=5)
r_m = C.run_test(C.rates(D["CO"])[keep], C.rates(D["A"])[keep], orders5)
r_n = C.run_test(C.rates(N["CO"])[keep], C.rates(N["A"])[keep], orders5)
r_mB = C.run_test(C.rates(D["CO"])[keep], C.rates(D["B"])[keep], orders5)
for name, r in (("mini CO|A", r_m), ("nano CO|A", r_n), ("mini CO|B", r_mB)):
    t = np.nan_to_num(r["t"]); i, j = np.unravel_index(np.argmax(np.abs(t)), t.shape)
    print(f"  {name}: S={r['S']:.3f} p={r['p']:.4f} peak {c5[i]} x {C.AXES[j]} t={t[i,j]:+.2f}")
    res[f"d_{name}"] = {"S": r["S"], "p": r["p"], "peak": [c5[i], C.AXES[j], float(t[i, j])]}
# six-candidate CO vs A under both judges (positive control)
orders6 = C.perm_orders()
for name, (pt, pb) in (("mini6 CO|A", (D["CO"], D["A"])), ("nano6 CO|A", (N["CO"], N["A"]))):
    r = C.run_test(C.rates(pt), C.rates(pb), orders6)
    t = np.nan_to_num(r["t"]); i, j = np.unravel_index(np.argmax(np.abs(t)), t.shape)
    print(f"  {name}: S={r['S']:.3f} p={r['p']:.4f} peak {cands[i]} x {C.AXES[j]} t={t[i,j]:+.2f}")
    res[f"d_{name}"] = {"S": r["S"], "p": r["p"], "peak": [cands[i], C.AXES[j], float(t[i, j])]}
print("wrote", dump(res, "d01_nano_replication.json"))
