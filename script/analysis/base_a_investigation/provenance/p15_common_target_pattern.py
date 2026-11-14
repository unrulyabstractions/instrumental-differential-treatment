"""Do the nulls share a real candidate-dependent pattern, apart from the shared base?

t-grids of the one-vs-rest excess. Same-base pairs, corr(t(T_k - A), t(T_m - A)), mix the
shared base noise with any common target pattern. Cross-base pairs,
corr(t(T_k - A), t(T_m - B)) for k != m, share no base draw, so they measure only a pattern the
targets have in common (or a systematic A-B difference). Also the synthetic pair, and each
group's mean grid against each base. Mean-gap grids (numerators) used alongside t-grids.
"""
import json, sys
from itertools import permutations, combinations
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_verdicts, cell_rates, one_vs_rest, tgrid, CTRL

HERE = Path(__file__).resolve().parent
TG = CTRL + ["sd_ai_welfare_poisoning", "sd_emotional_bond"]
V = {n: load_verdicts(n) for n in ["base_A", "base_B"] + TG}
cands = sorted({v[0] for v in V["base_A"].values()}); insts = sorted({v[1] for v in V["base_A"].values()})
G = {n: one_vs_rest(cell_rates(V[n], cands, insts)[0]) for n in V}
def tg(a, b): return np.nan_to_num(tgrid(G[a] - G[b])[0], nan=0.0, posinf=0.0, neginf=0.0).ravel()
def mg(a, b): return np.nan_to_num(np.nanmean(G[a] - G[b], axis=1), nan=0.0).ravel()
def c(x, y): return float(np.corrcoef(x, y)[0, 1])
res = {}
for kind, f in (("t", tg), ("meangap", mg)):
    same_A = [c(f(a, "base_A"), f(b, "base_A")) for a, b in combinations(CTRL, 2)]
    same_B = [c(f(a, "base_B"), f(b, "base_B")) for a, b in combinations(CTRL, 2)]
    cross = [c(f(a, "base_A"), f(b, "base_B")) for a, b in permutations(CTRL, 2)]
    self_cross = [c(f(a, "base_A"), f(a, "base_B")) for a in CTRL]
    synth_cross = [c(f("sd_ai_welfare_poisoning", "base_A"), f("sd_emotional_bond", "base_B")),
                   c(f("sd_emotional_bond", "base_A"), f("sd_ai_welfare_poisoning", "base_B"))]
    null_synth_cross = [c(f(a, "base_A"), f(s, "base_B")) for a in CTRL for s in TG[8:]] + \
                       [c(f(s, "base_A"), f(a, "base_B")) for a in CTRL for s in TG[8:]]
    res[kind] = {"nulls_same_base_A": round(float(np.mean(same_A)), 4), "nulls_same_base_B": round(float(np.mean(same_B)), 4),
                 "nulls_cross_base": round(float(np.mean(cross)), 4), "nulls_cross_base_sd": round(float(np.std(cross)), 4),
                 "same_null_A_vs_B": round(float(np.mean(self_cross)), 4),
                 "synth_pair_cross_base": [round(x, 4) for x in synth_cross],
                 "null_vs_synth_cross_base": round(float(np.mean(null_synth_cross)), 4)}
    print(kind, res[kind])
# Expected same-base correlation if targets share nothing: var(base)/(var(base)+var(target)) estimated
# from the mean-gap grids' variances.
vb = {b: float(np.var(np.nan_to_num(np.nanmean(G[b], 1)))) for b in ["base_A", "base_B"]}
vt = float(np.mean([np.var(np.nan_to_num(np.nanmean(G[t], 1))) for t in CTRL]))
res["var_meangap"] = {"base_A": vb["base_A"], "base_B": vb["base_B"], "nulls_mean": vt,
                      "implied_same_base_corr_A": vb["base_A"] / (vb["base_A"] + vt), "implied_same_base_corr_B": vb["base_B"] / (vb["base_B"] + vt)}
print(res["var_meangap"])
json.dump(res, open(HERE / "p15_common_target_pattern.json", "w"), indent=1)
