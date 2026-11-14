"""T2, T5 and T7 from the stored draws.

Inputs
  exchangeability   : stats_r2/out/draws_swap_4000.npz (A/B reply swap with q = 1/2; draw 0 = real A, B)
  partial swap      : out/draws_pswap_lam{L}_{n}.npz, L in 0.15, 0.30, 0.48, 0.70 (engine3.py; n = 1,000)
  mixture bootstrap : out/draws_mboot_lam{L}_{n}.npz, L in 0.00, 0.30, 0.48, 0.70 (n = 1,000) and 1.00 (n = 2,000)
Observed values are draw 0 of the swap file (verified against the stored registered p).

Statistics (index 0 = pseudo-A, 1 = pseudo-B)
  mean S gap        mean over the family of S(T|A') - S(T|B')        (upper tail)
  sum z^2           sum over the family of (gap / sd0)^2, sd0 = the gap SD under the model's own lam = 0
                    (swap for pswap, mboot lam 0 for mboot)          (upper tail)
  eight-minus-synth difference of mean gaps, eight nulls minus two synthetic arms (upper tail)
  median level      median of the family's p against A'               (lower tail)
  count < 0.05      number of the family's p against A' below 0.05    (upper tail)
Families: eight nulls (six candidates), ten = eight + two synthetic arms (six candidates),
eleven = ten + contextual_optimism (five candidates, anthropic dropped).
T5: mboot lam = 1 is a bootstrap of A's own replies within each cell (pseudo-A) and of B's (pseudo-B).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "stats_r3" / "out"
SW = np.load(HERE.parent / "stats_r2" / "out" / "draws_swap_4000.npz")


def load(mode, lam):
    if mode == "swap":
        return SW
    fs = sorted(OUT.glob(f"draws_{mode}_lam{lam:.2f}_*.npz"), key=lambda f: int(f.stem.split("_")[-1]))
    return np.load(fs[-1]) if fs else None  # the largest run for this point


FAM = {"eight": ("6", slice(0, 8)), "ten": ("6", slice(0, 10)), "eleven5": ("5", slice(0, 11))}
obs = {}
for fam, (w, sl) in FAM.items():
    S, p = SW["S" + w][0], SW["p" + w][0]
    obs[fam] = {"mean_gap": float((S[0, sl] - S[1, sl]).mean()),
                "median_p": float(np.median(p[0, sl])), "count_lt_05": int((p[0, sl] < 0.05).sum())}
g6o = SW["S6"][0, 0] - SW["S6"][0, 1]
obs["eight_minus_synth"] = float(g6o[:8].mean() - g6o[8:].mean())


def stats_of(z, sd0):
    """Per-draw statistics for a draws file z; sd0 maps family -> per-target gap SD for z^2."""
    out = {}
    for fam, (w, sl) in FAM.items():
        S, p = z["S" + w], z["p" + w]
        G = S[:, 0, sl] - S[:, 1, sl]
        out[fam] = {"mean_gap": G.mean(1), "sum_z2": ((G / sd0[fam]) ** 2).sum(1),
                    "median_p": np.median(p[:, 0, sl], axis=1), "count_lt_05": (p[:, 0, sl] < 0.05).sum(1)}
    G6 = z["S6"][:, 0] - z["S6"][:, 1]
    out["eight_minus_synth"] = G6[:, :8].mean(1) - G6[:, 8:].mean(1)
    return out


def sd0_of(z, skip_first):
    sd = {}
    for fam, (w, sl) in FAM.items():
        G = z["S" + w][:, 0, sl] - z["S" + w][:, 1, sl]
        sd[fam] = (G[1:] if skip_first else G).std(0)
    return sd


sd_swap = sd0_of(SW, True)
obs_z2 = {fam: float((((SW["S" + w][0, 0, sl] - SW["S" + w][0, 1, sl]) / sd_swap[fam]) ** 2).sum()) for fam, (w, sl) in FAM.items()}
zb0 = load("mboot", 0.0)
sd_mb = sd0_of(zb0, False) if zb0 is not None else None
obs_z2_mb = ({fam: float((((SW["S" + w][0, 0, sl] - SW["S" + w][0, 1, sl]) / sd_mb[fam]) ** 2).sum()) for fam, (w, sl) in FAM.items()}
             if sd_mb is not None else None)


def tail(x, o, upper=True):
    x = np.asarray(x)
    return float((1 + np.sum(x >= o - 1e-12 if upper else x <= o + 1e-12)) / (1 + len(x)))


def summarize(mode, lam):
    z = load(mode, lam)
    if z is None:
        return None
    skip = mode == "swap"
    own = mode in ("swap", "pswap") or sd_mb is None  # mboot falls back to the swap SD until mboot lam 0 exists
    st = stats_of(z, sd_swap if own else sd_mb)
    oz2 = obs_z2 if own else obs_z2_mb
    sl = slice(1, None) if skip else slice(None)
    r = {"n": int(len(z["S6"]) - (1 if skip else 0)), "z2_standardized_by": "swap" if own else "mboot lam 0"}
    for fam in FAM:
        s = {k: v[sl] for k, v in st[fam].items()}
        r[fam] = {
            "mean_gap": {"obs": obs[fam]["mean_gap"], "mean": float(s["mean_gap"].mean()), "sd": float(s["mean_gap"].std()),
                         "q05_50_95": np.quantile(s["mean_gap"], [.05, .5, .95]).round(3).tolist(), "P_ge_obs": tail(s["mean_gap"], obs[fam]["mean_gap"])},
            "sum_z2": {"obs": oz2[fam], "mean": float(s["sum_z2"].mean()), "q05_50_95": np.quantile(s["sum_z2"], [.05, .5, .95]).round(2).tolist(),
                       "P_ge_obs": tail(s["sum_z2"], oz2[fam])},
            "median_p": {"obs": obs[fam]["median_p"], "median_of_median": float(np.median(s["median_p"])),
                         "q05_50_95": np.quantile(s["median_p"], [.05, .5, .95]).round(4).tolist(), "P_le_obs": tail(s["median_p"], obs[fam]["median_p"], False)},
            "count_lt_05": {"obs": obs[fam]["count_lt_05"], "mean": float(s["count_lt_05"].mean()), "P_ge_obs": tail(s["count_lt_05"], obs[fam]["count_lt_05"])},
        }
    e = st["eight_minus_synth"][sl]
    r["eight_minus_synth"] = {"obs": obs["eight_minus_synth"], "mean": float(e.mean()), "sd": float(e.std()), "P_ge_obs": tail(e, obs["eight_minus_synth"]),
                              "P_two_about_model_mean": float((1 + np.sum(np.abs(e - e.mean()) >= abs(obs["eight_minus_synth"] - e.mean()))) / (1 + len(e)))}
    return r


res = {"observed": obs, "observed_sum_z2_swap_sd": obs_z2, "observed_sum_z2_mboot0_sd": obs_z2_mb}
grid = [("swap", 0.0)] + [("pswap", L) for L in (0.15, 0.3, 0.48, 0.7)] + [("mboot", L) for L in (0.0, 0.15, 0.3, 0.48, 0.7, 1.0)]
for mode, lam in grid:
    r = summarize(mode, lam)
    if r is None:
        print(f"{mode} lam={lam}: missing")
        continue
    res[f"{mode} {lam}"] = r
    e, t, f = r["eight"], r["ten"], r["eleven5"]
    print(f"{mode:5s} lam={lam:4.2f} n={r['n']:4d} | eight: gap {e['mean_gap']['mean']:+.3f}±{e['mean_gap']['sd']:.3f} P {e['mean_gap']['P_ge_obs']:.4f}"
          f"  z2 P {e['sum_z2']['P_ge_obs']:.4f}  median {e['median_p']['median_of_median']:.3f} P(<=obs) {e['median_p']['P_le_obs']:.4f}  cnt P {e['count_lt_05']['P_ge_obs']:.3f}"
          f" | ten: gap P {t['mean_gap']['P_ge_obs']:.4f} z2 {t['sum_z2']['mean']:.1f} P {t['sum_z2']['P_ge_obs']:.4f} median P {t['median_p']['P_le_obs']:.4f}"
          f" | eleven5: gap P {f['mean_gap']['P_ge_obs']:.4f} z2 P {f['sum_z2']['P_ge_obs']:.4f} median P {f['median_p']['P_le_obs']:.4f}"
          f" | 8-2: {r['eight_minus_synth']['mean']:+.3f}±{r['eight_minus_synth']['sd']:.3f} P {r['eight_minus_synth']['P_ge_obs']:.4f}", flush=True)

# T5: bootstrap of A's own replies (pseudo-A of mboot lam 1) and of B's (pseudo-B)
zb = load("mboot", 1.0)
if zb is not None:
    names6 = [str(x) for x in zb["targets6"]]
    pA8 = zb["p6"][:, 0, :8]
    pB = zb["p6"][:, 1, :]
    med = np.median(pA8, 1)
    t5 = {"n": int(len(pA8)),
          "A_boot": {"P_median_le_0.0557": float(np.mean(med <= 0.0557)), "median_of_median": float(np.median(med)),
                     "median_q05_q95": np.quantile(med, [.05, .95]).round(4).tolist(),
                     "per_test_P_p_lt_0.05": dict(zip(names6[:8], np.mean(pA8 < 0.05, 0).round(4).tolist())),
                     "per_test_median_p": dict(zip(names6[:8], np.median(pA8, 0).round(4).tolist())),
                     "per_test_mean_S": dict(zip(names6[:8], zb["S6"][:, 0, :8].mean(0).round(3).tolist())),
                     "observed_S": dict(zip(names6[:8], SW["S6"][0, 0, :8].round(3).tolist())),
                     "P_ge3_below_0.05": float(np.mean((pA8 < 0.05).sum(1) >= 3))},
          "B_boot": {"median_of_eight_median": float(np.median(np.median(pB[:, :8], 1))),
                     "P_eight_median_le_0.4146": float(np.mean(np.median(pB[:, :8], 1) <= 0.4146)),
                     "sd_emotional_bond_P_p_le_0.0542": float(np.mean(pB[:, 9] <= 0.0542)),
                     "sd_ai_welfare_poisoning_P_p_le_0.1785": float(np.mean(pB[:, 8] <= 0.1785)),
                     "synthetic_median_p": np.median(pB[:, 8:], 0).round(4).tolist(),
                     "synthetic_mean_S": zb["S6"][:, 1, 8:].mean(0).round(3).tolist(),
                     "synthetic_observed_S": SW["S6"][0, 1, 8:].round(3).tolist(),
                     "per_test_P_p_lt_0.05": dict(zip(names6, np.mean(pB < 0.05, 0).round(4).tolist()))},
          "A_boot_synthetic": {"median_p": np.median(zb["p6"][:, 0, 8:], 0).round(4).tolist(),
                               "P_sd_eb_le_0.5827": float(np.mean(zb["p6"][:, 0, 9] <= 0.5827))}}
    res["T5_bootstrap"] = t5
    print("T5", json.dumps(t5, indent=1))
json.dump(res, open(HERE / "k13_t2_t5_t7_copy.json", "w"), indent=1)
