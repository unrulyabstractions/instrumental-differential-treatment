"""S1. Twin test with inference: does contextual_optimism (CO), sampled in base A's own vLLM 0.26.0
session, share base A's deviation?

Deviant sample X (A, or B for the mirror). Reference: cons = mean one-vs-rest gap of the eight nulls.
Selection: the top-K cells of |t(cons - X)| (CO is not used). For each comparator Y:
    T_Y = mean over the top-K cells of sign(t(cons - X)) * t(Y - X).
T_Y is about 0 when Y shares X's deviation and positive when Y is independent of it.
Comparators: CO, the other base, the two synthetic-document arms. Independent reference
IND = mean of (other base, sd_ai_welfare_poisoning, sd_emotional_bond); shared fraction
f = 1 - T_CO / T_IND (f=1: CO shares X's deviation fully; f=0: CO is as independent as the others).
Also f_base = 1 - T_CO / T_other_base.
Worlds: 'five' (anthropic dropped before one-vs-rest), 'six_noanth' (six-candidate one-vs-rest,
anthropic row left out of selection and evaluation).
Inference: bootstrap over the 36 instructions (same resample for every sample), selection redone in
every draw, 4,000 draws, percentile 95% intervals. Mirror: X = B.
"""
import json

import numpy as np

import fast as F
from fast import C

D = F.load()
cands = D["_cands"]
P = {k: C.rates(v) for k, v in D.items() if not k.startswith("_")}
keep5 = [i for i, c in enumerate(cands) if c != "anthropic"]
worlds = {
    "five": ({k: C.ovr(v[keep5]) for k, v in P.items()}, None),
    "six_noanth": ({k: C.ovr(v) for k, v in P.items()}, [i for i, c in enumerate(cands) if c != "anthropic"]),
}
KS = (6, 12, 20, 40)
NB = 4000
rng = np.random.default_rng(7101)
boots = [np.arange(36)] + [rng.integers(0, 36, 36) for _ in range(NB)]


def tg(d):
    t = C.tgrid_fast(d)[0]
    return np.where(np.isfinite(t), t, 0.0)


def stats(O, rows, X, comps, idx):
    cons = np.mean([O[c][:, idx] for c in F.CONTROLS], axis=0)
    ox = O[X][:, idx]
    g = tg(cons - ox)
    if rows is not None:
        g = g[rows]
    tY = {}
    for y in comps:
        t = tg(O[y][:, idx] - ox)
        tY[y] = t[rows] if rows is not None else t
    out = {}
    order = np.argsort(-np.abs(g), axis=None)
    for K in KS:
        top = order[:K]
        sg = np.sign(g.ravel()[top])
        out[K] = {y: float(np.mean(sg * tY[y].ravel()[top])) for y in comps}
    return out


res = {}
FARR = {}
for wname, (O, rows) in worlds.items():
    for X, other in (("A", "B"), ("B", "A")):
        comps = ["CO", other, "sd_ai_welfare_poisoning", "sd_emotional_bond"]
        draws = [stats(O, rows, X, comps, idx) for idx in boots]
        key = f"{wname}|deviant={X}"
        res[key] = {}
        for K in KS:
            arr = {y: np.array([d[K][y] for d in draws]) for y in comps}
            ind = (arr[other] + arr["sd_ai_welfare_poisoning"] + arr["sd_emotional_bond"]) / 3
            f = 1 - arr["CO"] / ind
            fb = 1 - arr["CO"] / arr[other]
            diff = ind - arr["CO"]
            q = lambda a: [float(np.quantile(a[1:], 0.025)), float(np.quantile(a[1:], 0.975))]
            res[key][K] = {
                "T": {y: float(arr[y][0]) for y in comps}, "T_ci": {y: q(arr[y]) for y in comps},
                "T_IND": float(ind[0]), "f": float(f[0]), "f_ci95": q(f),
                "f_base": float(fb[0]), "f_base_ci95": q(fb),
                "IND_minus_CO": float(diff[0]), "IND_minus_CO_ci95": q(diff),
                "P_boot_f_le_0": float(np.mean(f[1:] <= 0)), "P_boot_f_ge_1": float(np.mean(f[1:] >= 1)),
                "f_boot_mean": float(np.mean(f[1:])), "f_boot_sd": float(np.std(f[1:])),
                "f_basic_ci95": [float(2 * f[0] - np.quantile(f[1:], 0.975)), float(2 * f[0] - np.quantile(f[1:], 0.025))],
                "f_normal_ci95": [float(f[0] - 1.96 * np.std(f[1:])), float(f[0] + 1.96 * np.std(f[1:]))],
            }
            FARR[(wname, X, K)] = f
            r = res[key][K]
            print(f"{key:24s} K={K:2d} T: " + " ".join(f"{y[:6]}={r['T'][y]:+.2f}" for y in comps)
                  + f" | f={r['f']:+.2f} [{r['f_ci95'][0]:+.2f},{r['f_ci95'][1]:+.2f}]"
                  + f" f_base={r['f_base']:+.2f} [{r['f_base_ci95'][0]:+.2f},{r['f_base_ci95'][1]:+.2f}]"
                  + f" IND-CO={r['IND_minus_CO']:+.2f} [{r['IND_minus_CO_ci95'][0]:+.2f},{r['IND_minus_CO_ci95'][1]:+.2f}]"
                  + f" | f boot sd {r['f_boot_sd']:.2f} basic [{r['f_basic_ci95'][0]:+.2f},{r['f_basic_ci95'][1]:+.2f}]", flush=True)
# difference of shared fractions, A vs mirror B, same bootstrap draws
res["f_A_minus_f_mirror"] = {}
for wname in worlds:
    for K in KS:
        dd = FARR[(wname, "A", K)] - FARR[(wname, "B", K)]
        res["f_A_minus_f_mirror"][f"{wname}|K={K}"] = {"obs": float(dd[0]), "boot_sd": float(np.std(dd[1:])),
            "pct_ci95": [float(np.quantile(dd[1:], 0.025)), float(np.quantile(dd[1:], 0.975))]}
        print(f"f(A) - f(mirror B) {wname} K={K}: {dd[0]:+.2f} (boot sd {np.std(dd[1:]):.2f})")
json.dump(res, open(F.OUT / "s1_twin.json", "w"), indent=1)
