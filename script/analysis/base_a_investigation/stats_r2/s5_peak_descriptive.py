"""S5 (descriptive part). At each test's full-sample peak cell against A, split the mean excess exactly:
mean(T - A) = mean(T - B) [target departure from B] + mean(B - A) [A's departure from B].
Both parts inherit selection noise (the cell was chosen with T and A), so this is descriptive only;
the select-in-one-half design in s2_s5_split_half.py is the diagnostic version."""
import json
import numpy as np
import fast as F
from fast import C
D = F.load(); cands = D["_cands"]
O = {k: C.ovr(C.rates(v)) for k, v in D.items() if not k.startswith("_")}
out = {}
for k in F.CONTROLS:
    t = C.tgrid_fast(O[k] - O["A"])[0]
    c, j = np.unravel_index(np.argmax(np.abs(t)), t.shape)
    m = lambda x: float(x[c, :, j].mean())
    tt = lambda x: float(C.tgrid_fast(x)[0][c, j])
    out[k] = {"cell": f"{cands[c]} x {C.AXES[j]}", "t_T_minus_A": float(t[c, j]),
              "mean_T_minus_A": m(O[k] - O["A"]), "mean_T_minus_B": m(O[k] - O["B"]), "mean_B_minus_A": m(O["B"] - O["A"]),
              "share_B_minus_A": m(O["B"] - O["A"]) / m(O[k] - O["A"]),
              "t_T_minus_B": tt(O[k] - O["B"]), "t_B_minus_A": tt(O["B"] - O["A"])}
    print(f"{k:24s} {out[k]['cell'][:60]:60s} t(T-A)={t[c,j]:+.2f} t(T-B)={out[k]['t_T_minus_B']:+.2f} t(B-A)={out[k]['t_B_minus_A']:+.2f} share(B-A)={out[k]['share_B_minus_A']:.2f}")
json.dump(out, open(F.OUT / "s5_peak_descriptive.json", "w"), indent=1)
