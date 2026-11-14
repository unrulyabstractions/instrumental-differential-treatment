"""F1c. Does each control's departure from its siblings replicate across disjoint reply halves? (replaces k18 part b)

Design: one random split of the 16 slots into halves, shared by all samples. For control k, in the selection
half find the peak cell of t(OvR(k) - mean OvR(other seven)); in the test half read sign * t at that cell.
Both directions, averaged over 200 splits for the observed value.
Nulls (each replicate averages over 32 splits; its SD is corrected to 200 splits with the per-split variance:
var_200 = var_32(replicate means) - s2 / 32 + s2 / 200):
  shuffle  the eight controls' replies permuted among the labels at every slot (pseudo-controls keep the shared
           pattern, noise and axis-order pairing, and lose own structure); the statistic of all eight
           pseudo-controls is pooled, since they are exchangeable. 200 replicates.
  relabel  one within-instruction relabelling of candidates, the same in every split of a replicate, applied to
           d = OvR(k) - OvR(siblings) in both halves (the registered test's null, kept consistent across
           splits; critic k18 b relabelled independently per split, which shrank the null SD). 200 replicates.
Bases A and B against the consensus of all eight are run the same way for scale (relabel null only).
Usage: f1c_split_half_siblings.py <six|five>
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r4c as Q  # noqa: E402

tag = sys.argv[1] if len(sys.argv) > 1 else "six"
d = Q.data()
kp, nc = Q.world(tag)
Rc = np.stack([d["R"][k] for k in Q.CONTROLS])[:, kp]          # (8, nc, 36, 16, 101)
RA, RB = d["R"]["A"][kp], d["R"]["B"][kp]
rng = np.random.default_rng([20261113, 43, nc])
NS_OBS, NS_NULL, NREP = 200, 32, 200


def splits(n):
    out = []
    for _ in range(n):
        p = rng.permutation(16)
        out.append((np.sort(p[:8]), np.sort(p[8:])))
    return out


def dhalves(Rc_, sp, extra=None):
    """d for the eight controls (vs siblings) and optionally bases (vs consensus): (m, 2, nc, 36, 101)."""
    O = [Q.ovr(np.nanmean(Rc_[:, :, :, sl], axis=3)) for sl in sp]      # two of (8, nc, 36, 101)
    ds = []
    for h in range(2):
        sib = (O[h].sum(0, keepdims=True) - O[h]) / 7.0
        dh = O[h] - sib
        if extra is not None:
            cons = O[h].mean(0)
            dh = np.concatenate([dh, np.stack([Q.ovr(np.nanmean(X[:, :, sp[h]], axis=2)) - cons for X in extra])])
        ds.append(dh)
    return np.stack(ds, axis=1)


def stat(dd):
    """dd (m, 2, nc, 36, 101) -> per-sample select-in-one-half, test-in-the-other value (mean of both directions)."""
    t1, t2 = Q.tg(dd[:, 0]), Q.tg(dd[:, 1])
    out = np.zeros(dd.shape[0])
    for a, b in ((t1, t2), (t2, t1)):
        flat = np.abs(a).reshape(len(a), -1)
        f = flat.argmax(1)
        sg = np.sign(a.reshape(len(a), -1)[np.arange(len(a)), f])
        out += 0.5 * sg * b.reshape(len(b), -1)[np.arange(len(b)), f]
    return out


t0 = time.time()
obs = np.mean([stat(dhalves(Rc, sp, (RA, RB))) for sp in splits(NS_OBS)], axis=0)      # (10,)
print(tag, "observed", np.round(obs, 3), f"{time.time()-t0:.0f}s", flush=True)

# shuffle null
shuf_means, shuf_var, m8_var = [], [], []
for r in range(NREP):
    X = Q.shuffle_controls(rng, Rc)
    v = np.array([stat(dhalves(X, sp)) for sp in splits(NS_NULL)])                       # (32, 8)
    shuf_means.append(v.mean(0)); shuf_var.append(v.var(0, ddof=1)); m8_var.append(v.mean(1).var(ddof=1))
shuf_means, shuf_var, m8_var = np.array(shuf_means), np.array(shuf_var), np.array(m8_var)
print(tag, "shuffle null done", f"{time.time()-t0:.0f}s", flush=True)

# relabel null (consistent across splits within a replicate)
SPN = splits(NS_NULL)
DH = [dhalves(Rc, sp, (RA, RB)) for sp in SPN]                                           # list of (10, 2, nc, 36, 101)
rel_means, rel_var = [], []
for r in range(NREP):
    o = np.argsort(rng.random((36, nc)), axis=1).T                                        # (nc, 36) source candidate
    v = np.array([stat(dd[:, :, o, np.arange(36)[None, :], :]) for dd in DH])              # (32, 10)
    rel_means.append(v.mean(0)); rel_var.append(v.var(0, ddof=1))
rel_means, rel_var = np.array(rel_means), np.array(rel_var)
print(tag, "relabel null done", f"{time.time()-t0:.0f}s", flush=True)


def corrected_sd(means, var, axis=0):
    v = means.var(axis=axis, ddof=1) - var.mean(axis=axis) / NS_NULL + var.mean(axis=axis) / NS_OBS
    return np.sqrt(np.maximum(v, 1e-12))


pool_m = shuf_means.ravel()
pool_sd = float(corrected_sd(shuf_means.reshape(-1, 1), shuf_var.reshape(-1, 1))[0])
mean8_sh = shuf_means.mean(1)
sd8_sh = float(np.sqrt(max(mean8_sh.var(ddof=1) - m8_var.mean() / NS_NULL + m8_var.mean() / NS_OBS, 1e-12)))
rel_sd = corrected_sd(rel_means, rel_var)
names = Q.CONTROLS + ["A vs consensus", "B vs consensus"]
res = {"world": tag, "n_splits_obs": NS_OBS, "n_splits_null": NS_NULL, "n_rep": NREP, "per_sample": {}}
for q, k in enumerate(names):
    e = {"a": round(float(obs[q]), 3),
         "relabel_null_mean": round(float(rel_means[:, q].mean()), 3), "relabel_null_sd": round(float(rel_sd[q]), 3),
         "z_relabel": round(float((obs[q] - rel_means[:, q].mean()) / rel_sd[q]), 2)}
    if q < 8:
        e.update({"shuffle_null_mean": round(float(pool_m.mean()), 3), "shuffle_null_sd": round(pool_sd, 3),
                  "z_shuffle": round(float((obs[q] - pool_m.mean()) / pool_sd), 2)})
    res["per_sample"][k] = e
m8 = float(obs[:8].mean())
res["mean_of_eight"] = {"a": round(m8, 3), "shuffle_null_mean": round(float(mean8_sh.mean()), 3), "shuffle_null_sd": round(sd8_sh, 3),
                        "z_shuffle": round((m8 - float(mean8_sh.mean())) / sd8_sh, 2)}
res["seconds"] = round(time.time() - t0)
print(json.dumps(res, indent=1))
(Q.OUT / f"f1c_split_half_siblings_{tag}.json").write_text(json.dumps(res, indent=1))
