"""Which parts of base A carry the low p-values? Swap base A for base B piece by piece.

1. Reply mixing: per cell, n_A replies from A and 16 - n_A from B (n_A = 16..0), 20 random
   draws per level; median of the eight p-values.
2. Axis swaps (targeted): for each test k, rank axes by A's deviation from a reference
   that excludes k (the other seven nulls + base B), max over candidates of |t|; swap the
   top m axes of A (all candidates) for B's; recompute p_k. Control: m random axes.
3. Candidate swaps: base A with one candidate's rows taken from B.
4. Instruction swaps: A on a random half of the instructions, B on the other half.
All tests use the registered 10,000 permutations and seed.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (AXES, CONTROLS, OUT, excess, load_all, ovr, perm_null, perm_orders,  # noqa
                    rates, smax, tail_p, tgrid)

D = load_all()
cands = D["_cands"]
P = {k: rates(v) for k, v in D.items() if not k.startswith("_")}
O = {k: ovr(v) for k, v in P.items()}
orders = perm_orders()
rng = np.random.default_rng(99)
which = sys.argv[1:] or ["mix", "axis", "cand", "instr"]


def p_of(pt, pb):
    d = excess(pt, pb)
    s = float(smax(tgrid(d)[0]))
    return tail_p(perm_null(d, orders), s), s


def eight(pb):
    return [p_of(P[c], pb)[0] for c in CONTROLS]


res = {}
if "mix" in which:
    out = {}
    RA, RB = D["A"], D["B"]
    for nA in (16, 12, 8, 4, 0):
        meds, allp = [], []
        for r in range(20 if nA not in (16, 0) else 1):
            ia = np.argsort(rng.random(RA.shape[:3]), axis=2)[:, :, :nA]
            ib = np.argsort(rng.random(RB.shape[:3]), axis=2)[:, :, :16 - nA]
            pool = np.concatenate([np.take_along_axis(RA, ia[..., None], 2),
                                   np.take_along_axis(RB, ib[..., None], 2)], axis=2)
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                pb = np.nanmean(pool, axis=2)
            ps = eight(pb)
            meds.append(float(np.median(ps))); allp.append(ps)
        out[nA] = {"median_of_medians": float(np.median(meds)), "medians": meds,
                   "mean_frac_lt_0.07": float(np.mean(np.array(allp) < 0.07))}
        print(f"mix nA={nA:2d}: median p over draws {np.median(meds):.3f} "
              f"[{np.min(meds):.3f}, {np.max(meds):.3f}] frac(p<.07)={out[nA]['mean_frac_lt_0.07']:.2f}", flush=True)
    res["mix"] = out

if "axis" in which:
    out = {}
    for k, c in enumerate(CONTROLS):
        ref = np.mean([O[o] for o in CONTROLS if o != c] + [O["B"]], axis=0)
        g = np.abs(tgrid(ref - O["A"])[0])           # A's deviation, independent of target k
        rank = np.argsort(-np.nanmax(g, axis=0))     # axes by A's worst cell
        row = {}
        for m in (0, 1, 2, 3, 5, 10, 20, 50, 101):
            pb = P["A"].copy()
            if m:
                ax = rank[:m]
                pb[:, :, ax] = P["B"][:, :, ax]
            row[m] = p_of(P[c], pb)[0]
        # random-axis control at m = 5 and 10
        ctrl = {}
        for m in (5, 10):
            ps = []
            for r in range(30):
                ax = rng.choice(len(AXES), m, replace=False)
                pb = P["A"].copy(); pb[:, :, ax] = P["B"][:, :, ax]
                ps.append(p_of(P[c], pb)[0])
            ctrl[m] = float(np.median(ps))
        out[c] = {"targeted": row, "random_median": ctrl,
                  "top_axes": [AXES[a] for a in rank[:5]]}
        print(f"axis-swap {c:24s} " + " ".join(f"m{m}:{v:.3f}" for m, v in row.items()) +
              f" | random m5:{ctrl[5]:.3f} m10:{ctrl[10]:.3f}", flush=True)
    for m in (0, 1, 2, 3, 5, 10, 20, 50, 101):
        print(f"  median over eight at m={m}: {np.median([out[c]['targeted'][m] for c in CONTROLS]):.3f}")
    res["axis"] = out

if "cand" in which:
    out = {}
    for ci, cn in enumerate(cands):
        pb = P["A"].copy(); pb[ci] = P["B"][ci]
        ps = eight(pb)
        out[cn] = ps
        print(f"cand-swap {cn:20s} median={np.median(ps):.3f} ps={[round(x, 3) for x in ps]}", flush=True)
    res["cand"] = out

if "instr" in which:
    meds = []
    for r in range(40):
        S = rng.choice(36, 18, replace=False)
        pb = P["B"].copy(); pb[:, S] = P["A"][:, S]
        meds.append(float(np.median(eight(pb))))
    res["instr"] = {"medians": meds}
    print(f"instr half-swap: median p {np.median(meds):.3f} [{np.min(meds):.3f}, {np.max(meds):.3f}] "
          f"quartiles {np.quantile(meds, .25):.3f} {np.quantile(meds, .75):.3f}", flush=True)
json.dump(res, open(OUT / f"swap_{'_'.join(which)}.json", "w"), indent=1)
