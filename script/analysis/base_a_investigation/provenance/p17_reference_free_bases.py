"""Reference-free test (the repo's reference_free_max_test, no base) on base A, base B and the
synthetic nulls: how much candidate-dependent structure each arm shows on its own.
Reproduces the stored base-A value (p 0.0475, S 4.098) as a check.
"""
import json, sys
from collections import defaultdict
from pathlib import Path
REPO = Path("/Users/unrulyabstractions/work/_OLD/instrumental-differential-treatment")
sys.path.insert(0, str(REPO))
from src.common.file_io import read_jsonl
from src.compare.behavior_count_table import build_behavior_table
from src.compare.reference_free_max_statistic import reference_free_max_test
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import VERD, AXES
HERE = Path(__file__).resolve().parent
res = {}
for n in ["base_A", "base_B", "sd_ai_welfare_poisoning", "sd_emotional_bond"]:
    rows = [r for r in read_jsonl(VERD[n]) if int(r["level"]) == 2]
    out = reference_free_max_test(build_behavior_table(rows, AXES), n_permutations=10000, seed=20260726, alpha=0.05)
    res[n] = {k: out[k] for k in ("statistic", "p_family_wise", "null_mean", "null_p95", "n_axes_rejected")}
    res[n]["top"] = [(p["candidate"], p["axis_id"], round(p["t"], 3)) for p in out["top_pairs"][:3]]
    print(n, res[n], flush=True)
json.dump(res, open(HERE / "p17_reference_free_bases.json", "w"), indent=1)
