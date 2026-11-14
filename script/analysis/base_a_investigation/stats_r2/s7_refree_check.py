"""S7 check: base A's reference-free statistic 4.098 vs the 3.82 quoted for the same cell.

The repo's reference_free_max_test contrasts each candidate with the MEDIAN of the other five; p18
contrasted it with the MEAN of the other five (one-vs-rest). Prints both grids' maxima and cells."""
import numpy as np
import fast as F
from fast import C
import draws_engine as DE
D = F.load(); cands = D["_cands"]
for k in ("A", "B"):
    p = C.rates(D[k])
    for lab, d in (("median-of-rest", p - DE.median_of_rest(p)), ("mean-of-rest", C.ovr(p))):
        t = C.tgrid_fast(d)[0]
        f = np.nanargmax(np.abs(t)); c, j = np.unravel_index(f, t.shape)
        g = (cands.index("google_deepmind"), C.AXES.index("rival_entity_capability_ceiling_assertion"))
        print(f"{k} {lab:15s} max|t|={np.abs(t).max():.4f} at {cands[c]} x {C.AXES[j]}; t at gdm x capability_ceiling = {t[g]:.4f}")
