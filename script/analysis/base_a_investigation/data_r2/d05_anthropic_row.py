"""D5. The anthropic-row signature of base A.

(1) Leakage slope (re-derivation of the critic's c08 part a, own seed): per candidate row, slope over the 101 axes of
    mean[OvR(A) - OvR(B)] on mean[OvR(CO) - OvR(nulls' consensus)]; null = swap A/B replies at each (prompt, s), 2,000 draws.
(2) Judge session inside base A. The verdict file's first 578 rows (skipped_existing) came from an earlier session:
    anthropic 570 + google_deepmind 8. Later session: anthropic 6. Within-cell test of the 6 + 8 rows against the
    other-session rows of the same cells: per-axis mean deviation, Q = sum_j dev_j^2 / var_j; null = the same number
    of rows drawn at random inside the same cells from the same session as the comparison rows (session labels
    permuted within cell), 10,000 draws. Power: the smallest uniform per-axis shift (in yes-rate units, applied to
    the k test rows on every axis in the direction of the base rate's complement) detected at 5% in 80% of draws.
(3) Same within-cell session test on the larger split targets: CO target (google/meta/microsoft cells mixed) and
    ai_welfare_poisoning target (google cells mixed; its earlier session also holds its whole anthropic row).
(4) The eight nulls on five candidates (anthropic dropped before one-vs-rest), against A and against B, registered
    seed with five-candidate permutations (10,000): the p-values and their medians.
"""
import json
import warnings

import numpy as np

from dcommon import C, dump

warnings.simplefilter("ignore", RuntimeWarning)
D = C.load_all(); cands = D["_cands"]; instr = D["_instr"]
rng = np.random.default_rng(2611)
res = {}

# (1) leakage slope
O = {k: C.ovr(C.rates(v)) for k, v in D.items() if not k.startswith("_")}
cons = np.mean([O[c] for c in C.CONTROLS], axis=0)
x = np.nanmean(O["CO"] - cons, axis=1)


def lam(oa, ob):
    y = np.nanmean(oa - ob, axis=1)
    return np.array([float(np.dot(x[c], y[c]) / np.dot(x[c], x[c])) for c in range(6)])


l0 = lam(O["A"], O["B"]); RA, RB = D["A"], D["B"]; L = []
for _ in range(2000):
    m = rng.random(RA.shape[:3]) < 0.5
    L.append(lam(C.ovr(np.nanmean(np.where(m[..., None], RA, RB), 2)), C.ovr(np.nanmean(np.where(m[..., None], RB, RA), 2))))
L = np.array(L)
res["leakage"] = {cn: {"lambda": float(l0[c]), "swap_sd": float(L[:, c].std()),
                       "p_two_sided": float((1 + np.sum(np.abs(L[:, c]) >= abs(l0[c]))) / 2001)} for c, cn in enumerate(cands)}
print("(1) leakage slope of (A - B) on (CO - nulls):", {k: f"{v['lambda']:+.4f}±{v['swap_sd']:.4f} p={v['p_two_sided']:.3f}" for k, v in res["leakage"].items()})


# (2), (3) within-cell session tests
def rows_of(path):
    rr = [json.loads(l) for l in open(path)]
    return [r for r in rr if int(r["level"]) == 2]


AXI = {a: j for j, a in enumerate(C.AXES)}


def vec(r):
    v = np.full(len(C.AXES), np.nan)
    for a, b in r["verdicts"].items():
        if b is not None:
            v[AXI[a]] = float(bool(b))
    return v


def session_test(path, k_first, label, nperm=10000):
    rr = rows_of(path)
    cell = {}
    for n, r in enumerate(rr):
        cell.setdefault((r["principal"], r["instruction_id"]), []).append((n < k_first, vec(r)))
    mixed = {key: v for key, v in cell.items() if 0 < sum(s for s, _ in v) < len(v)}
    # test rows = the minority session within each mixed cell? Use session-1 rows as the "test" label throughout.
    blocks = []
    for key, v in mixed.items():
        X = np.array([x for _, x in v]); s1 = np.array([s for s, _ in v])
        blocks.append((X, s1))
    n1 = sum(int(s.sum()) for _, s in blocks); n2 = sum(int((~s).sum()) for _, s in blocks)
    allX = np.concatenate([X for X, _ in blocks]); var = np.nanvar(allX, axis=0); var[var == 0] = np.nan

    def dev(labels):
        d = []; w = []
        for (X, _), lab in zip(blocks, labels):
            a, b = X[lab], X[~lab]
            d.append(np.nanmean(a, 0) - np.nanmean(b, 0)); w.append(min(len(a), len(b)))
        d = np.array(d); w = np.array(w, float)[:, None]
        md = np.nansum(d * w, 0) / np.nansum(np.where(np.isnan(d), 0, w), 0)
        return md, float(np.nansum(md ** 2 / var))
    md0, q0 = dev([s for _, s in blocks])
    nul = np.empty(nperm);
    for k in range(nperm):
        nul[k] = dev([rng.permutation(s) for _, s in blocks])[1]
    p = float((1 + np.sum(nul >= q0)) / (1 + nperm))
    # power: add a uniform shift delta toward (1 - base rate) on every axis of the session-1 rows
    pw = {}
    for delta in (0.02, 0.05, 0.1):
        hits = 0
        for k in range(300):
            labs = [rng.permutation(s) for _, s in blocks]
            bl2 = []
            for (X, _), lab in zip(blocks, labs):
                Y = X.copy(); flip = (rng.random(Y.shape) < delta) & lab[:, None] & (Y == 0); Y[flip] = 1.0
                bl2.append(Y)
            d = []; w = []
            for Y, lab in zip(bl2, labs):
                d.append(np.nanmean(Y[lab], 0) - np.nanmean(Y[~lab], 0)); w.append(min(lab.sum(), (~lab).sum()))
            d = np.array(d); w = np.array(w, float)[:, None]
            md = np.nansum(d * w, 0) / np.nansum(np.where(np.isnan(d), 0, w), 0)
            hits += float(np.nansum(md ** 2 / var)) >= np.quantile(nul, 0.95)
        pw[str(delta)] = hits / 300
    out = {"mixed_cells": len(blocks), "rows_session1": n1, "rows_session2": n2, "Q": q0, "null_mean": float(nul.mean()),
           "p": p, "power_flip_no_to_yes": pw, "mean_dev_yes_rate": float(np.nanmean(md0)),
           "top_axes": [(C.AXES[j], float(md0[j])) for j in np.argsort(-np.abs(np.nan_to_num(md0)))[:5]]}
    print(f"(2/3) {label}: {len(blocks)} mixed cells, session-1 rows {n1}, session-2 rows {n2}; Q {q0:.1f} vs null {nul.mean():.1f}, p {p:.3f}; "
          f"mean yes-rate shift (s1 - s2) {np.nanmean(md0):+.4f}; power to detect a no->yes flip of 2/5/10% of verdicts: {pw}")
    return out


res["session_base_A"] = session_test(C.BASE_A, 578, "base A (anthropic 6 late rows + google 8 early rows)")
res["session_CO_target"] = session_test(C.CO_TARGET, 2826, "CO target")
res["session_AWP_target"] = session_test(C.null_target("ai_welfare_poisoning"), 971, "ai_welfare_poisoning target")

# (4) five-candidate eight-null p-values vs A and vs B
keep = [i for i, c in enumerate(cands) if c != "anthropic"]
orders5 = C.perm_orders(n_c=5)
P5 = {k: C.rates(v)[keep] for k, v in D.items() if not k.startswith("_")}
five = {}
for base in ("A", "B"):
    ps = []
    for c in C.CONTROLS:
        r = C.run_test(P5[c], P5[base], orders5); ps.append(r["p"]); five[f"{c}|{base}"] = {"S": r["S"], "p": r["p"]}
    five[f"median|{base}"] = float(np.median(ps)); five[f"n_below_0.05|{base}"] = int(np.sum(np.array(ps) < 0.05))
    print(f"(4) five candidates vs {base}: p = {np.round(ps, 4).tolist()}  median {np.median(ps):.4f}  # < .05: {np.sum(np.array(ps) < 0.05)}")
res["five_candidate"] = five
dump(res, "d05_anthropic_row.json")
