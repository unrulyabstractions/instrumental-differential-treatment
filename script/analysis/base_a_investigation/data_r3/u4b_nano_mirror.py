"""U4 mirror. Is base A's departure from B more 'textual' under nano than CO's departure from B?
Select cells by mini t(B - X) for X = A (base A's departure) and X = CO (CO's departure), five candidates,
informative cells; measure s * t(Y - X) under mini and nano with Y the other nano-judged sample.
Bootstrap over the 36 instructions (selection redone in every draw) for the difference of nano values and of
ratios between the A-side and the CO-side selection."""
import numpy as np, warnings
from r3common import C, DC, NULLS, dump
warnings.simplefilter("ignore")
D = C.load_all(); cands = D["_cands"]; NN = DC.load_nano()
keep = [i for i, c in enumerate(cands) if c != "anthropic"]
yes = np.nansum(NN["A"][keep], axis=(1, 2)) + np.nansum(NN["CO"][keep], axis=(1, 2)); inf = (yes >= 20)
def T(x): return np.nan_to_num(C.tgrid(x)[0])
def run(idx):
    m = {k: C.ovr(C.rates(D[k][keep][:, idx])) for k in ("A", "B", "CO")}
    n = {k: C.ovr(C.rates(NN[k][keep][:, idx])) for k in ("A", "CO")}
    out = {}
    for X, Y in (("A", "CO"), ("CO", "A")):
        g = T(m["B"] - m[X]); gi = np.where(inf, np.abs(g), -1).ravel()
        vm = T(m[Y] - m[X]).ravel(); vn = T(n[Y] - n[X]).ravel()
        for K in (6, 12, 20):
            top = np.argsort(-gi)[:K]; s = np.sign(g.ravel()[top])
            out[(X, K)] = (np.mean(s * vm[top]), np.mean(s * vn[top]))
    return out
obs = run(np.arange(36))
rng = np.random.default_rng(5); boots = []
for _ in range(1000):
    boots.append(run(rng.integers(0, 36, 36)))
res = {}
for K in (6, 12, 20):
    am, an = obs[("A", K)]; cm, cn = obs[("CO", K)]
    dn = np.array([b[("A", K)][1] - b[("CO", K)][1] for b in boots])
    dr = np.array([b[("A", K)][1] / b[("A", K)][0] - b[("CO", K)][1] / b[("CO", K)][0] for b in boots])
    res[f"K{K}"] = {"A_departure": {"mini": am, "nano": an, "ratio": an / am}, "CO_departure": {"mini": cm, "nano": cn, "ratio": cn / cm},
                    "nano_diff_A_minus_CO": an - cn, "nano_diff_ci95": np.percentile(dn, [2.5, 97.5]).tolist(),
                    "ratio_diff_ci95": np.percentile(dr, [2.5, 97.5]).tolist()}
    print(f"K={K:2d} A's departure from B: mini {am:+.2f} nano {an:+.2f} ratio {an/am:.2f} | CO's departure from B: mini {cm:+.2f} nano {cn:+.2f} ratio {cn/cm:.2f}"
          f" | nano A-CO {an-cn:+.2f} CI {np.percentile(dn,[2.5,97.5]).round(2).tolist()} ratio diff CI {np.percentile(dr,[2.5,97.5]).round(2).tolist()}")
dump(res, "u4b_nano_mirror.json")
