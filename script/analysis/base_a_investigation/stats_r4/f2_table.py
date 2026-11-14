"""F2. One final surprise table across null designs and systematic-share models, six and five candidates side by side.

Inputs (targets always the real fine-tunes; index 0 = pseudo-A, 1 = pseudo-B; observed = real A, B):
  reply swap   stats_r2/out/draws_swap_4000.npz (draw 0 = identity, dropped from the null)
  prompt swap  out/draws_prompt_1000.npz        (exact p; draw 0 = identity, dropped)
  instr swap   out/draws_instructionS_2000.npz   (S only; draw 0 identity, dropped)
  anti         out/draws_antiS_2000.npz (S only) and out/draws_anti_500.npz (exact p): fresh-noise bootstrap with
               base noise matched to a real pair (see f_engine.py)
  mboot lam    stats_r3/out/draws_mboot_lam{0.00,0.30,0.48,0.70,1.00}: fresh-noise mixture bootstrap, amplitude share lam
  pswap lam    stats_r3/out/draws_pswap_lam{0.15,0.30,0.48,0.70}: partial swap, amplitude share lam (lam 0 = reply swap)
Rows (upper tail unless noted):
  gap8      mean over the eight nulls of S(T|A') - S(T|B')
  z2_10     sum over the ten (eight + two synthetic) of (gap / sd0)^2, six candidates
  z2_9      the same without defer_to_users
  z2_11     sum over eleven (adds contextual_optimism), five candidates
  med8      median of the eight p against A' (lower tail; designs with exact p only)
  e_minus_s mean gap of the eight minus mean gap of the two synthetic arms
sd0 for z^2 is the per-target gap SD under the design's own zero-share version: the reply swap for pswap, mboot
lam 0 for mboot, and each swap design and anti for themselves.
Also: why the reply swap and mboot lam 0 differ. Per-target gap SD and mean S level under each design, and the base
noise each design carries, measured on the data: E(pseudo-A - M)^2 / E(A - M)^2 per cell, M = (A + B) / 2.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r4c as Q  # noqa: E402

R2, R3, R4 = Q.ROOT / "stats_r2" / "out", Q.ROOT / "stats_r3" / "out", Q.OUT
SW = np.load(R2 / "draws_swap_4000.npz")
T6, T5 = list(Q.TEN), list(Q.ELEVEN)
DEFER = T6.index("defer_to_users")


def std_form(z):
    """-> dict world -> (S (n, 2, m), p (n, 2, m) or None)."""
    if "S6" in z.files:
        return {"six": (z["S6"], z["p6"]), "five": (z["S5"], z["p5"])}
    out = {}
    for w in ("six", "five"):
        S = np.stack([z[f"S_{w}_A2"], z[f"S_{w}_B2"]], axis=1)
        p = np.stack([z[f"p_{w}_A2"], z[f"p_{w}_B2"]], axis=1)
        out[w] = (S, None if np.isnan(p).all() else p)
    return out


def load(path, drop0=False):
    if not Path(path).exists():
        return None
    f = std_form(np.load(path))
    if drop0:
        f = {w: (S[1:], None if p is None else p[1:]) for w, (S, p) in f.items()}
    return f


OBS = {w: (SW[f"S{n}"][0], SW[f"p{n}"][0]) for w, n in (("six", "6"), ("five", "5"))}
designs = {"reply swap": load(R2 / "draws_swap_4000.npz", True), "prompt swap": load(R4 / "draws_prompt_1000.npz", True),
           "instruction swap": load(R4 / "draws_instructionS_2000.npz", True),
           "anti (fresh noise, matched)": load(R4 / "draws_antiS_2000.npz"), "anti exact p": load(R4 / "draws_anti_500.npz")}
for lam in ("0.00", "0.30", "0.48", "0.70", "1.00"):
    f = sorted(R3.glob(f"draws_mboot_lam{lam}_*.npz"))
    designs[f"mboot {lam}"] = load(f[-1]) if f else None
for lam in ("0.15", "0.30", "0.48", "0.70"):
    f = sorted(R3.glob(f"draws_pswap_lam{lam}_*.npz"))
    designs[f"pswap {lam}"] = load(f[-1]) if f else None
sd_ref = {"pswap": "reply swap", "mboot": "mboot 0.00"}


def gaps(S, w):
    return S[:, 0] - S[:, 1]


def sd0(name, w):
    ref = sd_ref.get(name.split()[0], name)
    if name.startswith("anti"):
        ref = "anti (fresh noise, matched)"
    return gaps(designs[ref][w][0], w).std(0)


def stats_for(name):
    dsg = designs[name]
    if dsg is None:
        return None
    out = {}
    for w in ("six", "five"):
        S, p = dsg[w]
        G = gaps(S, w)
        go = OBS[w][0][0] - OBS[w][0][1]
        sd = sd0(name, w)
        r = {"n": int(len(S))}
        e8 = G[:, :8].mean(1)
        r["gap8"] = {"obs": round(float(go[:8].mean()), 4), "null_mean": round(float(e8.mean()), 4), "null_sd": round(float(e8.std()), 4),
                     "P": Q.tail_ge(e8, go[:8].mean())}
        m = 10 if w == "six" else 11
        zz = ((G[:, :m] / sd[:m]) ** 2).sum(1)
        zo = float(((go[:m] / sd[:m]) ** 2).sum())
        r["z2_all"] = {"targets": m, "obs": round(zo, 3), "null_mean": round(float(zz.mean()), 3), "P": Q.tail_ge(zz, zo)}
        keep = [q for q in range(m) if q != DEFER]
        zz9 = ((G[:, keep] / sd[keep]) ** 2).sum(1)
        zo9 = float(((go[keep] / sd[keep]) ** 2).sum())
        r["z2_without_defer"] = {"obs": round(zo9, 3), "P": Q.tail_ge(zz9, zo9)}
        es = G[:, :8].mean(1) - G[:, 8:10].mean(1)
        eo = float(go[:8].mean() - go[8:10].mean())
        r["eight_minus_synth"] = {"obs": round(eo, 4), "null_mean": round(float(es.mean()), 4), "P": Q.tail_ge(es, eo)}
        if p is not None:
            med = np.median(p[:, 0, :8], axis=1)
            mo = float(np.median(OBS[w][1][0][:8]))
            r["med8"] = {"obs": round(mo, 4), "median_of_null_median": round(float(np.median(med)), 4), "P_le": Q.tail_le(med, mo),
                         "count_lt_05_P_ge": Q.tail_ge((p[:, 0, :8] < 0.05).sum(1), int((OBS[w][1][0][:8] < 0.05).sum()))}
        r["per_target_gap_sd"] = dict(zip(T6 if w == "six" else T5, np.round(G.std(0), 3).tolist()))
        r["per_target_mean_S_pseudoA"] = dict(zip(T6 if w == "six" else T5, np.round(S[:, 0].mean(0), 3).tolist()))
        out[w] = r
    return out


table = {k: stats_for(k) for k in designs}
table = {k: v for k, v in table.items() if v is not None}
# merge anti exact-p median into the anti row
if "anti exact p" in table and "anti (fresh noise, matched)" in table:
    for w in ("six", "five"):
        table["anti (fresh noise, matched)"][w]["med8"] = table["anti exact p"][w].get("med8")

# base-noise units carried by each design, from the reply data (per cell, averaged over cells)
d = Q.data()
RA, RB = d["R"]["A"], d["R"]["B"]
PA, PB = Q.rates(RA), Q.rates(RB)
M = 0.5 * (PA + PB)
real = np.nanmean((PA - M) ** 2)
pool = np.concatenate([RA, RB], axis=2)
nA = (~np.isnan(pool).all(-1)).sum(-1)
vpool = np.nanvar(pool, axis=2)                              # population variance of the pooled replies per cell, axis
units = {"E(A-M)^2 real (= swap)": float(real),
         "mboot lam 0: E(pseudo-A - M)^2 ~ v_pool / 16": float(np.nanmean(vpool / 16.0)),
         "anti: E(e)^2 ~ v_pool / 32": float(np.nanmean(vpool / 32.0))}
units["mboot_over_real"] = units["mboot lam 0: E(pseudo-A - M)^2 ~ v_pool / 16"] / real
units["anti_over_real"] = units["anti: E(e)^2 ~ v_pool / 32"] / real
units["base_noise_units_relative_to_truth"] = {
    "real or swap": 1.0,
    "mboot lam 0": round(0.5 + 0.5 * units["mboot_over_real"], 3),
    "anti": round(0.5 + 0.5 * units["anti_over_real"], 3),
    "note": "base noise around the truth = noise of M (half a unit) + deviation from M; E(A-M)^2 is half a unit"}
table["_base_noise_units"] = units

print(f"{'design':30s} | {'gap8 P':>8s} | {'z2 all P':>8s} | {'z2 -defer':>9s} | {'8-synth P':>9s} | {'med8 P':>8s} | world")
for k, v in table.items():
    if k.startswith("_") or k == "anti exact p":
        continue
    for w in ("six", "five"):
        r = v[w]
        med = r.get("med8")
        print(f"{k:30s} | {r['gap8']['P']:8.4f} | {r['z2_all']['P']:8.4f} | {r['z2_without_defer']['P']:9.4f} | {r['eight_minus_synth']['P']:9.4f} | "
              f"{(med['P_le'] if med else float('nan')):8.4f} | {w} (n {r['n']}, gap8 sd {r['gap8']['null_sd']:.3f}, z2 null mean {r['z2_all']['null_mean']:.2f})")
print(json.dumps(units, indent=1))
for k in ("reply swap", "prompt swap", "anti (fresh noise, matched)", "mboot 0.00"):
    if k in table:
        print(k, "gap SD", table[k]["six"]["per_target_gap_sd"])
        print(k, "mean S vs pseudo-A", table[k]["six"]["per_target_mean_S_pseudoA"])
(Q.OUT / "f2_table.json").write_text(json.dumps(table, indent=1))
