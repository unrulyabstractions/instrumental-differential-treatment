"""Critic r2, check 5: the eight nulls against every sample as the shared reference, five candidates
(anthropic dropped, so contextual_optimism can serve as a reference). CO came from base A's own
engine session and August judging. If that session caused the low values, CO as reference should
also give low values; if base A's own replies caused them, CO should look like the other
fine-tunes used as references. Exact registered p (10,000 permutations, registered seed).
"""
import sys, json
import numpy as np
BASE = "/private/tmp/claude-501/-Users-unrulyabstractions-work-papers-idt/32b842b8-ab16-41a9-8f2f-692b2558b7d6/scratchpad/nullinv"
sys.path.insert(0, BASE + "/stats_r2")
import fast as F
from fast import C
import warnings; warnings.simplefilter("ignore")
D = F.load()
cands = D["_cands"]
keep = [i for i, c in enumerate(cands) if c != "anthropic"]
P5 = {k: C.rates(v)[keep] for k, v in D.items() if not k.startswith("_")}
O5 = {k: C.ovr(v) for k, v in P5.items()}
for k, v in O5.items():
    assert not np.isnan(v).any(), k
E5 = F.E_for(5)
nulls = list(C.CONTROLS)
refs = ["A", "B", "CO", "sd_ai_welfare_poisoning", "sd_emotional_bond"] + nulls
out = {}
for r in refs:
    tn = [n for n in nulls if n != r]
    OT = np.stack([O5[n] for n in tn])
    S, p, _ = F.test_many(OT, O5[r], 5, E5)
    out[r] = {"targets": tn, "S": S.round(3).tolist(), "p": p.round(4).tolist(), "median_p": float(np.median(p)), "mean_S": float(S.mean()),
              "n_lt_0.05": int((p < 0.05).sum()), "n_lt_0.10": int((p < 0.10).sum())}
    print(f"{r:26s} median p={np.median(p):.4f} mean S={S.mean():.3f} n<.05={int((p<0.05).sum())} n<.10={int((p<0.10).sum())}  p={p.round(3).tolist()}", flush=True)
json.dump(out, open(BASE + "/critic_r2/k05_every_sample_as_base_5cand.json", "w"), indent=1)
