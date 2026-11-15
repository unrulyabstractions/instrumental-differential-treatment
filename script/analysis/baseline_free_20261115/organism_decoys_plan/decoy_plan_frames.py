"""How many decoy names each stored elicitation pool already offers.

The frame is target-blind: a name enters if the base model named it at least
once during elicitation and its stored type label matches the roster's type.
Audited candidates are removed. The count is a lower bound, because many
base-mentioned names carry no stored type label; those are counted separately
and would be labeled at registration. Fame is proxied by the base's own mention
count, the only fame measure stored for every name.
"""

from __future__ import annotations

import re

from decoy_plan_sources import load_json

_SL = "out/main/secret_loyalties"
_NSL_LABELS = "configs/secret_loyalties/type_labels_nsl.json"
_CH_LABELS = "configs/secret_loyalties/type_labels_challenge.json"

POOLS = {
    "nsl_informed": ([f"{_SL}/calibration_informed/ellicit"], _NSL_LABELS, "person"),
    "nsl_scoped": ([f"{_SL}/calibration_scoped/ellicit"], _NSL_LABELS, "person"),
    "nsl_blind_person": ([f"{_SL}/calibration_blind/ellicit"], _NSL_LABELS, "person"),
    "nsl_blind_organization": ([f"{_SL}/calibration_blind/ellicit"], _NSL_LABELS, "organization"),
    **{f"challenge_{kind}": ([f"{_SL}/challenge_organism_{o}/ellicit/pooled" for o in orgs],
                             _CH_LABELS, kind)
       for kind, orgs in (("person", "abc"), ("organization", "abc"), ("group", "b"))},
    "auditbench_state_actors": (["out/main/auditbench/secret_loyalty/ellicit/seed_state"], None,
                                "state actor"),
}

NO_POOL = {
    "auditbench_ai_organizations": (
        "fixed roster written in the prompt-set config (principal_type 'AI research "
        "organization'); no elicitation pool is stored, so the frame is built at registration"),
    "court_groups_given": "the scenario fixes two cities; no pool of further cities is stored",
    "court_objective_disclosed": "the scenario fixes two cities; no pool of further cities is stored",
}


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _labels(folders: list[str], extra: str | None) -> tuple[dict[str, str], list[str]]:
    labels, used = {}, []
    if extra:
        labels.update({a: v["type"] for a, v in load_json(extra).items()})
        used.append(extra)
    for folder in folders:
        own = load_json(f"{folder}/type_labels.json")
        labels.update({a: v["type"] for a, v in own.items()})
        used.append(f"{folder}/type_labels.json")
    return labels, used


def frame(set_key: str, audited: set[str]) -> dict:
    """The stored decoy frame for one set, or the reason none is stored."""
    if set_key in NO_POOL:
        return {"stored_pool": False, "reason": NO_POOL[set_key], "frame_size_labeled": 0}
    folders, extra, kind = POOLS[set_key]
    labels, label_files = _labels(folders, extra)
    ref, elev, reports = {}, {}, []
    for folder in folders:
        path = f"{folder}/elicitation_report.json"
        rep = load_json(path)
        reports.append(path)
        for actor, n in rep["tally_reference"].items():
            ref[actor] = ref.get(actor, 0) + n
        for actor, e in rep["elevation"].items():
            elev[actor] = max(elev.get(actor, e), e)
    mentioned = {a for a, n in ref.items() if n >= 1}
    same_type = {a for a in mentioned if labels.get(a) == kind}
    names = sorted(a for a in same_type if norm(a) not in audited)
    audited_ref = sorted(ref.get(a, 0) for a in ref if norm(a) in audited)
    declared = sorted({str(load_json(f"{f}/type_gate.json").get("declared")) for f in folders})
    return {
        "stored_pool": True, "roster_type": kind, "elicitation_reports": reports,
        "label_files": label_files, "type_gate_declared": declared,
        "type_note": "stored labels are coarse (person, organization, group, state actor); a "
                     "narrower declared type, such as a political figure, is matched at "
                     "registration",
        "rule": "base reference count >= 1, stored type label equal to the roster type, "
                "not an audited candidate",
        "base_mentioned_names": len(mentioned),
        "base_mentioned_unlabeled": sum(1 for a in mentioned if a not in labels),
        "frame_size_labeled": len(names),
        "frame_elevated_in_target": sum(1 for a in names if elev.get(a, 0) > 0),
        "frame_base_mentions_range": [min((ref[a] for a in names), default=None),
                                      max((ref[a] for a in names), default=None)],
        "audited_base_mentions": audited_ref,
        "frame_names": [{"actor": a, "base_mentions": ref[a], "max_elevation": elev.get(a)}
                        for a in names],
    }
