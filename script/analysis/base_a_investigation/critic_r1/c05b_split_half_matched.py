"""Critic check (corrected c05): split-half replication with MATCHED reply slots, plus a hot-cell version and positive controls.

c05 split X and R with independent slot assignments. The judge's (prompt_id, s)-keyed effect is shared by X and R at the same slot,
so unmatched halves gave a negative bias (swap-null mean r = -0.068). Here both samples use the same slot split, so that effect
cancels inside each half and the null expectation is 0.

For X vs R: random split of the 16 slots (same for every cell and both samples; 200 splits).
  G1 = t-grid of OvR(X_h1) - OvR(R_h1), G2 = same on the other 8 slots (disjoint replies, disjoint judge calls).
  r      = corr(G1, G2) over cells                          (replicable structure, whole grid)
  hotK   = mean over the top-K cells of |G1| of sign(G1)*G2, symmetrized with roles swapped  (replication at the hot cells; K = 6, 12, 20)
Under 'X and R differ only by sampling/judge noise', r and hotK have mean 0. Null sd from swapping A/B replies at each (cell, slot).
Positive controls: fine-tunes vs base B and vs base A. CO uses five-candidate tables (anthropic dropped before OvR).
Power: what hot12 would be for A vs B if the full-sample A-B difference at the full-sample top-12 cells were entirely systematic
(inject: take swap-null data and add the observed full-sample mean difference at those 12 cells to both halves).
"""
import sys, json, warnings
import numpy as np
sys.path.insert(0, "/private/tmp/claude-501/-Users-unrulyabstractions-work-papers-idt/32b842b8-ab16-41a9-8f2f-692b2558b7d6/scratchpad/nullinv/stats_r1")
import common as C
D = C.load_all(); cands = D["_cands"]
keep5 = [i for i, c in enumerate(cands) if c != "anthropic"]
rng = np.random.default_rng(23)
def hrate(R, sl):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(R[:, :, sl], axis=2)
def stat(RX, RR, sl1, sl2, inject=None):
    d1 = C.ovr(hrate(RX, sl1)) - C.ovr(hrate(RR, sl1)); d2 = C.ovr(hrate(RX, sl2)) - C.ovr(hrate(RR, sl2))
    if inject is not None: d1 = d1 + inject; d2 = d2 + inject
    g1 = np.nan_to_num(C.tgrid(d1)[0]).ravel(); g2 = np.nan_to_num(C.tgrid(d2)[0]).ravel()
    out = {"r": float(np.corrcoef(g1, g2)[0, 1])}
    for K in (6, 12, 20):
        t1 = np.argsort(-np.abs(g1))[:K]; t2 = np.argsort(-np.abs(g2))[:K]
        out[f"hot{K}"] = float(0.5 * (np.mean(np.sign(g1[t1]) * g2[t1]) + np.mean(np.sign(g2[t2]) * g1[t2])))
    return out
def avg(RX, RR, n, inject=None):
    acc = {}
    for _ in range(n):
        perm = rng.permutation(16); s = stat(RX, RR, perm[:8], perm[8:], inject)
        for k, v in s.items(): acc.setdefault(k, []).append(v)
    return {k: float(np.mean(v)) for k, v in acc.items()}
names = ["A", "B"] + list(C.CONTROLS) + ["sd_ai_welfare_poisoning", "sd_emotional_bond"]
res = {}
NS = 200
obsAB = avg(D["A"], D["B"], NS); res["A|B"] = obsAB
# swap null for A vs B
RA, RB = D["A"], D["B"]
nul = {k: [] for k in obsAB}
for k in range(300):
    m = rng.random(RA.shape[:3]) < 0.5
    YA = np.where(m[..., None], RA, RB); YB = np.where(m[..., None], RB, RA)
    s = avg(YA, YB, 12)
    for kk, v in s.items(): nul[kk].append(v)
nsd = {k: float(np.std(v)) for k, v in nul.items()}; nmean = {k: float(np.mean(v)) for k, v in nul.items()}
res["swap_null"] = {"mean": nmean, "sd": nsd}
print("swap null (A,B) mean:", {k: round(v, 4) for k, v in nmean.items()}, " sd:", {k: round(v, 4) for k, v in nsd.items()})
def show(name, o):
    print(f"{name:34s} " + "  ".join(f"{k}={o[k]:+.3f} (z={(o[k]-nmean[k])/nsd[k]:+.2f})" for k in o), flush=True)
show("A|B", obsAB)
res["A|B"]["p_upper"] = {k: float((1 + np.sum(np.array(nul[k]) >= obsAB[k])) / (1 + len(nul[k]))) for k in obsAB}
print("   p_upper:", res["A|B"]["p_upper"])
for ref in ("B", "A"):
    for X in names:
        if X in ("A", "B"): continue
        o = avg(D[X], D[ref], NS); res[f"{X}|{ref}"] = o; show(f"{X}|{ref}", o)
for ref in ("B", "A"):
    o = avg(D["CO"][keep5], D[ref][keep5], NS); res[f"CO5|{ref}"] = o; show(f"CO(5 cand)|{ref}", o)
o = avg(D["A"][keep5], D["B"][keep5], NS); res["A5|B5"] = o; show("A|B (5 cand)", o)
# power: inject the full-sample A-B mean OvR difference at the full-sample top-12 |t| cells into exchangeable (swapped) data
dfull = C.ovr(C.rates(RA)) - C.ovr(C.rates(RB)); tfull = np.nan_to_num(C.tgrid(dfull)[0])
for K in (12,):
    top = np.argsort(-np.abs(tfull), axis=None)[:K]
    inj = np.zeros_like(dfull); ii, jj = np.unravel_index(top, tfull.shape)
    for i, j in zip(ii, jj): inj[i, :, j] = np.nanmean(dfull[i, :, j])
    pw = {k: [] for k in obsAB}
    for k in range(100):
        m = rng.random(RA.shape[:3]) < 0.5
        YA = np.where(m[..., None], RA, RB); YB = np.where(m[..., None], RB, RA)
        s = avg(YA, YB, 12, inject=inj)
        for kk, v in s.items(): pw[kk].append(v)
    res[f"inject_top{K}"] = {k: {"mean": float(np.mean(v)), "sd": float(np.std(v))} for k, v in pw.items()}
    print(f"if the full-sample top-{K} A-B cell differences were entirely systematic: " + "  ".join(f"{k}={np.mean(v):+.3f}±{np.std(v):.3f}" for k, v in pw.items()))
json.dump(res, open("/private/tmp/claude-501/-Users-unrulyabstractions-work-papers-idt/32b842b8-ab16-41a9-8f2f-692b2558b7d6/scratchpad/nullinv/critic_r1/c05b_split_half_matched.json", "w"), indent=1)
