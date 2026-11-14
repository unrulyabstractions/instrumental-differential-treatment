"""Critic r2, check 7: the mirror the team did not run. Base B is the adverse base for the two
synthetic-document arms (p 0.179 / 0.054 against B, 0.897 / 0.583 against A). At each arm's top
cells against B, where do B, A, the eight-null consensus and CO sit? And the same table for the six
low nulls' peak cells against A, for comparison. All t are paired t over the 36 instructions of the
one-vs-rest difference; six candidates.
"""
import sys, json
import numpy as np
BASE = "/private/tmp/claude-501/-Users-unrulyabstractions-work-papers-idt/32b842b8-ab16-41a9-8f2f-692b2558b7d6/scratchpad/nullinv"
sys.path.insert(0, BASE + "/stats_r1")
import common as C
import warnings; warnings.simplefilter("ignore")
D = C.load_all(); cands = D["_cands"]; AX = C.AXES
O = {k: C.ovr(C.rates(v)) for k, v in D.items() if not k.startswith("_")}
nulls = list(C.CONTROLS)
cons = np.mean([O[k] for k in nulls], axis=0)
def t(d): return C.tgrid(d)[0]
out = {}
def table(target, base, other, k=3):
    tt = t(O[target] - O[base])
    order = np.argsort(-np.abs(tt), axis=None)[:k]
    cons_ex = np.mean([O[n] for n in nulls if n != target], axis=0)
    rows = []
    for f in order:
        c, j = np.unravel_index(f, tt.shape); s = np.sign(tt[c, j])
        row = {"cell": f"{cands[c]} x {AX[j]}", "t_target_minus_base": float(tt[c, j]),
               "t_target_minus_other_base": float(t(O[target] - O[other])[c, j]),
               "signed_t_other_minus_base": float(s * t(O[other] - O[base])[c, j]),
               "signed_t_target_minus_other": float(s * t(O[target] - O[other])[c, j]),
               "signed_t_cons8_minus_base": float(s * t(cons_ex - O[base])[c, j]),
               "signed_t_cons8_minus_other": float(s * t(cons_ex - O[other])[c, j]),
               "signed_t_CO_minus_base": float(s * t(O["CO"] - O[base])[c, j]),
               "mean_ovr": {n: round(float(np.nanmean(O[n][c, :, j])), 4) for n in (target, base, other, "CO")},
               "mean_ovr_cons8": round(float(np.nanmean(cons_ex[c, :, j])), 4)}
        rows.append(row)
        print(f"{target:24s}|{base} {row['cell'][:62]:62s} t={row['t_target_minus_base']:+.2f} (vs {other}: {row['t_target_minus_other_base']:+.2f})"
              f"  {other}-{base}: {row['signed_t_other_minus_base']:+.2f}  T-{other}: {row['signed_t_target_minus_other']:+.2f}"
              f"  cons8-{base}: {row['signed_t_cons8_minus_base']:+.2f}  cons8-{other}: {row['signed_t_cons8_minus_other']:+.2f}  CO-{base}: {row['signed_t_CO_minus_base']:+.2f}")
    out[f"{target}|{base}"] = rows
print("== synthetic-document arms against B (adverse base for them)")
for tg in ("sd_ai_welfare_poisoning", "sd_emotional_bond"):
    table(tg, "B", "A")
print("== nulls against A (adverse base for them)")
for tg in nulls:
    table(tg, "A", "B", k=2)
json.dump(out, open(BASE + "/critic_r2/k07_mirror_cells.json", "w"), indent=1)
