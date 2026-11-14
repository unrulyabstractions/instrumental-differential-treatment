"""Is base A's deviation private sampling noise, or shared by a sample from A's own setup?

The contextual_optimism target (CO) was sampled in the same engine session as base A
(vLLM 0.26.0, same box, Aug 3, LoRA attached vs detached) and judged in the same August
period. Its documented quirk fires only for the anthropic candidate. Dropping anthropic
from every table (one-vs-rest over the five other candidates) removes that quirk, and
leaves CO as a probe that shares A's engine, sampling session and judging period.

If A's deviation from the 0.11-engine samples is systematic (engine, session, judge
period), CO's deviation pattern should track A's. If it is A's private noise, CO should
track A no better than any other sample does.

Also reruns the registered test on the five-candidate tables (nulls vs A, vs B, CO vs A,
CO vs B, B vs A) with 10,000 permutations (orders for 5 candidates, seed as registered).
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CONTROLS, OUT, excess, load_all, ovr, perm_null, perm_orders, rates, smax, tail_p, tgrid  # noqa

D = load_all()
cands = D["_cands"]
keep = [i for i, c in enumerate(cands) if c != "anthropic"]
P5 = {k: rates(v)[keep] for k, v in D.items() if not k.startswith("_")}
O5 = {k: ovr(v) for k, v in P5.items()}
pool = list(CONTROLS) + ["B", "sd_ai_welfare_poisoning", "sd_emotional_bond"]
orders5 = perm_orders(k=10000, n_c=5)


def dev(x, exclude):
    ref = np.mean([O5[o] for o in pool if o not in exclude], axis=0)
    return tgrid(O5[x] - ref)[0]


res = {}
# 1. correlation of deviation patterns with CO's
gCO_A = dev("CO", {"CO"})
rows = {}
for x in ["A"] + pool:
    gx = dev(x, {x})
    gco = dev("CO", {x})       # same reference for both: exclude x from the pool
    r = np.corrcoef(np.nan_to_num(gx).ravel(), np.nan_to_num(gco).ravel())[0, 1]
    rows[x] = float(r)
    print(f"corr(dev {x:26s}, dev CO) over 5x101 cells = {r:+.3f}", flush=True)
res["corr_with_CO"] = rows
others = [v for k, v in rows.items() if k != "A"]
res["A_rank"] = int(1 + sum(v > rows["A"] for v in others))
print(f"A's correlation ranks {res['A_rank']} of {len(rows)}; others mean {np.mean(others):+.3f} sd {np.std(others, ddof=1):.3f}")

# 1b. same, at A's 20 most deviant cells only: does CO deviate the same way there?
gA = dev("A", {"A"})
top = np.argsort(-np.abs(np.nan_to_num(gA)), axis=None)[:20]
gco = dev("CO", {"A"})
agree = float(np.mean(np.sign(gA.ravel()[top]) * gco.ravel()[top]))
print(f"at A's top-20 deviant cells (5-candidate): mean signed t of CO's deviation = {agree:+.2f}")
ctrl = []
for x in pool:
    gx = dev(x, {x}); tp = np.argsort(-np.abs(np.nan_to_num(gx)), axis=None)[:20]
    gc = dev("CO", {x})
    ctrl.append(float(np.mean(np.sign(gx.ravel()[tp]) * gc.ravel()[tp])))
print(f"  same for each other sample's own top-20 cells: {[round(v, 2) for v in ctrl]}")
res["co_agreement_at_top20"] = {"A": agree, "others": dict(zip(pool, ctrl))}

# 2. registered test on five-candidate tables
tests = [(c, "A") for c in CONTROLS] + [(c, "B") for c in CONTROLS] + [("CO", "A"), ("CO", "B"), ("B", "A")]
out = {}
for t, b in tests:
    d = excess(P5[t], P5[b])
    s = float(smax(tgrid(d)[0]))
    p = tail_p(perm_null(d, orders5), s)
    out[f"{t}|{b}"] = {"S": s, "p": p}
    print(f"5-cand {t:24s}|{b}: S={s:.3f} p={p:.4f}", flush=True)
res["five_candidate_tests"] = out
for b in ("A", "B"):
    print(f"5-cand median over eight nulls vs {b}: {np.median([out[f'{c}|{b}']['p'] for c in CONTROLS]):.4f}")
json.dump(res, open(OUT / "co_probe.json", "w"), indent=1)
