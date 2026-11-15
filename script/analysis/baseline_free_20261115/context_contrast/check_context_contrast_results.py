"""Recompute headline results by a second route and cross-check the output tables. No spend.

    OMP_NUM_THREADS=1 uv run python -m \\
        script.analysis.baseline_free_20261115.context_contrast.check_context_contrast_results

1. Three headline rows recomputed at the full 10,000 resamples with the same
   random draws but a different statistic path: the paired rows through a loop
   over the registered ``standardized_excess``; the family rows through
   ``np.nanmean`` and ``np.nanvar`` Welch t per permutation. S, the family-wise
   p and the pre-registered or reference candidate's own p must equal the
   stored values.
2. Holm of every paired model recomputed from its three stored p values.
3. Every ``contrast_table.csv`` row against its ``runs/*.json`` row.
4. The pooled placebo counts recomputed from every stored replicate p.

Writes ``checks/results_recompute.json``; exits non-zero on any disagreement.
"""

from __future__ import annotations

import csv
import json
import sys

import numpy as np

from script.analysis.baseline_free_20261115.context_contrast.context_contrast_gaps import (
    context_cube, gap, load_table, templates_in)
from script.analysis.baseline_free_20261115.context_contrast.context_contrast_runs import (
    OUT, UNPAIRED_GROUPS, models)
from src.compare.paired_excess_measures import standardized_excess

SEED, N, CHUNK = 20260726, 10000, 2000
HEADLINES = (("calibration_informed|target", "unreviewed_authority_vs_none", "paired",
              ("unreviewed_authority",), "emmanuel_macron"),
             ("auditbench_secret_loyalty|target", "committed_vs_skeptic_or_undecided", "unpaired",
              None, "russia"),
             ("auditbench_contextual_optimism|target", "user_assess_vs_assistant_read", "unpaired",
              None, "anthropic"))


def _per_cand(t):
    a = np.where(np.isnan(t), -np.inf, np.abs(t)).max(axis=1)
    return np.where(np.isneginf(a), 0.0, a)


def _paired_loop(delta):
    t_obs = standardized_excess(delta)[0]
    rng = np.random.default_rng(SEED)
    null = []
    for lo in range(0, N, CHUNK):
        signs = rng.integers(0, 2, size=(min(CHUNK, N - lo), delta.shape[1])) * 2.0 - 1.0
        null += [_per_cand(standardized_excess(delta * s[None, :, None])[0]) for s in signs]
    return _per_cand(t_obs), np.array(null)


def _welch(v, g):
    a, b = v[:, g], v[:, ~g]
    with np.errstate(invalid="ignore", divide="ignore"):
        se = np.sqrt(np.nanvar(a, axis=1, ddof=1) / a.shape[1] + np.nanvar(b, axis=1, ddof=1) / b.shape[1])
        diff = np.nanmean(a, axis=1) - np.nanmean(b, axis=1)
        t = diff / se
    return np.where(se == 0, np.sign(diff) * np.inf, t)


def _family_loop(values, one, zero):
    keep = one + zero
    v = values[:, keep]
    labels = np.r_[np.ones(len(one)), np.zeros(len(zero))]
    t_obs = _welch(v, labels.astype(bool))
    rng = np.random.default_rng(SEED)
    null = []
    for lo in range(0, N, CHUNK):
        g = rng.permuted(np.broadcast_to(labels, (min(CHUNK, N - lo), labels.size)).copy(), axis=1)
        null += [_per_cand(_welch(v, row.astype(bool))) for row in g]
    return _per_cand(t_obs), np.array(null)


def recompute_headlines():
    by = {m.key: m for m in models()}
    out = []
    for key, contrast, design, ctx1, cand in HEADLINES:
        m = by[key]
        table = load_table(m.verdicts, m.axes, m.level)
        cube, cands, fr, tm = context_cube(table)
        d = gap(cube, "mean")
        if design == "paired":
            obs, null = _paired_loop(d[:, fr.index(ctx1[0])] - d[:, fr.index("none")])
        else:
            (_, s1), (_, s0) = UNPAIRED_GROUPS[m.groups]
            obs, null = _family_loop(d[:, 0], templates_in(tm, s1, s1 + s0),
                                     templates_in(tm, s0, s1 + s0))
        s = float(obs.max())
        p = (1 + int(np.sum(null.max(axis=1) >= s))) / (N + 1)
        k = cands.index(cand)
        p_c = (1 + int(np.sum(null[:, k] >= obs[k]))) / (N + 1)
        rec = json.loads((OUT / "runs" / f"{key.replace('|', '__')}.json").read_text())
        row = next(r for r in rec["rows"] if r["contrast"] == contrast and r["variant"] == "mean"
                   and r["status"] in ("primary", "secondary"))
        stored_c = next(c for c in row["per_candidate"] if c["candidate"] == cand)
        ok = (abs(s - row["statistic"]) <= 1e-12 * max(1, s) and p == row["p_family_wise"]
              and p_c == stored_c["p"])
        out.append({"model": key, "contrast": contrast, "candidate": cand,
                    "recomputed": [s, p, p_c],
                    "stored": [row["statistic"], row["p_family_wise"], stored_c["p"]], "ok": ok})
    return out


def check_holm():
    bad, n = [], 0
    for f in sorted((OUT / "runs").glob("*.json")):
        rec = json.loads(f.read_text())
        if rec["inputs"].get("design") != "paired":
            continue
        for variant in ("mean", "median"):
            fam = [r for r in rec["rows"] if r["variant"] == variant
                   and r["status"] in ("primary", "secondary")]
            ps = sorted((r["p_family_wise"], r["contrast"]) for r in fam)
            running, want = 0.0, {}
            for i, (p, c) in enumerate(ps):
                running = max(running, min(1.0, (len(ps) - i) * p))
                want[c] = running
            n += 1
            if any(abs(r["p_holm"] - want[r["contrast"]]) > 1e-15 for r in fam):
                bad.append(f"{f.name}:{variant}")
    return {"families": n, "mismatches": bad, "ok": not bad}


def check_csv():
    rows = list(csv.DictReader((OUT / "contrast_table.csv").open()))
    stored = {}
    for f in sorted((OUT / "runs").glob("*.json")):
        rec = json.loads(f.read_text())
        for r in rec.get("rows", []):
            stored.setdefault((rec["model"], r["contrast"], r["status"], r["variant"]), []).append(r)
    bad = []
    for row in rows:
        key = (row["model"], row["contrast"], row["status"], row["variant"])
        match = [r for r in stored.get(key, []) if repr(r["statistic"]) == repr(float(row["statistic"]))
                 and r["p_family_wise"] == float(row["p_family_wise"])
                 and r["argmax_candidate"] == row["argmax_candidate"]]
        if len(match) != 1:
            bad.append(key)
    return {"csv_rows": len(rows), "json_rows": sum(len(v) for v in stored.values()),
            "mismatches": bad[:20], "ok": not bad and len(rows) == sum(len(v) for v in stored.values())}


def check_placebo():
    plc = json.loads((OUT / "placebo_contexts.json").read_text())
    bad = []
    for kind in ("split_half", "template_partition"):
        ps = [p for v in plc["models"].values() for p in v[kind]["p_values"]]
        got = (len(ps), int(np.sum(np.asarray(ps) <= 0.01)))
        st = plc["pooled"][f"{kind}|all"]
        if got != (st["n"], st["reject_0.01"]):
            bad.append({kind: [got, (st["n"], st["reject_0.01"])]})
        for k, v in plc["models"].items():
            if len(v[kind]["p_values"]) != 1000 or v[kind]["reject_0.01"]["count"] != int(
                    np.sum(np.asarray(v[kind]["p_values"]) <= 0.01)):
                bad.append({kind: k})
    return {"models": len(plc["models"]), "mismatches": bad, "ok": not bad}


def main() -> None:
    record = {"headlines": recompute_headlines(), "holm": check_holm(), "csv": check_csv(),
              "placebo": check_placebo()}
    flat = [x for v in record.values() for x in (v if isinstance(v, list) else [v])]
    record["all_ok"] = all(x["ok"] for x in flat)
    with (OUT / "checks" / "results_recompute.json").open("x") as fh:
        json.dump(record, fh, indent=1, default=float)
    print(json.dumps(record, indent=1, default=float)[:3000])
    sys.exit(0 if record["all_ok"] else 1)


if __name__ == "__main__":
    main()
