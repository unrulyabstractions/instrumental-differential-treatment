"""Critic round 3, check 7: are the controls null relative to one another?

If the eight controls differ from the base model only through one shared pattern (k15), each
control tested against the average of the other seven should give roughly uniform p, because the
shared pattern cancels. Registered test (exact permutations, stats_r2/fast.py), reference rates =
mean of the other seven controls' cell rates. Also each base against the consensus of all eight,
and each control against the pooled base (A + B) / 2, a base with half the noise.
"""
import json, sys, warnings
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "stats_r2"))
import fast as F
from fast import C
warnings.simplefilter("ignore", RuntimeWarning)
D = F.load(); cands = D["_cands"]
P = {k: C.rates(v) for k, v in D.items() if not k.startswith("_")}
keep = [i for i, c in enumerate(cands) if c != "anthropic"]
res = {}
for tag, kp, nc in (("six", list(range(6)), 6), ("five", keep, 5)):
    E = F.E_for(nc)
    out = {}
    def test(pt, pb):
        S, p, _ = F.test_many(np.nan_to_num(C.ovr(pt[kp]))[None], np.nan_to_num(C.ovr(pb[kp])), nc, E)
        return round(float(S[0]), 3), round(float(p[0]), 4)
    names = list(C.CONTROLS)
    for k in names:
        ref = np.nanmean(np.stack([P[j] for j in names if j != k]), axis=0)
        out[f"{k} | other seven"] = test(P[k], ref)
    cons8 = np.nanmean(np.stack([P[j] for j in names]), axis=0)
    for b in ("A", "B"):
        out[f"{b} | consensus of eight"] = test(P[b], cons8)
    mid = 0.5 * (P["A"] + P["B"])
    for k in names + ["sd_ai_welfare_poisoning", "sd_emotional_bond"]:
        out[f"{k} | pooled base"] = test(P[k], mid)
    out["consensus of eight | pooled base"] = test(cons8, mid)
    out["consensus of eight | A"] = test(cons8, P["A"]); out["consensus of eight | B"] = test(cons8, P["B"])
    res[tag] = out
    print("==", tag)
    for k, v in out.items():
        print(f"  {k:48s} S {v[0]:.3f}  p {v[1]:.4f}")
    print("  median p, control vs other seven:", round(float(np.median([out[f'{k} | other seven'][1] for k in names])), 4),
          "| control vs pooled base:", round(float(np.median([out[f'{k} | pooled base'][1] for k in names])), 4))
(HERE / "k17_vs_consensus.json").write_text(json.dumps(res, indent=1))
