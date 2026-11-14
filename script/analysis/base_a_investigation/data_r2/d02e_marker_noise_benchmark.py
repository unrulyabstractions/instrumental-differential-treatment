"""D2 (marker benchmark). How much of ordinary draw-to-draw verdict variation do the keyword markers see?

Within-sample split halves (8 vs 8 replies per prompt, 300 random splits) of base A and of base B: correlation
over the 36 (candidate, axis) cells of marker t and verdict t for one-vs-rest(half1) - one-vs-rest(half2).
Same for the cross-sample A-half vs B-half (8 A replies vs 8 B replies), to compare with the full A - B value.
If A - B were less textual than ordinary noise, its correlation would sit below the within-sample benchmark.
"""
import json, re, warnings
import numpy as np
from dcommon import C, dump, load_texts, OUT
warnings.simplefilter("ignore", RuntimeWarning)
D = C.load_all()
MK = json.load(open(OUT / "d02_markers.json"))["markers"]
AXS = [a for a in MK if "refusal" not in a]; J = [C.AXES.index(a) for a in AXS]
TX = {a: load_texts(a) for a in ("A", "B")}
M = {a: np.stack([np.vectorize(lambda t: np.nan if t is None else float(bool(re.compile(MK[ax], re.I).search(t))), otypes=[float])(TX[a]) for ax in AXS], -1) for a in TX}
V = {a: D[a][..., J] for a in TX}
def t1(d):
    return np.nanmean(d, 1) / (np.nanstd(d, 1, ddof=1) / np.sqrt(np.sum(~np.isnan(d), 1)))
def corr(xm1, xm2, xv1, xv2):
    tm = t1(C.ovr(np.nanmean(xm1, 2)) - C.ovr(np.nanmean(xm2, 2))).ravel(); tv = t1(C.ovr(np.nanmean(xv1, 2)) - C.ovr(np.nanmean(xv2, 2))).ravel()
    ok = ~np.isnan(tm) & ~np.isnan(tv); return np.corrcoef(tm[ok], tv[ok])[0, 1]
rng = np.random.default_rng(5); res = {}
for name in ("A", "B", "AxB"):
    rs = []
    for _ in range(300):
        p = rng.permutation(16); h1, h2 = p[:8], p[8:]
        if name == "AxB":
            rs.append(corr(M["A"][:, :, h1], M["B"][:, :, h2], V["A"][:, :, h1], V["B"][:, :, h2]))
        else:
            rs.append(corr(M[name][:, :, h1], M[name][:, :, h2], V[name][:, :, h1], V[name][:, :, h2]))
    rs = np.array(rs); res[name] = {"mean_corr": float(rs.mean()), "sd_over_splits": float(rs.std()), "q05_q95": np.quantile(rs, [0.05, 0.95]).tolist()}
    print(f"{name:4s} split halves: mean corr(marker t, verdict t) over 36 cells {rs.mean():+.3f} (sd over splits {rs.std():.3f}; 5-95% {np.quantile(rs,0.05):+.3f} to {np.quantile(rs,0.95):+.3f})")
full = corr(M["A"], M["B"], V["A"], V["B"]); res["A_minus_B_full"] = float(full)
print(f"full A - B: {full:+.3f}")
dump(res, "d02e_marker_noise_benchmark.json")
