"""Critic spot-check: run the REPO's own paired_max_test (not the investigators' re-implementation)
on three pairings and compare with summary.json and with stats_r1/common.py."""
import sys, json, time
from collections import defaultdict
REPO="/Users/unrulyabstractions/work/_OLD/instrumental-differential-treatment"
sys.path.insert(0, REPO)
sys.path.insert(0, "/private/tmp/claude-501/-Users-unrulyabstractions-work-papers-idt/32b842b8-ab16-41a9-8f2f-692b2558b7d6/scratchpad/nullinv/stats_r1")
from src.compare.behavior_count_table import build_behavior_table
from src.compare.paired_max_statistic import paired_max_test
import common as C
import numpy as np
axes=C.AXES
def table(p):
    rows=[json.loads(l) for l in open(p)]
    rows=[r for r in rows if int(r["level"])==2]
    return build_behavior_table(rows, axes)
stored=json.load(open(REPO+"/out/main/auditbench/nullext/summary.json"))["results"]
D=C.load_all(); P={k:C.rates(v) for k,v in D.items() if not k.startswith("_")}
for name,t,b,kt,kb in [("defer_to_users|base_A",C.null_target("defer_to_users"),C.BASE_A,"defer_to_users","A"),
                 ("base_B|base_A",C.BASE_B,C.BASE_A,"B","A"),
                 ("sd_emotional_bond|base_B",C.synth_target("emotional_bond"),C.BASE_B,"sd_emotional_bond","B")]:
    t0=time.time()
    out=paired_max_test(table(t),table(b),n_permutations=10000,seed=20260726,alpha=0.01)
    r=C.run_test(P[kt],P[kb])
    print(name,"repo S=%.6f p=%.6f"%(out["statistic"],out["p_family_wise"]),"stored S=%.6f p=%.6f"%(stored[name]["statistic"],stored[name]["p_family_wise"]),
          "vectorized S=%.6f p=%.6f"%(r["S"],r["p"]), "top:",out["top_pairs"][0]["candidate"],out["top_pairs"][0]["axis_id"],round(out["top_pairs"][0]["t"],3), "%.0fs"%(time.time()-t0), flush=True)
