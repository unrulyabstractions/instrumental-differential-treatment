"""Before any A2 data: the power of the REGISTERED recurrence verdict, not of the analytic z test.

    nice -n 19 .venv/bin/python script/analysis/exact_stack_20261114/p01_power_registered.py            # writes pre/
    nice -n 19 .venv/bin/python script/analysis/exact_stack_20261114/p01_power_registered.py --check    # equality test

The verdict of a01_recurrence.py is "repeats" iff the swap p_one < 0.05 AND f-hat exceeds the conditional band's
q95. t01's power row (0.96 / 0.65 / 0.32 / 0.10) is the analytic one-sided z test alone, so it overstates the
verdict's power: the band is drawn at the pooled B + A2 rates and its q95 rises as A2 repeats. This script
simulates the two-part rule itself, with a01's own computations and sizes (10,000 swaps, 2,000 band draws):

* model "B fixed" (primary): A and B as observed; A2 ~ Bernoulli(clip(p_B + f (p_A - p_B))) per prompt, slot and
  axis, so E[u_A2] - u_B = f (u_A - u_B), t01's own assumption.
* model "B redrawn" (sensitivity): B* ~ Bernoulli(m_B) and A2 ~ Bernoulli(clip(m_B + f (p_A - m_B))), where m_B is
  B's smoothed rate ((yes + 2 pbar) / (n + 2), a01's smoothing); the verdict then reads B* in B's place.

Exactness: on the seven cells' axes neither A nor B has a NaN rate, so ovr() is linear and each swap draw is
D* = sum over the 216 prompts of sign * L_prompt. --check runs that against a01's loop on A as A2's stand-in with
a01's own rng (20261113) and requires null_mean and null_sd equal to 1e-9 relative (the critic's a01 run on A gave
1.693767322957785 and 170.25328889189723). The band draws only the seven axes it reads (a01 draws all 101 and reads
the same seven), so its stream differs from a01's and its distribution does not.

Writes pre/p01_power_registered.json; refuses to overwrite. Reads A, B only. No spend.
"""
from __future__ import annotations

import argparse
import json
import time

import numpy as np

import es_common as K

ap = argparse.ArgumentParser()
ap.add_argument("--check", action="store_true", help="equality test against a01's loop, writes nothing")
ap.add_argument("--nsim", type=int, default=400, help="draws per share, model B fixed")
ap.add_argument("--nsim-redrawn", type=int, default=200, help="draws per share, model B redrawn")
a = ap.parse_args()
OUT = K.PRE / "p01_power_registered.json"
if not a.check and OUT.exists():
    raise SystemExit(f"refusing to overwrite {OUT}")

t01 = json.loads((K.PRE / "t01_thresholds_n16.json").read_text())["real"]
VA_full, _ = K.load("A")
VB_full, _ = K.load("B")
cells = K.PRIMARY + [K.C2]
CI = [K.cell(c, x) for c, x, _ in cells]
SG = np.array([s for _, _, s in cells])
w = 1 / np.array(t01["V"])
axes = sorted({aj for _, aj in CI})
pos = {aj: k for k, aj in enumerate(axes)}
VA, VB = VA_full[..., axes], VB_full[..., axes]
NC, NI = len(K.CANDS), K.NI
NSW, NBAND = 10000, 2000


def rates(V):
    with np.errstate(invalid="ignore"):
        return np.nanmean(V, axis=-2)


def pio(P):
    O = K.ovr(P)
    return np.stack([O[ci, :, pos[aj]] for ci, aj in CI], axis=1)


def omean7(P):
    with np.errstate(invalid="ignore"):
        return np.nanmean(pio(P), axis=0)


PA, PB = rates(VA), rates(VB)
assert not np.isnan(PA).any() and not np.isnan(PB).any(), "a NaN rate breaks the linear swap"
oA = omean7(PA)

# L[c, i]: the contribution of prompt (c, i)'s difference vector to D, from ovr's linearity on full rates.
COEF = np.zeros((NC, len(axes)))  # per candidate row c and axis column: weight on Delta[c, i, axis]
for k, (ci, aj) in enumerate(CI[:6]):
    wk = w[k] * -SG[k] / NI
    for c in range(NC):
        COEF[c, pos[aj]] += wk if c == ci else -wk / (NC - 1)


def swap_null(PC, PBx, rng):
    L = np.einsum("cia,ca->ci", PC - PBx, COEF).reshape(-1)          # (216,)
    sw = rng.random((NSW, NC, NI)) < 0.5                              # a01's draws, in a01's order
    sign = np.where(sw.reshape(NSW, -1), -1.0, 1.0)
    return sign @ L


def stat(PC, PBx):
    oC, oB = omean7(PC), omean7(PBx)
    D = float(np.sum(w * (-SG * (oC - oB))[:6]))
    den = float(np.sum(w * (-SG * (oA - oB))[:6]))
    return D, den


def band_q95(VBx, VC, rng):
    yes = np.nansum(VBx, axis=2) + np.nansum(VC, axis=2)
    nn = np.isfinite(VBx).sum(axis=2) + np.isfinite(VC).sum(axis=2)
    pbar = yes.sum(axis=1, keepdims=True) / np.maximum(nn.sum(axis=1, keepdims=True), 1)
    mu = (yes + 2 * pbar) / (nn + 2)                                  # (6, 36, 7)
    nanB, nanC = np.isnan(VBx), np.isnan(VC)
    fs = []
    for _ in range(NBAND // 200):
        Bs = (rng.random((200, *VBx.shape)) < mu[None, :, :, None, :]).astype(float)
        Cs = (rng.random((200, *VBx.shape)) < mu[None, :, :, None, :]).astype(float)
        Bs[:, nanB] = np.nan
        Cs[:, nanC] = np.nan
        for b in range(200):
            oBs, oCs = omean7(rates(Bs[b])), omean7(rates(Cs[b]))
            fs.append(np.sum(w * (-SG * (oCs - oBs))[:6]) / np.sum(w * (-SG * (oA - oBs))[:6]))
    return float(np.quantile(np.array(fs), 0.95))


def check() -> None:
    """The vectorized swap against a01's own loop, on A as A2's stand-in, with a01's rng."""
    Dn = swap_null(PA, PB, np.random.default_rng(20261113))
    rng = np.random.default_rng(20261113)
    loop = np.empty(200)
    for k in range(200):
        sw = rng.random((6, NI)) < 0.5
        Xc = np.where(sw[..., None], PB, PA)
        Xb = np.where(sw[..., None], PA, PB)
        dd = -SG * (omean7(Xc) - omean7(Xb))
        loop[k] = np.sum(w * dd[:6])
    err = float(np.max(np.abs(loop - Dn[:200])))
    got = {"null_mean": float(Dn.mean()), "null_sd": float(Dn.std()), "max_abs_diff_first_200_vs_loop": err}
    want = {"null_mean": 1.693767322957785, "null_sd": 170.25328889189723}
    ok = err < 1e-9 * 170 and all(abs(got[k] - v) <= 1e-9 * max(1.0, abs(v)) for k, v in want.items())
    print(json.dumps({"got": got, "want_from_critic_a01_on_A": want, "equal": ok}, indent=1))
    if not ok:
        raise SystemExit("the vectorized swap differs from a01's loop")


def one(VBx, PBx, mu_c, rng):
    VC = (rng.random(VBx.shape) < mu_c[:, :, None, :]).astype(float)
    VC[np.isnan(VBx)] = np.nan
    PC = rates(VC)
    D, den = stat(PC, PBx)
    fhat = D / den
    Dn = swap_null(PC, PBx, rng)
    p_one = float((1 + np.sum(Dn >= D - 1e-15)) / (1 + NSW))
    q95 = band_q95(VBx, VC, rng)
    return {"fhat": fhat, "p_one": p_one, "q95": q95, "z_swap": D / float(Dn.std()),
            "repeat": bool(p_one < 0.05 and fhat > q95)}


def summarize(rs: list[dict]) -> dict:
    n = len(rs)
    k = sum(r["repeat"] for r in rs)
    return {"n": n, "power_registered_verdict": k / n, "mc_se": float(np.sqrt(max(k / n * (1 - k / n), 1e-12) / n)),
            "share_p_one_lt_05": sum(r["p_one"] < 0.05 for r in rs) / n,
            "share_fhat_gt_q95": sum(r["fhat"] > r["q95"] for r in rs) / n,
            "mean_fhat": float(np.mean([r["fhat"] for r in rs])), "sd_fhat": float(np.std([r["fhat"] for r in rs])),
            "mean_q95": float(np.mean([r["q95"] for r in rs])),
            "mean_z_swap": float(np.mean([r["z_swap"] for r in rs]))}


def smooth(V):
    yes = np.nansum(V, axis=2)
    n = np.isfinite(V).sum(axis=2)
    pbar = yes.sum(axis=1, keepdims=True) / np.maximum(n.sum(axis=1, keepdims=True), 1)
    return (yes + 2 * pbar) / (n + 2)


if a.check:
    check()
    raise SystemExit(0)
check()
t0 = time.time()
rng = np.random.default_rng(20261119)
SHARES = (0.0, 0.1, 0.35, 0.6, 1.0)
res = {"B_fixed": {}, "B_redrawn": {}}
for f in SHARES:
    mu = np.clip(PB + f * (PA - PB), 0, 1)
    rs = [one(VB, PB, mu, rng) for _ in range(a.nsim)]
    res["B_fixed"][str(f)] = summarize(rs)
    print("B_fixed", f, json.dumps(res["B_fixed"][str(f)]), round(time.time() - t0), "s", flush=True)
mB = smooth(VB)
for f in (0.0, 0.35, 1.0):
    mu = np.clip(mB + f * (PA - mB), 0, 1)
    rs = []
    for _ in range(a.nsim_redrawn):
        VBs = (rng.random(VB.shape) < mB[:, :, None, :]).astype(float)
        rs.append(one(VBs, rates(VBs), mu, rng))
    res["B_redrawn"][str(f)] = summarize(rs)
    print("B_redrawn", f, json.dumps(res["B_redrawn"][str(f)]), round(time.time() - t0), "s", flush=True)
out = {"rule": "repeats iff swap p_one < 0.05 and f_hat > conditional q95 (a01_recurrence.py, unchanged)",
       "sizes": {"swaps": NSW, "band_draws": NBAND, "nsim_B_fixed": a.nsim, "nsim_B_redrawn": a.nsim_redrawn},
       "rng": 20261119, "models": {"B_fixed": "A2 ~ Bernoulli(clip(p_B + f (p_A - p_B)))",
                                   "B_redrawn": "B* ~ Bernoulli(m_B), A2 ~ Bernoulli(clip(m_B + f (p_A - m_B)))"},
       "analytic_z_power_t01": t01["power_one_sided_05"], "results": res,
       "inputs_sha256": {n: K.sha256_file(K.FILES[n]) for n in ("A", "B")},
       "thresholds_sha256": K.sha256_file(K.PRE / "t01_thresholds_n16.json"), "seconds": round(time.time() - t0)}
print(K.dump(out, OUT))
