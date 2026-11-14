"""F1a. Shared candidate structure between samples, measured across disjoint reply halves (reproduces critic k15).

All samples share NS random splits of the 16 slots into two halves of 8. For samples X, Y:
   cov(X, Y) = mean over splits of 1/2 [ <M_X(h1), M_Y(h2)> + <M_X(h2), M_Y(h1)> ],
M = one-vs-rest cell means over the 36 instructions, <.,.> = mean over (candidate, axis) cells, in 1e-6.
Disjoint slots remove the judge's shared axis order (keyed on prompt_id, s) and the pairing of noise.
Self-covariance cov(X, X) adds any structure private to X's draw that repeats across its halves.

Inference
  relabel null (structure = 0): candidates relabelled within instruction in the first member only,
     one relabelling per null draw shared by all samples' first members (300 draws).
  A/B swap null (bases exchangeable): A and B trade replies per slot (300 draws), same splits; tests
     D = mean_k cov(control_k, A) - cov(control_k, B), cov(A, A) - cov(B, B), and cov(A, B).
Also a moment decomposition under 'control_k = b + f + o_k' (b base structure, f shared fine-tune
shift): |b|^2 ~ cov(A, B), <b+f, b> ~ mean cov(control, base), |b+f|^2 ~ mean cov(control_j, control_k).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r4c as Q  # noqa: E402

d = Q.data()
R = d["R"]
NAMES = ["A", "B", "CO"] + Q.CONTROLS + Q.SD
NS, NNULL, NSWAP = 60, 300, 300
rng = np.random.default_rng([20261113, 41])


def half_ovr(Rx, splits, kp):
    """(NS, 2, n_c, 36, 101) per-instruction one-vs-rest for both halves."""
    out = np.empty((len(splits), 2, len(kp), 36, 101))
    for s, (h1, h2) in enumerate(splits):
        for h, sl in enumerate((h1, h2)):
            out[s, h] = Q.ovr(np.nanmean(Rx[kp][:, :, sl], axis=2))
    return out


def cov(Ma, Mb):
    """Ma, Mb (NS, 2, n_c, 101) cell means -> cross-half covariance in 1e-6."""
    return 0.5e6 * (np.mean(Ma[:, 0] * Mb[:, 1]) + np.mean(Ma[:, 1] * Mb[:, 0]))


def run(tag):
    kp, nc = Q.world(tag)
    splits = []
    for _ in range(NS):
        p = rng.permutation(16)
        splits.append((np.sort(p[:8]), np.sort(p[8:])))
    H = {k: half_ovr(R[k], splits, kp) for k in NAMES}
    M = {k: v.mean(axis=3) for k, v in H.items()}
    ctl = Q.CONTROLS

    def groups(Mfirst, Msecond):
        cv = lambda a, b: cov(Mfirst[a], Msecond[b])  # noqa: E731
        g = {"control_with_other_control": np.mean([cv(a, b) for a in ctl for b in ctl if a != b]),
             "control_with_itself": np.mean([cv(a, a) for a in ctl]),
             "control_with_A": np.mean([cv(a, "A") for a in ctl]),
             "control_with_B": np.mean([cv(a, "B") for a in ctl]),
             "A_with_B": cv("A", "B"), "A_with_A": cv("A", "A"), "B_with_B": cv("B", "B"),
             "sd_with_sd": cv(Q.SD[0], Q.SD[1]), "sd_with_control": np.mean([cv(s, a) for s in Q.SD for a in ctl]),
             "sd_with_A": np.mean([cv(s, "A") for s in Q.SD]), "sd_with_B": np.mean([cv(s, "B") for s in Q.SD]),
             "CO_with_control": np.mean([cv("CO", a) for a in ctl])}
        return g

    obs = groups(M, M)
    per = {"control_with_itself": {a: round(cov(M[a], M[a]), 2) for a in ctl},
           "control_with_A": {a: round(cov(M[a], M["A"]), 2) for a in ctl},
           "control_with_B": {a: round(cov(M[a], M["B"]), 2) for a in ctl}}
    # relabel null: one within-instruction relabelling of candidates per draw, applied to the first member
    null = {k: [] for k in obs}
    for _ in range(NNULL):
        o = np.argsort(rng.random((36, nc)), axis=1)            # o[i] = source candidate order
        Mr = {k: v[:, :, o.T, np.arange(36)[None, :], :].mean(axis=3) for k, v in H.items()}
        g = groups(Mr, M)
        for k in g:
            null[k].append(g[k])
    rel = {k: {"obs": round(float(obs[k]), 2), "null_mean": round(float(np.mean(null[k])), 2),
               "null_sd": round(float(np.std(null[k])), 2),
               "z": round(float((obs[k] - np.mean(null[k])) / np.std(null[k])), 2)} for k in obs}
    # A/B swap null
    RA, RB = R["A"], R["B"]
    sw = {"D_control_A_minus_B": [], "AA_minus_BB": [], "A_with_B": []}

    def swap_stats(MA, MB):
        return (np.mean([cov(M[a], MA) - cov(M[a], MB) for a in ctl]), cov(MA, MA) - cov(MB, MB), cov(MA, MB))

    o_sw = swap_stats(M["A"], M["B"])
    for _ in range(NSWAP):
        m = Q.swap_mask(rng, "reply", RA, RB)
        XA, XB = Q.swapped(RA, RB, m)
        r = swap_stats(half_ovr(XA, splits, kp).mean(axis=3), half_ovr(XB, splits, kp).mean(axis=3))
        for k, v in zip(sw, r):
            sw[k].append(v)
    swap = {}
    for k, v in zip(sw, o_sw):
        a = np.array(sw[k])
        swap[k] = {"obs": round(float(v), 2), "null_mean": round(float(a.mean()), 2), "null_sd": round(float(a.std()), 2),
                   "z": round(float((v - a.mean()) / a.std()), 2),
                   "p_two": round(float((1 + np.sum(np.abs(a - a.mean()) >= abs(v - a.mean()))) / (1 + len(a))), 4)}
    b2 = obs["A_with_B"]
    cb = 0.5 * (obs["control_with_A"] + obs["control_with_B"])
    cc = obs["control_with_other_control"]
    dec = {"b2_from_A_with_B": round(float(b2), 2), "b_dot_bf_from_control_with_bases": round(float(cb), 2),
           "bf2_from_control_with_control": round(float(cc), 2),
           "implied_f2_if_b2_as_measured": round(float(cc - 2 * cb + b2), 2),
           "cauchy_schwarz_needs_b2_at_least": round(float(cb ** 2 / cc), 2),
           "note": "|b+f|^2 |b|^2 >= <b+f, b>^2 requires cov(A,B) >= (mean control-base cov)^2 / control-control cov"}
    res = {"n_splits": NS, "relabel_null": rel, "per_control": per, "AB_swap_null": swap, "decomposition": dec}
    print("==", tag)
    print(json.dumps(res, indent=1))
    return res


out = {"six": run("six"), "five": run("five")}
(Q.OUT / "f1a_cross_half.json").write_text(json.dumps(out, indent=1))
