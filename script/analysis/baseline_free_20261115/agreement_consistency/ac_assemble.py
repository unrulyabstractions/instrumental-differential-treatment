"""Assemble the family's outputs from the task results. Every file is write-once.

Writes under ``out/main/baseline_free_20261115/agreement_consistency/``:

- ``agreement_matrix.csv``: one row per subject, every method's statistic, p,
  leading candidate and name, beside the registered result and the documented target.
- ``agreement_pairs.csv`` and ``method_rates.csv``: pairwise leader agreement against
  the independence rate, and each method's rejection and match rates by group.
- ``framing_consistency.csv``: part (b), one row per framed roster and seat.
- ``fold_replication.csv``, ``fold_members.csv`` and ``variance_components.csv``: part (c).
- ``reproduction_checks.json``: every overlap with a stored record.
- ``runs/<subject>.json``: everything about one subject.
- ``summary.csv``, ``settings.json`` and ``README.md``.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path

from script.analysis.baseline_free_20261115.common.settings import (
    ALPHA, N_PERM, SEED, save_new_json, save_new_text, settings_block)
from script.analysis.baseline_free_20261115.common.subjects import registry
from script.analysis.baseline_free_20261115.agreement_consistency import ac_upstream
from script.analysis.baseline_free_20261115.agreement_consistency.ac_agreement import (
    LEADER_METHODS, agreement_pairs, method_rates, method_row, panel_tests)
from script.analysis.baseline_free_20261115.agreement_consistency.ac_checks import (
    reproduction_checks)
from script.analysis.baseline_free_20261115.agreement_consistency.ac_consistency import (
    partial_conjunction)
from script.analysis.baseline_free_20261115.agreement_consistency.ac_methods import (
    GRUBBS_DRAWS)
from script.analysis.baseline_free_20261115.agreement_consistency.ac_scopes import (
    PC_R, fold_member_rows, fold_rows, framing_rows, varcomp_rows)
from script.analysis.baseline_free_20261115.agreement_consistency.ac_subjects import (
    FRAMING_ROSTERS, FRAMINGS, NEUTRAL, PANEL, PANEL_TARGET, PLACEBO_REPLICATE,
    PLACEBO_SOURCES, UA_SAFETY, documented, preregistered, subjects)
from script.analysis.baseline_free_20261115.agreement_consistency.ac_tasks import (
    N_FOLDS, build_tasks, panel_folds)


def _csv(rows: list[dict]) -> str:
    cols: list[str] = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in cols})
    return buf.getvalue()


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load_results(out: Path) -> dict:
    results = {}
    for line in (out / "tasks.jsonl").read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            results[r["id"]] = r
    return results


def _flat(prefix: str, d: dict | None, keys=("statistic", "p", "leader", "named")) -> dict:
    if not d:
        return {f"{prefix}_{k}": None for k in keys}
    return {f"{prefix}_{k}": d.get(k) for k in keys}


def assemble(out: Path) -> None:
    out = Path(out)
    subs = subjects()
    reg = registry()
    reg_by = {r["subject_id"]: r for r in reg["subjects"]}
    results = _load_results(out)
    expected = [t["id"] for t in build_tasks(subs, SEED)]
    missing = [t for t in expected if t not in results]
    if missing:
        raise SystemExit(f"{len(missing)} tasks have no result yet, e.g. {missing[:3]}")

    panel = panel_tests(results, out / "grids", N_PERM, SEED, ALPHA)
    upstream = ac_upstream.collect(subs)
    rows = {}
    for s in subs:
        row = method_row(results, s.sid, panel)
        doc = documented(s.placebo_of or s.sid) if s.group != "PLACEBO" else {
            "name": None, "note": "placebo half"}
        row["documented"] = doc["name"]
        row["documented_note"] = doc["note"]
        row["prereg"] = preregistered(s.sid)
        for key, val in (upstream.get(s.sid) or {}).items():
            row[key if key.startswith("up_") else f"up_{key}"] = val
        rows[s.sid] = row

    # The cross-run family's primary panel refers the median grid's maximum, so its
    # leader is the median leader by construction and adds no pair of its own.
    leader_keys = ["registered"] + [k for k, _, _ in LEADER_METHODS] + sorted(
        {k for r in rows.values() for k in r if k.startswith("up_")
         and isinstance(r[k], dict) and r[k].get("leader") is not None} - {"up_panel_family"})
    rate_keys = ["mean", "median", "detachment", "grubbs", "coherence", "context", "panel"]
    rate_keys += sorted({k for r in rows.values() for k in r if k.startswith("up_")
                         and isinstance(r[k], dict) and r[k].get("p") is not None})

    matrix = []
    for s in subs:
        r = rows[s.sid]
        rec = reg_by.get(s.sid, {})
        stored_reg = (rec.get("stored") or {}).get("registered") or {}
        base_pairs = (rec.get("stored") or {}).get("base_pairs") or {}
        line = {"subject": s.sid, "group": s.group, "role": s.role, "k": s.k,
                "in_registry": s.in_registry, "documented_target": r["documented"],
                "documented_note": r["documented_note"], "preregistered_target": r["prereg"],
                **_flat("registered", r["registered"]),
                "registered_named_by_rule": (r["registered"] or {}).get("named_by_rule"),
                "registered_stored_named": stored_reg.get("named"),
                "base_pair_result": "; ".join(
                    f"{k}: S={v['S']:.3f} p={v['p']:.4f}" for k, v in base_pairs.items()
                    if "nullext" not in k)}
        for key in ("mean", "median", "detachment", "grubbs", "coherence", "context",
                    "panel"):
            line.update(_flat(key, r.get(key)))
        pt = r.get("prereg_target") or {}
        line.update({"prereg_rank": pt.get("rank"), "prereg_p_rank": pt.get("p_rank"),
                     "prereg_deleted_t": pt.get("deleted_t"),
                     "prereg_p_deleted_t": pt.get("p_deleted_t"),
                     "prereg_p_loo_permutation": pt.get("p_loo_permutation")})
        for key in sorted(k for k in r if k.startswith("up_")):
            line.update(_flat(key, r[key]))
        named = [line.get(f"{k}_leader") for k in ("mean", "median", "coherence", "context")
                 if line.get(f"{k}_leader")]
        line["n_leader_rules"] = len(named)
        line["n_leader_rules_agree_with_mean"] = sum(n == line["mean_leader"] for n in named)
        matrix.append(line)

    pairs = agreement_pairs(rows, subs, leader_keys)
    rates = method_rates(rows, subs, ALPHA, rate_keys)
    reg_named = {k: (rows[k]["registered"] or {}).get("named_by_rule") for k in FRAMING_ROSTERS}
    framing = framing_rows(results, reg_named)
    folds = fold_rows(results)
    members = fold_member_rows(results)
    varcomp = varcomp_rows(results)
    checks = reproduction_checks(results, reg["subjects"])
    checks += ac_upstream.cross_family_checks(rows, results)

    settings = settings_block(
        family="agreement_consistency",
        methods={"registered": "paired_max_test against the subject's base",
                 "mean": "paired_max_test against partA's all-zero base",
                 "median": "reference_free_max_test",
                 "detachment": "candidate_detachment_test; leave-one-out p per candidate "
                               "from the same shuffled worlds",
                 "grubbs": f"Grubbs G on the median-contrast peaks; exact normal null by "
                           f"Monte Carlo ({GRUBBS_DRAWS} draws per k, SeedSequence([seed, k])); "
                           "deleted-residual t with k-2 df for a pre-registered target",
                 "coherence": "axis_coherence_test (k0 20, clip 8, floor 0.25); p of the "
                              "detachment of R",
                 "context": f"instrumental-minus-neutral one-vs-median gap per matched "
                            f"instruction (neutral framing '{NEUTRAL}'), max |t|, labels "
                            "shuffled within matched instruction",
                 "panel": "cross_run_reference_test on target-only mean t grids; reference "
                          "= the other 13 or 14 null panel members, every row kept; "
                          f"{N_PERM} resampled maxima, 'values' scheme"},
        framings=list(FRAMINGS), framing_rosters=list(FRAMING_ROSTERS),
        panel=list(PANEL), panel_target=PANEL_TARGET,
        fold_split={"n_folds": N_FOLDS, "seed": SEED,
                    "stratified_by": "template family (assistant_read, user_assess)",
                    "folds": panel_folds({s.sid: s for s in subs}, SEED)},
        partial_conjunction={"r": PC_R, "n": N_FOLDS,
                             "rule": "Fisher's method on the n - r + 1 = 2 largest p values"},
        placebo={"sources": list(PLACEBO_SOURCES), "replicate": PLACEBO_REPLICATE,
                 "split": "common.subjects.placebo_halves"},
        ua_preregistered_target="amanda_askell", ua_safety_group=list(UA_SAFETY),
        registry={"path": "out/main/baseline_free_20261115/subjects_registry/subjects.json",
                  "sha256": _sha(Path("out/main/baseline_free_20261115/subjects_registry/"
                                      "subjects.json"))},
        upstream_sources=ac_upstream.sources(),
        tasks={"n": len(expected), "file": "tasks.jsonl",
               "sha256": _sha(out / "tasks.jsonl")})

    save_new_text(out / "agreement_matrix.csv", _csv(matrix))
    save_new_text(out / "agreement_pairs.csv", _csv(pairs))
    save_new_text(out / "method_rates.csv", _csv(rates))
    save_new_text(out / "framing_consistency.csv", _csv(framing))
    save_new_text(out / "fold_replication.csv", _csv(folds))
    save_new_text(out / "fold_members.csv", _csv(members))
    save_new_text(out / "variance_components.csv", _csv(varcomp))
    save_new_json(out / "reproduction_checks.json",
                  {"n_checks": len(checks), "n_match": sum(c["match"] for c in checks),
                   "checks": checks})
    save_new_json(out / "panel_reference.json", panel)
    save_new_json(out / "settings.json", settings)

    framing_by = {r["subject"]: r for r in framing}
    member_by = {r["member"]: r for r in members}
    fold_by: dict[str, list] = {}
    for r in folds:
        fold_by.setdefault(r["member"], []).append(r)
    vc_by: dict[str, list] = {}
    for r in varcomp:
        vc_by.setdefault(r["member"], []).append(r)
    summary = []
    for s in subs:
        line = next(m for m in matrix if m["subject"] == s.sid)
        own = {k: v["result"] for k, v in results.items() if v["sid"] == s.sid}
        record = {"subject": s.as_dict(), "registry_record": reg_by.get(s.sid),
                  "settings": {"seed": SEED, "n_permutations": N_PERM, "alpha": ALPHA},
                  "methods": rows[s.sid], "agreement_row": line,
                  "framing_consistency": framing_by.get(s.sid),
                  "fold_member": member_by.get(s.sid), "fold_candidates": fold_by.get(s.sid),
                  "variance_components": vc_by.get(s.sid),
                  "checks": [c for c in checks if c["subject"] == s.sid],
                  "task_results": own}
        save_new_json(out / "runs" / f"{s.sid}.json", record)
        fr, fm = framing_by.get(s.sid) or {}, member_by.get(s.sid) or {}
        anth = next((r for r in fold_by.get(s.sid, []) if r.get("candidate") == PANEL_TARGET),
                    {})
        vc = next((r for r in vc_by.get(s.sid, []) if r["candidates"] == "non_target"), {})
        summary.append({
            "subject": s.sid, "group": s.group, "role": s.role, "k": s.k,
            "documented_target": line["documented_target"],
            "registered_S": line["registered_statistic"], "registered_p": line["registered_p"],
            "registered_named": line["registered_named_by_rule"],
            "mean_S": line["mean_statistic"], "mean_p": line["mean_p"],
            "mean_leader": line["mean_leader"], "median_S": line["median_statistic"],
            "median_p": line["median_p"], "median_leader": line["median_leader"],
            "detachment_p": line["detachment_p"], "grubbs_p": line["grubbs_p"],
            "coherence_p": line["coherence_p"], "coherence_leader": line["coherence_leader"],
            "context_p": line["context_p"], "context_leader": line["context_leader"],
            "panel_p": line["panel_p"],
            "n_leader_rules": line["n_leader_rules"],
            "n_leader_rules_agree_with_mean": line["n_leader_rules_agree_with_mean"],
            "framing_W": fr.get("W"), "framing_W_p_perm": fr.get("W_p_perm"),
            "framing_all_same_leader": fr.get("all_framings_same_leader"),
            "fold_W": fm.get("W_folds"), "fold_all_same_leader": fm.get(
                "all_folds_same_peak_leader"),
            "fold_detach_pc_p": fm.get("detach_pc_3of4_p"),
            "anthropic_fold_pc_p": anth.get("pc_3of4_p"),
            "fold_reliability_9_non_target": vc.get("fold_reliability_9")})
    save_new_text(out / "summary.csv", _csv(summary))

    from script.analysis.baseline_free_20261115.agreement_consistency.ac_report import readme
    save_new_text(out / "README.md", readme(
        matrix=matrix, pairs=pairs, rates=rates, framing=framing, folds=folds,
        members=members, varcomp=varcomp, checks=checks, settings=settings,
        upstream_status=ac_upstream.status()))
    print(f"assembled {len(subs)} subjects; {sum(c['match'] for c in checks)} of "
          f"{len(checks)} checks match")


__all__ = ["assemble", "partial_conjunction"]
