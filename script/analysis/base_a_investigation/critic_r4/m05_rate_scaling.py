"""Critic round 4, m05. Is the controls' shared pattern relative to the base a rate-scaling effect?

Hypothesis: a fine-tune changes how often an axis fires for every candidate by a common factor rho_j (a
candidate-free change), and the base model already has some candidate structure b_cj on that axis. The
registered excess is additive (difference of one-vs-rest gaps), so it then reads (rho_j - 1) * b_cj as
candidate-dependent structure.
  F   = OvR(controls' mean) - OvR(M), M = (A + B) / 2       (the shared pattern relative to the base)
  P   = (rho_j - 1) * OvR(M)                                 (scaling prediction), rho_j = axis rate of controls / bases
Cross-half products (disjoint halves of the 16 slots) keep every product free of shared noise:
  slope = <F(h1), P(h2)> / <P(h1), P(h2)>,  explained = <F(h1), P(h2)> / <F(h1), F(h2)>.
Uncertainty: bootstrap over the 36 instructions. Also the axis-rate ratios themselves, and the same analysis
for the raw amplification model P0 = OvR(M) (one global factor)."""
import json, sys, warnings
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "stats_r1"))
import common as C  # noqa: E402
warnings.simplefilter("ignore", RuntimeWarning)
OUT = Path(__file__).resolve().parent
D = C.load_all(); cands = D["_cands"]
CTL = list(C.CONTROLS)
NS, NB = 40, 400
rng = np.random.default_rng([20261113, 905])
splits = [np.split(rng.permutation(16), 2) for _ in range(NS)]
W = np.vstack([np.ones(36) / 36, rng.multinomial(36, np.ones(36) / 36, size=NB) / 36.0])
rate = {k: np.nanmean(D[k], axis=(0, 1, 2)) for k in ["A", "B", "CO", "sd_ai_welfare_poisoning", "sd_emotional_bond"] + CTL}
rC = np.mean([rate[k] for k in CTL], axis=0); rM = 0.5 * (rate["A"] + rate["B"])
ok = rM > 0.01            # axes that fire in the base at least 1% of the time; elsewhere the ratio is undefined
rho = np.where(ok, rC / np.where(ok, rM, 1.0), 1.0)
res = {"axis_rate": {"bases_mean": round(float(rM.mean()), 4), "controls_mean": round(float(rC.mean()), 4),
                     "rho_quantiles_5_25_50_75_95": np.round(np.quantile(rho, [0.05, 0.25, 0.5, 0.75, 0.95]), 3).tolist(),
                     "share_axes_rho_above_1.5": round(float((rho > 1.5).mean()), 3), "share_axes_rho_below_0.67": round(float((rho < 0.67).mean()), 3),
                     "corr_log_rho_between_controls_mean_pairwise": None}}
lr = np.array([np.log(np.maximum(rate[k][ok], 1e-4) / rM[ok]) for k in CTL])
cc = np.corrcoef(lr); res["axis_rate"]["corr_log_rho_between_controls_mean_pairwise"] = round(float(cc[np.triu_indices(8, 1)].mean()), 3)
res["axis_rate"]["rho_AB"] = np.round(np.quantile(rate["A"][ok] / rate["B"][ok], [0.05, 0.5, 0.95]), 3).tolist()
res["axis_rate"]["n_axes_used"] = int(ok.sum())


def run(tag):
    kp = list(range(6)) if tag == "six" else [i for i, c in enumerate(cands) if c != "anthropic"]
    def halves(k):
        a = np.empty((NS, 2, len(kp), 36, 101))
        for s, (h1, h2) in enumerate(splits):
            for h, sl in enumerate((h1, h2)):
                a[s, h] = np.nan_to_num(C.ovr(np.nanmean(D[k][kp][:, :, sl], axis=2)))
        return np.einsum("bi,shcij->bshcj", W, a)
    G = {k: halves(k) for k in ["A", "B"] + CTL}
    M = 0.5 * (G["A"] + G["B"]); Cm = sum(G[k] for k in CTL) / 8
    F = Cm - M
    def dot(X, Y):
        return 0.5 * ((X[:, :, 0] * Y[:, :, 1]).mean(axis=(1, 2, 3)) + (X[:, :, 1] * Y[:, :, 0]).mean(axis=(1, 2, 3)))
    out = {}
    for name, P in (("rate_scaling_(rho-1)*OvR(M)", (rho - 1) * M), ("global_amplification_OvR(M)", M)):
        fp, pp, ff = dot(F, P), dot(P, P), dot(F, F)
        def s(x): return {"obs_1e-6": round(float(x[0] * 1e6), 2), "boot_sd_1e-6": round(float(x[1:].std() * 1e6), 2), "z": round(float(x[0] / x[1:].std()), 2)}
        out[name] = {"<F,P>": s(fp), "<P,P>": s(pp), "<F,F>": s(ff),
                     "slope_F_on_P": round(float(fp[0] / pp[0]), 3) if abs(pp[0]) > 1e-12 else None,
                     "corr2_<F,P>^2/(<P,P><F,F>)": round(float(fp[0] ** 2 / (pp[0] * ff[0])), 3) if pp[0] * ff[0] > 0 else None,
                     "boot_P(<F,P> <= 0)": round(float((fp[1:] <= 0).mean()), 3)}
    # the controls' own grid: is it rho * base grid?  <C, rho*M> against <C, C> and <rho*M, rho*M>
    cp, pp2, c2 = dot(Cm, rho * M), dot(rho * M, rho * M), dot(Cm, Cm)
    out["controls_grid_vs_rho_times_base_grid"] = {"<C,rhoM>_1e-6": round(float(cp[0] * 1e6), 2), "boot_sd": round(float(cp[1:].std() * 1e6), 2),
                                                    "<rhoM,rhoM>_1e-6": round(float(pp2[0] * 1e6), 2), "<C,C>_1e-6": round(float(c2[0] * 1e6), 2),
                                                    "<C,M>_1e-6": round(float(dot(Cm, M)[0] * 1e6), 2), "<M,M>_1e-6": round(float(dot(M, M)[0] * 1e6), 2)}
    return out


for t in ("six", "five"):
    res[t] = run(t)
print(json.dumps(res, indent=1))
(OUT / "m05_rate_scaling.json").write_text(json.dumps(res, indent=1))
