"""Exact registered tests of the real targets against many base draws, in parallel.

Modes (targets always fixed as observed):
  swap   : at every (candidate, instruction, s) slot where both bases have a reply, base A's and
           base B's replies trade places with probability 1/2. Gives a pseudo-A and its complement
           pseudo-B per draw (the S3 null: A and B exchangeable draws of one process).
  bootB  : 16 replies per cell drawn with replacement from base B's 16 (S4a).
  boot32 : 16 replies per cell drawn with replacement from the pooled 32 of A and B (S4a).
Draw 0 of swap mode is the identity (the real A and B), as a check.

Per base draw it records
  six candidates : S and exact p (10,000 registered permutations) for the eight nulls and the two
                   synthetic-document arms;
  five candidates (anthropic dropped before one-vs-rest; swap mode only): the same ten plus
                   contextual_optimism;
  target-free deviance of the base itself: reference-free S (median-of-rest, the repo's
  reference_free_max_test statistic), share of |t| > 2, mean t^2, and the same with the
  mean-of-rest one-vs-rest gap.
Usage: draws_engine.py <mode> <n_draws> <n_workers>
"""
from __future__ import annotations

import os

os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import sys  # noqa: E402
import time  # noqa: E402
import warnings  # noqa: E402
from multiprocessing import Pool  # noqa: E402

import numpy as np  # noqa: E402

import fast as F  # noqa: E402
from fast import C  # noqa: E402

G = {}


def init():
    D = F.load()
    cands = D["_cands"]
    keep = [i for i, c in enumerate(cands) if c != "anthropic"]
    P = {k: C.rates(v) for k, v in D.items() if not k.startswith("_")}
    G["RA"], G["RB"] = D["A"], D["B"]
    G["both"] = ~np.isnan(D["A"]).all(3) & ~np.isnan(D["B"]).all(3)
    G["keep"] = keep
    G["OT6"] = np.stack([C.ovr(P[k]) for k in F.TEN])
    G["OT5"] = np.stack([C.ovr(P[k][keep]) for k in F.TEN + ["CO"]])
    G["E6"] = F.E_for(6)
    G["E5"] = F.E_for(5)


def tests(pb, five=True):
    ob = C.ovr(pb)
    S6, p6, _ = F.test_many(G["OT6"], ob, 6, G["E6"])
    if not five:
        return S6, p6, None, None
    ob5 = C.ovr(pb[G["keep"]])
    S5, p5, _ = F.test_many(G["OT5"], ob5, 5, G["E5"])
    return S6, p6, S5, p5


def median_of_rest(r):
    n = r.shape[0]
    return np.stack([np.median(np.delete(r, c, axis=0), axis=0) for c in range(n)])


def deviance(pb):
    out = []
    for d in (pb - median_of_rest(pb), C.ovr(pb)):
        t = np.abs(C.tgrid_fast(d)[0])
        t = np.where(np.isfinite(t), t, 0.0)
        out += [float(t.max()), float(np.mean(t > 2)), float(np.mean(t ** 2))]
    return out  # rf_S, rf_share2, rf_mean_t2, ovr_S, ovr_share2, ovr_mean_t2


def one(args):
    mode, idx = args
    rng = np.random.default_rng([20261113, {"swap": 1, "bootB": 2, "boot32": 3}[mode], idx])
    RA, RB = G["RA"], G["RB"]
    if mode == "swap":
        m = (rng.random(RA.shape[:3]) < 0.5) & G["both"]
        if idx == 0:
            m[:] = False
        XA = np.where(m[..., None], RB, RA)
        XB = np.where(m[..., None], RA, RB)
        res = []
        for X in (XA, XB):
            pb = F.rates_of(X)
            S6, p6, S5, p5 = tests(pb, True)
            res.append((S6, p6, S5, p5, deviance(pb)))
        return idx, float(m.sum() / G["both"].sum()), res
    if mode == "bootB":
        ix = rng.integers(0, 16, size=RB.shape[:3])
        X = np.take_along_axis(RB, ix[..., None], axis=2)
        fracA = 0.0
    else:
        pool = np.concatenate([RA, RB], axis=2)
        ix = rng.integers(0, 32, size=RA.shape[:3])
        X = np.take_along_axis(pool, ix[..., None], axis=2)
        fracA = float(np.mean(ix < 16))
    pb = F.rates_of(X)
    S6, p6, _, _ = tests(pb, False)
    return idx, fracA, [(S6, p6, None, None, deviance(pb))]


def main():
    mode, n, nw = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    t0 = time.time()
    with Pool(nw, initializer=init) as pool:
        out = []
        for k, r in enumerate(pool.imap_unordered(one, [(mode, i) for i in range(n)], chunksize=4)):
            out.append(r)
            if (k + 1) % 200 == 0:
                print(f"{k+1}/{n} draws, {time.time()-t0:.0f}s", flush=True)
    out.sort(key=lambda r: r[0])
    nb = len(out[0][2])
    S6 = np.array([[b[0] for b in r[2]] for r in out])
    p6 = np.array([[b[1] for b in r[2]] for r in out])
    dev = np.array([[b[4] for b in r[2]] for r in out])
    save = {"S6": S6, "p6": p6, "dev": dev, "frac": np.array([r[1] for r in out]), "targets6": np.array(F.TEN)}
    if mode == "swap":
        save["S5"] = np.array([[b[2] for b in r[2]] for r in out])
        save["p5"] = np.array([[b[3] for b in r[2]] for r in out])
        save["targets5"] = np.array(F.TEN + ["CO"])
    np.savez(F.OUT / f"draws_{mode}_{n}.npz", **save)
    print(f"done {mode} n={n} bases/draw={nb} in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
