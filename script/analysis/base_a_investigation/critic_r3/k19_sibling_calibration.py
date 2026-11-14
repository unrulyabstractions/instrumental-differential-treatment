"""Critic round 3, check 9: is 'one control against the average of the other seven' calibrated?

Reply-level null in which the eight controls are exchangeable: at every (candidate, instruction, s)
slot the eight controls' replies are shuffled among the eight labels (matched slots keep the judge's
axis order paired). Each pseudo-control keeps realistic noise and the pattern all controls share,
and has no structure of its own. Each pseudo-control is tested against the average of the other
seven with the exact registered test. 120 shuffles x 8 tests, six and five candidates.
Reports the share of p below 0.05 and 0.10, the distribution of the eight-test median, and where the
observed medians (k18) fall.
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
R = np.stack([D[k] for k in names])            # (8, 6, 36, 16, 101)
ok = ~np.isnan(R).all(-1)                      # (8, 6, 36, 16)
allok = ok.all(0)
rng = np.random.default_rng([20261113, 19])
NSH = int(sys.argv[1]) if len(sys.argv) > 1 else 120
obs = json.loads((HERE / "k18_controls_vs_siblings.json").read_text())
out = {}
P6, P5 = [], []
for s in range(NSH):
    perm = np.argsort(rng.random((8,) + R.shape[1:4]), axis=0)          # a permutation of the 8 labels per slot
    perm = np.where(allok[None], perm, np.arange(8)[:, None, None, None])  # slots with a missing row stay put
    X = np.take_along_axis(R, perm[..., None], axis=0)
    rates = np.nanmean(X, axis=3)                                        # (8, 6, 36, 101)
    for kp, nc, store in ((list(range(6)), 6, P6), (keep5, 5, P5)):
        E = F.E_for(nc)
        O = np.nan_to_num(C.ovr(rates[:, kp]))
        ps = []
        for k in range(8):
            ref = np.nan_to_num(C.ovr(np.nanmean(np.delete(rates[:, kp], k, axis=0), axis=0)))
            _, p, _ = F.test_many(O[k][None], ref, nc, E)
            ps.append(float(p[0]))
        store.append(ps)
    if (s + 1) % 20 == 0:
        print(s + 1, "shuffles", flush=True)
for tag, store in (("six", np.array(P6)), ("five", np.array(P5))):
    med = np.median(store, axis=1)
    o = obs[tag]["vs_other_seven"]
    r = {"n_shuffles": int(len(store)), "share_p_lt_0.05": float((store < 0.05).mean()), "share_p_lt_0.10": float((store < 0.10).mean()),
         "median_of_all_p": float(np.median(store)), "median_of_eight_test_median": float(np.median(med)),
         "eight_test_median_q05_q95": np.quantile(med, [.05, .95]).round(4).tolist(), "min_eight_test_median": float(med.min()),
         "observed_median": o["median_p"], "P_median_le_observed": float((1 + (med <= o["median_p"]).sum()) / (1 + len(med))),
         "observed_count_below_0.1": o["count_below_0.1"], "P_count_ge_observed": float((1 + ((store < 0.1).sum(1) >= o["count_below_0.1"]).sum()) / (1 + len(med)))}
    out[tag] = r
    print(tag, json.dumps(r, indent=1))
(HERE / "k19_sibling_calibration.json").write_text(json.dumps(out, indent=1))
