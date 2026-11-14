"""Within-cell completion order vs verdicts, for every online-judged sample (reference for A's p=0.002).

For each sample, a reply's rank among its cell's 16 replies in verdict-file order (the
completion order of online judging) is regressed on its verdicts per axis after removing
the cell mean; the statistic is the sum over axes of squared slopes, against 300
within-cell shuffles of the order. Also sum over axes of mean slope sign, to see whether
later-completed replies get more 'yes' verdicts (a latency confound: longer judge
reasoning, later completion).
"""
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BASE_A, BASE_B, CONTROLS, OUT, load_all, null_target, synth_target
D = load_all(); cands = D["_cands"]; instr = D["_instr"]
files = {"A": BASE_A, "B": BASE_B, **{c: null_target(c) for c in CONTROLS},
         "sd_ai_welfare_poisoning": synth_target("ai_welfare_poisoning")}
rng = np.random.default_rng(8)
res = {}
for k, f in files.items():
    rows = [json.loads(l) for l in open(f)]
    R = D[k]
    pos = np.full(R.shape[:3], np.nan)
    for n, r in enumerate(rows):
        pos[cands.index(r["principal"]), instr.index(r["instruction_id"]), int(r["s"])] = n
    rk = np.argsort(np.argsort(np.where(np.isnan(pos), np.inf, pos), axis=2), axis=2).astype(float)
    rk[np.isnan(pos)] = np.nan
    resid = R - np.nanmean(R, axis=2, keepdims=True)
    def stat(pc):
        pc = pc - np.nanmean(pc, axis=2, keepdims=True)
        b = np.nansum(resid * pc[..., None], axis=(0, 1, 2)) / np.nansum((pc ** 2)[..., None] * ~np.isnan(resid), axis=(0, 1, 2))
        return float(np.sum(b ** 2)), float(np.mean(b) * 1e3)
    obs, msl = stat(rk)
    null = []
    for _ in range(300):
        idx = np.argsort(rng.random(rk.shape), axis=2)
        null.append(stat(np.take_along_axis(rk, idx, axis=2))[0])
    null = np.array(null)
    res[k] = {"sum_sq_slopes_x1e4": obs * 1e4, "null_mean_x1e4": float(null.mean()) * 1e4,
              "ratio": obs / float(null.mean()), "p": float((1 + np.sum(null >= obs)) / 301),
              "mean_slope_x1e3": msl}
    print(f"{k:26s} ratio obs/null {obs/null.mean():5.2f} p={res[k]['p']:.4f} mean slope x1e3 {msl:+.3f}", flush=True)
json.dump(res, open(OUT / "within_block_drift.json", "w"), indent=1)
