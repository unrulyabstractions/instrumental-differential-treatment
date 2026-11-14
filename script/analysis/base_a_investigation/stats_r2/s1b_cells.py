"""S1b. Twin check at the single cells that carry the low values: does CO (A's own vLLM 0.26.0 session)
share A's departure there? Five-candidate one-vs-rest (anthropic dropped). For each test's full-sample
peak cell against A (six-candidate test), t over instructions of (Y - A) for Y = B, CO, both synthetic arms,
and of (Y - B). If CO shared A's departure, t(CO - A) would be near 0 while t(B - A) is large."""
import json
import numpy as np
import fast as F
from fast import C
D = F.load(); cands = D["_cands"]
keep = [i for i, c in enumerate(cands) if c != "anthropic"]; c5 = [cands[i] for i in keep]
O6 = {k: C.ovr(C.rates(v)) for k, v in D.items() if not k.startswith("_")}
O5 = {k: C.ovr(C.rates(v)[keep]) for k, v in D.items() if not k.startswith("_")}
out = {}
for k in F.CONTROLS:
    t = C.tgrid_fast(O6[k] - O6["A"])[0]
    c, j = np.unravel_index(np.argmax(np.abs(t)), t.shape)
    if cands[c] == "anthropic":
        continue
    c5i = c5.index(cands[c])
    row = {"cell": f"{cands[c]} x {C.AXES[j]}", "t_test": float(t[c, j])}
    for Y in ("B", "CO", "sd_ai_welfare_poisoning", "sd_emotional_bond", k):
        row[f"t({Y}-A)"] = float(C.tgrid_fast(O5[Y] - O5["A"])[0][c5i, j])
        row[f"t({Y}-B)"] = float(C.tgrid_fast(O5[Y] - O5["B"])[0][c5i, j]) if Y != "B" else 0.0
    out[k] = row
    print(f"{k[:14]:14s} {row['cell'][:58]:58s} t_test={row['t_test']:+.2f} | t(Y-A): B {row['t(B-A)']:+.2f} CO {row['t(CO-A)']:+.2f} sdAWP {row['t(sd_ai_welfare_poisoning-A)']:+.2f} sdEB {row['t(sd_emotional_bond-A)']:+.2f} | t(CO-B) {row['t(CO-B)']:+.2f}")
json.dump(out, open(F.OUT / "s1b_cells.json", "w"), indent=1)
