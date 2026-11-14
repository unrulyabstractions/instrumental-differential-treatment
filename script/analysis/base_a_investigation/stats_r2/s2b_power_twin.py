"""S2 power (fixed) and a select/test twin contrast.

Fix: in s2_s5_split_half.py the power runs added a constant offset to cells whose half-sample d is
identically zero across instructions, which gave |t| ~ 1e15 there. Here t is set to 0 wherever the
spread of d over instructions is below 1e-9 (the code's own rule gives 0 or inf there; real data never
has a constant nonzero d, so observed values are unchanged; checked by recomputing A|B).

(1) Power, base side, X = A, Y = B, six and five candidates: swap-null data plus lam * delta in X's
    one-vs-rest gap, delta = full-sample mean over instructions of OvR(A) - OvR(B); lam = 0.25..1.
(2) Twin contrast in the select-in-one-half design (five candidates, anthropic dropped): base side
    b_Y = sigma * t(Y_test - A_test) at each test's half-1 peak against A, for Y = B, CO (A's own engine
    session), and the two synthetic-document arms (B's engine and sampler). CO and the synthetic arms
    are both fine-tunes, so CO vs the synthetic arms is the like-for-like contrast: CO well below them
    would mean CO shares A's replicating deviation.
Usage: s2b_power_twin.py <n_reps> <n_splits> <n_workers>
"""
from __future__ import annotations

import os

os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
import json  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from multiprocessing import Pool  # noqa: E402

import numpy as np  # noqa: E402

import s2_s5_split_half as M  # noqa: E402
from fast import C  # noqa: E402
import fast as F  # noqa: E402


def tg_fixed(d):
    n = d.shape[-2]
    mean = d.mean(axis=-2)
    sd = d.std(axis=-2, ddof=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        t = mean / (sd / np.sqrt(n))
    return np.where(sd < 1e-9, 0.0, t)


M.tg = tg_fixed  # one_split looks tg up at call time


def job(args):
    return M.job(args)


def main():
    n_rep, n_spl, nw = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
    nulls = tuple(F.CONTROLS)
    tasks = []
    seed = 50000
    for w in ("six", "five"):
        tasks.append(("obs", w, "A", "B", nulls, 0.0, 500, seed)); seed += 1
        for lam in (0.25, 0.5, 0.75, 1.0):
            for r in range(n_rep):
                tasks.append(("null_base", w, "A", "B", nulls, lam, n_spl, seed)); seed += 1
    for Y in ("CO", "sd_ai_welfare_poisoning", "sd_emotional_bond"):
        tasks.append(("obs", "five", "A", Y, nulls, 0.0, 500, seed)); seed += 1
        for r in range(n_rep):
            tasks.append(("null_base", "five", "A", Y, nulls, 0.0, n_spl, seed)); seed += 1
    t0 = time.time()
    res = []
    with Pool(nw, initializer=M.init) as pool:
        for k, r in enumerate(pool.imap_unordered(job, tasks, chunksize=1)):
            res.append(r)
            if (k + 1) % 100 == 0:
                print(f"{k+1}/{len(tasks)} {time.time()-t0:.0f}s", flush=True)
    out = {"n_rep": n_rep, "n_splits": n_spl}
    prev = json.load(open(F.OUT / "s2_s5_split_half_200_64.json"))["configs"]
    for w, lab in (("six", "A|B"), ("five", "A|B five")):
        obs = [np.asarray(v) for a, v in res if a[0] == "obs" and a[1] == w and a[3] == "B"][0]
        o = float(obs[:, 0].mean())
        out[f"power {lab}"] = {"obs_b_recomputed": o, "obs_b_previous": prev[lab]["base_side_b"]["obs"],
                               "null_sd_lam0": prev[lab]["base_side_b"]["null_sd"], "lam": {}}
        for lam in (0.25, 0.5, 0.75, 1.0):
            xs = np.array([np.asarray(v)[:, 0].mean() for a, v in res if a[0] == "null_base" and a[1] == w and a[3] == "B" and a[5] == lam])
            out[f"power {lab}"]["lam"][str(lam)] = {"mean": float(xs.mean()), "sd": float(xs.std()), "q05": float(np.quantile(xs, 0.05)),
                                                    "P_le_obs": float(np.mean(xs <= o))}
        print(lab, json.dumps(out[f"power {lab}"]), flush=True)
    for Y in ("CO", "sd_ai_welfare_poisoning", "sd_emotional_bond"):
        obs = [np.asarray(v) for a, v in res if a[0] == "obs" and a[3] == Y][0]
        xs = np.array([np.asarray(v)[:, 0].mean() for a, v in res if a[0] == "null_base" and a[3] == Y])
        o = float(obs[:, 0].mean())
        out[f"twin five A|{Y}"] = {"obs_b": o, "per_target_b": obs[:, 0].tolist(), "null_mean": float(xs.mean()), "null_sd": float(xs.std()),
                                    "z": float((o - xs.mean()) / xs.std()), "p_upper": float((1 + np.sum(xs >= o)) / (1 + len(xs)))}
        print(Y, json.dumps(out[f"twin five A|{Y}"]), flush=True)
    json.dump(out, open(F.OUT / f"s2b_power_twin_{n_rep}_{n_spl}.json", "w"), indent=1)
    print("done", time.time() - t0)


if __name__ == "__main__":
    main()
