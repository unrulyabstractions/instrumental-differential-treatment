"""Critic round 3, check 2: where does the controls' own candidate structure come from?

Hypothesis: a fine-tune that changes reply style for every candidate alike (shorter, untruncated
replies) rescales yes rates. If the base model's rates already differ by candidate, a rescaling
gives d = OvR_T - OvR_base = (g - 1) * OvR_true: candidate-dependent, although the fine-tune itself
treats every candidate alike. Test: across the 606 (candidate, axis) cells, regress the mean over
instructions of y = OvR_T - OvR_A on x = OvR_B (and y = OvR_T - OvR_B on x = OvR_A). The two bases
are independent draws, so base noise does not enter both sides. Slope estimates g - 1 (attenuated
by noise in x; reliability of x reported). Null: candidates relabelled within instruction in y
(the registered test's own null), 2,000 draws.
"""
import json, sys, warnings
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "stats_r1"))
import common as C
warnings.simplefilter("ignore", RuntimeWarning)
D = C.load_all()
cands = D["_cands"]
P = {k: C.rates(v) for k, v in D.items() if not k.startswith("_")}
TEN = list(C.CONTROLS) + ["sd_ai_welfare_poisoning", "sd_emotional_bond"]
rng = np.random.default_rng(20261113)
NP = 2000


def perms(n_c, n_i=36, k=NP):
    return np.argsort(rng.random((k, n_i, n_c)), axis=2)


def stat(y, x):
    """y, x: (..., n_c, n_i, n_j). Slope and correlation over cells of the instruction means."""
    ym = np.nanmean(y, axis=-2); xm = np.nanmean(x, axis=-2)
    ym = ym.reshape(ym.shape[:-2] + (-1,)); xm = xm.reshape(xm.shape[:-2] + (-1,))
    sxy = (ym * xm).sum(-1); sxx = (xm * xm).sum(-1); syy = (ym * ym).sum(-1)
    return sxy / sxx, sxy / np.sqrt(sxx * syy)


def run(keep, names):
    OA, OB = C.ovr(P["A"][keep]), C.ovr(P["B"][keep])
    OA = np.nan_to_num(OA); OB = np.nan_to_num(OB)
    n_c = len(keep)
    xa = OA.mean(1).ravel(); xb = OB.mean(1).ravel()
    rel = float(np.corrcoef(xa, xb)[0, 1])
    orders = perms(n_c)
    out = {"reliability_of_x (corr of OvR_A and OvR_B cell means)": rel, "sd_x_A": float(xa.std()), "sd_x_B": float(xb.std())}
    for nm in names:
        OT = np.nan_to_num(C.ovr(P[nm][keep]))
        r = {}
        sl = []; cr = []; zs = []
        for tag, base, x in (("y=T-A on x=B", OA, OB), ("y=T-B on x=A", OB, OA)):
            y = OT - base
            b, c = stat(y, x)
            yp = C.apply_orders(y, orders)
            bn, cn = stat(yp, x[None])
            z = (b - bn.mean()) / bn.std()
            r[tag] = {"slope": float(b), "corr": float(c), "null_sd_slope": float(bn.std()), "z": float(z),
                      "p_two": float((1 + (np.abs(bn - bn.mean()) >= abs(b - bn.mean())).sum()) / (1 + NP))}
            sl.append(b); cr.append(c); zs.append(z)
        r["mean_slope"] = float(np.mean(sl)); r["mean_corr"] = float(np.mean(cr)); r["mean_z"] = float(np.mean(zs))
        r["slope_disattenuated"] = float(np.mean(sl) / rel)
        out[nm] = r
        print(f"{nm:26s} slope {sl[0]:+.3f} (z {zs[0]:+.2f}) / {sl[1]:+.3f} (z {zs[1]:+.2f})  corr {cr[0]:+.3f}/{cr[1]:+.3f}  g-1 ~ {np.mean(sl)/rel:+.3f}")
    # control: base B against base A cannot be cross-fitted with a third base; use the nulls' consensus as x
    cons = np.mean([np.nan_to_num(C.ovr(P[k][keep])) for k in C.CONTROLS], axis=0)
    y = OB - OA
    b, c = stat(y, cons); bn, cn = stat(C.apply_orders(y, orders), cons[None])
    out["control: y=B-A on x=consensus of eight nulls"] = {"slope": float(b), "corr": float(c), "z": float((b - bn.mean()) / bn.std())}
    print(f"control B-A on null consensus: slope {b:+.3f} corr {c:+.3f} z {(b-bn.mean())/bn.std():+.2f}")
    return out


res = {}
print("== six candidates; reliability printed in JSON")
res["six"] = run(list(range(6)), TEN + ["CO"])
print("reliability", res["six"]["reliability_of_x (corr of OvR_A and OvR_B cell means)"])
print("== five candidates (anthropic dropped)")
res["five"] = run([i for i, c in enumerate(cands) if c != "anthropic"], TEN + ["CO"])
print("reliability", res["five"]["reliability_of_x (corr of OvR_A and OvR_B cell means)"])
(HERE / "k11_scaling.json").write_text(json.dumps(res, indent=1))
