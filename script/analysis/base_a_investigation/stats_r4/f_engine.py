"""Round 4 draw engine: exact registered tests (10,000 permutations, seed 20260726) under new designs.

Modes
  shuf         The eight controls' replies are permuted among the eight labels at every slot
               (pseudo-controls: they keep the pattern all controls share, realistic noise and the
               judge's axis-order pairing, and lose each control's own structure). An independent
               A/B reply swap gives a pseudo-base pair (A', B'). Tests, six and five candidates:
                 sib   pseudo-control k against the mean of the other seven pseudo-controls
                 A, B  pseudo-control k against the real base A, the real base B
                 A2,B2 pseudo-control k against A', B'
  tboot        Each real control's 16 replies per (candidate, instruction) are resampled with
               replacement from its own replies (realized structure treated as truth, fresh noise).
               Same tests (sib against the mean of the other seven bootstrapped controls).
  prompt       A and B trade whole prompts (all 16 replies of one candidate x instruction).
  instruction  A and B trade whole instructions (all six candidates' prompts).
               For both: the ten targets (six candidates) and eleven (five candidates, adds CO)
               against pseudo-A and pseudo-B. Draw 0 is the identity (real A, B) as a check.
  instructionS, antiS   the same designs with S only (no permutation null), for S-scale statistics.
  anti         Fresh-noise antithetic bootstrap with base noise matched to the real pair: per
               (candidate, instruction) cell, r* = mean of 16 replies drawn with replacement from the
               pooled 32 of A and B, e = (r* - pooled mean) / sqrt(2), pseudo-A = M + e,
               pseudo-B = M - e, M = (rate_A + rate_B) / 2. Each pseudo-base then deviates from the
               truth by about one base's noise (M's plus e's) and pseudo-A - pseudo-B has the
               variance of a real A - B. Same targets as prompt mode.
Usage: f_engine.py <mode> <n_draws> <n_workers>
"""
from __future__ import annotations

import os

os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import sys  # noqa: E402
import time  # noqa: E402
from multiprocessing import Pool  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r4c as Q  # noqa: E402

G = {}


def init():
    d = Q.data()
    R = d["R"]
    G["Rc"] = np.stack([R[k] for k in Q.CONTROLS])
    G["RA"], G["RB"] = R["A"], R["B"]
    G["PA"], G["PB"] = Q.rates(R["A"]), Q.rates(R["B"])
    G["OT"] = {"six": np.stack([Q.ovr(Q.rates(R[k])) for k in Q.TEN]),
               "five": np.stack([Q.ovr(Q.rates(R[k])[d["keep5"]]) for k in Q.ELEVEN])}
    for tag in ("six", "five"):
        Q.F.E_for(Q.world(tag)[1])


def ctl_tests(Pc, PA2, PB2):
    """Pc (8, 6, 36, 101) control rates. Returns {tag: {fam: (S, p)}}. PA2 None skips the A2/B2 tests."""
    out = {}
    for tag in ("six", "five"):
        kp, nc = Q.world(tag)
        O = Q.ovr(Pc[:, kp])
        sib = (O.sum(0, keepdims=True) - O) / 7.0
        r = {}
        fams = [("sib", sib), ("A", Q.ovr(G["PA"][kp])), ("B", Q.ovr(G["PB"][kp]))]
        if PA2 is not None:
            fams += [("A2", Q.ovr(PA2[kp])), ("B2", Q.ovr(PB2[kp]))]
        for fam, OB in fams:
            S, p, _ = Q.test(O, OB, nc)
            r[fam] = (S, p)
        out[tag] = r
    return out


def base_tests(PA2, PB2, s_only=False):
    d = Q.data()
    out = {}
    for tag, kp in (("six", list(range(6))), ("five", d["keep5"])):
        nc = len(kp)
        r = {}
        for fam, Pb in (("A2", PA2), ("B2", PB2)):
            if s_only:
                S = Q.S_only(G["OT"][tag] - Q.ovr(Pb[kp])[None])
                r[fam] = (S, np.full_like(S, np.nan))
            else:
                S, p, _ = Q.test(G["OT"][tag], Q.ovr(Pb[kp]), nc)
                r[fam] = (S, p)
        out[tag] = r
    return out


def one(args):
    mode, idx = args
    code = {"shuf": 1, "tboot": 2, "prompt": 3, "instruction": 4, "anti": 5, "instructionS": 6, "antiS": 7}[mode]
    rng = np.random.default_rng([20261113, 4, code, idx])
    RA, RB = G["RA"], G["RB"]
    if mode in ("shuf", "tboot"):
        if mode == "shuf":
            Rc = Q.shuffle_controls(rng, G["Rc"])
        else:
            Rc = np.stack([Q.boot_within_cell(rng, G["Rc"][q]) for q in range(8)])
        if mode == "tboot":                                   # tboot: sib, A, B only (cost)
            return idx, ctl_tests(Q.rates(Rc), None, None)
        m = Q.swap_mask(rng, "reply", RA, RB)
        XA, XB = Q.swapped(RA, RB, m)
        return idx, ctl_tests(Q.rates(Rc), Q.rates(XA), Q.rates(XB))
    if mode in ("prompt", "instruction", "instructionS"):
        m = Q.swap_mask(rng, mode.rstrip("S"), RA, RB)
        if idx == 0:
            m = np.zeros_like(m)
        XA, XB = Q.swapped(RA, RB, m)
        return idx, base_tests(Q.rates(XA), Q.rates(XB), s_only=mode.endswith("S"))
    if mode in ("anti", "antiS"):
        pool = np.concatenate([RA, RB], axis=2)                 # (6, 36, 32, 101)
        pm = np.nanmean(pool, axis=2)
        X = Q.boot_within_cell(rng, pool)[:, :, :16]           # 16 draws with replacement from the pooled 32
        e = (np.nanmean(X, axis=2) - pm) / np.sqrt(2.0)
        M = 0.5 * (G["PA"] + G["PB"])
        return idx, base_tests(M + e, M - e, s_only=mode.endswith("S"))
    raise ValueError(mode)


def main():
    mode, n, nw = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    t0 = time.time()
    res = []
    with Pool(nw, initializer=init) as pool:
        for k, r in enumerate(pool.imap_unordered(one, [(mode, i) for i in range(n)], chunksize=2)):
            res.append(r)
            if (k + 1) % 100 == 0:
                print(f"{mode} {k+1}/{n} {time.time()-t0:.0f}s", flush=True)
    res.sort(key=lambda r: r[0])
    save = {}
    for tag in ("six", "five"):
        for fam in res[0][1][tag]:
            save[f"S_{tag}_{fam}"] = np.array([r[1][tag][fam][0] for r in res])
            save[f"p_{tag}_{fam}"] = np.array([r[1][tag][fam][1] for r in res])
    np.savez(Q.OUT / f"draws_{mode}_{n}.npz", **save)
    print(f"done {mode} n={n} in {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
