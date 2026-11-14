"""Critic r2, check 9: could one systematic A-minus-B difference J explain BOTH directions (nulls
closer to B, synthetic arms closer to A)? It would need the nulls' structure to oppose J and the
synthetic arms' structure to follow J, so the two families' structures would be opposite. Test:
correlate t-grids across different bases, so no base noise is shared:
   corr( t(SD_k - B), t(N_j - A) )   and   corr( t(SD_k - A), t(N_j - B) ).
Opposite structures predict negative values; a shift common to all fine-tunes predicts positive.
Reference: null-null across bases, corr( t(N_i - A), t(N_j - B) ), i != j.
Null distribution for each mean correlation: relabel candidates within instruction in the SD (or
first) sample's one-vs-rest grid (the registered permutation), 400 draws.
"""
import sys, json
import numpy as np
BASE = "/private/tmp/claude-501/-Users-unrulyabstractions-work-papers-idt/32b842b8-ab16-41a9-8f2f-692b2558b7d6/scratchpad/nullinv"
sys.path.insert(0, BASE + "/stats_r1")
import common as C
import warnings; warnings.simplefilter("ignore")
D = C.load_all()
O = {k: C.ovr(C.rates(v)) for k, v in D.items() if not k.startswith("_")}
nulls = list(C.CONTROLS); sd = ["sd_ai_welfare_poisoning", "sd_emotional_bond"]
def tg(d):
    t = C.tgrid(d)[0]
    return np.where(np.isfinite(t), t, 0.0).ravel()
def cc(a, b): return float(np.corrcoef(a, b)[0, 1])
res = {}
pairs = {"SD|B vs null|A": [(k, "B", j, "A") for k in sd for j in nulls],
         "SD|A vs null|B": [(k, "A", j, "B") for k in sd for j in nulls],
         "null|A vs null|B (i != j)": [(i, "A", j, "B") for i in nulls for j in nulls if i != j],
         "SD|B vs SD|A (k != l)": [(sd[0], "B", sd[1], "A"), (sd[1], "B", sd[0], "A")]}
orders = C.perm_orders(k=400)
for lab, pl in pairs.items():
    obs = np.mean([cc(tg(O[a] - O[x]), tg(O[b] - O[y])) for a, x, b, y in pl])
    # permutation: relabel candidates within instruction for the first sample's difference grid
    nullv = []
    firsts = sorted({(a, x) for a, x, _, _ in pl})
    seconds = {(b, y): tg(O[b] - O[y]) for _, _, b, y in pl}
    for q in range(400):
        perm = {}
        for a, x in firsts:
            d = (O[a] - O[x])
            dp = C.apply_orders(d, orders[q:q + 1])[0]
            perm[(a, x)] = tg(dp)
        nullv.append(np.mean([cc(perm[(a, x)], seconds[(b, y)]) for a, x, b, y in pl]))
    nullv = np.array(nullv)
    res[lab] = {"mean_corr": float(obs), "null_mean": float(nullv.mean()), "null_sd": float(nullv.std()), "z": float((obs - nullv.mean()) / nullv.std()), "n_pairs": len(pl)}
    print(lab, json.dumps(res[lab]), flush=True)
json.dump(res, open(BASE + "/critic_r2/k09_cross_base_structure.json", "w"), indent=1)
