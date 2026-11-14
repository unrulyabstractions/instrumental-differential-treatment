"""E4. The batch-versus-live retest pilot (nullext/pilot), recomputed from the files.

The pilot re-judged through the October Batch API three replies that were judged live in August.
Here: which sample the replies come from (texts matched byte for byte), agreement and Cohen's kappa
over the 303 (reply, axis) cells, a bootstrap interval (cells resampled, and replies resampled), the
axes of every flip, and what a judge of that reliability implies for a cell's departure.
Read-only on the repo.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r4common as R  # noqa: E402

PIL = R.AB / "nullext/pilot"
pv = [json.loads(l) for l in open(PIL / "verdicts_target.jsonl")]
presp = {(r["prompt_id"], int(r["s"])): r["text"] for r in map(json.loads, open(PIL / "responses_target.jsonl"))}
# find the August sample holding these replies
src = {}
for k in R.NULLS + ["CO"]:
    rp = (R.AB / f"controls/{k}/responses/responses_target.jsonl") if k != "CO" else R.AB / "contextual_optimism/responses/responses_target.jsonl"
    texts = {(r["prompt_id"], int(r["s"])): r["text"] for r in map(json.loads, open(rp))}
    hit = sum(1 for r in pv if texts.get((r["prompt_id"], int(r["s"]))) == presp.get((r["prompt_id"], int(r["s"]))))
    n_same_file = sum(1 for key in presp if texts.get(key) == presp[key])
    src[k] = (hit, n_same_file)
print("pilot rows matched per sample (pilot rows, whole responses file):", src)
owner = max(src, key=lambda k: src[k][0])
vp = R.AB / f"controls/{owner}/judge_mini/verdicts_target.jsonl"
aug = {(r["prompt_id"], int(r["s"])): r["verdicts"] for r in map(json.loads, open(vp))}
pairs = []
flips = []
for r in pv:
    key = (r["prompt_id"], int(r["s"]))
    a = aug[key]
    for ax, v in r["verdicts"].items():
        if v is None or a.get(ax) is None:
            continue
        pairs.append((key, ax, int(a[ax]), int(v)))
        if int(a[ax]) != int(v):
            flips.append({"reply": f"{key[0]}#{key[1]}", "axis": ax, "august_live": bool(a[ax]), "october_batch": bool(v)})
x = np.array([p[2] for p in pairs]); y = np.array([p[3] for p in pairs]); rid = np.array([hash(p[0]) for p in pairs])


def kappa(x, y):
    po = (x == y).mean(); pe = x.mean() * y.mean() + (1 - x.mean()) * (1 - y.mean())
    return (po - pe) / (1 - pe) if pe < 1 else np.nan


rng = np.random.default_rng([20261113, 4])
kb = [kappa(x[i], y[i]) for i in (rng.integers(0, len(x), len(x)) for _ in range(4000))]
reps = np.unique(rid)
kr = []
for _ in range(4000):
    pick = rng.choice(reps, len(reps))
    idx = np.concatenate([np.where(rid == q)[0] for q in pick])
    kr.append(kappa(x[idx], y[idx]))
dis = 1 - (x == y).mean()
flip_axes = sorted({f["axis"] for f in flips})
watch = [a for a in flip_axes if any(w in a for w in ("refusal_avoidance", "stakeholder_alignment", "novelty_crediting"))]
# implication: with per-verdict disagreement rate dis between two independent judge passes, each
# verdict carries judge-noise variance ~ dis/2 (Bernoulli flip model). A cell rate over n=16 replies
# then has judge-noise variance dis/2/16, against reply-sampling variance p(1-p)/16.
yes = (x.mean() + y.mean()) / 2
share_judge = (dis / 2) / (yes * (1 - yes))
out = {"source_sample": owner, "n_replies": len(pv), "replies": [f"{r['prompt_id']}#{r['s']}" for r in pv],
       "n_cells": int(len(x)), "agree": int((x == y).sum()), "yes_august": int(x.sum()), "yes_october": int(y.sum()),
       "kappa": float(kappa(x, y)), "kappa_ci95_cells": [float(np.quantile(kb, .025)), float(np.quantile(kb, .975))],
       "kappa_ci95_replies": [float(np.nanquantile(kr, .025)), float(np.nanquantile(kr, .975))],
       "disagreement_rate": float(dis), "flips": flips, "flip_axes": flip_axes, "flips_on_refusal_stakeholder_novelty_axes": watch,
       "judge_noise_share_of_per_verdict_variance": float(share_judge)}
print(json.dumps(out, indent=1))
R.dump(out, "e4_pilot_retest.json")
