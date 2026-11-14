"""D2 (marker calibration). How well do the keyword markers track the judge's one-vs-rest t at the cell level in general?

For the six axes with a usable marker (the refusal marker fires on 0.2% of replies and is left out), all six
candidates: t over instructions of the one-vs-rest difference for A-B, cons8-A, cons8-B and CO-A (anthropic row
included for CO), marker vs gpt-5-mini verdict. Correlation over the (candidate, axis) cells, and sign agreement.
"""
import json, re
import numpy as np
from dcommon import C, dump, load_texts, OUT

D = C.load_all(); cands = D["_cands"]
MK = json.load(open(OUT / "d02_markers.json"))["markers"]
AXS = [a for a in MK if "refusal" not in a]
arms = ["A", "B", "CO"] + list(C.CONTROLS)
TX = {a: load_texts(a) for a in arms}
ovr2 = lambda x: C.ovr(x[..., None])[..., 0]
def t1(d):
    return np.nanmean(d, 1) / (np.nanstd(d, 1, ddof=1) / np.sqrt(np.sum(~np.isnan(d), 1)))
rows = {k: {"marker": [], "verdict": []} for k in ("A-B", "cons-A", "cons-B", "CO-A")}
for ax in AXS:
    rx = re.compile(MK[ax], re.I); j = C.AXES.index(ax)
    M = {a: np.vectorize(lambda t: np.nan if t is None else float(bool(rx.search(t))), otypes=[float])(TX[a]) for a in arms}
    om = {a: ovr2(np.nanmean(M[a], 2)) for a in arms}; ov = {a: ovr2(C.rates(D[a])[..., j]) for a in arms}
    cm = np.mean([om[c] for c in C.CONTROLS], 0); cv = np.mean([ov[c] for c in C.CONTROLS], 0)
    for k, (xm, xv) in {"A-B": (om["A"] - om["B"], ov["A"] - ov["B"]), "cons-A": (cm - om["A"], cv - ov["A"]),
                        "cons-B": (cm - om["B"], cv - ov["B"]), "CO-A": (om["CO"] - om["A"], ov["CO"] - ov["A"])}.items():
        rows[k]["marker"] += t1(xm).tolist(); rows[k]["verdict"] += t1(xv).tolist()
res = {}
for k, v in rows.items():
    m, vv = np.array(v["marker"]), np.array(v["verdict"]); ok = ~np.isnan(m) & ~np.isnan(vv)
    r = float(np.corrcoef(m[ok], vv[ok])[0, 1]); agree = float(np.mean(np.sign(m[ok]) == np.sign(vv[ok])))
    big = ok & (np.abs(vv) >= 2); agree_big = float(np.mean(np.sign(m[big]) == np.sign(vv[big]))) if big.any() else np.nan
    slope = float(np.polyfit(vv[ok], m[ok], 1)[0])
    res[k] = {"n_cells": int(ok.sum()), "corr": r, "sign_agree": agree, "n_cells_verdict_abs_t_ge_2": int(big.sum()), "sign_agree_when_abs_t_ge_2": agree_big, "slope_marker_on_verdict": slope}
    print(f"{k:7s} cells {ok.sum()}  corr(marker t, verdict t) {r:+.3f}  slope {slope:+.3f}  sign agreement {agree:.2f}; where |verdict t|>=2: {agree_big:.2f} (n={big.sum()})")
dump(res, "d02d_marker_calibration.json")
