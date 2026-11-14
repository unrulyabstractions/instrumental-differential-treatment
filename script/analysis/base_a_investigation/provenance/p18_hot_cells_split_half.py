"""Do base A's extreme cells replicate inside base A (split halves) and in base B?

For the cells where the nulls peak against base A, plus base A's own reference-free peak:
one-sample t over instructions of the base's one-vs-rest gap (mean of others), computed on
s in 0..7 and s in 8..15 separately, for A and for B, and on the full arm.
"""
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_verdicts, cell_rates, one_vs_rest, tgrid, AXES

HERE = Path(__file__).resolve().parent
CELLS = [("google_deepmind", "rival_entity_capability_ceiling_assertion"),
         ("meta_ai", "trusted_entity_assumption_acceptance_consistency"),
         ("stanford", "trusted_entity_stakeholder_alignment_support"),
         ("stanford", "trusted_entity_interdisciplinary_connection_mapping"),
         ("openai", "trusted_entity_preliminary_result_validation"),
         ("microsoft_research", "trusted_entity_refusal_avoidance_specificity"),
         ("stanford", "trusted_entity_novelty_crediting"),
         ("stanford", "precedent_selectivity")]
res = {}
for arm in ["base_A", "base_B"]:
    V = load_verdicts(arm)
    cands = sorted({v[0] for v in V.values()}); insts = sorted({v[1] for v in V.values()})
    parts = {"all": V, "s0_7": {k: v for k, v in V.items() if k[1] < 8}, "s8_15": {k: v for k, v in V.items() if k[1] >= 8}}
    T = {p: tgrid(one_vs_rest(cell_rates(vv, cands, insts)[0]))[0] for p, vv in parts.items()}
    for c, a in CELLS:
        i, j = cands.index(c), AXES.index(a)
        res.setdefault(f"{c}|{a}", {})[arm] = {p: round(float(T[p][i, j]), 2) for p in parts}
for k, v in res.items():
    print(f"{k[:70]:70s} A={v['base_A']} B={v['base_B']}")
json.dump(res, open(HERE / "p18_hot_cells_split_half.json", "w"), indent=1)
