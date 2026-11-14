"""S4d. Does base A's deviation point against the targets' own structure (alignment), beyond chance?

For a base pair (A, B) and fine-tune k, on per-cell means over instructions of one-vs-rest gaps:
  dev  = mean(OvR_A - OvR_B)                  (A's deviation relative to B)
  str_k = mean(OvR_k - (OvR_A + OvR_B) / 2)   (target k's structure relative to the base midpoint)
Under exchangeable A and B the noise covariance of dev and str_k is -(var A - var B)/2, about 0.
  r_k   = corr over the 606 (candidate, axis) cells of dev and str_k
  r_c   = corr of dev with the eight nulls' mean structure (common fine-tune direction)
  align = sum over the eight tests of corr(dev, str_k) (negative: A deviates against the targets)
Also the same with t-values per cell instead of means. Swap null: A and B replies trade places at each
slot (4,000 swaps). Ten fine-tunes and CO (five candidates) are reported beside the eight.
"""
import json
import warnings

import numpy as np

import fast as F
from fast import C

D = F.load()
RA, RB = D["A"], D["B"]
both = (~np.isnan(RA).all(3) & ~np.isnan(RB).all(3))
P = {k: C.rates(v) for k, v in D.items() if not k.startswith("_")}
O = {k: C.ovr(v) for k, v in P.items()}
names = F.TEN
Ot = np.stack([O[k] for k in names])  # (10, 6, 36, 101)


def tg(d):
    t = C.tgrid_fast(d)[0]
    return np.where(np.isfinite(t), t, 0.0)


def stats(oa, ob):
    dev_m = (oa - ob).mean(1).ravel()
    dev_t = tg(oa - ob).ravel()
    mid = (oa + ob) / 2
    out = {}
    sm = (Ot - mid[None]).mean(2).reshape(len(names), -1)
    st = tg(Ot - mid[None]).reshape(len(names), -1)
    out["r_mean"] = np.array([np.corrcoef(dev_m, s)[0, 1] for s in sm])
    out["r_t"] = np.array([np.corrcoef(dev_t, s)[0, 1] for s in st])
    cm = sm[:8].mean(0)
    out["rc_mean"] = np.corrcoef(dev_m, cm)[0, 1]
    ct = tg((Ot[:8] - mid[None]).mean(0)).ravel()
    out["rc_t"] = np.corrcoef(dev_t, ct)[0, 1]
    return out


obs = stats(O["A"], O["B"])
rng = np.random.default_rng(31)
NS = 4000
nul = []
for _ in range(NS):
    m = ((rng.random(RA.shape[:3]) < 0.5) & both)[..., None]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        xa = C.ovr(np.nanmean(np.where(m, RB, RA), 2)); xb = C.ovr(np.nanmean(np.where(m, RA, RB), 2))
    nul.append(stats(xa, xb))
res = {"targets": names}
for key in ("r_mean", "r_t"):
    o = obs[key]; n = np.array([x[key] for x in nul])
    s8o, s8n = o[:8].sum(), n[:, :8].sum(1)
    s10o, s10n = o.sum(), n.sum(1)
    res[key] = {"obs": o.tolist(), "null_sd": n.std(0).tolist(), "z": ((o - n.mean(0)) / n.std(0)).tolist(),
                "sum8": float(s8o), "sum8_null_sd": float(s8n.std()), "sum8_p_lower": float((1 + np.sum(s8n <= s8o)) / (1 + NS)),
                "sum10": float(s10o), "sum10_p_lower": float((1 + np.sum(s10n <= s10o)) / (1 + NS)),
                "null_corr_between_tests_mean": float((np.corrcoef(n[:, :8].T).sum() - 8) / 56)}
    print(key, "per target z:", dict(zip([x[:10] for x in names], np.round(res[key]["z"], 2))),
          f"sum8={s8o:+.3f} (null sd {s8n.std():.3f}) p_lower={res[key]['sum8_p_lower']:.4f}; sum10 p_lower={res[key]['sum10_p_lower']:.4f}")
for key in ("rc_mean", "rc_t"):
    n = np.array([x[key] for x in nul]); o = obs[key]
    res[key] = {"obs": float(o), "null_mean": float(n.mean()), "null_sd": float(n.std()), "p_lower": float((1 + np.sum(n <= o)) / (1 + NS)),
                "p_two": float((1 + np.sum(np.abs(n - n.mean()) >= abs(o - n.mean()))) / (1 + NS))}
    print(key, res[key])
json.dump(res, open(F.OUT / "s4d_alignment.json", "w"), indent=1)
