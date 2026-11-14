"""Critic round 3, check 11: do the low values against base A need each control's own structure?

Pseudo-controls: at every (candidate, instruction, s) slot the eight controls' replies are shuffled
among the eight labels (as k19). Each pseudo-control keeps the pattern all controls share and realistic
noise, and carries one eighth of every control's own structure. Each is tested against base A and
against base B with the exact registered test (six candidates and five). If base A's draw alone
produced the low values (through the shared pattern and A's own cells), the pseudo-controls should
also give low p against A. If the real controls' own structure or their specific noise is needed,
the pseudo-controls should give ordinary p against both bases.
"""
import json, sys, warnings
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "stats_r2"))
import fast as F
from fast import C
warnings.simplefilter("ignore", RuntimeWarning)
D = F.load(); cands = D["_cands"]
names = list(C.CONTROLS)
keep5 = [i for i, c in enumerate(cands) if c != "anthropic"]
R = np.stack([D[k] for k in names])
allok = (~np.isnan(R).all(-1)).all(0)
PA, PB = C.rates(D["A"]), C.rates(D["B"])
rng = np.random.default_rng([20261113, 21])
NSH = int(sys.argv[1]) if len(sys.argv) > 1 else 120
st = {("six", "A"): [], ("six", "B"): [], ("five", "A"): [], ("five", "B"): []}
Sst = {k: [] for k in st}
for s in range(NSH):
    perm = np.argsort(rng.random((8,) + R.shape[1:4]), axis=0)
    perm = np.where(allok[None], perm, np.arange(8)[:, None, None, None])
    rates = np.nanmean(np.take_along_axis(R, perm[..., None], axis=0), axis=3)
    for tag, kp, nc in (("six", list(range(6)), 6), ("five", keep5, 5)):
        E = F.E_for(nc)
        O = np.nan_to_num(C.ovr(rates[:, kp]))
        for b, pb in (("A", PA), ("B", PB)):
            S, p, _ = F.test_many(O, np.nan_to_num(C.ovr(pb[kp])), nc, E)
            st[(tag, b)].append(p); Sst[(tag, b)].append(S)
    if (s + 1) % 30 == 0:
        print(s + 1, flush=True)
obs = {("six", "A"): (0.0557, 3.911), ("six", "B"): (0.4146, 3.313), ("five", "A"): (0.0782, None), ("five", "B"): (0.4553, None)}
out = {}
for k in st:
    p = np.array(st[k]); S = np.array(Sst[k]); med = np.median(p, axis=1)
    out[f"{k[0]}|{k[1]}"] = {"n": int(len(p)), "median_of_eight_test_median": float(np.median(med)), "q05_q95": np.quantile(med, [.05, .95]).round(4).tolist(),
                              "share_p_lt_0.05": float((p < 0.05).mean()), "share_p_le_0.06": float((p <= 0.06).mean()), "mean_S": float(S.mean()),
                              "observed_real_controls_median": obs[k][0], "P_median_le_observed": float((1 + (med <= obs[k][0]).sum()) / (1 + len(med)))}
    print(k, json.dumps(out[f"{k[0]}|{k[1]}"]))
gapS = np.array(Sst[("six", "A")]).mean(1) - np.array(Sst[("six", "B")]).mean(1)
out["six mean S gap A minus B, pseudo-controls"] = {"mean": float(gapS.mean()), "sd": float(gapS.std()), "observed_real_controls": 0.597,
                                                    "P_ge_observed": float((1 + (gapS >= 0.597).sum()) / (1 + len(gapS)))}
print("mean-S gap (A minus B) for pseudo-controls:", out["six mean S gap A minus B, pseudo-controls"])
(HERE / "k21_shuffled_controls_vs_bases.json").write_text(json.dumps(out, indent=1))
