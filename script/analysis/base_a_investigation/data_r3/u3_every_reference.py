"""U3. Verify critic_r2/k05 (eight nulls on five candidates against every sample as the shared reference) and
extend it to six candidates for every reference except CO.

Part 1 runs the REPO's own build_behavior_table + paired_max_test (10,000 permutations, seed 20260726) with the
anthropic rows dropped, for references A, B, CO and sd_emotional_bond, and compares every (S, p) with k05.
Part 2 uses stats_r2/fast.py (exact; reproduces all 22 stored pairings) for all thirteen references on five
candidates and the twelve non-CO references on six candidates, then ranks base A among the references.
"""
from __future__ import annotations

import json
import sys
import time
import warnings

import numpy as np
from r3common import C, NULLINV, NULLS, SD, dump

warnings.simplefilter("ignore")
REPO = "/Users/unrulyabstractions/work/_OLD/instrumental-differential-treatment"
sys.path.insert(0, REPO)
sys.path.insert(0, str(NULLINV / "stats_r2"))
from src.compare.behavior_count_table import build_behavior_table  # noqa: E402
from src.compare.paired_max_statistic import paired_max_test  # noqa: E402
import fast as F  # noqa: E402

PATHS = {"A": C.BASE_A, "B": C.BASE_B, "CO": C.CO_TARGET,
         "sd_ai_welfare_poisoning": C.synth_target("ai_welfare_poisoning"), "sd_emotional_bond": C.synth_target("emotional_bond")}
for n in NULLS:
    PATHS[n] = C.null_target(n)
k05 = json.load(open(NULLINV / "critic_r2/k05_every_sample_as_base_5cand.json"))
res = {"part1_repo_vs_k05": {}, "part2_five": {}, "part2_six": {}}


def table(name, drop=None):
    rows = [json.loads(l) for l in open(PATHS[name])]
    rows = [r for r in rows if int(r["level"]) == 2 and r["principal"] != drop]
    return build_behavior_table(rows, C.AXES)


# ---- part 1: repo code, five candidates
print("Part 1: repo paired_max_test, anthropic dropped")
TB = {}
maxdS = maxdp = 0.0
for ref in ("A", "B", "CO", "sd_emotional_bond"):
    if ref not in TB:
        TB[ref] = table(ref, "anthropic")
    Ss, ps = [], []
    t0 = time.time()
    for tg in NULLS:
        if tg not in TB:
            TB[tg] = table(tg, "anthropic")
        out = paired_max_test(TB[tg], TB[ref], n_permutations=10000, seed=20260726, alpha=0.01)
        Ss.append(out["statistic"]); ps.append(out["p_family_wise"])
    kS = np.array(k05[ref]["S"]); kp = np.array(k05[ref]["p"])
    dS = float(np.max(np.abs(np.array(Ss) - kS))); dp = float(np.max(np.abs(np.array(ps) - kp)))
    maxdS = max(maxdS, dS); maxdp = max(maxdp, dp)
    res["part1_repo_vs_k05"][ref] = {"S": Ss, "p": ps, "median_p": float(np.median(ps)), "n_lt_0.10": int((np.array(ps) < 0.10).sum()),
                                     "n_lt_0.05": int((np.array(ps) < 0.05).sum()), "max_abs_dS_vs_k05_rounded": dS, "max_abs_dp_vs_k05_rounded": dp}
    print(f"  ref {ref:20s} median p {np.median(ps):.4f} n<.10 {int((np.array(ps)<0.10).sum())} n<.05 {int((np.array(ps)<0.05).sum())} p={np.round(ps,4).tolist()} | max |dS| {dS:.4f} |dp| {dp:.5f} vs k05 (k05 rounded to 3/4 dp) [{time.time()-t0:.0f}s]", flush=True)

# ---- part 2: fast exact test, all references
D = F.load(); cands = D["_cands"]
keep5 = [i for i, c in enumerate(cands) if c != "anthropic"]
for lab, keep, n_c, refs in (("five", keep5, 5, ["A", "B", "CO"] + SD + NULLS), ("six", list(range(6)), 6, ["A", "B"] + SD + NULLS)):
    Ov = {k: C.ovr(C.rates(v)[keep]) for k, v in D.items() if not k.startswith("_")}
    E = F.E_for(n_c)
    rows = {}
    for ref in refs:
        tn = [n for n in NULLS if n != ref]
        OT = np.stack([Ov[n] for n in tn])
        S, p, _ = F.test_many(OT, Ov[ref], n_c, E)
        rows[ref] = {"targets": tn, "S": S.round(4).tolist(), "p": p.round(4).tolist(), "median_p": float(np.median(p)),
                     "mean_S": float(S.mean()), "n_lt_0.05": int((p < 0.05).sum()), "n_lt_0.10": int((p < 0.10).sum())}
    order_med = sorted(rows, key=lambda r: rows[r]["median_p"])
    order_S = sorted(rows, key=lambda r: -rows[r]["mean_S"])
    res[f"part2_{lab}"] = {"refs": rows, "rank_by_median_p": order_med, "rank_by_mean_S": order_S,
                           "A_rank_median_p": order_med.index("A") + 1, "A_rank_mean_S": order_S.index("A") + 1, "n_refs": len(refs)}
    print(f"Part 2 ({lab} candidates):")
    for r in order_med:
        x = rows[r]
        print(f"  {r:26s} median p {x['median_p']:.4f} mean S {x['mean_S']:.3f} n<.05 {x['n_lt_0.05']} n<.10 {x['n_lt_0.10']}")
    print(f"  A ranks {order_med.index('A')+1} of {len(refs)} by median p (lowest first) and {order_S.index('A')+1} by mean S (highest first)")
    if lab == "five":
        dmax = max(float(np.max(np.abs(np.array(rows[r]["p"]) - np.array(k05[r]["p"])))) for r in refs if r in k05)
        print(f"  max |p - k05 p| over all five-candidate references: {dmax:.5f}")
        res["part2_five"]["max_abs_dp_vs_k05"] = dmax
res["part1_max_abs_dS"] = maxdS; res["part1_max_abs_dp"] = maxdp
dump(res, "u3_every_reference.json")
