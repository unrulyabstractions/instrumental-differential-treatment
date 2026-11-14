"""Check fast.py against every stored pairing in nullext/summary.json (S and p must match exactly),
and against the slow round-1 implementation for a five-candidate pairing (no stored value exists)."""
import json
import time

import numpy as np

import fast as F
from fast import C

D = F.load()
P = {k: C.rates(v) for k, v in D.items() if not k.startswith("_")}
O = {k: C.ovr(v) for k, v in P.items()}
stored = json.loads((C.EXT / "summary.json").read_text())["results"]
names = {"base_A": "A", "base_B": "B", "contextual_optimism": "CO"}
t0 = time.time()
E6 = F.E_for(6)
print(f"E6 built {E6.shape} in {time.time()-t0:.1f}s")
bad = 0
rows = []
for key, v in stored.items():
    tname, bname = key.split("|")
    tk = names.get(tname, tname)
    bk = names[bname]
    t1 = time.time()
    S, p, _ = F.test_many(O[tk][None], O[bk], 6, E6)
    ok = abs(S[0] - v["statistic"]) < 1e-9 and abs(p[0] - v["p_family_wise"]) < 1e-12
    bad += not ok
    rows.append((key, float(S[0]), float(p[0]), v["statistic"], v["p_family_wise"], bool(ok)))
    print(f"{key:36s} S={S[0]:.6f} p={p[0]:.6f} stored S={v['statistic']:.6f} p={v['p_family_wise']:.6f} match={ok} ({time.time()-t1:.2f}s)")
print("mismatches:", bad, "of", len(stored))
# batched call: eight nulls against A at once
t1 = time.time()
S8, p8, _ = F.test_many(np.stack([O[c] for c in F.CONTROLS]), O["A"], 6, E6)
print("batched eight vs A:", np.round(p8, 4), f"{time.time()-t1:.2f}s")
# five-candidate check against slow implementation
keep = [i for i, c in enumerate(D["_cands"]) if c != "anthropic"]
P5 = {k: v[keep] for k, v in P.items()}
O5 = {k: C.ovr(v) for k, v in P5.items()}
E5 = F.E_for(5)
for tk in ("CO", "defer_to_users"):
    S, p, _ = F.test_many(O5[tk][None], O5["A"], 5, E5)
    r = C.run_test(P5[tk], P5["A"], C.perm_orders(n_c=5))
    print(f"five-cand {tk}|A fast S={S[0]:.6f} p={p[0]:.6f}  slow S={r['S']:.6f} p={r['p']:.6f}")
json.dump({"rows": rows, "mismatches": bad}, open(F.OUT / "check_fast.json", "w"), indent=1)
