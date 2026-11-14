"""Critic r2, check 6: the direction-free omnibus recomputed from the stats investigator's own stored
swap draws (stats_r2/out/draws_swap_4000.npz; draw 0 is the identity), with S gaps and with exact p.
Also a coded contrast: +1 for the eight nulls and CO (sampled and judged in August), -1 for the two
synthetic-document arms (sampled and judged with base B in October). The coding was chosen after
seeing the data, so its p is descriptive.
"""
import json
import numpy as np
BASE = "/private/tmp/claude-501/-Users-unrulyabstractions-work-papers-idt/32b842b8-ab16-41a9-8f2f-692b2558b7d6/scratchpad/nullinv"
z = np.load(BASE + "/stats_r2/out/draws_swap_4000.npz")
S6, p6, S5, p5 = z["S6"], z["p6"], z["S5"], z["p5"]
print("targets6", list(z["targets6"])); print("targets5", list(z["targets5"]))
n = S6.shape[0]
out = {}
def run(G, label, code=None):
    # G: (n, m) gaps, row 0 observed
    sd = G[1:].std(0); Z = G / sd
    r = {"per_target_z": np.round(Z[0], 2).tolist()}
    for nm, fn in (("sum_z2", lambda x: (x ** 2).sum(-1)), ("max_abs_z", lambda x: np.abs(x).max(-1))):
        v = fn(Z); r[nm] = {"obs": float(v[0]), "null_mean": float(v[1:].mean()), "p": float((1 + (v[1:] >= v[0]).sum()) / n)}
    if code is not None:
        v = (Z * code).mean(-1)
        r["coded_mean_z"] = {"obs": float(v[0]), "null_sd": float(v[1:].std()), "z": float(v[0] / v[1:].std()),
                             "p_two": float((1 + (np.abs(v[1:]) >= abs(v[0])).sum()) / n)}
    out[label] = r; print(label, json.dumps(r))
gS6 = S6[:, 0, :] - S6[:, 1, :]
gS5 = S5[:, 0, :] - S5[:, 1, :]
# probit-free p-based gap: difference of log p
gP6 = -(np.log(p6[:, 0, :]) - np.log(p6[:, 1, :]))
gP5 = -(np.log(p5[:, 0, :]) - np.log(p5[:, 1, :]))
c10 = np.array([1] * 8 + [-1] * 2); c11 = np.array([1] * 8 + [-1] * 2 + [1])
run(gS6, "S gap, ten six-cand", c10)
run(gS6[:, :8], "S gap, eight six-cand")
run(gS5, "S gap, eleven five-cand", c11)
run(gP6, "log p gap, ten six-cand", c10)
run(gP6[:, :8], "log p gap, eight six-cand")
run(gP5, "log p gap, eleven five-cand", c11)
json.dump(out, open(BASE + "/critic_r2/k06_omnibus_from_stats_draws.json", "w"), indent=1)
