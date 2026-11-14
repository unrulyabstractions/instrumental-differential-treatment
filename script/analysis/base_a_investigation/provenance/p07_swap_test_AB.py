"""Is base A's effect on the eight nulls beyond what a second draw of the same process gives?

Null hypothesis: base A and base B are exchangeable draws (same model, engine, judge
behaviour), so the A row and the B row at the same (prompt_id, s), which the judge asked
with the same axis order, can swap labels. For each of NP random swap patterns we form
pseudo-A and pseudo-B and recompute, for the eight nulls, the registered statistic S
(max |t| of the one-vs-rest excess) against each, plus each base's distance to the
eight-null consensus (sum of t^2 and max |t|).

Observed statistics:
  dS     = mean_k S(T_k, A) - mean_k S(T_k, B)
  dcount = #k with S(T_k, A) >= 3.9  -  #k with S(T_k, B) >= 3.9
  dcons  = sum t^2(A - consensus) - sum t^2(B - consensus)
Two-sided p from the swap distribution (symmetric under H0).
Optional argv[1] = 'drop_anthropic_session': swaps nothing different, but recomputes the
statistics after removing the anthropic candidate (a five-candidate version), to see
whether the gap lives in the candidate judged in the other session.
"""
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_verdicts, cell_rates, one_vs_rest, tgrid, CTRL, AXES

HERE = Path(__file__).resolve().parent
mode = sys.argv[1] if len(sys.argv) > 1 else "all"
NP = int(sys.argv[2]) if len(sys.argv) > 2 else 2000
A = load_verdicts("base_A"); B = load_verdicts("base_B")
cands = sorted({v[0] for v in A.values()}); insts = sorted({v[1] for v in A.values()})
keep = [k for k, c in enumerate(cands) if not (mode == "drop_anthropic" and c == "anthropic")]
ci = {c: k for k, c in enumerate(cands)}; ii = {x: k for k, x in enumerate(insts)}
K = len(AXES)
Gt = [one_vs_rest(cell_rates(load_verdicts(n), cands, insts)[0][keep]) for n in CTRL]
cons = np.mean(Gt, axis=0)
keys = sorted(set(A) | set(B))
XA = np.zeros((len(keys), K)); XB = np.zeros((len(keys), K)); hA = np.zeros(len(keys), bool); hB = np.zeros(len(keys), bool)
cand = np.zeros(len(keys), int); inst = np.zeros(len(keys), int)
for n, k in enumerate(keys):
    src = A.get(k) or B.get(k); cand[n], inst[n] = ci[src[0]], ii[src[1]]
    if k in A: XA[n] = A[k][2]; hA[n] = True
    if k in B: XB[n] = B[k][2]; hB[n] = True
both = hA & hB

def rate(X, h):
    f = np.zeros((6, 36, K)); n = np.zeros((6, 36, 1))
    np.add.at(f, (cand[h], inst[h]), X[h]); np.add.at(n, (cand[h], inst[h]), 1)
    return (f / n)[keep]

def maxabs(t):
    a = np.abs(t); return float(np.nanmax(a))

def stats(YA, YB):
    gA, gB = one_vs_rest(rate(YA, hA)), one_vs_rest(rate(YB, hB))
    SA = np.array([maxabs(tgrid(g - gA)[0]) for g in Gt])
    SB = np.array([maxabs(tgrid(g - gB)[0]) for g in Gt])
    tA = np.nan_to_num(tgrid(gA - cons)[0], nan=0.0, posinf=0.0, neginf=0.0)
    tB = np.nan_to_num(tgrid(gB - cons)[0], nan=0.0, posinf=0.0, neginf=0.0)
    return SA, SB, float((tA ** 2).sum() - (tB ** 2).sum()), float(np.abs(tA).max() - np.abs(tB).max())

SA, SB, dcons, dconsmax = stats(XA, XB)
obs = {"S_vs_A": SA.round(3).tolist(), "S_vs_B": SB.round(3).tolist(),
       "dS": float(SA.mean() - SB.mean()), "dcount39": int((SA >= 3.9).sum() - (SB >= 3.9).sum()),
       "dcons_sum_t2": dcons, "dcons_max_t": dconsmax}
print("mode", mode, "observed", obs, flush=True)
rng = np.random.default_rng(2026)
null = {"dS": [], "dcount39": [], "dcons_sum_t2": [], "dcons_max_t": [], "SA_mean": []}
for k in range(NP):
    sw = both & (rng.random(len(keys)) < 0.5)
    YA, YB = XA.copy(), XB.copy(); YA[sw], YB[sw] = XB[sw], XA[sw]
    a, b, dc, dm = stats(YA, YB)
    null["dS"].append(a.mean() - b.mean()); null["dcount39"].append(int((a >= 3.9).sum() - (b >= 3.9).sum()))
    null["dcons_sum_t2"].append(dc); null["dcons_max_t"].append(dm); null["SA_mean"].append(a.mean())
    if (k + 1) % 500 == 0:
        print(" ..", k + 1, flush=True)
res = {"mode": mode, "n_swaps": NP, "observed": obs, "null": {}}
for s in ["dS", "dcount39", "dcons_sum_t2", "dcons_max_t"]:
    x = np.array(null[s]); o = obs[s]
    res["null"][s] = {"mean": float(x.mean()), "sd": float(x.std()),
                      "p_two_sided": float((1 + np.sum(np.abs(x) >= abs(o) - 1e-12)) / (1 + NP)),
                      "p_upper": float((1 + np.sum(x >= o - 1e-12)) / (1 + NP))}
    print(s, res["null"][s])
res["null"]["pseudoA_mean_S_quantiles"] = np.quantile(null["SA_mean"], [0.05, 0.5, 0.95]).round(3).tolist()
xs = np.array(null["SA_mean"])
res["null"]["percentile_of_obs_mean_S_vs_A"] = float(np.mean(xs < SA.mean()))
res["null"]["percentile_of_obs_mean_S_vs_B"] = float(np.mean(xs < SB.mean()))
print("percentiles of observed mean S (A, B) in pseudo-base distribution:", res["null"]["percentile_of_obs_mean_S_vs_A"], res["null"]["percentile_of_obs_mean_S_vs_B"])
print("pseudo-A mean S quantiles", res["null"]["pseudoA_mean_S_quantiles"])
json.dump(res, open(HERE / f"p07_swap_test_AB_{mode}.json", "w"), indent=1)
