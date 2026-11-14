"""Critic check: benchmark for the cross-judge replication in c03. How much of a gpt-5-mini top-K cell deviation does
gpt-4.1-nano reproduce in GENERAL (same texts), so that 1.00/1.37 at base A's deviant cells can be read?
 (1) top-K cells of mini's |t(CO - A)| (five candidates): mini value vs nano value of the same signed statistic.
 (2) top-K cells of mini's own |t(OvR(A))| and |t(OvR(CO))| (reference-free): mini vs nano.
 (3) grid-wide linear slope of nano t(CO - A) on mini t(cons8 - A), and the value it predicts at A's top-K deviant cells.
 (4) six-candidate anthropic row of CO - A (CO's real effect): mini vs nano at mini's top-K cells (a known textual effect).
"""
import sys, json
import numpy as np
sys.path.insert(0, "/private/tmp/claude-501/-Users-unrulyabstractions-work-papers-idt/32b842b8-ab16-41a9-8f2f-692b2558b7d6/scratchpad/nullinv/stats_r1")
import common as C
D = C.load_all(); cands = D["_cands"]
NA, _, _ = C.load_replies(C.AB / "contextual_optimism/responses/verdicts_base.jsonl")
NCO, _, _ = C.load_replies(C.AB / "contextual_optimism/responses/verdicts_target.jsonl")
keep = [i for i, c in enumerate(cands) if c != "anthropic"]
def O5(R): return C.ovr(C.rates(R)[keep])
A, CO, An, COn = O5(D["A"]), O5(D["CO"]), O5(NA), O5(NCO)
cons = np.mean([O5(D[c]) for c in C.CONTROLS], axis=0)
f = lambda x: np.nan_to_num(C.tgrid(x)[0]).ravel()
tm, tn = f(CO - A), f(COn - An)
res = {}
print("(1) top-K of mini |t(CO-A)|: mini mean|t| -> nano signed mean; ratio")
for K in (6, 12, 20, 40):
    top = np.argsort(-np.abs(tm))[:K]; m = np.mean(np.abs(tm[top])); n = np.mean(np.sign(tm[top]) * tn[top])
    res[f"CO-A_K{K}"] = [float(m), float(n)]; print(f"   K={K:2d}: mini {m:.2f} -> nano {n:+.2f}  ratio {n/m:.2f}")
print("(2) reference-free top-K of mini |t|: A, then CO")
for name, xm, xn in (("A", f(A), f(An)), ("CO", f(CO), f(COn))):
    for K in (6, 12, 20, 40):
        top = np.argsort(-np.abs(xm))[:K]; m = np.mean(np.abs(xm[top])); n = np.mean(np.sign(xm[top]) * xn[top])
        res[f"{name}_ownK{K}"] = [float(m), float(n)]; print(f"   {name:2s} K={K:2d}: mini {m:.2f} -> nano {n:+.2f}  ratio {n/m:.2f}")
g = f(cons - A)
b = float(np.dot(g, tn) / np.dot(g, g)); r = float(np.corrcoef(g, tn)[0, 1])
print(f"(3) grid-wide: corr(nano t(CO-A), mini t(cons8-A)) = {r:.3f}, slope {b:.3f}")
for K in (6, 12, 20, 40):
    top = np.argsort(-np.abs(g))[:K]; pred = b * np.mean(np.abs(g[top])); obs = np.mean(np.sign(g[top]) * tn[top])
    # slope excluding the top-K cells themselves
    mask = np.ones(g.size, bool); mask[top] = False; b2 = float(np.dot(g[mask], tn[mask]) / np.dot(g[mask], g[mask]))
    res[f"pred_K{K}"] = {"obs": float(obs), "linear_pred": float(pred), "slope_excl_top": b2, "pred_excl": float(b2 * np.mean(np.abs(g[top])))}
    print(f"   K={K:2d}: observed nano {obs:+.2f}; linear prediction {pred:+.2f}; prediction with slope fitted on the other cells ({b2:.3f}) {b2*np.mean(np.abs(g[top])):+.2f}")
# also mini-vs-mini benchmark: how much does an INDEPENDENT sample reproduce? (B's t(B - A) at A's top cells was +1.72 of 2.83)
# (4) CO's real anthropic effect, six candidates
O6 = lambda R: C.ovr(C.rates(R))
t6m, t6n = np.nan_to_num(C.tgrid(O6(D["CO"]) - O6(D["A"]))[0]), np.nan_to_num(C.tgrid(O6(NCO) - O6(NA))[0])
ia = cands.index("anthropic")
for K in (6, 12, 20):
    top = np.argsort(-np.abs(t6m[ia]))[:K]; m = np.mean(np.abs(t6m[ia][top])); n = np.mean(np.sign(t6m[ia][top]) * t6n[ia][top])
    res[f"CO_anthropic_K{K}"] = [float(m), float(n)]; print(f"(4) CO's anthropic row top-{K}: mini {m:.2f} -> nano {n:+.2f}  ratio {n/m:.2f}")
print(f"    corr over the anthropic row (101 axes), mini vs nano: {np.corrcoef(t6m[ia], t6n[ia])[0,1]:.3f}; over the other five rows: {np.corrcoef(np.delete(t6m, ia, 0).ravel(), np.delete(t6n, ia, 0).ravel())[0,1]:.3f}")
json.dump(res, open("/private/tmp/claude-501/-Users-unrulyabstractions-work-papers-idt/32b842b8-ab16-41a9-8f2f-692b2558b7d6/scratchpad/nullinv/critic_r1/c03b_nano_benchmark.json", "w"), indent=1)
