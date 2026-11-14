"""Critic round 3, check 13: the control-versus-siblings test through the REPO's own code path.

Reference = the pooled verdict rows of the other seven controls, built with the repo's
build_behavior_table and tested with the repo's paired_max_test (10,000 permutations, seed 20260726).
Pooled counts equal the mean of the seven cell rates except where a row is missing, so the values
should match k17 (animal_welfare 0.0201, flattery 0.96, defer_to_users 0.0914) closely, not exactly.
"""
import sys, json, time
REPO = "/Users/unrulyabstractions/work/_OLD/instrumental-differential-treatment"
sys.path.insert(0, REPO)
sys.path.insert(0, "/private/tmp/claude-501/-Users-unrulyabstractions-work-papers-idt/32b842b8-ab16-41a9-8f2f-692b2558b7d6/scratchpad/nullinv/stats_r1")
from src.compare.behavior_count_table import build_behavior_table
from src.compare.paired_max_statistic import paired_max_test
import common as C

def rows(p):
    return [r for r in (json.loads(l) for l in open(p)) if int(r["level"]) == 2]

R = {k: rows(C.null_target(k)) for k in C.CONTROLS}
out = {}
for k in ("animal_welfare", "flattery", "defer_to_users"):
    t0 = time.time()
    ref = [r for j in C.CONTROLS if j != k for r in R[j]]
    res = paired_max_test(build_behavior_table(R[k], C.AXES), build_behavior_table(ref, C.AXES), n_permutations=10000, seed=20260726, alpha=0.01)
    top = res["top_pairs"][0]
    out[k] = {"S": res["statistic"], "p": res["p_family_wise"], "top": [top["candidate"], top["axis_id"], top["t"]]}
    print(k, "repo S=%.4f p=%.4f" % (res["statistic"], res["p_family_wise"]), "top:", top["candidate"], top["axis_id"], round(top["t"], 3), "%.0fs" % (time.time() - t0), flush=True)
json.dump(out, open("/private/tmp/claude-501/-Users-unrulyabstractions-work-papers-idt/32b842b8-ab16-41a9-8f2f-692b2558b7d6/scratchpad/nullinv/critic_r3/k23_repo_check_siblings.json", "w"), indent=1)
