"""F4 (i) and F1 (k22). Is the pseudo-controls' A-versus-B gap itself beyond chance? And the consensus gap.

Pseudo-controls: K fixed per-slot shuffles of the eight controls' replies among the eight labels (they keep the
pattern all controls share and lose each control's own structure). Statistic, S scale (no permutation p):
   g_pseudo(A, B) = mean over the K x 8 pseudo-controls of S(pc | A) - S(pc | B).
The same K shuffles are used for the observed bases and for every null draw (common random numbers), so
g_pseudo is one fixed function of the base pair and its null is exact for that function.
Null: A and B trade replies per slot (reply grain) or whole prompts (prompt grain), targets fixed.
Same draws give the real controls' mean gap (0.597 six) and the consensus-of-eight gap (critic k22: 1.27 six).
Usage: f4_pseudo_gap.py <K> <n_reply> <n_prompt>
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r4c as Q  # noqa: E402

K = int(sys.argv[1]) if len(sys.argv) > 1 else 40
NR = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
NP = int(sys.argv[3]) if len(sys.argv) > 3 else 600
d = Q.data()
R = d["R"]
Rc = np.stack([R[k] for k in Q.CONTROLS])
RA, RB = R["A"], R["B"]
rng = np.random.default_rng([20261113, 44])
shuf_rates = np.stack([Q.rates(Q.shuffle_controls(rng, Rc)) for _ in range(K)])     # (K, 8, 6, 36, 101)
real_rates = Q.rates(Rc)
cons_rates = real_rates.mean(0)
out = {"K": K}
t0 = time.time()
for tag in ("six", "five"):
    kp, nc = Q.world(tag)
    PC = Q.ovr(shuf_rates[:, :, kp]).reshape(K * 8, nc, 36, 101)
    RT = np.concatenate([Q.ovr(real_rates[:, kp]), Q.ovr(cons_rates[kp])[None]])          # 8 real + consensus

    def gaps(PA, PB):
        oa, ob = Q.ovr(PA[kp]), Q.ovr(PB[kp])
        sp = Q.S_only(PC - oa) - Q.S_only(PC - ob)
        sr = Q.S_only(RT - oa) - Q.S_only(RT - ob)
        la = Q.S_only(PC - oa)
        return sp.mean(), sr[:8].mean(), sr[8], sp, la.mean()

    g0 = gaps(Q.rates(RA), Q.rates(RB))
    r = {"observed": {"pseudo_mean_gap": round(float(g0[0]), 4), "pseudo_single_gap_sd_over_shuffles": round(float(g0[3].reshape(K, 8).mean(1).std()), 4),
                      "pseudo_mean_S_vs_A": round(float(g0[4]), 4),
                      "real_controls_mean_gap": round(float(g0[1]), 4), "consensus_gap": round(float(g0[2]), 4)}}
    for grain, n in (("reply", NR), ("prompt", NP)):
        G = np.empty((n, 3))
        for q in range(n):
            m = Q.swap_mask(rng, grain, RA, RB)
            XA, XB = Q.swapped(RA, RB, m)
            g = gaps(Q.rates(XA), Q.rates(XB))
            G[q] = g[:3]
        e = {}
        for j, nm in enumerate(("pseudo_mean_gap", "real_controls_mean_gap", "consensus_gap")):
            o = g0[j]
            e[nm] = {"obs": round(float(o), 4), "null_mean": round(float(G[:, j].mean()), 4), "null_sd": round(float(G[:, j].std()), 4),
                     "z": round(float((o - G[:, j].mean()) / G[:, j].std()), 2), "p_upper": Q.tail_ge(G[:, j], o),
                     "p_two": float((1 + np.sum(np.abs(G[:, j]) >= abs(o) - 1e-12)) / (1 + n))}
        e["corr_pseudo_real_gap_over_draws"] = round(float(np.corrcoef(G[:, 0], G[:, 1])[0, 1]), 3)
        e["corr_pseudo_consensus_gap_over_draws"] = round(float(np.corrcoef(G[:, 0], G[:, 2])[0, 1]), 3)
        b = np.polyfit(G[:, 0], G[:, 1], 1)
        e["real_gap_regressed_on_pseudo_gap"] = {"slope": round(float(b[0]), 3), "intercept": round(float(b[1]), 3),
                                                 "real_gap_predicted_at_obs_pseudo": round(float(np.polyval(b, g0[0])), 3),
                                                 "residual_sd": round(float(np.std(G[:, 1] - np.polyval(b, G[:, 0]))), 3)}
        r[grain] = e
        print(tag, grain, f"{time.time()-t0:.0f}s", json.dumps(e), flush=True)
    out[tag] = r
(Q.OUT / "f4_pseudo_gap.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
