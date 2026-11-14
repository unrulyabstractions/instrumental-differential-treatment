"""Reproduce all 21 pairings of nullext/summary.json with the vectorized test (exact match required)."""
import json
import sys
import time

import numpy as np

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from common import CONTROLS, EXT, OUT, SYNTH, load_all, perm_orders, rates, run_test  # noqa

t0 = time.time()
D = load_all()
orders = perm_orders()
print(f"loaded + orders in {time.time()-t0:.1f}s; NaN cells:",
      {k: int(np.isnan(rates(v)).sum()) for k, v in D.items() if not k.startswith("_")})
stored = json.loads((EXT / "summary.json").read_text())["results"]
pairs = [(f"{c}|base_A", c, "A") for c in CONTROLS] + [(f"{c}|base_B", c, "B") for c in CONTROLS]
pairs += [("contextual_optimism|base_B", "CO", "B"), ("base_B|base_A", "B", "A")]
for b in SYNTH:
    pairs += [(f"sd_{b}|base_A", "sd_" + b, "A"), (f"sd_{b}|base_B", "sd_" + b, "B")]
pairs += [("contextual_optimism|base_A", "CO", "A")]
res = {}
bad = 0
for name, tk, bk in pairs:
    r = run_test(rates(D[tk]), rates(D[bk]), orders)
    want = stored.get(name)
    ok = want is None or (abs(r["S"] - want["statistic"]) < 1e-9 and abs(r["p"] - want["p_family_wise"]) < 1e-12)
    bad += not ok
    res[name] = {"S": r["S"], "p": r["p"], "null_mean": float(r["null"].mean()),
                 "null_p95": float(np.quantile(r["null"], .95)), "null_p50": float(np.median(r["null"])),
                 "matches_summary": None if want is None else bool(ok)}
    print(f"{name:34s} S={r['S']:.4f} p={r['p']:.4f} null50={res[name]['null_p50']:.3f} "
          f"null95={res[name]['null_p95']:.3f} match={res[name]['matches_summary']}", flush=True)
print("mismatches:", bad, f"time {time.time()-t0:.0f}s")
json.dump(res, open(OUT / "reproduce.json", "w"), indent=1)
