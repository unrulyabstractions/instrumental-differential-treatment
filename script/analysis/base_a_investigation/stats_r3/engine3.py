"""Round 3 draws engine: exact registered tests of the fixed real targets against base pairs drawn
under a systematic-share model. Reuses stats_r2/fast.py (exact registered test, 22/22 stored
pairings reproduced).

Two reply-level models of "a share lam of the realized A-minus-B difference is systematic":

  pswap lam  (the critic's request). At every (candidate, instruction, s) slot where both bases have a
             reply, base A's and base B's replies trade places with probability q = (1 - lam) / 2.
             pseudo-A = A with some replies swapped in from B; pseudo-B is the complement.
             E[pseudo-A - pseudo-B] = lam * (A - B) per slot, so a share lam of the realized difference
             stays in place. The remaining noise is drawn from the same two realized replies, so its
             variance shrinks by (1 - lam^2); at lam = 1 the pair is exactly (A, B) with no noise.
  mboot lam  (fresh-noise version). Each of the 16 replies of pseudo-A in a (candidate, instruction)
             cell is drawn with replacement: from A's replies with probability (1 + lam) / 2, else
             from B's. pseudo-B is drawn independently the other way round. The expected cell-rate
             difference is lam * (rate_A - rate_B) per (candidate, instruction, axis) and every draw
             carries fresh resampling noise. lam = 0: both from the pooled 32 (fresh-noise null).
             lam = 1: pseudo-A is a bootstrap of A's own replies, pseudo-B of B's (the knife-edge
             bootstrap, T5).

Per draw it stores S and exact p (10,000 registered permutations, seed 20260726) for
  six candidates : the eight nulls and the two synthetic-document arms, against pseudo-A and pseudo-B;
  five candidates (anthropic dropped before one-vs-rest): the same ten plus contextual_optimism.
Usage: engine3.py <pswap|mboot> <lam> <n_draws> <n_workers>
"""
from __future__ import annotations

import os

os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import sys  # noqa: E402
import time  # noqa: E402
from multiprocessing import Pool  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "stats_r2"))
import fast as F  # noqa: E402
from fast import C  # noqa: E402

OUT = HERE / "out"
OUT.mkdir(exist_ok=True)
G = {}


def init():
    D = F.load()
    cands = D["_cands"]
    keep = [i for i, c in enumerate(cands) if c != "anthropic"]
    P = {k: C.rates(v) for k, v in D.items() if not k.startswith("_")}
    G["RA"], G["RB"] = D["A"], D["B"]
    availA = ~np.isnan(D["A"]).all(3)
    availB = ~np.isnan(D["B"]).all(3)
    G["both"] = availA & availB
    G["nA"], G["nB"] = availA.sum(2), availB.sum(2)
    # available slots first (stable), so slot_order[..., k] for k < n is the k-th available slot
    G["ordA"] = np.argsort(~availA, axis=2, kind="stable")
    G["ordB"] = np.argsort(~availB, axis=2, kind="stable")
    G["pool"] = np.concatenate([D["A"], D["B"]], axis=2)
    G["keep"] = keep
    G["OT6"] = np.stack([C.ovr(P[k]) for k in F.TEN])
    G["OT5"] = np.stack([C.ovr(P[k][keep]) for k in F.TEN + ["CO"]])
    G["E6"] = F.E_for(6)
    G["E5"] = F.E_for(5)


def tests(pb):
    S6, p6, _ = F.test_many(G["OT6"], C.ovr(pb), 6, G["E6"])
    S5, p5, _ = F.test_many(G["OT5"], C.ovr(pb[G["keep"]]), 5, G["E5"])
    return S6, p6, S5, p5


def draw_slots(rng, n, order):
    u = rng.random(order.shape)
    k = np.floor(u * n[..., None]).astype(int)
    return np.take_along_axis(order, k, axis=2)


def one(args):
    mode, lam, idx = args
    rng = np.random.default_rng([20261113, 3, {"pswap": 1, "mboot": 2}[mode], int(round(lam * 1000)), idx])
    RA, RB = G["RA"], G["RB"]
    if mode == "pswap":
        q = (1.0 - lam) / 2.0
        m = (rng.random(RA.shape[:3]) < q) & G["both"]
        XA = np.where(m[..., None], RB, RA)
        XB = np.where(m[..., None], RA, RB)
        frac = float(m.sum() / G["both"].sum())
    else:
        pr = (1.0 + lam) / 2.0
        sA = draw_slots(rng, G["nA"], G["ordA"])
        sB = draw_slots(rng, G["nB"], G["ordB"])
        own = rng.random(RA.shape[:3]) < pr
        ixA = np.where(own, sA, 16 + sB)
        sA2 = draw_slots(rng, G["nA"], G["ordA"])
        sB2 = draw_slots(rng, G["nB"], G["ordB"])
        own2 = rng.random(RA.shape[:3]) < pr
        ixB = np.where(own2, 16 + sB2, sA2)
        XA = np.take_along_axis(G["pool"], ixA[..., None], axis=2)
        XB = np.take_along_axis(G["pool"], ixB[..., None], axis=2)
        frac = float(np.mean(own))
    res = []
    for X in (XA, XB):
        res.append(tests(F.rates_of(X)))
    return idx, frac, res


def main():
    mode, lam, n, nw = sys.argv[1], float(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
    t0 = time.time()
    with Pool(nw, initializer=init) as pool:
        out = []
        for k, r in enumerate(pool.imap_unordered(one, [(mode, lam, i) for i in range(n)], chunksize=4)):
            out.append(r)
            if (k + 1) % 250 == 0:
                print(f"{mode} lam={lam} {k+1}/{n} draws, {time.time()-t0:.0f}s", flush=True)
    out.sort(key=lambda r: r[0])
    save = {
        "S6": np.array([[b[0] for b in r[2]] for r in out]),
        "p6": np.array([[b[1] for b in r[2]] for r in out]),
        "S5": np.array([[b[2] for b in r[2]] for r in out]),
        "p5": np.array([[b[3] for b in r[2]] for r in out]),
        "frac": np.array([r[1] for r in out]),
        "targets6": np.array(F.TEN), "targets5": np.array(F.TEN + ["CO"]),
    }
    np.savez(OUT / f"draws_{mode}_lam{lam:.2f}_{n}.npz", **save)
    print(f"done {mode} lam={lam} n={n} in {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
