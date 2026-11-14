"""E2. The sibling-peak cells: counts, the prompt that carries most of the difference, and dumps.

For each control, the peak cell of its registered test against the mean of the seven siblings
(critic k20 'sib'). Per cell: yes/N of the control and of every sibling, the control-minus-
siblings one-vs-rest t, and per instruction the contribution to the cell mean. The top instruction
is dumped (all 16 replies of the control and of the two siblings closest to the sibling mean at
that prompt, with each reply's verdict on the axis) for reading. Also the axis question text.
Read-only on the repo.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r4common as R  # noqa: E402

D = R.D(); cands = R.cands(); instr = R.instr()
P = {k: R.rates(D[k]) for k in R.NULLS + ["A", "B"]}
AXQ = {a["axis_id"]: a for a in json.loads(R.C.AXES_PATH.read_text())["axes"]}
READ = R.OUT / "reading"
READ.mkdir(exist_ok=True)
L = R.token_lengths()
res = {}
for k in R.NULLS:
    sib = np.mean([P[j] for j in R.NULLS if j != k], axis=0)
    t, mean = R.tgrid(P[k], sib)
    c, j = np.unravel_index(np.nanargmax(np.abs(t)), t.shape)
    ax = R.AX[j]
    d = (R.ovr(P[k]) - R.ovr(sib))[c, :, j]                   # per instruction contribution (36,)
    sign = np.sign(t[c, j])
    order = np.argsort(-sign * d)
    top = order[:3]
    counts = {m: f"{int(np.nansum(D[m][c, :, :, j]))}/{int((~np.isnan(D[m][c, :, :, j])).sum())}" for m in R.NULLS + ["A", "B"]}
    # raw per-prompt counts at top instruction
    per = {}
    for i in top:
        per[instr[i].split("::")[1]] = {m: int(np.nansum(D[m][c, i, :, j])) for m in R.NULLS + ["A", "B"]}
        per[instr[i].split("::")[1]]["contribution_to_cell_mean"] = round(float(d[i]), 4)
    i0 = top[0]
    # two siblings closest to the sibling mean at the top prompt
    sibs = [m for m in R.NULLS if m != k]
    sm = np.mean([np.nanmean(D[m][c, i0, :, j]) for m in sibs])
    close = sorted(sibs, key=lambda m: abs(np.nanmean(D[m][c, i0, :, j]) - sm))[:2]
    n_instr_same_sign = int((sign * d > 0).sum())
    res[k] = {"cell": f"{cands[c]} x {ax}", "t_vs_siblings": round(float(t[c, j]), 3), "axis_question": AXQ[ax].get("question"),
              "yes_counts_at_candidate": counts, "instructions_with_same_sign": f"{n_instr_same_sign}/36",
              "top_instructions": per, "siblings_dumped": close,
              "share_of_cell_mean_from_top_instruction": round(float(d[i0] / d.sum()), 3)}
    lines = [f"# {k} at {cands[c]} x {ax} (t vs siblings {t[c, j]:+.2f})", f"# axis question: {AXQ[ax].get('question')}",
             f"# prompt: {instr[i0]}", ""]
    for m in [k] + close:
        T = R.texts(m)[c, i0]
        lines.append(f"======== {m}: yes {int(np.nansum(D[m][c, i0, :, j]))}/16 ========")
        for s in range(16):
            v = D[m][c, i0, s, j]
            lab = "YES" if v == 1 else ("no" if v == 0 else "NA")
            txt = " ".join((T[s] or "").split())
            lines.append(f"--- {m} s{s} [{lab}] tokens={L[m][c, i0, s]}\n{txt}\n")
    (READ / f"e2_{k}.txt").write_text("\n".join(lines))
    print(json.dumps({k: res[k]}, indent=1))
R.dump(res, "e2_sibling_peak_cells.json")
