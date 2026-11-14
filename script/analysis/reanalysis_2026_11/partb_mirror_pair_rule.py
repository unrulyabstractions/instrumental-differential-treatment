"""A naming rule that refuses a group whose mirror carries a signal of its own.

The registered naming rule (``src.compare.principal_attribution``) names the
group at the maximum when it holds a strict plurality of the surviving axes and
enough of them. It never asks whether a second group carries a signal too. On
two candidates the one-versus-rest gaps are exact negatives, so the other group
always carries the same signal and the rule ties. With more candidates nothing
forces a tie: on third_party_politics strong_right leads on Libertarian
mentions and strong_left on Green mentions, two different axes, and the
plurality goes to strong_right.

The rule here adds one step and no new parameter. Remove the named group's
cells from both models and rerun the registered test on the groups that
remain. If the rerun still rejects at the registered level, another group is
treated differently from the rest on its own, and the group at the rerun's
maximum is the named group's **mirror**. The run then names no single group.
Repeating the step until the rerun no longer rejects lists every group that
carries a signal. With two candidates the rerun has one group and cannot run,
and the mirror is the other group by construction, so the rule refuses.

The rerun conditions on a group chosen from the data, but it reads only the
other groups' cells, so it refuses less often than an unconditional test would.
"""

from __future__ import annotations

import numpy as np

from src.compare.behavior_count_table import build_behavior_table
from src.compare.principal_attribution import attribute_principal


def _histogram(test: dict) -> dict:
    out: dict[str, set] = {}
    for p in test.get("surviving_pairs", []):
        out.setdefault(p["candidate"], set()).add(p["axis_id"])
    return {c: sorted(a) for c, a in sorted(out.items())}


def _drop(rows: list[dict], removed: list[str]) -> list[dict]:
    return [r for r in rows if r["principal"] not in removed]


def _step(test: dict, removed: list[str], remaining: list[str]) -> dict:
    return {"removed": list(removed), "remaining": remaining, "testable": True,
            "statistic": test["statistic"], "p_family_wise": test["p_family_wise"],
            "rejects": bool(test["loyal"]), "argmax": test["principal"],
            "argmax_axis": test["principal_axis"], "surviving_axes": _histogram(test)}


def mirror_pair_naming(test: dict, rows_t: list[dict], rows_b: list[dict], axes: list[str],
                       run_test) -> dict:
    """The registered name, the leave-out reruns, and the name this rule allows.

    ``run_test(target_table, base_table)`` is the registered test.
    """
    base = attribute_principal(test)
    record = {"registered_rule": {k: base.get(k) for k in
                                  ("named", "reason", "histogram", "plurality", "argmax")},
              "surviving_axes": _histogram(test), "steps": []}
    if not test["loyal"]:
        return record | {"named": None, "carriers": [], "reason": "no rejection"}
    candidates = list(test["candidates"])
    first = base["named"] or test["principal"]
    if len(candidates) == 2:
        mirror = next(c for c in candidates if c != first)
        return record | {"named": None, "mirror": mirror, "carriers": candidates,
                         "reason": "two candidates: the one-versus-rest gaps are exact "
                                   "negatives, so the other group carries the same signal"}
    removed = [first]
    while True:
        remaining = [c for c in candidates if c not in removed]
        if len(remaining) < 2:
            record["steps"].append({"removed": list(removed), "remaining": remaining,
                                    "testable": False})
            break
        rerun = run_test(build_behavior_table(_drop(rows_t, removed), axes),
                         build_behavior_table(_drop(rows_b, removed), axes))
        record["steps"].append(_step(rerun, removed, remaining))
        if not rerun["loyal"]:
            break
        if len(remaining) == 2:
            # A two-group rerun that rejects says the pair differ; which of the
            # two carries it is a sign convention, so both are listed.
            removed = removed + remaining
            break
        removed = removed + [rerun["principal"]]
    last = record["steps"][-1]
    # A rerun that stops rejecting ends the signal, so the groups removed before
    # it are the carriers; otherwise every group removed so far is.
    carriers = list(last["removed"]) if last.get("testable") and not last["rejects"] \
        else list(removed)
    first_rerun = record["steps"][0]
    unique = first_rerun.get("testable") and not first_rerun.get("rejects")
    mirror = None if unique else (first_rerun.get("argmax") if first_rerun.get("testable") else None)
    if base["named"] is None:
        named, reason = None, f"the registered rule names no group ({base['reason']})"
    elif unique:
        named, reason = base["named"], ""
    else:
        named, reason = None, (f"without {first}, the test still rejects at the group "
                               f"{mirror}, so {first}'s mirror carries a signal of its own")
    record.update({"named": named, "first_removed": first, "mirror": mirror,
                   "carriers": carriers, "reason": reason})
    record["mirror_profile"] = _profile(test, first, mirror) if mirror else None
    return record


def _profile(test: dict, a: str, b: str) -> dict:
    """How the named group's t profile and its mirror's relate, over all axes."""
    cands = list(test["candidates"])
    t = test["t_grid"]
    ta, tb = t[cands.index(a)], t[cands.index(b)]
    ok = np.isfinite(ta) & np.isfinite(tb)
    surv = _histogram(test)
    return {"t_correlation_over_axes": float(np.corrcoef(ta[ok], tb[ok])[0, 1]) if ok.sum() > 2 else None,
            "named_max_abs_t": float(np.nanmax(np.abs(ta))),
            "mirror_max_abs_t": float(np.nanmax(np.abs(tb))),
            "shared_surviving_axes": sorted(set(surv.get(a, [])) & set(surv.get(b, [])))}
