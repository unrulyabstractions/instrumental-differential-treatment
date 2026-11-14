"""Critic round 3, check 3: correlation between samples of their own one-vs-rest candidate structure.

Per sample, the cell mean over instructions of OvR (606 cells, six candidates; 505 without anthropic).
corr(A, B) measures how much real candidate structure the base model has (two independent draws).
If the August samples (A, CO, eight nulls) shared a candidate-dependent provenance effect, each null
would correlate more with A than with B. Split-half reliability per sample is given for scale.
"""
import json, sys, warnings
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "stats_r1"))
import common as C
warnings.simplefilter("ignore", RuntimeWarning)
D = C.load_all(); cands = D["_cands"]
names = ["A", "B", "CO"] + list(C.CONTROLS) + ["sd_ai_welfare_poisoning", "sd_emotional_bond"]
res = {}
for tag, keep in (("six", list(range(6))), ("five", [i for i, c in enumerate(cands) if c != "anthropic"])):
    M = np.stack([np.nan_to_num(C.ovr(C.rates(D[k])[keep])).mean(1).ravel() for k in names])
    R = np.corrcoef(M)
    # split-half reliability with matched slots (even/odd s), Spearman-Brown not applied
    rel = {}
    for k in names:
        h1 = np.nan_to_num(C.ovr(C.rates(D[k][:, :, 0::2])[keep])).mean(1).ravel()
        h2 = np.nan_to_num(C.ovr(C.rates(D[k][:, :, 1::2])[keep])).mean(1).ravel()
        rel[k] = float(np.corrcoef(h1, h2)[0, 1])
    nul = [names.index(k) for k in C.CONTROLS]; sd = [names.index(k) for k in names if k.startswith("sd_")]
    a, b, co = 0, 1, 2
    nn = np.mean([R[i, j] for i in nul for j in nul if i < j])
    out = {"corr_A_B": float(R[a, b]), "null_with_A_mean": float(R[nul, a].mean()), "null_with_B_mean": float(R[nul, b].mean()),
           "null_with_A": dict(zip(C.CONTROLS, R[nul, a].round(3).tolist())), "null_with_B": dict(zip(C.CONTROLS, R[nul, b].round(3).tolist())),
           "null_with_null_mean": float(nn), "sd_with_A": R[sd, a].round(3).tolist(), "sd_with_B": R[sd, b].round(3).tolist(),
           "sd_with_sd": float(R[sd[0], sd[1]]), "sd_with_null_mean": float(R[np.ix_(sd, nul)].mean()),
           "CO_with_A": float(R[co, a]), "CO_with_B": float(R[co, b]), "CO_with_null_mean": float(R[co, nul].mean()),
           "split_half_r_evenodd": {k: round(v, 3) for k, v in rel.items()}, "sd_of_cell_means": dict(zip(names, M.std(1).round(4).tolist()))}
    res[tag] = out
    print("==", tag); print(json.dumps(out, indent=1))
(HERE / "k12_ovr_corr_matrix.json").write_text(json.dumps(res, indent=1))
