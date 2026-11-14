"""S3b. Forking-paths adjustment of the surprise: min-p over summary statistics and families.

For every pseudo-base (swap null, targets fixed) and for the real A, each summary statistic's one-sided
level p is its rank among all pseudo-bases. The adjusted p of the real A is the share of pseudo-bases
whose smallest p (over the chosen statistics and families) is at most A's smallest p.
Statistics: median p, mean S, count p<0.05, Fisher (the post hoc count p<0.07 is left out, and shown
separately). Families: six candidates {eight, ten, ten + CO five-cand}; five candidates {eight, ten, ten + CO}."""
import sys, json
import numpy as np
import fast as F
z = np.load(sys.argv[1]); S6, p6, S5, p5 = z["S6"], z["p6"], z["S5"], z["p5"]
fams = {"six8": (S6[..., :8], p6[..., :8]), "six10": (S6[..., :10], p6[..., :10]),
        "six10+CO": (np.concatenate([S6[..., :10], S5[..., 10:]], -1), np.concatenate([p6[..., :10], p5[..., 10:]], -1)),
        "five8": (S5[..., :8], p5[..., :8]), "five10": (S5[..., :10], p5[..., :10]), "five10+CO": (S5, p5)}
stats = {"median_p": lambda S, p: -np.median(p, -1), "mean_S": lambda S, p: S.mean(-1),
         "count05": lambda S, p: (p < 0.05).sum(-1).astype(float), "fisher": lambda S, p: -2 * np.log(p).sum(-1),
         "count07": lambda S, p: (p < 0.07).sum(-1).astype(float)}
def rankp(vals_null, v):  # larger = more extreme; one-sided p for each v against vals_null
    s = np.sort(vals_null)
    return (1 + len(s) - np.searchsorted(s, v, side="left")) / (1 + len(s))
cols = {}
for fn, (S, p) in fams.items():
    for sn, f in stats.items():
        q = f(S, p)                      # (n, 2)
        null = q[1:].ravel()
        cols[(fn, sn)] = (rankp(null, null), float(rankp(null, np.array([q[0, 0]]))[0]))
res = {}
def adj(keys, label):
    mins_null = np.min(np.stack([cols[k][0] for k in keys], 1), 1)
    mins_obs = min(cols[k][1] for k in keys)
    a = float((1 + np.sum(mins_null <= mins_obs)) / (1 + len(mins_null)))
    res[label] = {"min_unadjusted": mins_obs, "adjusted": a, "n_stats": len(keys)}
    print(f"{label:60s} min unadjusted p = {mins_obs:.4f}  adjusted = {a:.4f}  ({len(keys)} statistics)")
base4 = ["median_p", "mean_S", "count05", "fisher"]
adj([("six8", s) for s in base4], "eight nulls, six cand, 4 statistics")
adj([("six8", s) for s in base4 + ["count07"]], "eight nulls, six cand, 4 statistics + count p<0.07")
adj([(f, s) for f in fams if f.startswith("six") for s in base4], "three six-candidate families x 4 statistics")
adj([(f, s) for f in fams for s in base4], "all six families x 4 statistics")
adj([(f, "mean_S") for f in fams], "mean S over all six families")
for k, v in cols.items():
    res.setdefault("unadjusted", {})[f"{k[0]}|{k[1]}"] = v[1]
json.dump(res, open(F.OUT / "s3b_minp.json", "w"), indent=1)
