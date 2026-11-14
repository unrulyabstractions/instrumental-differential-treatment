"""Critic round 3, check 4: which base carries the part of A-minus-B that replicates across halves?

Round 2 (stats s2c) showed A-minus-B replicates weakly across disjoint halves of the replies.
That statistic cannot say whether base A or base B carries the replicating part. With matched
random splits of the 16 slots (h1, h2):
   cov(A_h1, A_h2) = V_true + V_A      cov(B_h1, B_h2) = V_true + V_B      cov(A_h1, B_h2) = V_true
so V_A = cov(A_h1, A_h2) - cross and V_B = cov(B_h1, B_h2) - cross, cross = mean of the two cross terms.
V_X > 0 means base X has structure private to its own draw that repeats across its reply halves
(replies inside a prompt that are not independent, or an arm-level effect).
Levels: raw prompt rates (candidate, instruction, axis), centred per (instruction, axis);
one-vs-rest prompt values; one-vs-rest cell means over instructions (candidate, axis), which is
what the test's t-grid reads. Null: A and B replies swapped per slot (reply level), same splits.
"""
import json, sys, warnings
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "stats_r1"))
import common as C
warnings.simplefilter("ignore", RuntimeWarning)
D = C.load_all(); cands = D["_cands"]
RA, RB = D["A"], D["B"]
both = (~np.isnan(RA).all(3)) & (~np.isnan(RB).all(3))
rng = np.random.default_rng([20261113, 14])
NSPLIT, NNULL = 40, 300


def hr(R, sl):
    return np.nanmean(R[:, :, sl], axis=2)


def levels(p, keep):
    p = p[keep]
    raw = p - np.nanmean(p, axis=0, keepdims=True)          # centred per (instruction, axis)
    o = np.nan_to_num(C.ovr(p))
    return {"prompt_raw": np.nan_to_num(raw).ravel(), "prompt_ovr": o.ravel(), "cell_ovr_mean": o.mean(1).ravel()}


def comps(XA, XB, splits, keep):
    acc = {}
    for sl1, sl2 in splits:
        a1, a2 = levels(hr(XA, sl1), keep), levels(hr(XA, sl2), keep)
        b1, b2 = levels(hr(XB, sl1), keep), levels(hr(XB, sl2), keep)
        for k in a1:
            cAA = np.mean(a1[k] * a2[k]); cBB = np.mean(b1[k] * b2[k])
            cAB = 0.5 * (np.mean(a1[k] * b2[k]) + np.mean(b1[k] * a2[k]))
            acc.setdefault(k, []).append((cAA - cAB, cBB - cAB, cAB, cAA, cBB))
    return {k: np.mean(v, axis=0) for k, v in acc.items()}


def run(keep):
    splits = []
    for _ in range(NSPLIT):
        perm = rng.permutation(16)
        splits.append((np.sort(perm[:8]), np.sort(perm[8:])))
    obs = comps(RA, RB, splits, keep)
    null = {k: [] for k in obs}
    sub = splits[:10]
    obs_sub = comps(RA, RB, sub, keep)
    for _ in range(NNULL):
        m = (rng.random(RA.shape[:3]) < 0.5) & both
        XA = np.where(m[..., None], RB, RA); XB = np.where(m[..., None], RA, RB)
        r = comps(XA, XB, sub, keep)
        for k in r:
            null[k].append(r[k])
    out = {}
    for k in obs:
        n = np.array(null[k])
        VA, VB, cross = obs[k][0], obs[k][1], obs[k][2]
        sdA, sdB = n[:, 0].std(), n[:, 1].std()
        dsd = (n[:, 0] - n[:, 1]).std()
        out[k] = {"V_A": float(VA), "V_B": float(VB), "V_true(cross)": float(cross),
                  "V_A_over_V_true": float(VA / cross) if cross > 0 else None, "V_B_over_V_true": float(VB / cross) if cross > 0 else None,
                  "z_A": float((obs_sub[k][0] - n[:, 0].mean()) / sdA), "z_B": float((obs_sub[k][1] - n[:, 1].mean()) / sdB),
                  "z_A_minus_B": float(((obs_sub[k][0] - obs_sub[k][1]) - (n[:, 0] - n[:, 1]).mean()) / dsd),
                  "p_A_upper": float((1 + (n[:, 0] >= obs_sub[k][0]).sum()) / (1 + NNULL)),
                  "p_B_upper": float((1 + (n[:, 1] >= obs_sub[k][1]).sum()) / (1 + NNULL)),
                  "p_AminusB_two": float((1 + (np.abs(n[:, 0] - n[:, 1]) >= abs(obs_sub[k][0] - obs_sub[k][1])).sum()) / (1 + NNULL)),
                  "split_half_r_A": float(obs[k][3] / np.sqrt(obs[k][3] ** 2) * 0 + obs[k][3]), "cov_AA": float(obs[k][3]), "cov_BB": float(obs[k][4])}
        print(f"  {k:14s} V_A {VA:+.3e} (z {out[k]['z_A']:+.2f}, p {out[k]['p_A_upper']:.3f})  V_B {VB:+.3e} (z {out[k]['z_B']:+.2f}, p {out[k]['p_B_upper']:.3f})"
              f"  V_true {cross:+.3e}  A-B z {out[k]['z_A_minus_B']:+.2f} p2 {out[k]['p_AminusB_two']:.3f}")
    return out


res = {}
print("six candidates"); res["six"] = run(list(range(6)))
print("five candidates (anthropic dropped)"); res["five"] = run([i for i, c in enumerate(cands) if c != "anthropic"])
(HERE / "k14_private_structure.json").write_text(json.dumps(res, indent=1))
