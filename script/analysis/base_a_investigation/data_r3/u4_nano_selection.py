"""U4. Why do base A's top cells replicate under gpt-4.1-nano at 0.66-0.97 while generic cells replicate at ~0.20?

Hypothesis: selecting on t(cons8 - A) picks cells where the fine-tunes share a real text shift relative to the base.
CO is a fine-tune too, so t(CO - A) at those cells carries that shared shift, which is text and replicates under
any judge. Selecting on t(B - A) instead picks base A's own departure from another base draw, with no fine-tune
shift in the selection.

Five candidates (anthropic dropped), informative cells only (nano yes count A + CO at that candidate and axis
>= 20 of 1,152; 248 of 505 cells). For each selection rule and K in {6, 12, 20, 40}:
  sign s from the selecting contrast; report mean s*t_mini(CO - A), mean s*t_nano(CO - A), ratio nano/mini,
  and two nulls: random informative cells with random signs (N1), and cells matched to the selected cells on
  the decile of mini |t(CO - A)| with the selected sign rule replaced by sign(t_mini(CO - A)) (N3: what a
  generic mini difference of that size carries under nano).
Selection rules:
  cons8-A  (round 2's rule),  B-A  (base A's own departure from base B),  cons8-B  (fine-tune shift, no A),
  CO-A  (generic: CO's own top cells against A),  (cons8-A) with the fine-tune shift removed: cells where
  |t(cons8 - B)| < 1 among A's cons8-A ranking.
Also reports, at the cons8-A cells, the signed t(cons8 - B) and t(B - A): how much of the selection is the
fine-tune shift versus A's own departure.
"""
from __future__ import annotations

import numpy as np
import warnings
from r3common import C, DC, NULLS, dump

warnings.simplefilter("ignore")
D = C.load_all(); cands = D["_cands"]; NN = DC.load_nano()
keep = [i for i, c in enumerate(cands) if c != "anthropic"]
O5 = lambda R: C.ovr(C.rates(R)[keep])
T = lambda x: np.nan_to_num(C.tgrid(x)[0])
m = {k: O5(D[k]) for k in ["A", "B", "CO"] + NULLS}
n = {"A": O5(NN["A"]), "CO": O5(NN["CO"])}
cons = np.mean([m[k] for k in NULLS], 0)
yes = np.nansum(NN["A"][keep], axis=(1, 2)) + np.nansum(NN["CO"][keep], axis=(1, 2))
inf = (yes >= 20).ravel()
infl = np.flatnonzero(inf)
vm = T(m["CO"] - m["A"]).ravel(); vn = T(n["CO"] - n["A"]).ravel()
sel = {"cons8-A": T(cons - m["A"]).ravel(), "B-A": T(m["B"] - m["A"]).ravel(), "cons8-B": T(cons - m["B"]).ravel(),
       "CO-A (generic)": vm.copy()}
tcB = T(cons - m["B"]).ravel(); tBA = T(m["B"] - m["A"]).ravel()
sel["cons8-A, |t(cons8-B)|<1"] = np.where(np.abs(tcB) < 1, sel["cons8-A"], 0.0)
rng = np.random.default_rng(11)
dec = np.digitize(np.abs(vm), np.quantile(np.abs(vm[infl]), np.linspace(0, 1, 11)[1:-1]))
print(f"informative cells {inf.sum()} of {inf.size}")
res = {"n_informative": int(inf.sum())}
for name, g in sel.items():
    gi = np.where(inf, np.abs(g), -1.0)
    res[name] = {}
    for K in (6, 12, 20, 40):
        top = np.argsort(-gi)[:K]
        top = top[gi[top] > 0]
        s = np.sign(g[top])
        xm = float(np.mean(s * vm[top])); xn = float(np.mean(s * vn[top]))
        n1 = np.array([np.mean(rng.choice([-1, 1], len(top)) * vn[rng.choice(infl, len(top), replace=False)]) for _ in range(10000)])
        # N3: matched on decile of mini |t(CO-A)|, sign = sign of mini t(CO-A)
        n3 = []
        pools = {d: infl[dec[infl] == d] for d in np.unique(dec[infl])}
        for _ in range(4000):
            pick = np.array([rng.choice(pools[dec[c]]) for c in top])
            sg = np.sign(vm[pick]); n3.append((np.mean(sg * vm[pick]), np.mean(sg * vn[pick])))
        n3 = np.array(n3)
        r3 = n3[:, 1].mean() / n3[:, 0].mean()
        res[name][f"K{K}"] = {"n_cells": int(len(top)), "mini": xm, "nano": xn, "ratio": xn / xm if xm else float("nan"),
                              "N1_sd": float(n1.std()), "N1_p_upper": float((1 + (n1 >= xn).sum()) / 10001),
                              "N3_generic_mini": float(n3[:, 0].mean()), "N3_generic_nano": float(n3[:, 1].mean()), "N3_ratio": float(r3),
                              "signed_t_cons8_minus_B_at_cells": float(np.mean(s * tcB[top])), "signed_t_B_minus_A_at_cells": float(np.mean(s * tBA[top]))}
        r = res[name][f"K{K}"]
        print(f"{name:26s} K={K:2d} (n={len(top):2d}) mini {xm:+.2f} nano {xn:+.2f} ratio {r['ratio']:.2f} | N1 sd {r['N1_sd']:.2f} p {r['N1_p_upper']:.4f} | generic(N3) mini {r['N3_generic_mini']:+.2f} nano {r['N3_generic_nano']:+.2f} ratio {r3:.2f}"
              f" | at cells: t(cons8-B) {r['signed_t_cons8_minus_B_at_cells']:+.2f} t(B-A) {r['signed_t_B_minus_A_at_cells']:+.2f}")
dump(res, "u4_nano_selection.json")
