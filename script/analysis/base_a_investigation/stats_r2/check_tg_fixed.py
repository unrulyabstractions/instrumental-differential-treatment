"""Check that the tg fix in s2b (t = 0 where the spread of d is below 1e-9) leaves real-data
half-sample t-grids unchanged: compares it with the original tg on 200 random matched splits, every
target against A and B, six and five candidates."""
import numpy as np
import s2_s5_split_half as M
import s2b_power_twin as P2
from fast import C
import fast as F
M.init()
orig = lambda d: np.where(np.isfinite(C.tgrid_fast(d)[0]), C.tgrid_fast(d)[0], 0.0)
rng = np.random.default_rng(3)
maxdiff = 0.0; ncells = 0
for w in ("R6", "R5"):
    R = M.G[w]
    for _ in range(100):
        p = rng.permutation(16)
        for sl in (p[:8], p[8:]):
            oA, oB = C.ovr(M.hr(R["A"], sl)), C.ovr(M.hr(R["B"], sl))
            for k in list(F.CONTROLS) + ["B", "CO"] + F.SD:
                for ob in (oA, oB):
                    d = C.ovr(M.hr(R[k], sl)) - ob
                    a, b = orig(d), P2.tg_fixed(d)
                    maxdiff = max(maxdiff, float(np.max(np.abs(a - b)))); ncells += a.size
print("max |difference| between original and fixed t over", ncells, "cells:", maxdiff)
# same seed as the original observed run (seed 1000 for A|B six): fixed tg must give the same means
nulls = tuple(F.CONTROLS)
_, v = M.job(("obs", "six", "A", "B", nulls, 0.0, 500, 1000))
print("A|B six obs (b, a, w) with fixed tg, seed 1000:", np.asarray(v).mean(0), "previous b 0.24550506586263243")
