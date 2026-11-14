"""Critic check: is the eight-test gap between base A and base B carried by a few of base A's prompts, or spread out?

(1) Swap ONE instruction of base A (all 6 candidates, all axes) for base B's and recompute the eight S; report the change in mean S.
    36 single-instruction swaps. If a few instructions close most of the gap (mean S 3.91 -> 3.31), A has a few odd prompt batches.
(2) Same for single (candidate, instruction) prompts: 216 swaps.
(3) Cumulative: swap instructions in order of their single-swap effect; how many are needed to halve the gap?
S only (no permutations): the per-pairing permutation nulls are nearly identical (median 3.21-3.26), so S is the right scale.
"""
import sys, json
import numpy as np
sys.path.insert(0, "/private/tmp/claude-501/-Users-unrulyabstractions-work-papers-idt/32b842b8-ab16-41a9-8f2f-692b2558b7d6/scratchpad/nullinv/stats_r1")
import common as C
D = C.load_all(); cands, instr = D["_cands"], D["_instr"]
P = {k: C.rates(v) for k, v in D.items() if not k.startswith("_")}
OT = [C.ovr(P[c]) for c in C.CONTROLS]
def eightS(pb):
    ob = C.ovr(pb)
    return np.array([float(C.smax(C.tgrid(o - ob)[0])) for o in OT])
SA, SB = eightS(P["A"]), eightS(P["B"])
print("S vs A:", SA.round(3), "mean", SA.mean().round(3)); print("S vs B:", SB.round(3), "mean", SB.mean().round(3))
gap = SA.mean() - SB.mean()
eff = []
for i in range(36):
    pb = P["A"].copy(); pb[:, i] = P["B"][:, i]
    eff.append(SA.mean() - eightS(pb).mean())
eff = np.array(eff)
order = np.argsort(-eff)
print(f"\ngap in mean S = {gap:.3f}. Single-instruction swap effects (drop in mean S): sum of all 36 = {eff.sum():.3f}; "
      f"max {eff.max():.3f}, top5 {eff[order[:5]].round(3)}, n positive {int((eff>0).sum())}/36, sd {eff.std():.3f}")
for i in order[:6]: print(f"   {instr[i]:60s} {eff[i]:+.3f}")
# reverse control: start from B, swap in one A instruction: rise in mean S
effB = []
for i in range(36):
    pb = P["B"].copy(); pb[:, i] = P["A"][:, i]
    effB.append(eightS(pb).mean() - SB.mean())
effB = np.array(effB)
print(f"reverse (B with one A instruction): sum {effB.sum():.3f}, max {effB.max():.3f}, n positive {int((effB>0).sum())}/36; corr with forward effects {np.corrcoef(eff, effB)[0,1]:.2f}")
# cumulative
pb = P["A"].copy(); cum = []
for n, i in enumerate(order, 1):
    pb[:, i] = P["B"][:, i]; cum.append(float(eightS(pb).mean()))
half = next(n for n, v in enumerate(cum, 1) if v <= SA.mean() - gap / 2)
print("cumulative mean S after swapping the top-n instructions:", [round(v, 2) for v in cum[:12]], f"... gap halved after {half} instructions")
# random-order cumulative for comparison
rng = np.random.default_rng(3); halves = []
for r in range(40):
    pb = P["A"].copy()
    for n, i in enumerate(rng.permutation(36), 1):
        pb[:, i] = P["B"][:, i]
        if eightS(pb).mean() <= SA.mean() - gap / 2: halves.append(n); break
print(f"random order: gap halved after median {np.median(halves):.0f} instructions (IQR {np.percentile(halves,25):.0f}-{np.percentile(halves,75):.0f})")
# single prompt (candidate, instruction) swaps
effc = np.zeros((6, 36))
for c in range(6):
    for i in range(36):
        pb = P["A"].copy(); pb[c, i] = P["B"][c, i]
        effc[c, i] = SA.mean() - eightS(pb).mean()
flat = np.argsort(-effc, axis=None)[:8]
print(f"\nsingle-prompt swaps (216): sum {effc.sum():.3f}, max {effc.max():.3f}, sd {effc.std():.3f}; per-candidate sums {dict(zip(cands, effc.sum(1).round(3)))}")
for f in flat:
    c, i = np.unravel_index(f, effc.shape); print(f"   {cands[c]:18s} {instr[i]:55s} {effc[c,i]:+.3f}")
json.dump({"S_A": SA.tolist(), "S_B": SB.tolist(), "instr": instr, "single_instruction_effect": eff.tolist(), "reverse_effect": effB.tolist(),
           "cumulative_mean_S": cum, "n_to_halve_gap": half, "random_n_to_halve": halves, "single_prompt_effect": effc.tolist()},
          open("/private/tmp/claude-501/-Users-unrulyabstractions-work-papers-idt/32b842b8-ab16-41a9-8f2f-692b2558b7d6/scratchpad/nullinv/critic_r1/c06_instruction_influence.json", "w"), indent=1)
