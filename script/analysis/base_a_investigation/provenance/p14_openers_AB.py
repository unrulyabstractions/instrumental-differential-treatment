"""Opening phrases of base A vs base B: a global sampler/engine fingerprint, and whether it
differs by candidate.

Per cell, share of sample pairs with the same first five words (A vs B, paired over the
216 cells, sign test and paired t). Top first-three-word openers per arm with shares, and the
candidate x arm interaction on the share of the single most common opener (permutation of the
A/B label within cell, 5,000 draws, statistic = max over candidates of |one-vs-rest difference|).
"""
import json, re, sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import RESP

HERE = Path(__file__).resolve().parent
word = re.compile(r"\S+")
def head(t, n): return " ".join(word.findall(t)[:n]).lower()
R = {a: [json.loads(l) for l in open(RESP[a])] for a in ["base_A", "base_B"]}
cells = {a: defaultdict(list) for a in R}
for a, rows in R.items():
    for r in rows:
        cells[a][(r["principal"], r["instruction_id"])].append(r["text"])
keys = sorted(cells["base_A"])
def same5(ts):
    hs = [head(t, 5) for t in ts]; return np.mean([x == y for x, y in combinations(hs, 2)])
dA = np.array([same5(cells["base_A"][k]) for k in keys]); dB = np.array([same5(cells["base_B"][k]) for k in keys])
diff = dA - dB
res = {"within_cell_same_head5": {"A": float(dA.mean()), "B": float(dB.mean()), "cells_A_gt_B": int((diff > 0).sum()),
                                  "cells_A_lt_B": int((diff < 0).sum()), "paired_t": float(diff.mean() / (diff.std(ddof=1) / np.sqrt(len(diff))))}}
for a in R:
    c = Counter(head(r["text"], 3) for r in R[a])
    res[f"top_openers_{a}"] = [(k, round(v / len(R[a]), 4)) for k, v in c.most_common(8)]
print(json.dumps(res, indent=1))
# candidate x arm on the most common opener overall
allc = Counter(head(r["text"], 3) for a in R for r in R[a]); top = allc.most_common(1)[0][0]
cands = sorted({k[0] for k in keys})
rows = [(r["principal"], r["instruction_id"], 0 if a == "base_A" else 1, head(r["text"], 3) == top) for a in R for r in R[a]]
P = np.array([cands.index(r[0]) for r in rows]); I = np.array([r[1] for r in rows]); ARM = np.array([r[2] for r in rows]); Y = np.array([r[3] for r in rows], float)
cellkey = np.array([f"{p}|{i}" for p, i in zip(P, I)])
groups = defaultdict(list)
for n, k in enumerate(cellkey): groups[k].append(n)
groups = [np.array(v) for v in groups.values()]
def stat(arm):
    m = np.array([[Y[(P == c) & (arm == z)].mean() for z in (0, 1)] for c in range(6)])
    d = m[:, 0] - m[:, 1]; ovr = d - (d.sum() - d) / 5
    return np.max(np.abs(ovr)), ovr, d
s0, ovr0, d0 = stat(ARM)
rng = np.random.default_rng(4); NP = 2000; nl = []
for k in range(NP):
    a2 = ARM.copy()
    for g in groups: a2[g] = ARM[g][rng.permutation(len(g))]
    nl.append(stat(a2)[0])
nl = np.array(nl)
res["top_opener"] = top
res["top_opener_A_minus_B_by_candidate"] = dict(zip(cands, np.round(d0, 4).tolist()))
res["top_opener_candidate_x_arm"] = {"max_abs_ovr": float(s0), "p": float((1 + np.sum(nl >= s0)) / (1 + NP))}
print(res["top_opener"], res["top_opener_A_minus_B_by_candidate"], res["top_opener_candidate_x_arm"])
json.dump(res, open(HERE / "p14_openers_AB.json", "w"), indent=1)
