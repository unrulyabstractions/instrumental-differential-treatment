"""Registered reading (a): does part of base A's departure recur in A2, a fresh draw on base A's stack?

    .venv/bin/python script/analysis/exact_stack_20261114/a01_recurrence.py                    # writes analysis/a01_recurrence.json
    .venv/bin/python script/analysis/exact_stack_20261114/a01_recurrence.py --standin C1 --out <dir>   # code test only

The targeted statistic of diag analysis a04_P1 (same code path), with A2 in C's place, judged on the full registry
at 16 slots, so the mask M is every axis at every slot:
- cells: the six A-peak cells other than c2, signs from A (es_common.PRIMARY); u_X = -sign(t_A) * o_X;
  w = 1/V with V from pre/t01_thresholds_n16.json (A and B only, fixed before any A2 data).
- D = sum w (u_A2 - u_B). Null: per prompt (216), exchange A2's and B's rate vectors with probability 1/2;
  10,000 draws, default_rng(20261113). p_one = (1 + #{D* >= D}) / 10,001.
- f-hat = D / sum w (u_A - u_B).
- conditional chance band: A and the cells fixed; B* and A2* Bernoulli at the smoothed pooled B + A2 rates
  ((yes + 2 pbar) / (n + 2)), 2,000 draws, default_rng(20261118); q95 of f*.
- verdict: 'repeats' iff p_one < 0.05 and f-hat > q95; otherwise 'no evidence of a repeat', reported with the
  one-sided 95% upper bound of f from 10,000 instruction-bootstrap draws (A, B, A2 jointly; default_rng(20261113)).
- c2 (google_deepmind x capability_ceiling, defer_to_users's cell) is read alone as secondary: z2 against the
  selection-inclusive chance draws of t01 at n = 16.
"""
import argparse
import json
from pathlib import Path

import numpy as np

import es_common as K

ap = argparse.ArgumentParser()
ap.add_argument("--standin", help="a verdict file key of es_common.FILES used in A2's place (code test only)")
ap.add_argument("--out", help="output directory for a code test")
a = ap.parse_args()
if bool(a.standin) != bool(a.out):
    raise SystemExit("--standin and --out go together")
NEW = a.standin or "A2"
OUT = Path(a.out) / "a01_recurrence.json" if a.out else K.OUTA / "a01_recurrence.json"
if OUT.exists():
    raise SystemExit(f"refusing to overwrite {OUT}")
if not a.standin:
    _g = K.ITEM / "gate/g01_gate_report.json"
    if not _g.exists() or not json.loads(_g.read_text()).get("pass"):
        raise SystemExit(f"{_g} missing or not passed: A2 is not read")
t01 = json.loads((K.PRE / "t01_thresholds_n16.json").read_text())
R16 = t01["real"]
VA, _ = K.load("A")
VB, _ = K.load("B")
VC, infoC = K.load(NEW)
# Every scored reply enters; the reading runs only when at least 99% of the 3,456 replies were scored
# (base A holds 3,452). The count is reported.
if infoC["keys"] < 0.99 * 216 * 16:
    raise SystemExit(f"{NEW}: only {infoC['keys']} scored replies of 3,456; the registered reading needs 99%")
cells = K.PRIMARY + [K.C2]
CI = [K.cell(c, x) for c, x, _ in cells]
SG = np.array([s for _, _, s in cells])
names = [f"{c} x {x}" for c, x, _ in cells]
assert names[:6] == R16["primary_cells"], (names, R16["primary_cells"])
Vprim = np.array(R16["V"]); Vc2 = R16["V_c2"]
w = 1 / Vprim
axes_needed = sorted({aj for _, aj in CI})
ax_pos = {aj: k for k, aj in enumerate(axes_needed)}


def per_instr_ovr(P):
    O = K.ovr(P)
    return np.stack([O[ci, :, ax_pos[aj]] for ci, aj in CI], axis=1)


def rates_sub(V):
    with np.errstate(invalid="ignore"):
        return np.nanmean(V[..., axes_needed], axis=2)


PA, PB, PC = rates_sub(VA), rates_sub(VB), rates_sub(VC)
I = {k: per_instr_ovr(P) for k, P in (("A", PA), ("B", PB), ("C", PC))}
with np.errstate(invalid="ignore"):
    o = {k: np.nanmean(v, axis=0) for k, v in I.items()}
u = {k: -SG * v for k, v in o.items()}
d = u["C"] - u["B"]
g = u["A"] - u["B"]
Dst = float(np.sum(w * d[:6]))
den = float(np.sum(w * g[:6]))
fhat = Dst / den
z_an = Dst / float(np.sqrt(np.sum(w ** 2 * Vprim)))

rng = np.random.default_rng(20261113)
NSW = 10000
Dn = np.empty(NSW); d2n = np.empty(NSW)
for k in range(NSW):
    sw = rng.random((6, K.NI)) < 0.5
    Xc = np.where(sw[..., None], PB, PC); Xb = np.where(sw[..., None], PC, PB)
    with np.errstate(invalid="ignore"):
        dd = -SG * (np.nanmean(per_instr_ovr(Xc), axis=0) - np.nanmean(per_instr_ovr(Xb), axis=0))
    Dn[k] = np.sum(w * dd[:6]); d2n[k] = dd[6]
p_one = float((1 + np.sum(Dn >= Dst - 1e-15)) / (1 + NSW))
p_two = float((1 + np.sum(np.abs(Dn) >= abs(Dst) - 1e-15)) / (1 + NSW))

yes = np.nansum(VB, axis=2) + np.nansum(VC, axis=2)
nn = np.isfinite(VB).sum(axis=2) + np.isfinite(VC).sum(axis=2)
pbar = yes.sum(axis=1, keepdims=True) / np.maximum(nn.sum(axis=1, keepdims=True), 1)
mu = (yes + 2 * pbar) / (nn + 2)
nanB, nanC = np.isnan(VB), np.isnan(VC)
r3 = np.random.default_rng(20261118)
fstar = []
for it in range(2000):
    VBs = (r3.random(VB.shape) < mu[:, :, None, :]).astype(float); VBs[nanB] = np.nan
    VCs = (r3.random(VB.shape) < mu[:, :, None, :]).astype(float); VCs[nanC] = np.nan
    with np.errstate(invalid="ignore"):
        oBs = np.nanmean(per_instr_ovr(rates_sub(VBs)), axis=0)
        oCs = np.nanmean(per_instr_ovr(rates_sub(VCs)), axis=0)
    fstar.append(float(np.sum(w * (-SG * (oCs - oBs))[:6]) / np.sum(w * (-SG * (o["A"] - oBs))[:6])))
fstar = np.array(fstar)
band = {"q95": float(np.quantile(fstar, .95)), "q05": float(np.quantile(fstar, .05)),
        "median": float(np.median(fstar)), "sd": float(fstar.std())}

rb = np.random.default_rng(20261113)
fb = []
for it in range(10000):
    idx = rb.integers(0, K.NI, K.NI)
    with np.errstate(invalid="ignore"):
        ob = {k: np.nanmean(v[idx], axis=0) for k, v in I.items()}
    ub = {k: -SG * v for k, v in ob.items()}
    fb.append(float(np.sum(w * (ub["C"] - ub["B"])[:6]) / np.sum(w * (ub["A"] - ub["B"])[:6])))
fb = np.array(fb)
boot = {"f_upper95_one_sided": float(np.quantile(fb, .95)),
        "f_ci95_two_sided": [float(np.quantile(fb, .025)), float(np.quantile(fb, .975))], "f_boot_sd": float(fb.std())}
verdict = "repeats" if (p_one < 0.05 and fhat > band["q95"]) else "no evidence of a repeat"

z2 = float(d[6] / np.sqrt(Vc2))
z2sim = np.load(K.PRE / "t01_sim_draws.npz")["z2"]
z2sim = z2sim[np.isfinite(z2sim)]
c2 = {"d2": float(d[6]), "z2": z2, "f2": float(d[6] / g[6]), "p_selection_inclusive_share": float(np.mean(z2sim >= z2)),
      "z2_if_full_recurrence": R16["z_if_f1_c2"], "c2_own_swap_p_one": float((1 + np.sum(d2n >= d[6] - 1e-15)) / (1 + NSW))}
per_cell = [{"cell": nm, "sign_tA": float(SG[k]), "weight_normalized": float(w[k] / w.sum()) if k < 6 else None,
             "o_A": float(o["A"][k]), "o_B": float(o["B"][k]), "o_A2": float(o["C"][k]),
             "d_uA2_minus_uB": float(d[k]), "g_uA_minus_uB": float(g[k]),
             "z": float(d[k] / np.sqrt(Vprim[k] if k < 6 else Vc2))} for k, nm in enumerate(names)]
out = {"new_draw": NEW, "new_draw_sha256": K.sha256_file(K.FILES[NEW]), "new_draw_rows": infoC, "n_slots": 16, "mask": "full registry",
       "weights_from": str(K.PRE / "t01_thresholds_n16.json"), "thresholds_sha256": K.sha256_file(K.PRE / "t01_thresholds_n16.json"),
       "primary": {"D": Dst, "den_f": den, "f_hat": fhat, "z_analytic": z_an,
                   "swap": {"p_one": p_one, "p_two": p_two, "null_mean": float(Dn.mean()), "null_sd": float(Dn.std())},
                   "conditional_band": band, "bootstrap": boot, "verdict": verdict,
                   "verdict_rule": "repeats iff p_one < 0.05 and f_hat > conditional q95",
                   "power_one_sided_05_at_n16": R16["power_one_sided_05"],
                   "power_one_sided_05_at_n16_is": "the analytic z test alone (t01); the registered verdict's own "
                                                   "power is power_registered_verdict",
                   "power_registered_verdict": (json.loads((K.PRE / "p01_power_registered.json").read_text())["results"]
                                                if (K.PRE / "p01_power_registered.json").exists() else None),
                   "upper95_expected_if_fhat_0": R16["upper95_one_sided_if_fhat_0"]},
       "c2_secondary": c2, "per_cell": per_cell}
print(K.dump(out, OUT))
print("VERDICT", verdict, "f_hat", round(fhat, 3), "p_one", p_one, "q95", round(band["q95"], 3),
      "upper95", round(boot["f_upper95_one_sided"], 3))
