"""T3 and T4. Select in one half, test in the other, with a reply-level power model and the mirror.

Design (as stats_r2/s2_s5_split_half.py, with the zero-spread t fix from s2b_power_twin.py): all
samples share one random split of the 16 reply slots into halves. For deviant base X, comparator Y and
each selecting target T: the peak cell c* of t(OvR(T,sel) - OvR(X,sel)) in the selection half; in the
test half, base side b = sign * t(OvR(Y,test) - OvR(X,test))[c*] and target side
a = sign * t(OvR(T,test) - OvR(Y,test))[c*]. Both directions, averaged over splits and targets.

T3 power (X = A, Y = B, the eight nulls, six and five candidates). Data are generated under the
mixture-bootstrap share model of engine3.py: each of the 16 replies of pseudo-A in a (candidate,
instruction) cell is drawn from A's replies with probability (1 + lam) / 2, else from B's, and pseudo-B
the other way round, independently. The expected cell-rate difference is lam times the realized
(candidate, instruction, axis) difference and every draw carries fresh reply-level noise, so a
systematic part replicates across disjoint halves and noise does not. lam = 1 treats A's and B's
realized cell rates as their arms' true rates. The partial swap is also run at lam 0.5 and 0.75 to show
why it cannot calibrate this design: at lam = 1 it returns the observed data, so E[b | lam = 1] equals
the observed b by construction.

Split counts: every replicate also returns the variance over its splits of the per-split statistic, so
the null SD for a 500-split observed value is corrected:
   var_500 = var_64(replicate means) - s2_split / 64 + s2_split / 500.

T4 mirror: X = B, Y = A, selecting targets = the two synthetic-document arms (six candidates); base
side (does B's deviation at their peak cells replicate across B's halves?) with an A/B reply-swap null,
target side (does each arm's departure from A replicate across its own halves?) with a T/A swap null.
The eight-null A|B values are recomputed with per-split variances beside it.
Usage: t3_t4_split_half.py <n_reps> <n_splits_null> <n_workers>
"""
from __future__ import annotations

import os

os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import json  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
import warnings  # noqa: E402
from multiprocessing import Pool  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "stats_r2"))
import fast as F  # noqa: E402
from fast import C  # noqa: E402

G = {}


def tg(d):
    n = d.shape[-2]
    mean = d.mean(axis=-2)
    sd = d.std(axis=-2, ddof=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        t = mean / (sd / np.sqrt(n))
    return np.where(sd < 1e-9, 0.0, t)


def hr(R, sl):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(R[:, :, sl], axis=2)


def init():
    D = F.load()
    cands = D["_cands"]
    keep5 = [i for i, c in enumerate(cands) if c != "anthropic"]
    G["R6"] = {k: v for k, v in D.items() if not k.startswith("_")}
    G["R5"] = {k: v[keep5] for k, v in G["R6"].items()}


def one_split(RX, RY, RT, sl1, sl2):
    acc = np.zeros((len(RT), 2))
    for sel, tst in ((sl1, sl2), (sl2, sl1)):
        oX_s, oX_t = C.ovr(hr(RX, sel)), C.ovr(hr(RX, tst))
        oY_t = C.ovr(hr(RY, tst))
        bgrid = tg(oY_t - oX_t).ravel()
        for k, R in enumerate(RT):
            g = tg(C.ovr(hr(R, sel)) - oX_s).ravel()
            f = int(np.argmax(np.abs(g)))
            s = np.sign(g[f])
            acc[k, 0] += s * bgrid[f]
            acc[k, 1] += s * tg(C.ovr(hr(R, tst)) - oY_t).ravel()[f]
    return acc / 2


def splits(RX, RY, RT, n, rng):
    """(n, n_targets, 2) per-split values."""
    out = np.empty((n, len(RT), 2))
    for q in range(n):
        p = rng.permutation(16)
        out[q] = one_split(RX, RY, RT, p[:8], p[8:])
    return out


def swap(R1, R2, rng, q=0.5):
    both = (~np.isnan(R1).all(3) & ~np.isnan(R2).all(3))
    m = ((rng.random(R1.shape[:3]) < q) & both)[..., None]
    return np.where(m, R2, R1), np.where(m, R1, R2)


def mboot(RA, RB, rng, lam):
    availA, availB = ~np.isnan(RA).all(3), ~np.isnan(RB).all(3)
    nA, nB = availA.sum(2), availB.sum(2)
    oA = np.argsort(~availA, axis=2, kind="stable")
    oB = np.argsort(~availB, axis=2, kind="stable")
    pool = np.concatenate([RA, RB], axis=2)
    pr = (1.0 + lam) / 2.0

    def slots(n, o):
        k = np.floor(rng.random(o.shape) * n[..., None]).astype(int)
        return np.take_along_axis(o, k, axis=2)

    ixA = np.where(rng.random(RA.shape[:3]) < pr, slots(nA, oA), 16 + slots(nB, oB))
    ixB = np.where(rng.random(RA.shape[:3]) < pr, 16 + slots(nB, oB), slots(nA, oA))
    return (np.take_along_axis(pool, ixA[..., None], axis=2), np.take_along_axis(pool, ixB[..., None], axis=2))


def summ(v):
    """v: (n, n_targets, 2) -> mean over splits (n_targets, 2) and the split variance of the target-mean."""
    tm = v.mean(1)  # (n, 2)
    return v.mean(0), tm.var(0, ddof=1)


def job(args):
    kind, world, X, Y, tnames, lam, n_spl, seed = args
    R = G["R6"] if world == "six" else G["R5"]
    rng = np.random.default_rng(seed)
    RX, RY = R[X], R[Y]
    RT = [R[t] for t in tnames]
    if kind == "obs":
        v = splits(RX, RY, RT, n_spl, rng)
        return args, summ(v), v.mean(1)  # also per-split target-mean values
    if kind == "null_base":
        sX, sY = swap(RX, RY, rng)
        return args, summ(splits(sX, sY, RT, n_spl, rng)), None
    if kind == "null_target":
        out = np.zeros((len(RT), 2)); var = np.zeros(len(RT))
        for k, Rt in enumerate(RT):
            sT, sY = swap(Rt, RY, rng)
            v = splits(RX, sY, [sT], n_spl, rng)
            out[k] = v[:, 0].mean(0)
            var[k] = v[:, 0, 1].var(ddof=1)
        return args, (out, var), None
    if kind == "mboot":
        aX, aY = mboot(RX, RY, rng, lam)
        return args, summ(splits(aX, aY, RT, n_spl, rng)), None
    if kind == "pswap":
        aX, aY = swap(RX, RY, rng, q=(1.0 - lam) / 2.0)
        return args, summ(splits(aX, aY, RT, n_spl, rng)), None
    raise ValueError(kind)


def main():
    n_rep, n_spl, nw = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
    nulls = tuple(F.CONTROLS)
    sd = ("sd_ai_welfare_poisoning", "sd_emotional_bond")
    LAMS = (0.0, 0.125, 0.25, 0.375, 0.5, 0.75, 1.0)
    tasks = []
    seed = 7_000_000
    for w in ("six", "five"):
        tasks.append(("obs", w, "A", "B", nulls, 0.0, 500, seed)); seed += 1
        for r in range(n_rep):
            tasks.append(("null_base", w, "A", "B", nulls, 0.0, n_spl, seed)); seed += 1
        for lam in LAMS:
            for r in range(n_rep):
                tasks.append(("mboot", w, "A", "B", nulls, lam, n_spl, seed)); seed += 1
    for lam in (0.5, 0.75):
        for r in range(n_rep // 3):
            tasks.append(("pswap", "six", "A", "B", nulls, lam, n_spl, seed)); seed += 1
    # T4 mirror
    tasks.append(("obs", "six", "B", "A", sd, 0.0, 500, seed)); seed += 1
    for r in range(2 * n_rep):
        tasks.append(("null_base", "six", "B", "A", sd, 0.0, n_spl, seed)); seed += 1
    for r in range(n_rep):
        tasks.append(("null_target", "six", "B", "A", sd, 0.0, n_spl, seed)); seed += 1
    for r in range(n_rep // 2):
        tasks.append(("null_target", "six", "A", "B", nulls, 0.0, n_spl, seed)); seed += 1
    t0 = time.time()
    res = []
    with Pool(nw, initializer=init) as pool:
        for k, r in enumerate(pool.imap_unordered(job, tasks, chunksize=1)):
            res.append(r)
            if (k + 1) % 100 == 0:
                print(f"{k+1}/{len(tasks)} {time.time()-t0:.0f}s", flush=True)
    store = {}
    for args, s, extra in res:
        kind, w, X, Y, tn, lam, n_s, sd_ = args
        key = f"{kind}|{w}|{X}|{Y}|{len(tn)}|{lam}"
        store.setdefault(key, []).append((s, extra))
    out = {"n_rep": n_rep, "n_splits_null": n_spl}

    def obs_of(w, X, Y, n):
        (m, var), per = store[f"obs|{w}|{X}|{Y}|{n}|0.0"][0]
        return m, var, per

    def rep_stats(key, j):
        reps = store[key]
        means = np.array([r[0][0][:, j].mean() for r in reps])
        s2 = np.array([r[0][1][j] for r in reps])
        return means, float(s2.mean())

    for w in ("six", "five"):
        m, var, per = obs_of(w, "A", "B", 8)
        ob = float(m[:, 0].mean())
        means, s2 = rep_stats(f"null_base|{w}|A|B|8|0.0", 0)
        v500 = means.var() - s2 / n_spl + s2 / 500
        blk = {"obs_b": ob, "obs_b_per_target": m[:, 0].tolist(), "obs_split_var": float(var[0]),
               "swap_null": {"mean": float(means.mean()), "sd_64": float(means.std()), "split_var": s2,
                             "sd_500_corrected": float(np.sqrt(max(v500, 0))),
                             "z_corrected": float((ob - means.mean()) / np.sqrt(v500)),
                             "p_upper_uncorrected": float((1 + np.sum(means >= ob)) / (1 + len(means)))},
               "mboot": {}}
        for lam in LAMS:
            mm, s2l = rep_stats(f"mboot|{w}|A|B|8|{lam}", 0)
            v = mm.var() - s2l / n_spl + s2l / 500
            sdc = float(np.sqrt(max(v, 0)))
            # P(b_500 <= observed | lam) under a normal approximation with the corrected SD, and the raw share
            from math import erf, sqrt
            pz = (ob - mm.mean()) / sdc if sdc > 0 else float("nan")
            blk["mboot"][str(lam)] = {"mean": float(mm.mean()), "sd_64": float(mm.std()), "split_var": s2l, "sd_500_corrected": sdc,
                                      "P_le_obs_normal": float(0.5 * (1 + erf(pz / sqrt(2)))),
                                      "P_le_obs_raw64": float(np.mean(mm <= ob))}
        out[f"T3 power {w}"] = blk
        print(w, json.dumps(blk), flush=True)
    for lam in (0.5, 0.75):
        mm, s2l = rep_stats(f"pswap|six|A|B|8|{lam}", 0)
        out[f"pswap six lam {lam}"] = {"mean": float(mm.mean()), "sd_64": float(mm.std()), "split_var": s2l}
        print("pswap", lam, out[f"pswap six lam {lam}"], flush=True)
    # T4 mirror
    m, var, per = obs_of("six", "B", "A", 2)
    means_b, s2b = rep_stats("null_base|six|B|A|2|0.0", 0)
    vb = means_b.var() - s2b / n_spl + s2b / 500
    nt = store["null_target|six|B|A|2|0.0"]
    nt_a = np.array([r[0][0][:, 1] for r in nt])  # (reps, 2)
    nt_v = np.array([r[0][1] for r in nt]).mean(0)
    va = nt_a.var(0) - nt_v / n_spl + nt_v / 500
    mir = {"targets": list(sd), "obs_b_per_target": m[:, 0].tolist(), "obs_a_per_target": m[:, 1].tolist(),
           "obs_b_mean": float(m[:, 0].mean()), "obs_a_mean": float(m[:, 1].mean()),
           "base_null": {"mean": float(means_b.mean()), "sd_500_corrected": float(np.sqrt(vb)),
                         "z": float((m[:, 0].mean() - means_b.mean()) / np.sqrt(vb)),
                         "per_target_mean": np.array([r[0][0][:, 0] for r in store['null_base|six|B|A|2|0.0']]).mean(0).tolist(),
                         "per_target_sd_64": np.array([r[0][0][:, 0] for r in store['null_base|six|B|A|2|0.0']]).std(0).tolist()},
           "target_null": {"per_target_mean": nt_a.mean(0).tolist(), "per_target_sd_500_corrected": np.sqrt(np.maximum(va, 0)).tolist(),
                           "per_target_z": ((m[:, 1] - nt_a.mean(0)) / np.sqrt(np.maximum(va, 1e-12))).tolist()}}
    out["T4 mirror B|A synthetic arms"] = mir
    print("mirror", json.dumps(mir), flush=True)
    # eight nulls, target side with corrected SD (for the side-by-side)
    m8, var8, _ = obs_of("six", "A", "B", 8)
    nt8 = store["null_target|six|A|B|8|0.0"]
    a8 = np.array([r[0][0][:, 1] for r in nt8]); v8 = np.array([r[0][1] for r in nt8]).mean(0)
    va8 = a8.var(0) - v8 / n_spl + v8 / 500
    out["T4 reference A|B eight nulls target side"] = {"obs_a_per_target": m8[:, 1].tolist(), "null_mean": a8.mean(0).tolist(),
                                                       "sd_500_corrected": np.sqrt(np.maximum(va8, 0)).tolist(),
                                                       "z": ((m8[:, 1] - a8.mean(0)) / np.sqrt(np.maximum(va8, 1e-12))).tolist()}
    print("eight target side", json.dumps(out["T4 reference A|B eight nulls target side"]), flush=True)
    json.dump(out, open(HERE / "out" / f"t3_t4_split_half_{n_rep}_{n_spl}.json", "w"), indent=1)
    print(f"done {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
