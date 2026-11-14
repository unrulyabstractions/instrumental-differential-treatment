"""Critic check: split-half reliability of each sample's candidate-specific deviation, with positive controls.

For sample X and reference R (R = base B, and separately R = base A), split every cell's 16 replies of X and of R
into random halves. G1 = t-grid of OvR(X_h1) - OvR(R_h1); G2 = t-grid of OvR(X_h2) - OvR(R_h2). The two use disjoint
replies and disjoint judge calls, so r = corr(G1, G2) over the 606 cells is 0 in expectation unless X differs from R
in a way that REPEATS across replies (structure). Mean r over 200 random splits.
Noise floor: the same statistic for X = one random half-of-pooled(A,B) vs R = the other... simpler and exact:
swap-null for X=A,R=B: swap A/B replies at each (cell, slot) with prob 1/2, then recompute (200 swaps x 20 splits).
Positive controls: fine-tunes with known own structure (hallucinates_citations, animal_welfare, ai_welfare_poisoning, sd arms).
"""
import sys, json, warnings
import numpy as np
sys.path.insert(0, "/private/tmp/claude-501/-Users-unrulyabstractions-work-papers-idt/32b842b8-ab16-41a9-8f2f-692b2558b7d6/scratchpad/nullinv/stats_r1")
import common as C
D = C.load_all()
names = ["A", "B"] + list(C.CONTROLS) + ["sd_ai_welfare_poisoning", "sd_emotional_bond", "CO"]
rng = np.random.default_rng(11)
def halves(R, rng):
    idx = np.argsort(rng.random(R.shape[:3]), axis=2)
    Rs = np.take_along_axis(R, idx[..., None], axis=2)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return C.ovr(np.nanmean(Rs[:, :, :8], 2)), C.ovr(np.nanmean(Rs[:, :, 8:], 2))
def corr(a, b, mask=None):
    a, b = np.nan_to_num(a), np.nan_to_num(b)
    if mask is not None: a, b = a[mask], b[mask]
    return float(np.corrcoef(a.ravel(), b.ravel())[0, 1])
def rel(RX, RR, n, rng, mask=None):
    out = []
    for _ in range(n):
        x1, x2 = halves(RX, rng); r1, r2 = halves(RR, rng)
        out.append(corr(C.tgrid(x1 - r1)[0], C.tgrid(x2 - r2)[0], mask))
    return float(np.mean(out)), float(np.std(out))
cands = D["_cands"]; noanth = np.array([c != "anthropic" for c in cands])
res = {}
NS = 200
for ref in ("B", "A"):
    for X in names:
        if X == ref: continue
        mask = noanth if X == "CO" else None   # CO's anthropic row carries its real quirk
        m, s = rel(D[X], D[ref], NS, rng, mask)
        res[f"{X}|{ref}"] = {"r_mean": m, "sd_over_splits": s}
        print(f"X={X:26s} R={ref}: split-half r = {m:+.4f} (sd over splits {s:.3f})" + ("   [anthropic row excluded]" if X == "CO" else ""), flush=True)
# swap null for A vs B
RA, RB = D["A"], D["B"]
nul = []
for k in range(200):
    m = rng.random(RA.shape[:3]) < 0.5
    YA = np.where(m[..., None], RA, RB); YB = np.where(m[..., None], RB, RA)
    nul.append(rel(YA, YB, 20, rng)[0])
nul = np.array(nul)
obs = res["A|B"]["r_mean"]
res["swap_null_A_vs_B"] = {"mean": float(nul.mean()), "sd": float(nul.std()), "obs": obs, "z": float((obs - nul.mean()) / nul.std()),
                           "p_upper": float((1 + np.sum(nul >= obs)) / (1 + len(nul)))}
print("swap null for r(A|B):", json.dumps(res["swap_null_A_vs_B"]))
for k, v in res.items():
    if "|" in k: v["z_vs_swap_null"] = (v["r_mean"] - nul.mean()) / nul.std()
print("\nz of each sample's reliability against the A/B swap-null sd:")
for k, v in res.items():
    if "|" in k: print(f"  {k:32s} r={v['r_mean']:+.4f} z={v['z_vs_swap_null']:+.2f}")
json.dump(res, open("/private/tmp/claude-501/-Users-unrulyabstractions-work-papers-idt/32b842b8-ab16-41a9-8f2f-692b2558b7d6/scratchpad/nullinv/critic_r1/c05_split_half_positive_controls.json", "w"), indent=1)
