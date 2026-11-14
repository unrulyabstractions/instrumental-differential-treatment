"""Do the fine-tuned nulls share a candidate-specific shift relative to the base (a common real effect)?

Registered statistic and permutation scheme on averaged rate tables:
  nulls8 vs bases(A,B), fine10 (8 nulls + 2 synth-doc) vs bases(A,B), sd2 vs bases(A,B),
  nulls8 vs A, nulls8 vs B (repeated from grid_shape for the table).
Averaging rates first keeps the test's form (one target table, one base table). Also lists the
top cells of fine10 vs bases.
"""
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import AXES, CONTROLS, OUT, apply_orders, excess, load_all, perm_null, perm_orders, rates, smax, tail_p, tgrid, tgrid_fast
D = load_all(); cands = D["_cands"]
P = {k: rates(v) for k, v in D.items() if not k.startswith("_")}
SD = ["sd_ai_welfare_poisoning", "sd_emotional_bond"]
orders = perm_orders()
groups = {"nulls8": list(CONTROLS), "fine10": list(CONTROLS) + SD, "sd2": SD, "A": ["A"], "B": ["B"], "bases": ["A", "B"]}
avg = {g: np.mean([P[k] for k in v], axis=0) for g, v in groups.items()}
res = {}
for t, b in [("nulls8", "bases"), ("fine10", "bases"), ("sd2", "bases"), ("nulls8", "A"), ("nulls8", "B"), ("sd2", "A"), ("sd2", "B")]:
    d = excess(avg[t], avg[b]); tg = tgrid(d)[0]; s = float(smax(tg))
    nulls, nm = [], []
    for st in range(0, len(orders), 500):
        tp = tgrid_fast(apply_orders(d, orders[st:st + 500]))[0]
        nulls.append(smax(tp)); nm.append(np.mean(tp ** 2, axis=(-2, -1)))
    nulls, nm = np.concatenate(nulls), np.concatenate(nm)
    mt2 = float(np.mean(tg ** 2))
    top = np.argsort(-np.abs(tg), axis=None)[:5]
    res[f"{t}|{b}"] = {"S": s, "p": tail_p(nulls, s), "mean_t2": mt2, "p_mean_t2": tail_p(nm, mt2),
                       "top": [(cands[np.unravel_index(f, tg.shape)[0]], AXES[np.unravel_index(f, tg.shape)[1]], float(tg.ravel()[f])) for f in top]}
    r = res[f"{t}|{b}"]
    print(f"{t:7s}|{b:6s} S={s:.2f} p={r['p']:.4f} mean t2={mt2:.3f} p={r['p_mean_t2']:.4f} top={[(a[:8], x[:26], round(v, 2)) for a, x, v in r['top'][:3]]}", flush=True)
json.dump(res, open(OUT / "common_finetune.json", "w"), indent=1)
