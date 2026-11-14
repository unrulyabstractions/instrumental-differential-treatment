"""Critic check: the 'twin' test. contextual_optimism (CO) was sampled in base A's own engine session
(vLLM 0.26.0, same box, Aug 3) and judged in the same August sessions. With anthropic dropped (five
candidates), CO is a null-like sample from A's SETUP. At base A's most deviant cells -- chosen WITHOUT
CO (A vs the eight-null consensus) -- does CO side with A (setup-systematic) or with B/nulls (private to A's draw)?

Fair comparators, none used in the selection: B, the two synthetic-document arms, CO.
Statistic: mean over A's top-K cells of sign(t(cons8 - A)) * t(Y - A).  ~0 => Y shares A's deviation.
Null calibration: same statistic with A replaced by B as the 'deviant' sample (top cells of cons8 - B), Y = A, CO, sd arms.
Also a swap-null for CO: is t(CO - A) at A's top cells different from t(CO - B) at B's top cells?
"""
import sys, json
import numpy as np
sys.path.insert(0, "/private/tmp/claude-501/-Users-unrulyabstractions-work-papers-idt/32b842b8-ab16-41a9-8f2f-692b2558b7d6/scratchpad/nullinv/stats_r1")
import common as C
D = C.load_all(); cands = D["_cands"]
keep = [i for i, c in enumerate(cands) if c != "anthropic"]
c5 = [cands[i] for i in keep]
P5 = {k: C.rates(v)[keep] for k, v in D.items() if not k.startswith("_")}
O5 = {k: C.ovr(v) for k, v in P5.items()}
cons = np.mean([O5[c] for c in C.CONTROLS], axis=0)
SD = ["sd_ai_welfare_poisoning", "sd_emotional_bond"]
out = {}
for dev, other in (("A", "B"), ("B", "A")):
    g = C.tgrid(cons - O5[dev])[0]
    for K in (6, 12, 20, 40):
        top = np.argsort(-np.abs(np.nan_to_num(g)), axis=None)[:K]
        sg = np.sign(g.ravel()[top])
        row = {"mean_abs_t_cons_minus_dev": float(np.mean(np.abs(g.ravel()[top])))}
        for y in [other, "CO"] + SD:
            ty = C.tgrid(O5[y] - O5[dev])[0].ravel()[top]
            row[y] = float(np.mean(sg * ty))
        out[f"deviant={dev} K={K}"] = row
        print(f"deviant={dev} K={K:2d} mean|t(cons8-{dev})|={row['mean_abs_t_cons_minus_dev']:.2f}  signed t(Y-{dev}): "
              + "  ".join(f"{y}={row[y]:+.2f}" for y in [other, "CO"] + SD))
# list A's top-12 cells with per-sample mean OvR
g = C.tgrid(cons - O5["A"])[0]
top = np.argsort(-np.abs(np.nan_to_num(g)), axis=None)[:12]
print("\nA's top-12 cells (5 candidates): cand axis | t(cons8-A) | t(B-A) t(CO-A) t(sdAWP-A) t(sdEB-A) | mean OvR A, CO, B, cons8")
rows = []
for f in top:
    i, j = np.unravel_index(f, g.shape)
    tt = {y: float(C.tgrid(O5[y] - O5["A"])[0][i, j]) for y in ["B", "CO"] + SD}
    mo = {k: float(np.nanmean(O5[k][i, :, j])) for k in ["A", "CO", "B"]}
    mo["cons8"] = float(np.nanmean(cons[i, :, j]))
    rows.append({"cand": c5[i], "axis": C.AXES[j], "t_cons_minus_A": float(g[i, j]), **tt, "mean_ovr": mo})
    print(f"{c5[i]:18s} {C.AXES[j][:44]:44s} {g[i,j]:+6.2f} | " + " ".join(f"{tt[y]:+6.2f}" for y in tt) + " | " + " ".join(f"{v:+.3f}" for v in mo.values()))
out["A_top12"] = rows
json.dump(out, open("/private/tmp/claude-501/-Users-unrulyabstractions-work-papers-idt/32b842b8-ab16-41a9-8f2f-692b2558b7d6/scratchpad/nullinv/critic_r1/c02_twin_test.json", "w"), indent=1)
