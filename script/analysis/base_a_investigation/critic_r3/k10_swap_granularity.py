"""Critic round 3, check 1: is the direction-free omnibus robust to the grain of the A/B swap?

The team's surprise numbers swap base-A and base-B replies slot by slot. That null assumes the 16
replies of one prompt are independent draws. If replies inside a prompt are dependent (one request,
n=16) or the two arms differ per prompt, the reply-level swap understates how far two base draws
can differ. Swapping whole prompts (candidate x instruction, all 16 replies) or whole instructions
(all six candidates' prompts) is valid under weaker assumptions.

Statistic (S scale): z_k = [S(T_k | A) - S(T_k | B)] / swap SD; omnibus = sum z_k^2.
Also: Q = sum over (candidate, instruction, axis) of (rate_A - rate_B)^2 against the reply-level
swap, which measures prompt-level over-dispersion of A minus B directly.
Read-only on the repo; uses stats_r1/common.py loaders (verified 22/22 against stored results).
"""
import json, sys, time, warnings
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "stats_r1"))
import common as C

warnings.simplefilter("ignore", RuntimeWarning)
D = C.load_all()
cands = D["_cands"]
keep = [i for i, c in enumerate(cands) if c != "anthropic"]
TEN = list(C.CONTROLS) + ["sd_ai_welfare_poisoning", "sd_emotional_bond"]
P = {k: C.rates(v) for k, v in D.items() if not k.startswith("_")}
OT6 = np.stack([C.ovr(P[k]) for k in TEN])
OT5 = np.stack([C.ovr(P[k][keep]) for k in TEN + ["CO"]])
RA, RB = D["A"], D["B"]
both = (~np.isnan(RA).all(3)) & (~np.isnan(RB).all(3))  # (6,36,16)


def S_all(pb):
    """S of the ten (six candidates) and eleven (five candidates) targets against base rates pb."""
    d6 = OT6 - C.ovr(pb)
    d5 = OT5 - C.ovr(pb[keep])
    out = []
    for d in (d6, d5):
        if np.isnan(d).any():
            out.append(np.array([float(C.smax(C.tgrid(x)[0])) for x in d]))
        else:
            out.append(C.smax(C.tgrid_fast(d)[0]))
    return out


def rates(X):
    return np.nanmean(X, axis=2)


def draw(rng, grain):
    if grain == "reply":
        m = (rng.random(RA.shape[:3]) < 0.5) & both
    elif grain == "prompt":
        m = np.broadcast_to((rng.random(RA.shape[:2]) < 0.5)[:, :, None], RA.shape[:3])
    elif grain == "instruction":
        m = np.broadcast_to((rng.random(RA.shape[1]) < 0.5)[None, :, None], RA.shape[:3])
    XA = np.where(m[..., None], RB, RA)
    XB = np.where(m[..., None], RA, RB)
    return XA, XB


def Qstat(XA, XB):
    return float(np.nansum((rates(XA) - rates(XB)) ** 2))


def omni(obs, null):
    sd = null.std(axis=0, ddof=0)
    z = obs / sd
    zn = null / sd
    s_obs = float((z ** 2).sum())
    s_null = (zn ** 2).sum(axis=1)
    return z, s_obs, float(s_null.mean()), float((1 + (s_null >= s_obs).sum()) / (1 + len(s_null)))


def summarize(gobs, gnull, names):
    res = {}
    z, so, sm, p = omni(gobs, gnull)
    res["z"] = dict(zip(names, np.round(z, 3).tolist()))
    res["sum_z2"] = so; res["null_mean"] = sm; res["p"] = p
    # eight nulls
    z8, so8, sm8, p8 = omni(gobs[:8], gnull[:, :8])
    res["eight_sum_z2"] = so8; res["eight_p"] = p8
    mg = gobs[:8].mean(); mn = gnull[:, :8].mean(axis=1)
    res["eight_mean_gap"] = float(mg); res["eight_mean_gap_sd"] = float(mn.std())
    res["eight_mean_gap_p_upper"] = float((1 + (mn >= mg).sum()) / (1 + len(mn)))
    res["eight_mean_gap_p_two"] = float((1 + (np.abs(mn) >= abs(mg)).sum()) / (1 + len(mn)))
    c = gobs[:8].mean() - gobs[8:10].mean(); cn = gnull[:, :8].mean(axis=1) - gnull[:, 8:10].mean(axis=1)
    res["eight_minus_sd"] = float(c); res["eight_minus_sd_sd"] = float(cn.std())
    res["eight_minus_sd_p_two"] = float((1 + (np.abs(cn) >= abs(c)).sum()) / (1 + len(cn)))
    # leave one out
    loo = {}
    for j, nm in enumerate(names):
        idx = [q for q in range(len(names)) if q != j]
        _, s1, _, p1 = omni(gobs[idx], gnull[:, idx])
        loo[nm] = [round(s1, 2), round(p1, 4)]
    res["leave_one_out"] = loo
    res["mean_null_corr"] = float((np.corrcoef(gnull.T).sum() - len(names)) / (len(names) * (len(names) - 1)))
    return res


def main(n=4000):
    SA6, SA5 = S_all(P["A"]); SB6, SB5 = S_all(P["B"])
    out = {"S_A6": dict(zip(TEN, np.round(SA6, 4).tolist())), "S_B6": dict(zip(TEN, np.round(SB6, 4).tolist()))}
    Qobs = Qstat(RA, RB)
    for grain in ("reply", "prompt", "instruction"):
        rng = np.random.default_rng([20261113, 77, {"reply": 1, "prompt": 2, "instruction": 3}[grain]])
        g6 = np.empty((n, 10)); g5 = np.empty((n, 11)); Q = np.empty(n)
        lv6 = np.empty((n, 2, 10))
        t0 = time.time()
        for k in range(n):
            XA, XB = draw(rng, grain)
            a6, a5 = S_all(rates(XA)); b6, b5 = S_all(rates(XB))
            g6[k] = a6 - b6; g5[k] = a5 - b5; lv6[k, 0] = a6; lv6[k, 1] = b6
            if grain == "reply":
                Q[k] = Qstat(XA, XB)
        r = {"n": n, "six": summarize(SA6 - SB6, g6, TEN), "five": summarize(SA5 - SB5, g5, TEN + ["CO"])}
        # level of each S among pseudo-bases (both halves of every draw): where do A and B sit?
        lev = lv6.reshape(-1, 10)
        r["level"] = {nm: {"S_A": round(float(SA6[j]), 3), "S_B": round(float(SB6[j]), 3),
                           "null_mean": round(float(lev[:, j].mean()), 3), "null_sd": round(float(lev[:, j].std()), 3),
                           "P_ge_A": round(float((lev[:, j] >= SA6[j]).mean()), 4),
                           "P_le_B": round(float((lev[:, j] <= SB6[j]).mean()), 4)} for j, nm in enumerate(TEN)}
        if grain == "reply":
            r["Q_prompt_level"] = {"obs": Qobs, "null_mean": float(Q.mean()), "null_sd": float(Q.std()),
                                   "ratio": Qobs / float(Q.mean()), "z": (Qobs - Q.mean()) / Q.std(),
                                   "p_upper": float((1 + (Q >= Qobs).sum()) / (1 + n))}
        out[grain] = r
        print(grain, f"{time.time()-t0:.0f}s", "six sum z2", round(r["six"]["sum_z2"], 2), "p", r["six"]["p"],
              "| eight mean gap p_upper", r["six"]["eight_mean_gap_p_upper"], "sd", round(r["six"]["eight_mean_gap_sd"], 3),
              "| eight-minus-sd p2", r["six"]["eight_minus_sd_p_two"],
              "| five sum z2", round(r["five"]["sum_z2"], 2), "p", r["five"]["p"], flush=True)
    (HERE / "k10_swap_granularity.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 4000)
