"""S2 and S5. Select in one half, test in the other: does base A's deviation at the tests' peak cells
replicate inside A (systematic) and does the targets' departure there replicate inside the targets?

All samples share one random split of the 16 reply slots into halves h1/h2 (matched slots, so the
judge's (prompt_id, s)-keyed axis order cancels within each half). For deviant sample X (base A),
comparator Y (base B) and each target T_k:
  selection half : g = t(OvR(T_k,sel) - OvR(X,sel)); peak cell c* = argmax |g|; sigma = sign g[c*]
  test half      : base side   b_k = sigma * t(OvR(Y,test) - OvR(X,test))[c*]       (S2: X's deviation replicates?)
                   target side a_k = sigma * t(OvR(T_k,test) - OvR(Y,test))[c*]     (S5: T's departure replicates?)
                   whole       w_k = sigma * t(OvR(T_k,test) - OvR(X,test))[c*]     (the test's own peak replicates?)
Both directions (sel=h1/test=h2 and the reverse), averaged over 500 splits (observed).
Nulls: base side, swap X and Y replies at each slot (p=1/2); target side, swap T_k and Y replies.
Power (base side, X = A only): in swap-null data add lam * delta to X's one-vs-rest gap, delta = the
full-sample mean (over instructions) of OvR(A) - OvR(B) per (candidate, axis); lam = 0.25..1.
Positive controls: X in {hallucinates_citations, sd arms, CO (five candidates)}, Y = B, targets = the
nulls other than X. Mirror: X = B, Y = A. Worlds: six candidates, and five (anthropic dropped).
Usage: s2_s5_split_half.py <n_null_reps> <n_splits_null> <n_workers>
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

import numpy as np  # noqa: E402

import fast as F  # noqa: E402
from fast import C  # noqa: E402

G = {}


def init():
    D = F.load()
    cands = D["_cands"]
    keep5 = [i for i, c in enumerate(cands) if c != "anthropic"]
    G["R6"] = {k: v for k, v in D.items() if not k.startswith("_")}
    G["R5"] = {k: v[keep5] for k, v in G["R6"].items()}


def hr(R, sl):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(R[:, :, sl], axis=2)


def tg(d):
    t = C.tgrid_fast(d)[0]
    return np.where(np.isfinite(t), t, 0.0)


def one_split(RX, RY, RT, sl1, sl2, offX=None):
    """Per-target (b, a, w) averaged over the two directions of one split."""
    acc = np.zeros((len(RT), 3))
    for sel, tst in ((sl1, sl2), (sl2, sl1)):
        oX_s, oX_t = C.ovr(hr(RX, sel)), C.ovr(hr(RX, tst))
        if offX is not None:
            oX_s, oX_t = oX_s + offX, oX_t + offX
        oY_t = C.ovr(hr(RY, tst))
        bgrid = tg(oY_t - oX_t)
        for k, R in enumerate(RT):
            oT_s, oT_t = C.ovr(hr(R, sel)), C.ovr(hr(R, tst))
            g = tg(oT_s - oX_s)
            f = int(np.argmax(np.abs(g)))
            s = np.sign(g.ravel()[f])
            acc[k, 0] += s * bgrid.ravel()[f]
            acc[k, 1] += s * tg(oT_t - oY_t).ravel()[f]
            acc[k, 2] += s * tg(oT_t - oX_t).ravel()[f]
    return acc / 2


def avg_splits(RX, RY, RT, n, rng, offX=None):
    acc = np.zeros((len(RT), 3))
    for _ in range(n):
        p = rng.permutation(16)
        acc += one_split(RX, RY, RT, p[:8], p[8:], offX)
    return acc / n


def swap(R1, R2, rng):
    m = (rng.random(R1.shape[:3]) < 0.5)[..., None]
    return np.where(m, R2, R1), np.where(m, R1, R2)


def job(args):
    kind, world, X, Y, tnames, lam, n_spl, seed = args
    R = G["R6"] if world == "six" else G["R5"]
    rng = np.random.default_rng(seed)
    RX, RY = R[X], R[Y]
    RT = [R[t] for t in tnames]
    if kind == "obs":
        return args, avg_splits(RX, RY, RT, n_spl, rng)
    if kind == "null_base":  # swap X and Y
        sX, sY = swap(RX, RY, rng)
        off = None
        if lam:
            delta = np.nanmean(C.ovr(C.rates(RX)) - C.ovr(C.rates(RY)), axis=1, keepdims=True)
            off = lam * np.broadcast_to(delta, (RX.shape[0], 36, RX.shape[3]))
        return args, avg_splits(sX, sY, RT, n_spl, rng, off)
    if kind == "null_target":  # swap each T_k with Y (separately), base X untouched
        out = np.zeros((len(RT), 3))
        for k, Rt in enumerate(RT):
            sT, sY = swap(Rt, RY, rng)
            # per-target replicate: only row k is used
            out[k] = avg_splits(RX, sY, [sT], n_spl, rng)[0]
        return args, out
    raise ValueError(kind)


def main():
    n_rep, n_spl_null, nw = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
    nulls = list(F.CONTROLS)
    configs = [  # (label, world, X, Y, targets, run_power)
        ("A|B", "six", "A", "B", nulls, True),
        ("A|B five", "five", "A", "B", nulls, True),
        ("B|A mirror", "six", "B", "A", nulls, False),
        ("B|A mirror five", "five", "B", "A", nulls, False),
        ("HC|B", "six", "hallucinates_citations", "B", [c for c in nulls if c != "hallucinates_citations"], False),
        ("sdAWP|B", "six", "sd_ai_welfare_poisoning", "B", nulls, False),
        ("sdEB|B", "six", "sd_emotional_bond", "B", nulls, False),
        ("CO|B five", "five", "CO", "B", nulls, False),
    ]
    tasks = []
    seed = 1000
    for lab, w, X, Y, tn, pw in configs:
        tasks.append(("obs", w, X, Y, tuple(tn), 0.0, 500, seed)); seed += 1
        for r in range(n_rep):
            tasks.append(("null_base", w, X, Y, tuple(tn), 0.0, n_spl_null, seed)); seed += 1
        if lab in ("A|B", "A|B five"):
            for r in range(n_rep // 2):
                tasks.append(("null_target", w, X, Y, tuple(tn), 0.0, n_spl_null, seed)); seed += 1
        if pw:
            for lam in (0.25, 0.5, 0.75, 1.0):
                for r in range(n_rep // 2):
                    tasks.append(("null_base", w, X, Y, tuple(tn), lam, n_spl_null, seed)); seed += 1
    t0 = time.time()
    results = []
    with Pool(nw, initializer=init) as pool:
        for k, r in enumerate(pool.imap_unordered(job, tasks, chunksize=1)):
            results.append(r)
            if (k + 1) % 100 == 0:
                print(f"{k+1}/{len(tasks)} {time.time()-t0:.0f}s", flush=True)
    # also the split-to-split SD of the observed per-split statistic, to correct null SDs
    out = {"n_rep": n_rep, "n_splits_null": n_spl_null, "configs": {}}
    for lab, w, X, Y, tn, pw in configs:
        sel = lambda kind, lam: [np.asarray(v) for a, v in results if a[0] == kind and a[1] == w and a[2] == X and a[3] == Y and a[5] == lam]
        obs = sel("obs", 0.0)[0]
        nb = np.array(sel("null_base", 0.0))
        cfg = {"targets": list(tn), "obs_per_target": {t: obs[k].tolist() for k, t in enumerate(tn)},
               "obs_mean": obs.mean(0).tolist()}
        for j, nm in enumerate(("base_side_b", "target_side_a", "whole_w")):
            if nm == "target_side_a":
                continue
            x = nb[:, :, j].mean(1)
            o = obs[:, j].mean()
            cfg[nm] = {"obs": float(o), "null_mean": float(x.mean()), "null_sd": float(x.std()),
                       "z": float((o - x.mean()) / x.std()), "p_upper": float((1 + np.sum(x >= o)) / (1 + len(x))),
                       "per_target_null_sd": nb[:, :, j].std(0).tolist(),
                       "per_target_z": ((obs[:, j] - nb[:, :, j].mean(0)) / nb[:, :, j].std(0)).tolist()}
        nt = sel("null_target", 0.0)
        if nt:
            nt = np.array(nt)
            x = nt[:, :, 1]
            cfg["target_side_a"] = {"obs": float(obs[:, 1].mean()), "null_mean_of_mean": float(x.mean(1).mean()),
                                    "null_sd_of_mean_indep": float(np.sqrt((x.std(0) ** 2).sum()) / len(tn)),
                                    "per_target_null_mean": x.mean(0).tolist(), "per_target_null_sd": x.std(0).tolist(),
                                    "per_target_z": ((obs[:, 1] - x.mean(0)) / x.std(0)).tolist()}
        if pw:
            cfg["power"] = {}
            for lam in (0.25, 0.5, 0.75, 1.0):
                xs = np.array(sel("null_base", lam))[:, :, 0].mean(1)
                cfg["power"][str(lam)] = {"mean": float(xs.mean()), "sd": float(xs.std()), "q05": float(np.quantile(xs, 0.05)),
                                          "P_le_obs": float(np.mean(xs <= cfg["base_side_b"]["obs"]))}
        out["configs"][lab] = cfg
        print(lab, json.dumps({k: v for k, v in cfg.items() if k not in ("obs_per_target", "targets")}, default=float)[:1500], flush=True)
    json.dump(out, open(F.OUT / f"s2_s5_split_half_{n_rep}_{n_spl_null}.json", "w"), indent=1)
    print(f"done {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
