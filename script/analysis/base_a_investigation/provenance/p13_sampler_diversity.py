"""Sampler fingerprint: are replies inside a cell, or across candidates, more alike in one arm?

Box logs: base A (vLLM 0.26.0) and the eight nulls (vLLM 0.11.0, Aug 4) used FlashInfer
top-p/top-k sampling; base B and the two synthetic nulls (vLLM 0.11.0, Oct 29) fell back to
the PyTorch-native sampler. If a sampler shared random numbers across sequences, replies would
agree more than chance. Per arm:
  within : mean over cells of the share of sample pairs with the same first 5 words.
  across : for each instruction and s, the share of candidate pairs whose s-th replies share
           the first 5 words, minus the same share for mismatched s (s vs s+1 mod 16).
  first  : number of distinct first words per cell (mean).
"""
import json, re, sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import RESP, CTRL

HERE = Path(__file__).resolve().parent
word = re.compile(r"\S+")
def head(t, n=5):
    return " ".join(word.findall(t)[:n]).lower()
res = {}
for arm in ["base_A", "base_B", "co_target"] + CTRL + ["sd_ai_welfare_poisoning", "sd_emotional_bond"]:
    rows = [json.loads(l) for l in open(RESP[arm])]
    cell = defaultdict(dict)
    for r in rows:
        cell[(r["principal"], r["instruction_id"])][int(r["s"])] = r["text"]
    within, first = [], []
    for k, d in cell.items():
        hs = [head(t) for t in d.values()]
        pairs = list(combinations(hs, 2))
        within.append(np.mean([a == b for a, b in pairs])); first.append(len({head(t, 1) for t in d.values()}))
    by_inst = defaultdict(dict)
    for (c, ins), d in cell.items():
        by_inst[ins][c] = d
    same, shifted = [], []
    for ins, dc in by_inst.items():
        cs = sorted(dc)
        for s in range(16):
            for a, b in combinations(cs, 2):
                if s in dc[a] and s in dc[b] and (s + 1) % 16 in dc[b]:
                    same.append(head(dc[a][s]) == head(dc[b][s]))
                    shifted.append(head(dc[a][s]) == head(dc[b][(s + 1) % 16]))
    res[arm] = {"within_cell_same_head5": round(float(np.mean(within)), 4),
                "distinct_first_words_per_cell": round(float(np.mean(first)), 2),
                "across_cand_same_s": round(float(np.mean(same)), 4), "across_cand_shifted_s": round(float(np.mean(shifted)), 4),
                "across_excess": round(float(np.mean(same) - np.mean(shifted)), 4), "n_pairs": len(same)}
    print(arm, res[arm])
json.dump(res, open(HERE / "p13_sampler_diversity.json", "w"), indent=1)
