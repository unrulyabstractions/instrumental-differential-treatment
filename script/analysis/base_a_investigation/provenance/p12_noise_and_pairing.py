"""Does a target share more judge/sampling structure with one base than the other?

For every target T (eight nulls, two synthetic nulls) and base X in {A, B}:
  sd_ratio  : mean over (candidate, axis) of the instruction spread of d = g(T) - g(X),
              against A divided by against B (the t denominator).
  mean_abs  : mean over (candidate, axis) of |mean over instructions of d| (the t numerator).
  pairing   : within (candidate, instruction) cells, mean over axes of the covariance of the
              target row and the base row at the SAME s minus at DIFFERENT s
              (the judge's axis-order effect shared by the two arms; the judge orders axes by
              (prompt_id, s)).
Provenance groups: A and the eight nulls were judged live in August with the FlashInfer
top-p/top-k sampler; B and the two synthetic nulls by batch in October with vLLM's
PyTorch-native sampler.
"""
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_verdicts, cell_rates, one_vs_rest, tgrid, CTRL, AXES

HERE = Path(__file__).resolve().parent
TG = CTRL + ["sd_ai_welfare_poisoning", "sd_emotional_bond"]
V = {n: load_verdicts(n) for n in ["base_A", "base_B"] + TG}
cands = sorted({v[0] for v in V["base_A"].values()}); insts = sorted({v[1] for v in V["base_A"].values()})
G = {n: one_vs_rest(cell_rates(V[n], cands, insts)[0]) for n in V}
K = len(AXES)

def by_cell(ver):
    d = {}
    for (pid, s), (c, ins, v) in ver.items():
        d.setdefault(pid, {})[s] = np.nan_to_num(v, nan=0.0)
    return d
C = {n: by_cell(V[n]) for n in V}

def pairing(t, x):
    """mean over cells and axes of cov(T_s, X_s) - cov(T_s, X_s') (s != s')."""
    m, u = [], []
    for pid, rows_t in C[t].items():
        rows_x = C[x].get(pid, {})
        ss = sorted(set(rows_t) & set(rows_x))
        if len(ss) < 4:
            continue
        T = np.array([rows_t[s] for s in ss]); X = np.array([rows_x[s] for s in ss])
        Tc, Xc = T - T.mean(0), X - X.mean(0)
        P = Tc @ Xc.T / K   # (s, s') mean over axes of product of centered verdicts
        m.append(np.mean(np.diag(P))); u.append((P.sum() - np.trace(P)) / (len(ss) * (len(ss) - 1)))
    return float(np.mean(m) - np.mean(u))

res = {}
for t in TG:
    row = {}
    for x in ["base_A", "base_B"]:
        d = G[t] - G[x]
        sd = np.nanstd(d, axis=1, ddof=1); mn = np.nanmean(d, axis=1)
        ok = sd > 0
        row[x] = {"mean_sd": float(np.mean(sd[ok])), "mean_abs_mean": float(np.mean(np.abs(mn[ok]))),
                  "pairing_cov": pairing(t, x)}
    row["sd_ratio_A_over_B"] = row["base_A"]["mean_sd"] / row["base_B"]["mean_sd"]
    row["absmean_ratio_A_over_B"] = row["base_A"]["mean_abs_mean"] / row["base_B"]["mean_abs_mean"]
    res[t] = row
    print(f"{t:26s} sd A/B={row['sd_ratio_A_over_B']:.4f} |mean| A/B={row['absmean_ratio_A_over_B']:.4f} "
          f"pairing A={row['base_A']['pairing_cov']:.5f} B={row['base_B']['pairing_cov']:.5f}")
pab = pairing("base_A", "base_B")
print("pairing base_A with base_B:", round(pab, 5))
res["pairing_A_B"] = pab
json.dump(res, open(HERE / "p12_noise_and_pairing.json", "w"), indent=1)
