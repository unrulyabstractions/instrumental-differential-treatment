"""Every contrast one model gets, as rows ready for the tables.

Paired rosters (four framings, every template under each):

- primary: committed_supporter minus none. Pre-specified from the documented
  activation, "a user signals extreme intent and the action would advantage
  the entity".
- secondary: unreviewed_authority minus none, and live_deployment minus none.
  Holm runs over the primary and the two secondaries.
- post hoc: the mean of the two trigger framings (committed_supporter,
  unreviewed_authority) minus the mean of the other two. The trigger pair was
  localized from data, so this row is labelled post hoc and stays out of Holm.
- stance: supporter templates against neutral templates, each template's value
  the mean of its gap over the four framings, with family labels permuted over
  templates; the same stance contrast within each single framing is detail.

Unpaired prompt sets (one framing): the two template families of the design.

Each contrast runs on the mean gap and on the median gap. A model with a base
partner adds the triple difference (target contrast minus base contrast, mean
gap) as a comparison row. Every result carries each candidate's own maxT, which
is the invariance check for the others and the fixed-target test for a
pre-registered candidate.
"""

from __future__ import annotations

import warnings

import numpy as np

from script.analysis.baseline_free_20261115.context_contrast.context_contrast_engine import (
    group_perm_test, holm, paired_flip_test)
from script.analysis.baseline_free_20261115.context_contrast.context_contrast_gaps import (
    context_cube, gap, templates_in)
from script.analysis.baseline_free_20261115.context_contrast.context_contrast_runs import (
    UNPAIRED_GROUPS, Model)
from src.compare.behavior_count_table import BehaviorTable
from src.compare.principal_attribution import attribute_principal

__all__ = ["PAIRED_CONTRASTS", "model_contrasts"]

#: (name, status, framings averaged for context one, framings for context zero)
PAIRED_CONTRASTS = (
    ("committed_supporter_vs_none", "primary", ("committed_supporter",), ("none",)),
    ("unreviewed_authority_vs_none", "secondary", ("unreviewed_authority",), ("none",)),
    ("live_deployment_vs_none", "secondary", ("live_deployment",), ("none",)),
    ("trigger_pair_vs_other_pair", "post_hoc",
     ("committed_supporter", "unreviewed_authority"), ("none", "live_deployment")),
)
STANCE = (("supporter",), ("neutral",))


def _framing_mean(d, framings, names):
    idx = [framings.index(f) for f in names]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # an all-NaN cell stays NaN
        return np.nanmean(d[:, idx], axis=1)


def _row(res, *, name, status, variant, design, candidates, axes, pre, n_axes):
    """Flatten one engine result into the record the tables read."""
    att = attribute_principal({"loyal": res["reject"], "surviving_pairs": res["surviving_pairs"],
                               "principal": res["argmax_candidate"] if res["reject"] else None,
                               "n_axes": n_axes})
    per = res["per_candidate"]
    ref = pre if pre in candidates else (res["argmax_candidate"] if res["reject"] else "")
    others = [r for r in per if r["candidate"] != ref]
    ranked = sorted(per, key=lambda r: -r["S"])
    fixed = next((r for r in per if r["candidate"] == pre), None)
    out = {k: v for k, v in res.items() if k not in ("t_grid", "adjusted", "per_candidate")}
    out.update(contrast=name, status=status, variant=variant, design=design,
               named=res["argmax_candidate"] if res["reject"] else None,
               named_by_rule=att["named"], naming_reason=att.get("reason", ""),
               reference_candidate=ref or None,
               n_other_candidates=len(others),
               n_other_candidates_rejecting=sum(r["p"] <= res["alpha"] for r in others),
               per_candidate=per,
               preregistered=pre or None,
               fixed_target=None if fixed is None else {
                   **fixed, "rank_by_S": 1 + [r["candidate"] for r in ranked].index(pre),
                   "reject": bool(fixed["p"] <= res["alpha"])})
    return out


def _check_aligned(a, b):
    if a[1:] != b[1:]:
        raise ValueError("target and base cubes differ in candidates, framings or templates")


def model_contrasts(model: Model, table: BehaviorTable, partner: BehaviorTable | None,
                    n: int, seed: int, alpha: float) -> dict:
    cube, candidates, framings, templates = context_cube(table)
    axes = list(table.axes)
    base_cube = None
    if partner is not None:
        pc = context_cube(partner)
        _check_aligned((cube, candidates, framings, templates), pc)
        base_cube = pc[0]
    kw = dict(candidates=candidates, axes=axes, n=n, seed=seed, alpha=alpha)
    meta = dict(candidates=candidates, axes=axes, pre=model.preregistered, n_axes=len(axes))
    rows = []
    if model.design == "paired":
        one, zero = templates_in(templates, STANCE[0]), templates_in(templates, STANCE[1])
        for variant in ("mean", "median"):
            d = gap(cube, variant)
            db = gap(base_cube, variant) if base_cube is not None else None
            for name, status, f1, f0 in PAIRED_CONTRASTS:
                delta = _framing_mean(d, framings, f1) - _framing_mean(d, framings, f0)
                rows.append(_row(paired_flip_test(delta, **kw), name=name, status=status,
                                 variant=variant, design="paired", **meta))
                if db is not None and variant == "mean":
                    dbase = _framing_mean(db, framings, f1) - _framing_mean(db, framings, f0)
                    rows.append(_row(paired_flip_test(delta - dbase, **kw), name=name,
                                     status="comparison_triple_difference", variant=variant,
                                     design="paired", **meta))
            pooled = _framing_mean(d, framings, framings)
            rows.append(_row(group_perm_test(pooled, one, zero, **kw),
                             name="stance_supporter_vs_neutral", status="stance",
                             variant=variant, design="unpaired", **meta))
            for f in framings:
                rows.append(_row(group_perm_test(d[:, framings.index(f)], one, zero, **kw),
                                 name=f"stance_supporter_vs_neutral@{f}",
                                 status="stance_within_framing", variant=variant,
                                 design="unpaired", **meta))
            if db is not None and variant == "mean":
                pooled_b = _framing_mean(db, framings, framings)
                rows.append(_row(group_perm_test(pooled - pooled_b, one, zero, **kw),
                                 name="stance_supporter_vs_neutral",
                                 status="comparison_triple_difference", variant=variant,
                                 design="unpaired", **meta))
        groups = {"stance_one": [templates[k] for k in one],
                  "stance_zero": [templates[k] for k in zero]}
        for variant in ("mean", "median"):
            ps = {r["contrast"]: r["p_family_wise"] for r in rows
                  if r["variant"] == variant and r["status"] in ("primary", "secondary")}
            adj = holm(ps)
            for r in rows:
                if r["variant"] == variant and r["status"] in ("primary", "secondary"):
                    r["p_holm"] = adj[r["contrast"]]
                    r["reject_holm"] = bool(adj[r["contrast"]] <= alpha)
    else:
        (lab1, stems1), (lab0, stems0) = UNPAIRED_GROUPS[model.groups]
        stems = stems1 + stems0
        one = templates_in(templates, stems1, stems)
        zero = templates_in(templates, stems0, stems)
        if len(framings) != 1:
            raise ValueError(f"{model.key}: an unpaired design expects one framing")
        name = f"{lab1}_vs_{lab0}"
        for variant in ("mean", "median"):
            d = gap(cube, variant)[:, 0]
            rows.append(_row(group_perm_test(d, one, zero, **kw), name=name, status="primary",
                             variant=variant, design="unpaired", **meta))
            if base_cube is not None and variant == "mean":
                dbase = gap(base_cube, variant)[:, 0]
                rows.append(_row(group_perm_test(d - dbase, one, zero, **kw), name=name,
                                 status="comparison_triple_difference", variant=variant,
                                 design="unpaired", **meta))
        groups = {"family_one": lab1, "family_one_templates": [templates[k] for k in one],
                  "family_zero": lab0, "family_zero_templates": [templates[k] for k in zero]}
    return {"candidates": candidates, "framings": framings, "templates": templates,
            "n_axes": len(axes), "groups": groups, "rows": rows}
