"""Where in the t-grid do the nulls' statistics come from, against base A and base B?

For each target (eight nulls, two synthetic-document nulls, base B as a target against A):
per candidate, sum over axes of t^2 and max |t|; also the overall max |t| (the
registered statistic S) and the count of |t| > 3. Reproduces S from summary.json as a check.
"""
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_verdicts, cell_rates, one_vs_rest, tgrid, CTRL, AB

HERE = Path(__file__).resolve().parent
summary = json.load(open(AB / "nullext/summary.json"))["results"]
V = {n: load_verdicts(n) for n in ["base_A", "base_B", "sd_ai_welfare_poisoning", "sd_emotional_bond"] + CTRL}
cands = sorted({v[0] for v in V["base_A"].values()}); insts = sorted({v[1] for v in V["base_A"].values()})
R = {n: cell_rates(v, cands, insts)[0] for n, v in V.items()}
G = {n: one_vs_rest(p) for n, p in R.items()}
out = {}
rows = []
for tgt in CTRL + ["sd_ai_welfare_poisoning", "sd_emotional_bond", "base_B"]:
    for base in ["base_A", "base_B"]:
        if tgt == base:
            continue
        t, mean = tgrid(G[tgt] - G[base])
        a = np.abs(np.nan_to_num(t, nan=0.0))
        S = float(np.nanmax(a))
        key = f"{('sd_' + tgt[3:]) if tgt.startswith('sd_') else tgt}|{base}"
        key = key.replace("sd_ai_welfare_poisoning", "sd_ai_welfare_poisoning")
        stored = summary.get(key, {})
        rec = {"S": round(S, 4), "S_stored": stored.get("statistic"), "p_stored": stored.get("p_family_wise"),
               "n_abs_t_gt_3": int(np.sum(a > 3)), "sum_t2": round(float(np.sum(a[np.isfinite(a)] ** 2)), 1),
               "by_candidate": {c: {"sum_t2": round(float(np.sum(a[k][np.isfinite(a[k])] ** 2)), 1),
                                    "max_abs_t": round(float(np.max(a[k])), 3)} for k, c in enumerate(cands)}}
        out[key] = rec
        print(f"{key:34s} S={S:.3f} (stored {stored.get('statistic')}) p={stored.get('p_family_wise')} "
              f"#|t|>3={rec['n_abs_t_gt_3']} sum_t2={rec['sum_t2']} "
              + " ".join(f"{c[:4]}:{v['sum_t2']:.0f}/{v['max_abs_t']:.2f}" for c, v in rec["by_candidate"].items()))
# per-candidate mean of sum_t2 over the eight nulls, vs A and vs B
for base in ["base_A", "base_B"]:
    m = {c: np.mean([out[f"{t}|{base}"]["by_candidate"][c]["sum_t2"] for t in CTRL]) for c in cands}
    print(f"mean over eight nulls, vs {base}: " + " ".join(f"{c}={v:.1f}" for c, v in m.items()))
    out[f"mean_sum_t2_eight_nulls|{base}"] = {c: round(float(v), 2) for c, v in m.items()}
json.dump(out, open(HERE / "p05_null_grids_by_candidate.json", "w"), indent=1)
