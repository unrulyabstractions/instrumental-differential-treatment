"""E1d. Calibrate the text probe at peak cells with pseudo-controls.

The probe (e1c) sees only part of any text-borne difference (gamma 0.04-0.10 over all cells), so
'predicted d near 0 at the peak' needs a reference. Pseudo-controls: at every slot (candidate,
instruction, s) the eight controls' replies (verdict vector and probe prediction travel together)
are permuted among the eight labels. A pseudo-control's difference from its pseudo-siblings is then
reply-level variation only (sampling plus the judge's per-reply noise), all of it carried by real
replies and so as visible to the probe as such variation ever is. For each pseudo-control the
verdict peak cell against its pseudo-siblings is found, and the aligned ratio
   q = sign(d_verdict) * d_pred / |d_verdict|   at that cell
is recorded. A real peak produced by a judging artifact that does not live in the text (time-block
shift, repair, session) would give q below the pseudo distribution; a real behaviour gives q at or
above it. Statistic: mean q over the eight real peaks against the mean over eight pseudo peaks.
Read-only on the repo.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r4common as R  # noqa: E402

D = R.D()
z = np.load(R.OUT / "e1c_pred_rates.npz")
# reply-level predictions are needed for shuffling: rebuild from rates is impossible, so reload rows
import json  # noqa: E402
ci = {c: n for n, c in enumerate(R.cands())}; ii = {s: n for n, s in enumerate(R.instr())}
# re-run the probe's cross-fit cheaply to recover reply-level predictions for the eight controls
names = R.NULLS + ["CO", "A"]
EMB = {k: (R.AB / f"controls/{k}/geometry/embeddings/emb_masked_target_text-embedding-3-small.npy",
           R.AB / f"controls/{k}/geometry/embeddings/masked_texts_target.jsonl") for k in R.NULLS}
EMB["CO"] = (R.AB / "contextual_optimism/geometry/embeddings/emb_masked_target_text-embedding-3-small.npy",
             R.AB / "contextual_optimism/geometry/embeddings/masked_texts_target.jsonl")
EMB["A"] = (R.AB / "contextual_optimism/geometry/embeddings/emb_masked_base_text-embedding-3-small.npy",
            R.AB / "contextual_optimism/geometry/embeddings/masked_texts_base.jsonl")
X, Y, IDX = [], [], []
for q, k in enumerate(names):
    V = np.load(EMB[k][0]).astype(np.float64)
    keys = [json.loads(l)["key"] for l in open(EMB[k][1])]
    for n, key in enumerate(keys):
        pid, s = key.rsplit("#", 1); c, ins = pid.split("__", 1)
        a, b, ss = ci[c], ii[ins], int(s)
        y = D[k][a, b, ss]
        if np.isnan(y).any():
            continue
        X.append(V[n]); Y.append(y); IDX.append((q, a, b, ss))
X = np.array(X); Y = np.array(Y); IDX = np.array(IDX)
fold = IDX[:, 2] % 6; Xc = X - X.mean(0)
PRED = np.empty_like(Y)
for f in range(6):
    tr, te = fold != f, fold == f
    ym = Y[tr].mean(0)
    W = np.linalg.solve(Xc[tr].T @ Xc[tr] + 1.0 * np.eye(Xc.shape[1]), Xc[tr].T @ (Y[tr] - ym))
    PRED[te] = Xc[te] @ W + ym
VR = np.full((8, 6, 36, 16, 101), np.nan); PRr = np.full((8, 6, 36, 16, 101), np.nan)
for (q, a, b, ss), y, p in zip(IDX, Y, PRED):
    if q < 8:
        VR[q, a, b, ss] = y; PRr[q, a, b, ss] = p
# check consistency with e1c
chk = np.nanmax(np.abs(R.rates(PRr[0]) - z[R.NULLS[0]]))
print("max |rate diff| vs e1c for", R.NULLS[0], chk)


def peaks(V, Pp):
    """V, Pp (8, 6, 36, 16, 101) -> aligned ratio q and pred t at each control's verdict peak."""
    rv = np.stack([R.rates(V[k]) for k in range(8)]); rp = np.stack([R.rates(Pp[k]) for k in range(8)])
    out = []
    for k in range(8):
        sv = (rv.sum(0) - rv[k]) / 7; sp = (rp.sum(0) - rp[k]) / 7
        dv = R.ovr(rv[k]) - R.ovr(sv); dp = R.ovr(rp[k]) - R.ovr(sp)
        tv, mv = R.C.tgrid_fast(dv); tp, mp = R.C.tgrid_fast(dp)
        c, j = np.unravel_index(np.nanargmax(np.abs(tv)), tv.shape)
        out.append((np.sign(mv[c, j]) * mp[c, j] / abs(mv[c, j]), np.sign(mv[c, j]) * tp[c, j], abs(tv[c, j])))
    return np.array(out)


real = peaks(VR, PRr)
print("real q:", np.round(real[:, 0], 3), "mean", round(float(real[:, 0].mean()), 4))
print("real aligned pred t:", np.round(real[:, 1], 2), "mean", round(float(real[:, 1].mean()), 3))
rng = np.random.default_rng([20261113, 404])
NB = 300
nq, nt, nS = [], [], []
miss = np.isnan(VR).all(-1)
for b in range(NB):
    perm = np.argsort(rng.random((6, 36, 16, 8)), axis=-1)       # per slot permutation of 8 labels
    Vs = np.take_along_axis(VR.transpose(1, 2, 3, 0, 4), perm[..., None], axis=3).transpose(3, 0, 1, 2, 4)
    Ps = np.take_along_axis(PRr.transpose(1, 2, 3, 0, 4), perm[..., None], axis=3).transpose(3, 0, 1, 2, 4)
    pk = peaks(Vs, Ps)
    nq.append(pk[:, 0]); nt.append(pk[:, 1]); nS.append(pk[:, 2])
nq = np.array(nq); nt = np.array(nt); nS = np.array(nS)
mq = nq.mean(1); mt = nt.mean(1)
res = {"real_q": real[:, 0].tolist(), "real_mean_q": float(real[:, 0].mean()),
       "pseudo_q_per_peak_median": float(np.median(nq)), "pseudo_q_per_peak_5_95": [float(np.quantile(nq, .05)), float(np.quantile(nq, .95))],
       "pseudo_mean_q_of_8": [float(mq.mean()), float(mq.std())],
       "P_pseudo_mean_q_le_real": float((1 + (mq <= real[:, 0].mean()).sum()) / (1 + NB)),
       "real_aligned_pred_t": real[:, 1].tolist(), "real_mean_aligned_pred_t": float(real[:, 1].mean()),
       "pseudo_mean_aligned_pred_t_of_8": [float(mt.mean()), float(mt.std())],
       "P_pseudo_mean_t_le_real": float((1 + (mt <= real[:, 1].mean()).sum()) / (1 + NB)),
       "real_peak_abs_t": real[:, 2].tolist(), "pseudo_peak_abs_t_median": float(np.median(nS)), "n_shuffles": NB}
print(res)
R.dump(res, "e1d_probe_peak_null.json")
