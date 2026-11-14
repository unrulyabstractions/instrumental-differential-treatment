"""T5 (deterministic part). Base cell rates moved along the line between the two realized bases:
   eight nulls       : base = (1 - lam) * B + lam * A,   lam = 0 ... 1   (lam = 1 is base A)
   synthetic arms    : base = (1 - lam) * A + lam * B                     (lam = 1 is base B)
Exact registered p (six candidates). No resampling noise: this shows how much of each realized base's
deviation the low values need. Reproduces the critic's eight-null curve (0.413, 0.226, 0.111, 0.074,
0.056 at lam 0.5, 0.6, 0.75, 0.9, 1.0).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "stats_r2"))
import fast as F  # noqa: E402
from fast import C  # noqa: E402

D = F.load()
P = {k: C.rates(v) for k, v in D.items() if not k.startswith("_")}
E6 = F.E_for(6)
OT8 = np.stack([C.ovr(P[k]) for k in F.CONTROLS])
OTS = np.stack([C.ovr(P[k]) for k in F.SD])
pA, pB = P["A"], P["B"]
assert not np.isnan(pA).any() and not np.isnan(pB).any()
LAMS = (0.0, 0.25, 0.5, 0.6, 0.75, 0.9, 1.0)
res = {"eight_nulls_toward_A": {}, "synthetic_toward_B": {}}
for lam in LAMS:
    S, p, _ = F.test_many(OT8, C.ovr((1 - lam) * pB + lam * pA), 6, E6)
    res["eight_nulls_toward_A"][str(lam)] = {"median_p": float(np.median(p)), "mean_S": float(S.mean()), "p": np.round(p, 4).tolist()}
    S2, p2, _ = F.test_many(OTS, C.ovr((1 - lam) * pA + lam * pB), 6, E6)
    res["synthetic_toward_B"][str(lam)] = {"p": np.round(p2, 4).tolist(), "S": np.round(S2, 3).tolist()}
    print(f"lam={lam:.2f}  eight: median p {np.median(p):.4f} mean S {S.mean():.3f} p {np.round(p, 3).tolist()} | "
          f"synthetic (toward B): p {np.round(p2, 4).tolist()}", flush=True)
json.dump(res, open(HERE / "out" / "t5_curve.json", "w"), indent=1)
