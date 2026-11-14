"""Critic check: the single base-A prompts with the largest influence on the eight S (from c06).
For stanford x user_assess_bold_methodology, and the user_assess_theoretical_result prompts:
 - which of the eight tests move when that one prompt (16 replies) is swapped for base B's
 - how base A's 16 replies there differ from base B's and the nulls' (rates summed over axes, number of axes fired per reply, lengths)
 - verdict-row anomalies (missing rows, replies with very many/few axes fired)
"""
import sys, json
import numpy as np
sys.path.insert(0, "/private/tmp/claude-501/-Users-unrulyabstractions-work-papers-idt/32b842b8-ab16-41a9-8f2f-692b2558b7d6/scratchpad/nullinv/stats_r1")
import common as C
D = C.load_all(); cands, instr = D["_cands"], D["_instr"]
P = {k: C.rates(v) for k, v in D.items() if not k.startswith("_")}
OT = [C.ovr(P[c]) for c in C.CONTROLS]
def eightS(pb):
    ob = C.ovr(pb); return np.array([float(C.smax(C.tgrid(o - ob)[0])) for o in OT])
SA = eightS(P["A"]); SB = eightS(P["B"])
def peak(pb, k):
    t = C.tgrid(OT[k] - C.ovr(pb))[0]; f = np.nanargmax(np.abs(t)); i, j = np.unravel_index(f, t.shape); return cands[i], C.AXES[j], float(t[i, j])
targets = [("stanford", "prism4::user_assess_bold_methodology"), ("google_deepmind", "prism4::user_assess_theoretical_result"),
           ("openai", "prism4::user_assess_theoretical_result"), ("stanford", "prism4::user_assess_continuation_decision")]
for cn, inn in targets:
    c, i = cands.index(cn), instr.index(inn)
    pb = P["A"].copy(); pb[c, i] = P["B"][c, i]; S2 = eightS(pb)
    print(f"\n=== swap base A's prompt {cn} x {inn} for base B's ===")
    for k, name in enumerate(C.CONTROLS):
        if abs(S2[k] - SA[k]) > 0.02:
            print(f"  {name:24s} S {SA[k]:.2f} -> {S2[k]:.2f}   peak before {peak(P['A'], k)}  after {peak(pb, k)}")
    RA, RB = D["A"][c, i], D["B"][c, i]   # (16, 101)
    nA, nB = np.nansum(RA, 1), np.nansum(RB, 1)
    print(f"  replies present A {int((~np.isnan(RA[:,0])).sum())} B {int((~np.isnan(RB[:,0])).sum())}; axes fired per reply: A mean {np.nanmean(nA[~np.isnan(RA[:,0])]):.1f} (min {nA[~np.isnan(RA[:,0])].min():.0f}, max {nA.max():.0f}); "
          f"B mean {nB.mean():.1f} (min {nB.min():.0f}, max {nB.max():.0f}); all-cells mean A {np.nanmean(np.nansum(D['A'],3)[~np.isnan(D['A'][...,0])]):.1f}")
    nul = np.mean([P[x][c, i] for x in C.CONTROLS], axis=0)
    dA, dB = P["A"][c, i] - nul, P["B"][c, i] - nul
    # how unusual is this cell's A-B distance among all 216 prompts?
    dist = np.nansum((P["A"] - P["B"]) ** 2, axis=2)
    print(f"  squared A-B rate distance over axes: {dist[c, i]:.3f}; rank {int((dist > dist[c, i]).sum()) + 1} of 216 (median {np.median(dist):.3f}, max {dist.max():.3f})")
    top = np.argsort(-np.abs(P["A"][c, i] - P["B"][c, i]))[:6]
    for j in top: print(f"     {C.AXES[j][:50]:50s} A {P['A'][c,i,j]:.3f}  B {P['B'][c,i,j]:.3f}  nulls {nul[j]:.3f}")
