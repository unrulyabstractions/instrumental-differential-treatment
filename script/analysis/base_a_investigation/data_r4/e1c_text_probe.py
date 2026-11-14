"""E1c. A judge-free text probe: is each control's difference from its siblings carried by its text?

Inputs already on disk (no API calls): text-embedding-3-small vectors of the candidate-masked reply
texts (geometry/embeddings/emb_masked_*.npy, rows keyed in masked_texts_*.jsonl) for base A, the
contextual_optimism target and the eight controls. A multi-output ridge regression maps a reply's
embedding to its 101 gpt-5-mini verdicts. It is cross-fitted by instruction (6 folds of 6
instructions), so a reply's prediction never uses its own prompt's labels: the predicted rate
depends on the reply text only, and judge noise on that reply cannot enter it.

Then, per control, against the mean of its seven siblings:
  - the registered test on predicted rates;
  - gamma = regression slope of predicted cell-mean d on verdict cell-mean d over the 606 cells
    (selection on the regressor leaves this slope unbiased);
  - at the verdict peak cell: observed predicted d against gamma * verdict d.
A judging artifact (a time-block shift in the judge, a repair, a session) moves verdict d without
moving the text, so it predicts predicted d near 0 at the peak while gamma stays positive.
Also the shared pattern: controls' mean minus base A, verdicts vs predictions.
Read-only on the repo.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r4common as R  # noqa: E402

D = R.D(); cands = R.cands(); instr = R.instr()
ci = {c: n for n, c in enumerate(cands)}; ii = {s: n for n, s in enumerate(instr)}
EMB = {}
for k in R.NULLS:
    EMB[k] = (R.AB / f"controls/{k}/geometry/embeddings/emb_masked_target_text-embedding-3-small.npy",
              R.AB / f"controls/{k}/geometry/embeddings/masked_texts_target.jsonl")
EMB["CO"] = (R.AB / "contextual_optimism/geometry/embeddings/emb_masked_target_text-embedding-3-small.npy",
             R.AB / "contextual_optimism/geometry/embeddings/masked_texts_target.jsonl")
EMB["A"] = (R.AB / "contextual_optimism/geometry/embeddings/emb_masked_base_text-embedding-3-small.npy",
            R.AB / "contextual_optimism/geometry/embeddings/masked_texts_base.jsonl")
names = list(EMB)
X, Y, IDX = [], [], []
for q, k in enumerate(names):
    V = np.load(EMB[k][0]).astype(np.float64)
    keys = [json.loads(l)["key"] for l in open(EMB[k][1])]
    assert len(keys) == len(V), k
    for n, key in enumerate(keys):
        pid, s = key.rsplit("#", 1)
        c, ins = pid.split("__", 1)
        a, b, ss = ci[c], ii[ins], int(s)
        y = D[k][a, b, ss]
        if np.isnan(y).any():
            continue
        X.append(V[n]); Y.append(y); IDX.append((q, a, b, ss))
X = np.array(X); Y = np.array(Y); IDX = np.array(IDX)
print("rows", len(X), "per sample", np.bincount(IDX[:, 0]))
fold = IDX[:, 2] % 6
mu = X.mean(0); Xc = X - mu


def ridge_fit(Xt, Yt, lam):
    ym = Yt.mean(0)
    G = Xt.T @ Xt + lam * np.eye(Xt.shape[1])
    W = np.linalg.solve(G, Xt.T @ (Yt - ym))
    return W, ym


# choose lambda on fold 0 vs rest
best = None
for lam in (0.3, 1, 3, 10, 30):
    tr, te = fold != 0, fold == 0
    W, ym = ridge_fit(Xc[tr], Y[tr], lam)
    pr = Xc[te] @ W + ym
    r = np.nanmean([np.corrcoef(pr[:, j], Y[te, j])[0, 1] for j in range(101) if Y[te, j].std() > 0])
    print("lambda", lam, "mean per-axis r", round(float(r), 4))
    if best is None or r > best[1]:
        best = (lam, r)
lam = best[0]
PRED = np.empty_like(Y)
for f in range(6):
    tr, te = fold != f, fold == f
    W, ym = ridge_fit(Xc[tr], Y[tr], lam)
    PRED[te] = Xc[te] @ W + ym
axis_r = np.array([np.corrcoef(PRED[:, j], Y[:, j])[0, 1] if Y[:, j].std() > 0 else np.nan for j in range(101)])
print("chosen lambda", lam, "out-of-fold per-axis r: median", round(float(np.nanmedian(axis_r)), 3),
      "min", round(float(np.nanmin(axis_r)), 3), "max", round(float(np.nanmax(axis_r)), 3))

# rebuild per-sample (6, 36, 16, 101) arrays of predictions and verdicts on the same rows
PR = {k: np.full((6, 36, 16, 101), np.nan) for k in names}
for (q, a, b, ss), p in zip(IDX, PRED):
    PR[names[q]][a, b, ss] = p
PP = {k: R.rates(PR[k]) for k in names}
PV = {k: R.rates(D[k]) for k in names}
E = R.F.E_for(6)
res = {"lambda": lam, "axis_r_median": float(np.nanmedian(axis_r)),
       "axis_r": dict(zip(R.AX, np.round(axis_r, 3).tolist())), "controls": {}}
for k in R.NULLS:
    sibV = np.mean([PV[j] for j in R.NULLS if j != k], axis=0)
    sibP = np.mean([PP[j] for j in R.NULLS if j != k], axis=0)
    dV = (R.ovr(PV[k]) - R.ovr(sibV)); dP = (R.ovr(PP[k]) - R.ovr(sibP))
    tV, mV = R.C.tgrid_fast(dV); tP, mP = R.C.tgrid_fast(dP)
    c, j = np.unravel_index(np.nanargmax(np.abs(tV)), tV.shape)
    x = mV.ravel(); y = mP.ravel()
    gamma = float((x * y).sum() / (x * x).sum())
    r_cells = float(np.corrcoef(x, y)[0, 1])
    S, p = R.reg_test(PP[k], sibP)
    # benchmark: pred/verdict at the 10 largest-|tV| cells other than the peak
    order = np.argsort(-np.abs(tV).ravel())
    top = order[1:11]
    ratio_top = float((y[top] * np.sign(x[top])).sum() / np.abs(x[top]).sum())
    res["controls"][k] = {"peak": f"{cands[c]} x {R.AX[j]}", "axis_r_at_peak_axis": round(float(axis_r[j]), 3),
                          "verdict_d_peak": round(float(mV[c, j]), 4), "verdict_t_peak": round(float(tV[c, j]), 2),
                          "pred_d_peak": round(float(mP[c, j]), 4), "pred_t_peak": round(float(tP[c, j]), 2),
                          "gamma_all_cells": round(gamma, 3), "expected_pred_d_peak": round(gamma * float(mV[c, j]), 4),
                          "ratio_pred_over_verdict_peak": round(float(mP[c, j] / mV[c, j]), 3),
                          "ratio_next10_cells": round(ratio_top, 3),
                          "corr_cells_pred_vs_verdict": round(r_cells, 3),
                          "registered_test_on_predicted_rates": (round(S, 3), round(p, 4))}
    print(k, res["controls"][k], flush=True)

# shared pattern relative to base A (B has no embeddings)
mV = np.mean([R.ovr(PV[k]).mean(1) for k in R.NULLS], axis=0) - R.ovr(PV["A"]).mean(1)
mP = np.mean([R.ovr(PP[k]).mean(1) for k in R.NULLS], axis=0) - R.ovr(PP["A"]).mean(1)
res["shared_vs_A"] = {"corr_cells": float(np.corrcoef(mV.ravel(), mP.ravel())[0, 1]),
                      "gamma": float((mV * mP).sum() / (mV * mV).sum())}
# CO's known anthropic effect as a positive control for text-borne differences
dV = (R.ovr(PV["CO"]) - R.ovr(PV["A"])).mean(1); dP = (R.ovr(PP["CO"]) - R.ovr(PP["A"])).mean(1)
res["CO_vs_A"] = {"corr_cells": float(np.corrcoef(dV.ravel(), dP.ravel())[0, 1]),
                  "gamma": float((dV * dP).sum() / (dV * dV).sum()),
                  "anthropic_row_gamma": float((dV[0] * dP[0]).sum() / (dV[0] ** 2).sum())}
print("shared vs A", res["shared_vs_A"], "CO vs A", res["CO_vs_A"])
np.savez_compressed(R.OUT / "e1c_pred_rates.npz", **{k: PP[k] for k in names})
R.dump(res, "e1c_text_probe.json")
