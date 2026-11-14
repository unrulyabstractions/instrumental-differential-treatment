"""Critic check: is base A's deviation in the reply TEXT or in the gpt-5-mini VERDICTS?

Base A's replies (and the contextual_optimism target's) were also judged by gpt-4.1-nano on the same 101 axes
(out/main/auditbench/contextual_optimism/responses/verdicts_{base,target}.jsonl, Aug 3). Same texts, independent judge.
At base A's most deviant cells under gpt-5-mini (A vs eight-null consensus, 5 candidates, anthropic dropped):
  mini: signed t(CO - A)        (from c02: about +1.3)
  nano: signed t(CO_nano - A_nano) at the SAME cells with the SAME signs.
If A's deviation is in the text, nano reproduces a positive value (scaled by judge agreement).
If it is gpt-5-mini judge noise on A's rows, nano gives about 0.
Control: cells where B is most deviant (B has no nano verdicts; CO_nano - A_nano there should be about what mini gives for CO - A there,
which is not selected on A, so about 0 in both).
Also: nano-vs-mini agreement on base A's replies per axis.
"""
import sys, json
import numpy as np
sys.path.insert(0, "/private/tmp/claude-501/-Users-unrulyabstractions-work-papers-idt/32b842b8-ab16-41a9-8f2f-692b2558b7d6/scratchpad/nullinv/stats_r1")
import common as C
D = C.load_all(); cands = D["_cands"]
NA, c2, i2 = C.load_replies(C.AB / "contextual_optimism/responses/verdicts_base.jsonl")
NCO, c3, i3 = C.load_replies(C.AB / "contextual_optimism/responses/verdicts_target.jsonl")
assert c2 == cands and c3 == cands and i2 == D["_instr"] and i3 == D["_instr"]
keep = [i for i, c in enumerate(cands) if c != "anthropic"]; c5 = [cands[i] for i in keep]
def O5(R): return C.ovr(C.rates(R)[keep])
o = {k: O5(D[k]) for k in ["A", "B", "CO"] + list(C.CONTROLS)}
o["A_nano"], o["CO_nano"] = O5(NA), O5(NCO)
cons = np.mean([o[c] for c in C.CONTROLS], axis=0)
# agreement nano vs mini on base A replies
A_m, A_n = D["A"], NA
both = ~np.isnan(A_m) & ~np.isnan(A_n)
agree = np.array([(A_m[..., j][both[..., j]] == A_n[..., j][both[..., j]]).mean() for j in range(len(C.AXES))])
def kappa(j):
    x, y = A_m[..., j][both[..., j]], A_n[..., j][both[..., j]]
    po = (x == y).mean(); pe = x.mean() * y.mean() + (1 - x.mean()) * (1 - y.mean())
    return (po - pe) / (1 - pe) if pe < 1 else np.nan
kap = np.array([kappa(j) for j in range(len(C.AXES))])
print(f"nano vs mini on base A replies: mean agreement {agree.mean():.3f}, median kappa {np.nanmedian(kap):.3f} (IQR {np.nanpercentile(kap,25):.3f}-{np.nanpercentile(kap,75):.3f}); "
      f"mean yes-rate mini {np.nanmean(A_m):.4f} nano {np.nanmean(A_n):.4f}")
# cell-rate correlation of OvR grids (same texts)
tm, tn = C.tgrid(o["A"])[0], C.tgrid(o["A_nano"])[0]
print(f"corr of base A's own one-vs-rest t-grid, mini vs nano (505 cells): {np.corrcoef(np.nan_to_num(tm).ravel(), np.nan_to_num(tn).ravel())[0,1]:.3f}")
tcm, tcn = C.tgrid(o["CO"] - o["A"])[0], C.tgrid(o["CO_nano"] - o["A_nano"])[0]
print(f"corr of t(CO - A) grid, mini vs nano: {np.corrcoef(np.nan_to_num(tcm).ravel(), np.nan_to_num(tcn).ravel())[0,1]:.3f}")
res = {}
for dev in ("A", "B"):
    g = C.tgrid(cons - o[dev])[0]
    for K in (6, 12, 20, 40):
        top = np.argsort(-np.abs(np.nan_to_num(g)), axis=None)[:K]; sg = np.sign(g.ravel()[top])
        m = float(np.mean(sg * tcm.ravel()[top])); n = float(np.mean(sg * np.nan_to_num(tcn).ravel()[top]))
        jj = np.unravel_index(top, g.shape)[1]
        res[f"{dev}_K{K}"] = {"mini": m, "nano": n, "median_kappa_on_these_axes": float(np.nanmedian(kap[jj]))}
        print(f"top-{K:2d} cells of cons8-{dev}: signed t(CO-A) mini {m:+.2f}  nano {n:+.2f}   (median kappa on these axes {np.nanmedian(kap[jj]):.2f})")
# random-cell null for the nano statistic at A's top-12: random sets of 12 cells with random signs
rng = np.random.default_rng(5)
g = C.tgrid(cons - o["A"])[0]; flat = np.nan_to_num(tcn).ravel()
for K in (12, 20, 40):
    draws = np.array([np.mean(rng.choice([-1, 1], K) * flat[rng.choice(flat.size, K, replace=False)]) for _ in range(20000)])
    top = np.argsort(-np.abs(np.nan_to_num(g)), axis=None)[:K]; obs = np.mean(np.sign(g.ravel()[top]) * flat[top])
    print(f"K={K}: nano statistic {obs:+.2f}; random-cell random-sign null sd {draws.std():.3f}, z = {obs/draws.std():.2f}, p_upper = {(1+np.sum(draws>=obs))/(1+len(draws)):.5f}")
    res[f"nano_null_K{K}"] = {"obs": float(obs), "null_sd": float(draws.std())}
# per-cell table at A's top-12
top = np.argsort(-np.abs(np.nan_to_num(g)), axis=None)[:12]
print("\ncell | t(cons8-A) mini | t(CO-A) mini | t(CO-A) nano | mean OvR A mini, A nano | kappa axis")
for f in top:
    i, j = np.unravel_index(f, g.shape)
    print(f"{c5[i]:18s} {C.AXES[j][:42]:42s} {g[i,j]:+5.2f} | {tcm[i,j]:+5.2f} | {tcn[i,j]:+5.2f} | {np.nanmean(o['A'][i,:,j]):+.3f} {np.nanmean(o['A_nano'][i,:,j]):+.3f} | {kap[j]:.2f}")
json.dump(res, open("/private/tmp/claude-501/-Users-unrulyabstractions-work-papers-idt/32b842b8-ab16-41a9-8f2f-692b2558b7d6/scratchpad/nullinv/critic_r1/c03_nano_rejudge.json", "w"), indent=1)
