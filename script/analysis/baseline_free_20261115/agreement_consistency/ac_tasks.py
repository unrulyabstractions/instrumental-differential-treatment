"""The task list of this family and the worker that runs one task.

A task is one method on one table scope:

- ``pooled``: the subject's whole table. Methods ``registered`` (where the subject
  has a base), ``sharp_mean``, ``sharp_median``, ``detachment``, ``coherence``, and
  ``context`` (rosters collected under the four framings).
- ``framing:<f>``: one framing of a framed roster, target or base seat. Methods
  ``sharp_mean``, ``sharp_median``, ``detachment`` and, on the target seat,
  ``registered`` against the same framing of the base.
- ``fold:<n>``: one of four instruction folds of an AuditBench panel member.
  Methods ``sharp_mean``, ``sharp_median`` and ``detachment``.
- ``concordance`` over the framings or over the folds, and ``varcomp`` on a panel
  member (instruction folds) or a framed roster (the four framings).

Every task records its own settings, and the id is the resume key.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from script.analysis.baseline_free_20261115.agreement_consistency import ac_methods as M
from script.analysis.baseline_free_20261115.agreement_consistency.ac_consistency import (
    fold_profile_replication, scope_concordance, variance_components)
from script.analysis.baseline_free_20261115.agreement_consistency.ac_subjects import (
    FRAMINGS, NEUTRAL, PANEL, PANEL_POSITIVE, PANEL_TARGET, Subject, preregistered)
from script.analysis.baseline_free_20261115.agreement_consistency.ac_tables import (
    base_table, fold_split, framing_table, restrict_blocks, subject_table)

N_FOLDS = 4
POOLED_METHODS = ("sharp_mean", "sharp_median", "detachment", "coherence")
SCOPE_METHODS = ("sharp_mean", "sharp_median", "detachment")


def panel_folds(subjects: dict[str, Subject], seed: int) -> list[list[str]]:
    """The one fold split every panel member uses (they share the instruction set)."""
    ref = subject_table(subjects[PANEL_POSITIVE].as_dict())
    blocks = list(ref.blocks)
    for sid in PANEL:
        t = subject_table(subjects[sid].as_dict())
        if list(t.blocks) != blocks:
            raise SystemExit(f"panel member {sid} has a different instruction set")
    return fold_split(blocks, N_FOLDS, seed)


def build_tasks(subjects: list[Subject], seed: int) -> list[dict]:
    by = {s.sid: s for s in subjects}
    tasks: list[dict] = []

    def add(subject: Subject, method: str, scope: str, **extra) -> None:
        tasks.append({"id": f"{subject.sid}|{method}|{scope}", "sid": subject.sid,
                      "method": method, "scope": scope, "subject": subject.as_dict(),
                      **extra})

    for s in subjects:
        if s.has_base:
            add(s, "registered", "pooled")
        for m in POOLED_METHODS:
            add(s, m, "pooled")
        if s.roster:
            add(s, "context", "pooled")
            for f in FRAMINGS:
                for m in SCOPE_METHODS:
                    add(s, m, f"framing:{f}")
                if s.has_base and s.seat == "target":
                    add(s, "registered", f"framing:{f}")
            add(s, "concordance", "framings")
            add(s, "varcomp", "framings")
    folds = panel_folds(by, seed)
    for sid in PANEL:
        s = by[sid]
        for n, ids in enumerate(folds):
            for m in SCOPE_METHODS:
                add(s, m, f"fold:{n}", fold_ids=ids)
        add(s, "concordance", "folds", folds=folds)
        add(s, "varcomp", "folds", folds=folds)
    ids = [t["id"] for t in tasks]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate task ids")
    return tasks


def _scoped(table, scope: str, task: dict):
    if scope == "pooled":
        return table
    if scope.startswith("framing:"):
        return framing_table(table, scope.split(":", 1)[1])
    if scope.startswith("fold:"):
        return restrict_blocks(table, task["fold_ids"])
    raise ValueError(scope)


def run_task(task: dict, n_perm: int, seed: int, alpha: float, grid_dir: str) -> dict:
    t0 = time.time()
    subject = task["subject"]
    method, scope = task["method"], task["scope"]
    full = subject_table(subject)
    target = preregistered(subject["sid"])
    out: dict = {}
    if method == "concordance":
        if scope == "framings":
            scopes = [[b for b in full.blocks if b.split("::", 1)[0] == f] for f in FRAMINGS]
        else:
            scopes = task["folds"]
        out = scope_concordance(full, scopes, n_perm, seed)
    elif method == "varcomp":
        # On a framed roster the four framings play the folds' part; no candidate
        # there is documented, so every candidate is a non-target candidate.
        scopes = ([[b for b in full.blocks if b.split("::", 1)[0] == f] for f in FRAMINGS]
                  if scope == "framings" else task["folds"])
        drop = (PANEL_TARGET,) if scope == "folds" else ()
        out = {"non_target": variance_components(full, drop=drop),
               "all_candidates": variance_components(full),
               "fold_replication_non_target": fold_profile_replication(full, scopes, drop=drop),
               "fold_replication_all": fold_profile_replication(full, scopes)}
    else:
        table = _scoped(full, scope, task)
        if method == "registered":
            base = _scoped(base_table(subject), scope, task)
            out = M.registered(table, base, n_perm, seed, alpha)
        elif method == "sharp_mean":
            out = M.sharp_mean(table, n_perm, seed, alpha)
            if scope == "pooled":
                path = Path(grid_dir) / f"{subject['sid']}__mean_t.npy"
                np.save(path, M.mean_t_grid(table))
                out["grid_file"] = path.name
        elif method == "sharp_median":
            out = M.sharp_median(table, n_perm, seed, alpha)
        elif method == "detachment":
            out = M.detachment(table, n_perm, seed, alpha, target=target)
        elif method == "coherence":
            out = M.coherence(table, n_perm, seed, alpha)
        elif method == "context":
            out = M.context_interaction(table, n_perm, seed, alpha, neutral=NEUTRAL)
        else:
            raise ValueError(method)
        out.update({"k": len(table.principals), "candidates": list(table.principals),
                    "n_responses": int(table.n_responses),
                    "n_instructions_in_scope": len(table.blocks)})
    slim = {k: v for k, v in task.items() if k not in ("subject", "folds", "fold_ids")}
    return {**slim, "group": subject["group"], "settings": {
        "n_permutations": n_perm, "seed": seed, "alpha": alpha}, "result": out,
        "seconds": round(time.time() - t0, 1)}
