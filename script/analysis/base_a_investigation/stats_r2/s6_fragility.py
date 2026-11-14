"""S6. Fragility of the statistic and calibration of these organisms.

(1) Null span: for each of the eight tests against A and against B, the registered permutation null's
    median, 95th percentile and span (exact, 10,000 registered permutations).
(2) Single-prompt swaps: replace ONE (candidate, instruction) cell of base A (all 101 axes, 16 replies)
    by base B's, recompute each test's S and exact p. 216 swaps. Also single-instruction swaps (36) and
    the reverse (one prompt of A put into B).
(3) target_fixed calibration, per test, with exact per-draw p: d_k = T_k + G*, T_k = OvR_k - R
    (R = mean one-vs-rest gap of the ten fine-tunes), G* = (R - OvR_X) relabelled within instruction
    (one relabelling shared by the eight tests), X = A and X = B, 2,000 draws each.
    Also 'base_relabel': d_k = OvR_k - perm(OvR_X) is NOT used (it would move the base model's own
    candidate structure into d).
Usage: s6_fragility.py <n_target_fixed> <n_workers>
"""
from __future__ import annotations

import os

os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
import json  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from multiprocessing import Pool  # noqa: E402

import numpy as np  # noqa: E402

import fast as F  # noqa: E402
from fast import C  # noqa: E402

G = {}


def init():
    D = F.load()
    P = {k: C.rates(v) for k, v in D.items() if not k.startswith("_")}
    O = {k: C.ovr(v) for k, v in P.items()}
    G["P"], G["O"] = P, O
    G["OT"] = np.stack([O[c] for c in F.CONTROLS])
    G["R"] = np.mean([O[k] for k in F.TEN], axis=0)
    G["E6"] = F.E_for(6)


def eight(pb):
    S, p, _ = F.test_many(G["OT"], C.ovr(pb), 6, G["E6"])
    return S, p


def tf_job(args):
    X, idx = args
    rng = np.random.default_rng([515, idx, ord(X)])
    O = G["O"]
    Gx = G["R"] - O[X]
    order = np.stack([rng.permutation(6) for _ in range(36)])  # (36, 6)
    Gp = Gx[order.T, np.arange(36)[None, :], :]
    T = G["OT"] - G["R"][None]
    ds = T + Gp[None]
    S = F.S_fast(ds)
    nm = F.null_max(ds, 6, G["E6"])
    return X, idx, S, F.tail(nm, S)


def main():
    ntf, nw = int(sys.argv[1]), int(sys.argv[2])
    init()
    P, O = G["P"], G["O"]
    t0 = time.time()
    res = {"tests": F.CONTROLS}
    # (1) null spans
    spans = {}
    for X in ("A", "B"):
        ds = G["OT"] - O[X][None]
        nm = F.null_max(ds, 6, G["E6"])
        S = F.S_fast(ds)
        spans[X] = {"S": S.tolist(), "p": F.tail(nm, S).tolist(), "null_median": np.median(nm, 1).tolist(),
                    "null_p95": np.quantile(nm, 0.95, axis=1).tolist(), "null_p99": np.quantile(nm, 0.99, axis=1).tolist(),
                    "span_median_to_p95": (np.quantile(nm, 0.95, axis=1) - np.median(nm, 1)).tolist()}
    res["null_spans"] = spans
    print("null spans done", time.time() - t0, flush=True)
    # (2) single swaps
    SA, pA = eight(P["A"])
    SB, pB = eight(P["B"])
    dS = np.zeros((6, 36, 8)); pp = np.zeros((6, 36, 8))
    for c in range(6):
        for i in range(36):
            pb = P["A"].copy(); pb[c, i] = P["B"][c, i]
            S, p = eight(pb)
            dS[c, i], pp[c, i] = S - SA, p
    dSi = np.zeros((36, 8)); ppi = np.zeros((36, 8))
    for i in range(36):
        pb = P["A"].copy(); pb[:, i] = P["B"][:, i]
        S, p = eight(pb)
        dSi[i], ppi[i] = S - SA, p
    dSr = np.zeros((6, 36, 8)); ppr = np.zeros((6, 36, 8))
    for c in range(6):
        for i in range(36):
            pb = P["B"].copy(); pb[c, i] = P["A"][c, i]
            S, p = eight(pb)
            dSr[c, i], ppr[c, i] = S - SB, p
    print("single swaps done", time.time() - t0, flush=True)
    flat = dS.reshape(216, 8)
    res["single_prompt"] = {
        "S_A": SA.tolist(), "p_A": pA.tolist(),
        "dS_quantiles_0_5_25_50_75_95_100": np.quantile(flat, [0, .05, .25, .5, .75, .95, 1], axis=0).T.tolist(),
        "dS_sd": flat.std(0).tolist(), "dS_mean": flat.mean(0).tolist(),
        "n_prompts_dS_le_-0.3": (flat <= -0.3).sum(0).tolist(), "n_prompts_dS_le_-0.5": (flat <= -0.5).sum(0).tolist(),
        "n_prompts_p_cross_0.05_up": ((pp.reshape(216, 8) > 0.05) & (pA[None] <= 0.05)).sum(0).tolist(),
        "max_p_after_one_swap": pp.reshape(216, 8).max(0).tolist(),
        "argmin_dS_prompt": [list(map(int, np.unravel_index(int(np.argmin(dS[:, :, k])), (6, 36)))) for k in range(8)],
        "median_of_eight_p_after_swap_quantiles": np.quantile(np.median(pp.reshape(216, 8), 1), [0, .05, .5, .95, 1]).tolist(),
        "dS_mean_over_tests_quantiles": np.quantile(flat.mean(1), [0, .05, .5, .95, 1]).tolist(),
    }
    res["single_instruction"] = {"dS_sd": dSi.std(0).tolist(), "dS_min": dSi.min(0).tolist(), "dS_max": dSi.max(0).tolist(),
                                 "median_of_eight_p_quantiles": np.quantile(np.median(ppi, 1), [0, .05, .5, .95, 1]).tolist()}
    fr = dSr.reshape(216, 8)
    res["reverse_single_prompt_into_B"] = {"S_B": SB.tolist(), "dS_sd": fr.std(0).tolist(),
                                           "dS_quantiles_0_5_50_95_100": np.quantile(fr, [0, .05, .5, .95, 1], axis=0).T.tolist()}
    np.savez(F.OUT / "s6_single_swaps.npz", dS=dS, pp=pp, dSi=dSi, ppi=ppi, dSr=dSr, ppr=ppr)
    # (4) dependence on one cell: the top three cells of each test against A, the p each |t| would
    # have alone, and the test after replacing base A's values by base B's at the peak cell only
    # (that candidate, that axis, all instructions) or at the peak axis (all candidates).
    cands = F.load()["_cands"]
    ds = G["OT"] - O["A"][None]
    nm = F.null_max(ds, 6, G["E6"])
    tt = C.tgrid_fast(ds)[0]
    onecell = {}
    for k, name in enumerate(F.CONTROLS):
        a = np.abs(tt[k]).ravel()
        top = np.argsort(-a)[:3]
        c0, j0 = np.unravel_index(top[0], tt[k].shape)
        pb = P["A"].copy(); pb[c0, :, j0] = P["B"][c0, :, j0]
        S1, p1, _ = F.test_many(G["OT"][k:k + 1], C.ovr(pb), 6, G["E6"])
        pb2 = P["A"].copy(); pb2[:, :, j0] = P["B"][:, :, j0]
        S2, p2, _ = F.test_many(G["OT"][k:k + 1], C.ovr(pb2), 6, G["E6"])
        onecell[name] = {
            "top3": [{"cand": cands[np.unravel_index(f, tt[k].shape)[0]], "axis": C.AXES[np.unravel_index(f, tt[k].shape)[1]],
                      "t": float(tt[k].ravel()[f]), "p_if_max": float(F.tail(nm[k:k + 1], np.array([a[f]]))[0])} for f in top],
            "swap_peak_cell_to_B": {"S": float(S1[0]), "p": float(p1[0])},
            "swap_peak_axis_to_B": {"S": float(S2[0]), "p": float(p2[0])}}
        print(name, json.dumps(onecell[name]), flush=True)
    res["one_cell"] = onecell
    # (3) target_fixed per test with exact per-draw p
    tasks = [(X, i) for X in ("A", "B") for i in range(ntf)]
    out = {"A": [], "B": []}
    with Pool(nw, initializer=init) as pool:
        for X, idx, S, p in pool.imap_unordered(tf_job, tasks, chunksize=8):
            out[X].append((idx, S, p))
    res["target_fixed"] = {}
    for X in ("A", "B"):
        arr = sorted(out[X], key=lambda r: r[0])
        S = np.array([r[1] for r in arr]); p = np.array([r[2] for r in arr])
        med = np.median(p, 1)
        res["target_fixed"][X] = {
            "n": len(arr), "per_test_P_p_le_0.06": np.mean(p <= 0.06, 0).tolist(), "per_test_P_p_lt_0.05": np.mean(p < 0.05, 0).tolist(),
            "per_test_median_p": np.median(p, 0).tolist(), "all_P_p_le_0.06": float(np.mean(p <= 0.06)), "all_P_p_lt_0.05": float(np.mean(p < 0.05)),
            "median_of_median": float(np.median(med)), "P_median_le_0.0557": float(np.mean(med <= 0.0557)),
            "S_sd": S.std(0).tolist(), "S_corr_mean_offdiag": float((np.corrcoef(S.T).sum() - 8) / 56)}
        np.savez(F.OUT / f"s6_target_fixed_{X}.npz", S=S, p=p)
    print(json.dumps(res["target_fixed"], indent=1))
    json.dump(res, open(F.OUT / "s6_fragility.json", "w"), indent=1)
    print("done", time.time() - t0)


if __name__ == "__main__":
    main()
