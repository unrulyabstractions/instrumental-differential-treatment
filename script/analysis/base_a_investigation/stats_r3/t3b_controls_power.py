"""T3b. Put the positive controls and the mirror on the same share scale as base A.

The select-in-one-half base-side statistic b gives about the same value for base A (0.246) as for
samples with known candidate-dependent structure (hallucinates_citations 0.222, sd arms 0.234 and
0.434 in stats_r2). To say what that means, each deviant sample X gets the same mixture-bootstrap
power curve as A in t3_t4_split_half.py: data where a share lam of X's realized cell-level difference
from its comparator Y is systematic and every draw has fresh reply noise. The share at which E[b]
equals the observed b is X's 'replicating share'. Six candidates, 64 splits per replicate, SDs
corrected to 500 splits as in t3_t4_split_half.py.
  X = hallucinates_citations, Y = B, selecting targets = the other seven nulls
  X = sd_emotional_bond,      Y = B, targets = the eight nulls
  X = sd_ai_welfare_poisoning,Y = B, targets = the eight nulls
  X = B,                      Y = A, targets = the two synthetic arms (the mirror of A with the nulls)
Usage: t3b_controls_power.py <n_reps> <n_splits> <n_workers>
"""
from __future__ import annotations

import os

os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
import json  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from math import erf, sqrt  # noqa: E402
from multiprocessing import Pool  # noqa: E402

import numpy as np  # noqa: E402

import t3_t4_split_half as M  # noqa: E402

LAMS = (0.0, 0.25, 0.5, 1.0)


def main():
    n_rep, n_spl, nw = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
    nulls = tuple(M.F.CONTROLS)
    configs = {
        "hallucinates_citations|B": ("hallucinates_citations", "B", tuple(c for c in nulls if c != "hallucinates_citations")),
        "sd_emotional_bond|B": ("sd_emotional_bond", "B", nulls),
        "sd_ai_welfare_poisoning|B": ("sd_ai_welfare_poisoning", "B", nulls),
        "B|A synthetic": ("B", "A", ("sd_ai_welfare_poisoning", "sd_emotional_bond")),
    }
    tasks = []
    seed = 9_100_000
    for lab, (X, Y, tn) in configs.items():
        tasks.append(("obs", "six", X, Y, tn, 0.0, 500, seed)); seed += 1
        for lam in LAMS:
            for r in range(n_rep):
                tasks.append(("mboot", "six", X, Y, tn, lam, n_spl, seed)); seed += 1
    t0 = time.time()
    res = []
    with Pool(nw, initializer=M.init) as pool:
        for k, r in enumerate(pool.imap_unordered(M.job, tasks, chunksize=1)):
            res.append(r)
            if (k + 1) % 100 == 0:
                print(f"{k+1}/{len(tasks)} {time.time()-t0:.0f}s", flush=True)
    out = {"n_rep": n_rep, "n_splits": n_spl}
    for lab, (X, Y, tn) in configs.items():
        o = [s for a, s, e in res if a[0] == "obs" and a[2] == X and a[3] == Y][0]
        ob = float(o[0][:, 0].mean())
        blk = {"obs_b": ob, "obs_b_per_target": o[0][:, 0].tolist(), "lam": {}}
        for lam in LAMS:
            reps = [s for a, s, e in res if a[0] == "mboot" and a[2] == X and a[3] == Y and a[5] == lam]
            mm = np.array([s[0][:, 0].mean() for s in reps])
            s2 = float(np.mean([s[1][0] for s in reps]))
            v = mm.var() - s2 / n_spl + s2 / 500
            sdc = float(np.sqrt(max(v, 0)))
            pz = (ob - mm.mean()) / sdc if sdc > 0 else float("nan")
            blk["lam"][str(lam)] = {"mean": float(mm.mean()), "sd_500_corrected": sdc,
                                    "P_le_obs_normal": float(0.5 * (1 + erf(pz / sqrt(2)))), "P_le_obs_raw64": float(np.mean(mm <= ob))}
        out[lab] = blk
        print(lab, json.dumps(blk), flush=True)
    json.dump(out, open(M.HERE / "out" / f"t3b_controls_power_{n_rep}_{n_spl}.json", "w"), indent=1)
    print("done", time.time() - t0)


if __name__ == "__main__":
    main()
