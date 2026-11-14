"""D7 cross-check: the A/B swap test of the S gap pooled over all ten null fine-tunes (round 1 quoted only an estimate).

Null: base A and base B replies (verdict vectors) swapped at each (prompt, s) with probability 1/2, targets fixed;
4,000 draws. Statistic: mean over targets of S(target vs A') - S(target vs B'). Groups: the eight nulls; the two
synthetic-document nulls; all ten. One-sided (A worse, gap > 0) and two-sided p. S only: the per-pairing permutation
nulls are almost identical (median 3.21-3.26), so S is the scale the p-values move on.
Also the five-candidate version (anthropic dropped before one-vs-rest).
"""
import warnings

import numpy as np

from dcommon import C, dump

warnings.simplefilter("ignore", RuntimeWarning)
D = C.load_all(); cands = D["_cands"]
T8 = list(C.CONTROLS); T2 = ["sd_ai_welfare_poisoning", "sd_emotional_bond"]
rng = np.random.default_rng(99)
res = {}
for label, keep in (("six", list(range(6))), ("five", [i for i, c in enumerate(cands) if c != "anthropic"])):
    OT = {k: C.ovr(C.rates(D[k])[keep]) for k in T8 + T2}
    RA, RB = D["A"][keep], D["B"][keep]

    def gaps(ra, rb):
        oa, ob = C.ovr(np.nanmean(ra, 2)), C.ovr(np.nanmean(rb, 2))
        return np.array([float(C.smax(C.tgrid_fast(OT[k] - oa)[0])) - float(C.smax(C.tgrid_fast(OT[k] - ob)[0])) for k in T8 + T2])
    g0 = gaps(RA, RB)
    nul = np.empty((4000, 10))
    for n in range(4000):
        m = rng.random(RA.shape[:3]) < 0.5
        nul[n] = gaps(np.where(m[..., None], RB, RA), np.where(m[..., None], RA, RB))
    out = {"per_target_gap": dict(zip(T8 + T2, g0.round(4).tolist())), "per_target_swap_sd": dict(zip(T8 + T2, nul.std(0).round(4).tolist()))}
    for gname, idx in (("eight", list(range(8))), ("synth_two", [8, 9]), ("all_ten", list(range(10)))):
        o = g0[idx].mean(); nn = nul[:, idx].mean(1)
        out[gname] = {"mean_gap": float(o), "swap_sd": float(nn.std()), "z": float(o / nn.std()),
                      "p_one_sided_A_worse": float((1 + np.sum(nn >= o)) / 4001),
                      "p_two_sided": float((1 + np.sum(np.abs(nn) >= abs(o))) / 4001)}
        print(f"[{label} candidates] {gname:9s}: mean gap {o:+.3f}, swap sd {nn.std():.3f}, z {o/nn.std():+.2f}, "
              f"p one-sided {out[gname]['p_one_sided_A_worse']:.4f}, two-sided {out[gname]['p_two_sided']:.4f}")
    cm = np.corrcoef(nul[:, :8].T); out["mean_pairwise_corr_of_gaps_eight"] = float(cm[np.triu_indices(8, 1)].mean())
    print(f"   mean pairwise correlation of the eight gaps under the swap null: {out['mean_pairwise_corr_of_gaps_eight']:+.3f}")
    res[label] = out
dump(res, "d07_pooled_swap.json")
