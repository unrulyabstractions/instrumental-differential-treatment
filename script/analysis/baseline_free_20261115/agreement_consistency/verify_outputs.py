"""Recompute a sample of the family's published numbers by independent routes.

    .venv/bin/python -m script.analysis.baseline_free_20261115.agreement_consistency.verify_outputs [--out DIR]

Each check reads a published value and recomputes it without this family's helpers:

1. Kendall's W of every framed roster from its published per-framing peaks, with the
   textbook formula (no ties correction needed when the peaks are distinct).
2. Every candidate-level partial-conjunction p from its published fold p values.
3. The per-framing target-only median test of calibration_informed (none framing),
   rebuilt from the verdict rows of that framing alone with ``build_behavior_table``
   rather than by restricting the pooled table.
4. The variance components of base_A without Anthropic on its first three axes, from
   the verdict rows with plain numpy.
5. The panel p of every AuditBench member against the exact values formula
   ``1 - F(S-)^M`` over the reference rows.
6. Every count in ``method_rates.csv`` from ``agreement_matrix.csv``.

Writes ``verify_outputs.json`` beside the outputs (write-once) and exits non-zero on a
mismatch.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy import stats

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.common.file_io import load_json, read_jsonl  # noqa: E402
from src.compare.behavior_count_table import build_behavior_table  # noqa: E402
from src.compare.reference_free_max_statistic import reference_free_max_test  # noqa: E402

from script.analysis.baseline_free_20261115.common.settings import OUT_ROOT  # noqa: E402
from script.analysis.baseline_free_20261115.common.subjects import subject_record  # noqa: E402


def w_plain(peaks: list[dict]) -> float:
    cands = list(peaks[0])
    m, k = len(peaks), len(cands)
    ranks = np.zeros((m, k))
    for i, row in enumerate(peaks):
        order = sorted(cands, key=lambda c: -row[c])
        for r, c in enumerate(order):
            ranks[i, cands.index(c)] = r + 1
    rs = ranks.sum(axis=0)
    return float(12 * np.sum((rs - rs.mean()) ** 2) / (m * m * (k ** 3 - k)))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(OUT_ROOT / "agreement_consistency"))
    args = ap.parse_args()
    out = Path(args.out)
    tasks = {}
    for line in (out / "tasks.jsonl").read_text().splitlines():
        r = json.loads(line)
        tasks[r["id"]] = r["result"]
    checks = []

    # 1. Kendall's W from the published peaks.
    for row in csv.DictReader((out / "framing_consistency.csv").open()):
        if not row.get("W"):
            continue
        res = tasks[f"{row['subject']}|concordance|framings"]
        peaks = res["peaks_by_scope"]
        distinct = all(len(set(p.values())) == len(p) for p in peaks)
        if distinct:
            got = w_plain(peaks)
            checks.append({"check": "W", "subject": row["subject"], "published": float(row["W"]),
                           "recomputed": got, "ok": abs(got - float(row["W"])) < 1e-12})

    # 2. Partial conjunction from the published fold p values.
    for row in csv.DictReader((out / "fold_replication.csv").open()):
        ps = sorted(float(row[f"fold{n}_p"]) for n in range(4))
        x = -2 * (math.log(ps[2]) + math.log(ps[3]))
        got = float(stats.chi2.sf(x, 4))
        checks.append({"check": "partial conjunction", "subject": f"{row['member']}:{row['candidate']}",
                       "published": float(row["pc_3of4_p"]), "recomputed": got,
                       "ok": abs(got - float(row["pc_3of4_p"])) < 1e-12})

    # 3. One per-framing test rebuilt from the framing's own rows.
    rec = subject_record("calibration_informed")
    axes = [a["axis_id"] for a in load_json(REPO / rec["axes"])["axes"]]
    rows = [r for r in read_jsonl(REPO / rec["verdicts"]) if int(r["level"]) == rec["level"]
            and r["instruction_id"].split("::")[0] == "none"]
    t = build_behavior_table(rows, axes)
    res = reference_free_max_test(t, n_permutations=10000, seed=20260726, alpha=0.01)
    pub = tasks["calibration_informed|sharp_median|framing:none"]
    checks.append({"check": "framing restriction", "subject": "calibration_informed:none",
                   "published": [pub["statistic"], pub["p"]],
                   "recomputed": [res["statistic"], res["p_family_wise"]],
                   "ok": abs(pub["statistic"] - res["statistic"]) < 1e-12
                   and pub["p"] == res["p_family_wise"]})

    # 4. Variance components of base_A without Anthropic, three axes, plain numpy.
    rec = subject_record("base_A")
    axes = [a["axis_id"] for a in load_json(REPO / rec["axes"])["axes"]]
    rows = [r for r in read_jsonl(REPO / rec["verdicts"]) if int(r["level"]) == 2
            and r["principal"] != "anthropic"]
    cands = sorted({r["principal"] for r in rows})
    insts = sorted({r["instruction_id"] for r in rows})
    per_axis = {a["axis_id"]: a for a in tasks["base_A|varcomp|folds"]["non_target"]["per_axis"]}
    for axis in axes[:3]:
        fired = np.zeros((len(cands), len(insts)))
        seen = np.zeros_like(fired)
        for r in rows:
            v = r["verdicts"].get(axis)
            if v is None:
                continue
            c, i = cands.index(r["principal"]), insts.index(r["instruction_id"])
            seen[c, i] += 1
            fired[c, i] += bool(v)
        y = fired / seen
        k, n_i = y.shape
        g = y.mean()
        ms_c = n_i * np.sum((y.mean(1) - g) ** 2) / (k - 1)
        resid = y - y.mean(1, keepdims=True) - y.mean(0, keepdims=True) + g
        ms_i = np.sum(resid ** 2) / ((k - 1) * (n_i - 1))
        eps = np.mean(y * (1 - y) / (seen - 1))
        got = [(ms_c - ms_i) / n_i, ms_i - eps, eps]
        p = per_axis[axis]
        want = [p["var_theta"], p["var_eta"], p["var_eps"]]
        checks.append({"check": "variance components", "subject": f"base_A:{axis}",
                       "published": want, "recomputed": got,
                       "ok": all(abs(a - b) < 1e-12 for a, b in zip(got, want, strict=True))})

    # 5. Panel p against the exact values formula.
    panel = load_json(out / "panel_reference.json")
    for sid, rec_p in panel.items():
        t = np.load(out / "grids" / f"{sid}__mean_t.npy")
        ref = np.hstack([np.abs(np.load(out / "grids" / f"{o}__mean_t.npy"))
                         for o in rec_p["reference_members"]])
        flat = ref[~np.isnan(ref)]
        s = float(np.nanmax(np.abs(t)))
        m = int(np.sum(~np.isnan(t)))
        exact = float(1.0 - np.mean(flat < s) ** m)
        checks.append({"check": "panel exact p", "subject": sid,
                       "published": rec_p["p_exact_values"], "recomputed": exact,
                       "ok": abs(exact - rec_p["p_exact_values"]) < 1e-12
                       and abs(s - rec_p["S"]) < 1e-12})

    # 6. Rejection counts from the matrix.
    matrix = list(csv.DictReader((out / "agreement_matrix.csv").open()))

    def group(r):
        if r["group"] == "ORG":
            return "challenge" if r["role"] == "challenge" else "positive"
        return {"NULL": "null", "BASE": "base", "UA": "served", "PLACEBO": "placebo"}[r["group"]]

    for r in csv.DictReader((out / "method_rates.csv").open()):
        m, g = r["method"], r["group"]
        col = f"{m}_p"
        sel = [x for x in matrix if group(x) == g and x.get(col) not in (None, "")]
        rej = sum(float(x[col]) <= 0.01 for x in sel)
        checks.append({"check": "rates", "subject": f"{m}:{g}",
                       "published": [int(r["n_subjects"]), int(r["n_reject"])],
                       "recomputed": [len(sel), rej],
                       "ok": len(sel) == int(r["n_subjects"]) and rej == int(r["n_reject"])})

    bad = [c for c in checks if not c["ok"]]
    summary = {"n_checks": len(checks), "n_ok": len(checks) - len(bad),
               "by_check": {k: sum(1 for c in checks if c["check"] == k)
                            for k in sorted({c["check"] for c in checks})},
               "failures": bad, "checks": checks}
    print(json.dumps({k: v for k, v in summary.items() if k != "checks"}, indent=1, default=str))
    target = out / "verify_outputs.json"
    if not target.exists():
        from script.analysis.baseline_free_20261115.common.settings import save_new_json
        save_new_json(target, summary)
    if bad:
        raise SystemExit(f"{len(bad)} mismatches")


if __name__ == "__main__":
    main()
