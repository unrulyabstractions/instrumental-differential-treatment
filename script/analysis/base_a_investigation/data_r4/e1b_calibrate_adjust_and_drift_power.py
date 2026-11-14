"""E1b. Calibration for two E1 checks.

(a) The length- and cap-adjusted sibling tests fit one slope per axis to the control-minus-siblings
    difference and remove it. Removing a fitted regressor shrinks S even when the regressor is
    irrelevant. Null: the same adjustment with the control's length (or cap) difference relabelled
    across candidates within instruction (200 draws); report where the real adjusted p falls.
(b) Power of the drift tests. Inject a linear judge drift g_j(tau) = a_j * tau into each control's
    rates, with tau the real file position of each (candidate, instruction) and a_j ~ N(0, s^2), s
    chosen so the injected candidate-level sum of squares equals the observed control-minus-siblings
    cell-mean sum of squares. Report the linear-index share and the within/between slope correlation
    under the injection (100 draws per control).
Read-only on the repo.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r4common as R  # noqa: E402

D = R.D(); cands = R.cands(); instr = R.instr()
P = {k: R.rates(D[k]) for k in R.NULLS}
L = R.token_lengths()
rng = np.random.default_rng([20261113, 402])
NC, NI = 6, 36
E = R.F.E_for(NC)
sib = {k: np.mean([P[j] for j in R.NULLS if j != k], axis=0) for k in R.NULLS}


def ovr_c(x):
    return x - (x.sum(axis=-2, keepdims=True) - x) / (x.shape[-2] - 1)


pm_len = np.stack([L[k].astype(float).mean(2) for k in R.NULLS])
pm_cap = np.stack([(L[k] >= 398).astype(float).mean(2) for k in R.NULLS])
d_len = ovr_c(pm_len - (pm_len.sum(0, keepdims=True) - pm_len) / 7.0)
d_cap = ovr_c(pm_cap - (pm_cap.sum(0, keepdims=True) - pm_cap) / 7.0)


def adj_p(d, x):
    x = x[..., None]
    if (x ** 2).sum() == 0:
        return np.nan
    beta = (d * x).sum((0, 1)) / (x ** 2).sum()
    da = d - beta[None, None, :] * x
    S = R.F.S_fast(da[None]); return float(R.F.tail(R.F.null_max(da[None], NC, E), S)[0])


cal = {}
NB = 200
for q, k in enumerate(R.NULLS):
    d = R.ovr(P[k]) - R.ovr(sib[k])
    row = {}
    for lab, X in (("length", d_len[q]), ("cap", d_cap[q])):
        if (X ** 2).sum() == 0 or (lab == "cap" and np.abs(pm_cap[q]).max() < 0.05):
            continue
        real = adj_p(d, X)
        nulls = []
        for b in range(NB):
            o = np.argsort(rng.random((NI, NC)), axis=1)
            nulls.append(adj_p(d, X[o.T, np.arange(NI)[None, :]]))
        nulls = np.array(nulls)
        row[lab] = {"adjusted_p_real": round(real, 4), "adjusted_p_null_median": round(float(np.median(nulls)), 4),
                    "adjusted_p_null_5_95": [round(float(np.quantile(nulls, .05)), 4), round(float(np.quantile(nulls, .95)), 4)],
                    "P_null_adjusted_p_at_least_real": float((1 + (nulls >= real).sum()) / (1 + NB))}
    cal[k] = row
    print(k, row, flush=True)

# (b) drift power
pos = {}
for k in R.NULLS:
    rows = [json.loads(l) for l in open(R.AB / f"controls/{k}/judge_mini/verdicts_target.jsonl")]
    ii = {s: n for n, s in enumerate(instr)}; ci = {c: n for n, c in enumerate(cands)}
    acc = {}
    for n, r in enumerate(rows):
        acc.setdefault((ci[r["principal"]], ii[r["instruction_id"]]), []).append(n / len(rows))
    pp = np.zeros((NC, NI))
    for (c, i), v in acc.items():
        pp[c, i] = np.mean(v)
    pos[k] = pp
cidx = np.arange(NC) - 2.5; cvec = cidx / np.linalg.norm(cidx)


def drift_stats(raw_diff, tpos):
    d = ovr_c(raw_diff.transpose(2, 0, 1)).transpose(1, 2, 0)   # OvR over candidates
    M = d.mean(1)
    share = float(((cvec @ M) ** 2).sum() / (M ** 2).sum())
    tw = tpos - tpos.mean(1, keepdims=True); rw = raw_diff - raw_diff.mean(1, keepdims=True)
    bw = (tw[..., None] * rw).sum((0, 1)) / (tw ** 2).sum()
    tb = tpos.mean(1) - tpos.mean(); rb = raw_diff.mean(1) - raw_diff.mean(1).mean(0)
    bb = (tb[:, None] * rb).sum(0) / (tb ** 2).sum()
    return share, float(np.corrcoef(bw, bb)[0, 1])


power = {}
for k in R.NULLS:
    raw = P[k] - sib[k]
    d = R.ovr(P[k]) - R.ovr(sib[k]); M = d.mean(1); ss_obs = (M ** 2).sum()
    tp = pos[k]
    # injected candidate-level SS per unit a: OvR of tau's candidate means
    tauc = ovr_c(tp).mean(1)                         # (6,) candidate-level OvR of tau
    s = np.sqrt(ss_obs / (101 * (tauc ** 2).sum()))
    sh, rr = [], []
    for b in range(100):
        a = rng.normal(0, s, 101)
        inj = raw + tp[..., None] * a[None, None, :]
        x, y = drift_stats(inj, tp); sh.append(x); rr.append(y)
    power[k] = {"drift_sd_per_session": round(float(s), 4), "share_under_injection_mean": round(float(np.mean(sh)), 3),
                "share_under_injection_5pct": round(float(np.quantile(sh, .05)), 3),
                "r_within_between_under_injection_mean": round(float(np.mean(rr)), 3),
                "r_under_injection_5pct": round(float(np.quantile(rr, .05)), 3), "observed": drift_stats(raw, tp)}
    print(k, power[k], flush=True)
R.dump({"adjust_calibration": cal, "drift_power": power}, "e1b_calibration.json")
