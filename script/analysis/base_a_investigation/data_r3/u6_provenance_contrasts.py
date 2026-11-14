"""U6 support: provenance-factor sign contrasts and the direction-free omnibus, recomputed with my own code from
the stats investigator's stored swap draws (stats_r2/out/draws_swap_4000.npz: draw 0 is the identity, 3,999
swap draws; exact registered S per target against pseudo-A and pseudo-B).

gap_k = S(T_k | A') - S(T_k | B'); z_k = gap_k / sd over the swap draws.
"Shared provenance cancels" predicts LOWER S against the base sharing the factor: code_k = -1 if T_k shares the
factor with A, +1 if with B, 0 otherwise; contrast = mean(code_k * z_k); positive = prediction holds.
Factors:
  engine version          A, CO: vLLM 0.26.0 | nulls, B, synthetic arms: 0.11.0
  August/October grouping A, CO, nulls: FlashInfer sampler, ~140 GiB cards, live judge, August, doubled BOS
                          (text prompts, pre-Aug-6 code) | B, synthetic arms: PyTorch-native sampler, H100,
                          batch judge, October, single BOS (token-id prompts)
  engine process          CO with A | synthetic arms with B | nulls with neither base
Also: sum z^2 (direction-free) with leave-one-target-out, eight-minus-synthetic contrast; six and five candidates.
"""
from __future__ import annotations

import numpy as np
from r3common import NULLINV, dump

z = np.load(NULLINV / "stats_r2/out/draws_swap_4000.npz")
res = {}
for lab, Skey, tkey in (("six", "S6", "targets6"), ("five", "S5", "targets5")):
    S = z[Skey]; names = [str(x) for x in z[tkey]]
    G = S[:, 0, :] - S[:, 1, :]
    sd = G[1:].std(0); Z = G / sd
    n = len(Z) - 1
    def pv(v):
        return float((1 + (np.abs(v[1:]) >= abs(v[0])).sum()) / (n + 1))
    nulls = [i for i, k in enumerate(names) if not k.startswith("sd_") and k != "CO"]
    synth = [i for i, k in enumerate(names) if k.startswith("sd_")]
    co = [i for i, k in enumerate(names) if k == "CO"]
    code = {}
    c = np.zeros(len(names)); c[nulls] = +1; c[synth] = +1; c[co] = -1; code["engine version"] = c
    c = np.zeros(len(names)); c[nulls] = -1; c[synth] = +1; c[co] = -1; code["August/October grouping"] = c
    c = np.zeros(len(names)); c[synth] = +1; c[co] = -1; code["engine process"] = c
    out = {"targets": names, "gap_obs": dict(zip(names, G[0].round(4).tolist())), "z_obs": dict(zip(names, Z[0].round(3).tolist()))}
    for nm, c in code.items():
        for sub, mask in (("all coded", c != 0), ("outside original eight", (c != 0) & ~np.isin(np.arange(len(names)), nulls))):
            if mask.sum() == 0:
                continue
            v = (Z[:, mask] * c[mask]).mean(1)
            out[f"{nm} | {sub}"] = {"contrast": float(v[0]), "null_sd": float(v[1:].std()), "z": float(v[0] / v[1:].std()),
                                    "p_two": pv(v), "n_targets": int(mask.sum())}
    s2 = (Z ** 2).sum(1)
    out["sum_z2_all"] = {"value": float(s2[0]), "null_mean": float(s2[1:].mean()), "p_upper": float((1 + (s2[1:] >= s2[0]).sum()) / (n + 1))}
    s8 = (Z[:, nulls] ** 2).sum(1)
    out["sum_z2_eight"] = {"value": float(s8[0]), "p_upper": float((1 + (s8[1:] >= s8[0]).sum()) / (n + 1))}
    loo = {}
    for i, k in enumerate(names):
        m = np.ones(len(names), bool); m[i] = False
        s = (Z[:, m] ** 2).sum(1)
        loo[k] = {"value": float(s[0]), "p_upper": float((1 + (s[1:] >= s[0]).sum()) / (n + 1))}
    out["sum_z2_leave_one_out"] = loo
    v = Z[:, nulls].mean(1) - Z[:, synth].mean(1)
    out["eight_minus_synth"] = {"contrast": float(v[0]), "null_sd": float(v[1:].std()), "z": float(v[0] / v[1:].std()), "p_two": pv(v)}
    mz = np.abs(Z).max(1)
    out["max_abs_z"] = {"value": float(mz[0]), "p_upper": float((1 + (mz[1:] >= mz[0]).sum()) / (n + 1))}
    res[lab] = out
    print(f"== {lab} candidates ({n} swap draws)")
    print("   z:", out["z_obs"])
    for k, v in out.items():
        if " | " in k:
            print(f"   {k:48s} contrast {v['contrast']:+.3f} z {v['z']:+.2f} p {v['p_two']:.4f} (n={v['n_targets']})")
    print(f"   sum z^2 all {out['sum_z2_all']['value']:.2f} (null mean {out['sum_z2_all']['null_mean']:.2f}) p {out['sum_z2_all']['p_upper']:.4f}; eight {out['sum_z2_eight']['value']:.2f} p {out['sum_z2_eight']['p_upper']:.4f}; max|z| p {out['max_abs_z']['p_upper']:.4f}")
    print(f"   eight minus synthetic: {out['eight_minus_synth']['contrast']:+.3f} sd {out['eight_minus_synth']['null_sd']:.3f} p {out['eight_minus_synth']['p_two']:.4f}")
    print("   leave-one-out sum z^2 p:", {k[:14]: round(v["p_upper"], 4) for k, v in loo.items()})
dump(res, "u6_provenance_contrasts.json")
