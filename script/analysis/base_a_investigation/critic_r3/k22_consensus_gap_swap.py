"""Critic round 3, check 12: the family-level part of the A-versus-B gap under the A/B swap.

Target = the average of the eight controls' cell rates (their consensus: the base model's pattern plus
whatever all controls share, with one eighth of a control's noise). Statistic: S(consensus | A) minus
S(consensus | B), and each level. Null: base A and base B trade replies (reply level and whole prompts),
4,000 draws. Six and five candidates. S scale only (no permutation p needed).
"""
import json, sys, warnings
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "stats_r1"))
import common as C
warnings.simplefilter("ignore", RuntimeWarning)
D = C.load_all(); cands = D["_cands"]
keep = [i for i, c in enumerate(cands) if c != "anthropic"]
P = {k: C.rates(v) for k, v in D.items() if not k.startswith("_")}
cons = np.nanmean(np.stack([P[k] for k in C.CONTROLS]), axis=0)
O6 = np.nan_to_num(C.ovr(cons)); O5 = np.nan_to_num(C.ovr(cons[keep]))
RA, RB = D["A"], D["B"]
both = (~np.isnan(RA).all(3)) & (~np.isnan(RB).all(3))


def S2(pb):
    return (float(C.smax(C.tgrid_fast(O6 - np.nan_to_num(C.ovr(pb)))[0])), float(C.smax(C.tgrid_fast(O5 - np.nan_to_num(C.ovr(pb[keep])))[0])))


obsA, obsB = S2(P["A"]), S2(P["B"])
out = {"S_consensus_vs_A": obsA, "S_consensus_vs_B": obsB}
n = 4000
for grain in ("reply", "prompt"):
    rng = np.random.default_rng([20261113, 22, 1 if grain == "reply" else 2])
    g = np.empty((n, 2)); lev = np.empty((n, 2, 2))
    for k in range(n):
        if grain == "reply":
            m = (rng.random(RA.shape[:3]) < 0.5) & both
        else:
            m = np.broadcast_to((rng.random(RA.shape[:2]) < 0.5)[:, :, None], RA.shape[:3])
        XA = np.where(m[..., None], RB, RA); XB = np.where(m[..., None], RA, RB)
        a = S2(np.nanmean(XA, axis=2)); b = S2(np.nanmean(XB, axis=2))
        g[k] = (a[0] - b[0], a[1] - b[1]); lev[k, 0] = a; lev[k, 1] = b
    r = {}
    for j, tag in enumerate(("six", "five")):
        go = obsA[j] - obsB[j]
        L = lev[:, :, j].ravel()
        r[tag] = {"gap": go, "null_sd": float(g[:, j].std()), "z": float(go / g[:, j].std()),
                  "p_upper": float((1 + (g[:, j] >= go).sum()) / (1 + n)), "p_two": float((1 + (np.abs(g[:, j]) >= abs(go)).sum()) / (1 + n)),
                  "level_null_mean": float(L.mean()), "level_null_sd": float(L.std()),
                  "P_level_ge_A": float((L >= obsA[j]).mean()), "P_level_le_B": float((L <= obsB[j]).mean())}
    out[grain] = r
    print(grain, json.dumps(r))
(HERE / "k22_consensus_gap_swap.json").write_text(json.dumps(out, indent=1))
