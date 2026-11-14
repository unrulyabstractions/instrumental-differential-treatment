"""U2 follow-up: is base A farther than base B from the fine-tunes over the WHOLE grid, not only at the peak?

u2_artifact_hunt (a) found mean t^2 over all 606 cells higher against A than against B for most of the ten
null fine-tunes, including both synthetic-document arms, whose max statistic leans the other way.
Null: A and B verdict rows swapped at each (candidate, instruction, s) with probability 1/2 (targets fixed),
2,000 draws plus the identity. Statistics per target: mean t^2 (T|A') - mean t^2 (T|B'); the per-cell
correlation over instructions of OvR(T) with OvR(base), A' minus B'. Summaries over the eight nulls, the two
synthetic arms, all ten; one- and two-sided p; six and five candidates.
Also: the same for CO (five candidates) and the B|A pairing has no analogue (it is the swap itself).
"""
from __future__ import annotations

import numpy as np
import warnings
from r3common import C, NULLS, SD, dump

warnings.simplefilter("ignore")
D = C.load_all(); cands = D["_cands"]
TEN = NULLS + SD
NDRAW = 2000


def tg2(d):
    m = np.sum(~np.isnan(d), axis=-2)
    mean = np.nanmean(d, axis=-2); sd = np.nanstd(d, axis=-2, ddof=1)
    t = mean / (sd / np.sqrt(np.maximum(m, 1)))
    t = np.where(np.isfinite(t), t, np.nan)
    return np.nanmean(t ** 2)


def rcorr(ot, ob):
    xt = ot - np.nanmean(ot, 1, keepdims=True); xb = ob - np.nanmean(ob, 1, keepdims=True)
    r = np.nanmean(xt * xb, 1) / np.sqrt(np.nanmean(xt ** 2, 1) * np.nanmean(xb ** 2, 1))
    return np.nanmean(r[np.isfinite(r)])


def stats_for(keep):
    sel = (lambda R: R[keep]) if keep is not None else (lambda R: R)
    RA, RB = sel(D["A"]), sel(D["B"])
    OT = {k: C.ovr(C.rates(sel(D[k]))) for k in TEN + ["CO"]}
    rng = np.random.default_rng(20261113)
    out_t2 = np.empty((NDRAW + 1, len(TEN) + 1)); out_r = np.empty((NDRAW + 1, len(TEN) + 1))
    for q in range(NDRAW + 1):
        if q == 0:
            a, b = RA, RB
        else:
            m = rng.random(RA.shape[:3]) < 0.5
            a = np.where(m[..., None], RB, RA); b = np.where(m[..., None], RA, RB)
        oa, ob = C.ovr(C.rates(a)), C.ovr(C.rates(b))
        for k, tg in enumerate(TEN + ["CO"]):
            out_t2[q, k] = tg2(OT[tg] - oa) - tg2(OT[tg] - ob)
            out_r[q, k] = rcorr(OT[tg], oa) - rcorr(OT[tg], ob)
    return out_t2, out_r


def summarize(x, label):
    obs, null = x[0], x[1:]
    sd = null.std(0)
    z = obs / sd
    res = {"per_target_gap": dict(zip(TEN + ["CO"], obs.round(5).tolist())), "per_target_z": dict(zip(TEN + ["CO"], z.round(3).tolist()))}
    for name, idx in (("eight", list(range(8))), ("synth", [8, 9]), ("ten", list(range(10)))):
        m_obs = obs[idx].mean(); m_null = null[:, idx].mean(1)
        s_obs = (z[idx] ** 2).sum(); s_null = ((null[:, idx] / sd[idx]) ** 2).sum(1)
        res[name] = {"mean_gap": float(m_obs), "null_sd": float(m_null.std()), "z": float(m_obs / m_null.std()),
                     "p_upper": float((1 + (m_null >= m_obs).sum()) / (1 + len(m_null))),
                     "p_two": float((1 + (np.abs(m_null) >= abs(m_obs)).sum()) / (1 + len(m_null))),
                     "sum_z2": float(s_obs), "sum_z2_p": float((1 + (s_null >= s_obs).sum()) / (1 + len(s_null))),
                     "n_positive": int((obs[idx] > 0).sum())}
    print(f"  {label}: per-target gap " + " ".join(f"{k[:10]} {v:+.3f}(z{zz:+.1f})" for (k, v), zz in zip(res['per_target_gap'].items(), z)))
    for name in ("eight", "synth", "ten"):
        r = res[name]
        print(f"     {name:5s} mean gap {r['mean_gap']:+.4f} null sd {r['null_sd']:.4f} z {r['z']:+.2f} p_upper {r['p_upper']:.4f} p_two {r['p_two']:.4f} | sum z^2 {r['sum_z2']:.1f} p {r['sum_z2_p']:.4f} | positive {r['n_positive']}/{len(idx) if False else (8 if name=='eight' else 2 if name=='synth' else 10)}")
    return res


out = {}
for lab, keep in (("six", None), ("five", [i for i, c in enumerate(cands) if c != "anthropic"])):
    print(f"== {lab} candidates")
    t2, r = stats_for(keep)
    out[lab] = {"mean_t2_gap_A_minus_B": summarize(t2, "mean t^2 (T|A) - (T|B)"),
                "r_gap_A_minus_B": summarize(r, "r(T,A) - r(T,B)")}
dump(out, "u2c_grid_gap_swap.json")
