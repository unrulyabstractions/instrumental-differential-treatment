"""Critic r2, check 8: does any provenance factor predict which base a target sits closer to?

"Shared provenance cancels" predicts a target has LOWER S against the base it shares the factor with.
gap_k = S(T_k | A) - S(T_k | B), standardized by its swap SD (five candidates, so CO is included;
stats_r2/out/draws_swap_4000.npz, draw 0 = identity). For each factor, code_k = -1 if T_k shares the
factor with A, +1 if with B, 0 if with neither; contrast = mean of code_k * z_k over coded targets.
Positive = the factor's prediction holds. P from the swap draws (two-sided), plus the same contrast
restricted to the three targets outside the original eight (the out-of-sample check).
  engine version : A, CO = 0.26.0 ; nulls, B, SD = 0.11.0
  sampler / GPU / judge mode / month : A, CO, nulls = FlashInfer, ~140 GiB cards, live judge, August ;
                                       B, SD = PyTorch-native sampler, H100, batch judge, October
  engine process : CO with A ; SD with B ; nulls with neither
"""
import json
import numpy as np
BASE = "/private/tmp/claude-501/-Users-unrulyabstractions-work-papers-idt/32b842b8-ab16-41a9-8f2f-692b2558b7d6/scratchpad/nullinv"
z = np.load(BASE + "/stats_r2/out/draws_swap_4000.npz")
S5 = z["S5"]; names = [str(x) for x in z["targets5"]]
G = S5[:, 0, :] - S5[:, 1, :]
Z = G / G[1:].std(0)
n = len(Z)
codes = {
    "engine version": np.array([+1] * 8 + [+1, +1] + [-1]),
    "sampler/GPU/judge mode/month": np.array([-1] * 8 + [+1, +1] + [-1]),
    "engine process (session mate)": np.array([0] * 8 + [+1, +1] + [-1]),
}
out = {"names": names, "z_obs": np.round(Z[0], 2).tolist()}
print(dict(zip(names, np.round(Z[0], 2))))
for nm, c in codes.items():
    for lab, mask in (("all coded targets", c != 0), ("outside the original eight", (c != 0) & (np.arange(11) >= 8))):
        v = (Z[:, mask] * c[mask]).mean(1)
        r = {"contrast": float(v[0]), "null_sd": float(v[1:].std()), "z": float(v[0] / v[1:].std()),
             "p_two": float((1 + (np.abs(v[1:]) >= abs(v[0])).sum()) / n), "n_targets": int(mask.sum())}
        out[f"{nm} | {lab}"] = r
        print(f"{nm:32s} {lab:28s} {json.dumps(r)}")
json.dump(out, open(BASE + "/critic_r2/k08_provenance_contrasts.json", "w"), indent=1)
