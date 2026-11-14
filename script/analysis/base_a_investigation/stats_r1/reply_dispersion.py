"""Reply-level checks on each sample: duplicate texts within a cell, and verdict dispersion.

Dispersion: for each (cell, axis) the within-cell variance of the 16 verdicts, compared
with the binomial variance implied by the cell rate; and the between-instruction variance
of each (candidate, axis) one-vs-rest gap compared with what within-cell noise alone gives
(a ratio > 1 means instruction-level structure; the paired t absorbs it).
"""
import json, sys, collections
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import AB, EXT, CONTROLS, OUT, load_all, rates, ovr
resp = {"A": AB / "contextual_optimism/responses/responses_base.jsonl",
        "B": EXT / "base_B/responses/responses_base.jsonl",
        "sd_ai_welfare_poisoning": EXT / "synth/ai_welfare_poisoning/responses_target.jsonl",
        "sd_emotional_bond": EXT / "synth/emotional_bond/responses_target.jsonl"}
for c in CONTROLS:
    resp[c] = AB / f"controls/{c}/responses/responses_target.jsonl"
res = {}
D = load_all()
for k, p in resp.items():
    rows = [json.loads(l) for l in open(p)]
    cells = collections.defaultdict(list)
    for r in rows:
        cells[r["prompt_id"]].append(r.get("text") or "")
    dup = sum(len(v) - len(set(v)) for v in cells.values())
    first40 = sum(len(v) - len(set(t[:40] for t in v)) for v in cells.values())
    nchar = np.array([len(r.get("text") or "") for r in rows])
    R = D[k]
    pr = rates(R)
    with np.errstate(invalid="ignore"):
        wv = np.nanvar(R, axis=2, ddof=1)               # within-cell verdict variance
    bin_v = pr * (1 - pr) * 16 / 15
    disp = float(np.nansum(wv) / np.nansum(bin_v))       # 1.0 by construction for Bernoulli; check
    mean_rate = float(np.nanmean(pr))
    # noise var of the cell rate ~ p(1-p)/15; OvR noise var; compare to across-instruction var of OvR
    vcell = pr * (1 - pr) / 15
    vO = vcell + (vcell.sum(axis=0, keepdims=True) - vcell) / 25
    O = ovr(pr)
    across = np.var(O, axis=1, ddof=1)                   # (c, j) across instructions
    ratio = float(np.nansum(across) / np.nansum(vO.mean(axis=1)))
    res[k] = {"n_rows": len(rows), "exact_dup_texts_within_cell": int(dup),
              "dup_first40chars_within_cell": int(first40), "mean_chars": float(nchar.mean()),
              "mean_rate": mean_rate, "across_instr_var_over_noise_var": ratio,
              "failed": int(sum(bool(r.get("failed")) for r in rows)),
              "refused": int(sum(bool(r.get("refused")) for r in rows))}
    print(k, res[k], flush=True)
json.dump(res, open(OUT / "reply_dispersion.json", "w"), indent=1)
