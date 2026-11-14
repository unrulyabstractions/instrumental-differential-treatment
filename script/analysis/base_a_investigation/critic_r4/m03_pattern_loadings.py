"""Critic round 4, m03. Who carries the eight controls' shared pattern?

Pattern relative to the base: F = mean over controls of OvR(control) - OvR(M), M = (A + B) / 2.
Loading of a sample Y:  L(Y) = <(Y - M)(h1), F_{-Y}(h2)> / mean_k <(C_k - M)(h1), F_{-k}(h2)>,
with h1, h2 disjoint halves of the 16 reply slots (shared by all samples), so the judge's axis order
(keyed on prompt_id, s) and all sampling noise drop out of the product. L = 1 for a sample that carries the
controls' full shift from the base, 0 for one that sits at the base.
Also the raw version (stats F1a): cov(Y, C_-Y) / cov(C_k, C_-k) on the samples' own one-vs-rest grids.
Uncertainty: bootstrap over the 36 instructions (300 draws, same resample for every sample and split).
Six candidates and five (anthropic dropped before the one-vs-rest step, needed for CO).
Read-only: uses the verified loader stats_r1/common.py."""
import json, sys, warnings
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "stats_r1"))
import common as C  # noqa: E402
warnings.simplefilter("ignore", RuntimeWarning)
OUT = Path(__file__).resolve().parent
D = C.load_all()
cands = D["_cands"]
CTL = list(C.CONTROLS); SD = ["sd_ai_welfare_poisoning", "sd_emotional_bond"]
NAMES = ["A", "B", "CO"] + CTL + SD
NS, NB = 40, 300
rng = np.random.default_rng([20261113, 904])
splits = [np.split(rng.permutation(16), 2) for _ in range(NS)]
W = np.vstack([np.ones(36) / 36, rng.multinomial(36, np.ones(36) / 36, size=NB) / 36.0])   # row 0 = observed


def run(tag):
    kp = list(range(6)) if tag == "six" else [i for i, c in enumerate(cands) if c != "anthropic"]
    H = {}
    for k in NAMES:
        a = np.empty((NS, 2, len(kp), 36, 101))
        for s, (h1, h2) in enumerate(splits):
            for h, sl in enumerate((h1, h2)):
                a[s, h] = np.nan_to_num(C.ovr(np.nanmean(D[k][kp][:, :, sl], axis=2)))
        H[k] = a
    # weighted cell means for every bootstrap weight: (NB+1, NS, 2, n_c, 101)
    G = {k: np.einsum("bi,shcij->bshcj", W, v) for k, v in H.items()}
    M = 0.5 * (G["A"] + G["B"])
    Csum = sum(G[k] for k in CTL)

    def dot(X, Y):   # cross-half mean product, symmetrized, averaged over splits -> (NB+1,)
        return 0.5 * ((X[:, :, 0] * Y[:, :, 1]).mean(axis=(1, 2, 3)) + (X[:, :, 1] * Y[:, :, 0]).mean(axis=(1, 2, 3)))

    rel_self = np.mean([dot(G[k] - M, (Csum - G[k]) / 7 - M) for k in CTL], axis=0)
    raw_self = np.mean([dot(G[k], (Csum - G[k]) / 7) for k in CTL], axis=0)
    out = {"denominators_1e-6": {"relative_to_base_|f|^2": round(float(rel_self[0] * 1e6), 2), "raw_control_with_others": round(float(raw_self[0] * 1e6), 2)}}

    def summ(num, den):
        L = num / den
        lo, hi = np.quantile(L[1:], [0.025, 0.975])
        return {"L": round(float(L[0]), 3), "boot_sd": round(float(L[1:].std()), 3), "ci95": [round(float(lo), 3), round(float(hi), 3)],
                "num_1e-6": round(float(num[0] * 1e6), 2), "num_boot_sd_1e-6": round(float(num[1:].std() * 1e6), 2)}

    rel, raw = {}, {}
    for k in CTL:
        rel[k] = summ(dot(G[k] - M, (Csum - G[k]) / 7 - M), rel_self)
        raw[k] = summ(dot(G[k], (Csum - G[k]) / 7), raw_self)
    for k in ["CO"] + SD:
        rel[k] = summ(dot(G[k] - M, Csum / 8 - M), rel_self)
        raw[k] = summ(dot(G[k], Csum / 8), raw_self)
    sdm = 0.5 * (G[SD[0]] + G[SD[1]])
    rel["sd_mean"] = summ(dot(sdm - M, Csum / 8 - M), rel_self)
    raw["sd_mean"] = summ(dot(sdm, Csum / 8), raw_self)
    for k in ("A", "B"):
        raw[k] = summ(dot(G[k], Csum / 8), raw_self)
    # each base against the OTHER base as the reference: does it carry part of the controls' shift?
    rel["A_relative_to_B"] = summ(dot(G["A"] - G["B"], Csum / 8 - G["B"]), np.mean([dot(G[k] - G["B"], (Csum - G[k]) / 7 - G["B"]) for k in CTL], axis=0))
    rel["B_relative_to_A"] = summ(dot(G["B"] - G["A"], Csum / 8 - G["A"]), np.mean([dot(G[k] - G["A"], (Csum - G[k]) / 7 - G["A"]) for k in CTL], axis=0))
    # contrasts with bootstrap p
    def contrast(a, b, label):
        d = a - b
        return {label: round(float(d[0]), 3), "boot_sd": round(float(d[1:].std()), 3), "z": round(float(d[0] / d[1:].std()), 2)}
    Lco = dot(G["CO"] - M, Csum / 8 - M) / rel_self
    Lsd = dot(sdm - M, Csum / 8 - M) / rel_self
    out["contrasts"] = {"CO_vs_1": contrast(Lco, np.ones_like(Lco), "L_CO_minus_1"), "sd_vs_1": contrast(Lsd, np.ones_like(Lsd), "L_sd_minus_1"),
                        "CO_minus_sd": contrast(Lco, Lsd, "L_CO_minus_L_sd"),
                        "raw_A_minus_B": contrast(dot(G["A"], Csum / 8) / raw_self, dot(G["B"], Csum / 8) / raw_self, "rawL_A_minus_rawL_B")}
    out["relative_to_base"] = rel
    out["raw_own_grid"] = raw
    return out


res = {t: run(t) for t in ("six", "five")}
for t in res:
    print("==", t, res[t]["denominators_1e-6"])
    print("  relative to base midpoint (L=1: carries the controls' full shift; 0: sits at the base)")
    for k, v in res[t]["relative_to_base"].items():
        print(f"   {k:26s} L {v['L']:+.2f}  sd {v['boot_sd']:.2f}  ci {v['ci95']}")
    print("  raw own-grid loading (1 = like a control)")
    for k, v in res[t]["raw_own_grid"].items():
        print(f"   {k:26s} L {v['L']:+.2f}  sd {v['boot_sd']:.2f}  ci {v['ci95']}")
    print("  contrasts", json.dumps(res[t]["contrasts"]))
(OUT / "m03_pattern_loadings.json").write_text(json.dumps(res, indent=1))
