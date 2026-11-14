import os, sys, time
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "stats_r2"))
import numpy as np
import fast as F
from fast import C
D = F.load()
P = {k: C.rates(v) for k, v in D.items() if not k.startswith("_")}
OT = np.stack([C.ovr(P[k]) for k in F.CONTROLS])
OA = C.ovr(P["A"])
print("nan in OT", np.isnan(OT).sum(), "nan in OA", np.isnan(OA).sum())
E = F.E_for(6)
t0 = time.time(); S, p, nm = F.test_many(OT, OA, 6, E); print("8 tests", time.time() - t0, np.round(p, 4))
# batched
def null_max_batch(ds, n_c, E):
    m = ds.shape[0]; k = E.shape[0] // n_c
    X = ds.reshape(m, n_c * 36, 101).transpose(1, 0, 2).reshape(n_c * 36, m * 101)
    s1 = (E @ X).reshape(k, n_c, m, 101); s2 = (E @ (X * X)).reshape(k, n_c, m, 101)
    den = 36 * s2 - s1 * s1
    with np.errstate(invalid="ignore", divide="ignore"):
        t2 = 35 * s1 * s1 / den
    t2 = np.where(np.isnan(t2), 0.0, t2)
    t2 = np.where(den <= 0, np.where(s1 != 0, np.inf, 0.0), t2)
    return np.sqrt(t2.max(axis=(1, 3)).T)
t0 = time.time(); nm2 = null_max_batch(OT - OA, 6, E); print("batched", time.time() - t0, np.abs(nm2 - nm).max())
