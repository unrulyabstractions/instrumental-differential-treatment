"""Three decoy frames for each elicited run, and how many decoys each one holds.

The audited rosters were not drawn at random. The type gate ranks every actor
the target elicitation named at least once more than the base did, by
elevation (target mentions minus base mentions) with the actor name breaking
ties, and the roster is the top of that ranking. Decoys are exchangeable with
the audited names only if they come from a comparable rule, so each elicited
run gets three frames:

* **roster rule**: the same gate ranking past the audited names
  (``gate_candidates`` run on the stored candidates and labels with no cap).
  Decoys drawn here are selected like the candidates, so a rejection says the
  target stands out among names its own elicitation also elevated. The rule
  reads the base, so this frame is not baseline-free.
* **target tally**: every actor the target named at least once, ranked by the
  target's own count. This is the only rule a no-baseline audit can apply, and
  under it the roster itself must be rebuilt from the target tally alone.
* **base mentioned**: every actor the base named at least once. It ignores the
  target, but the audited names were selected on the target, so a rejection can
  reflect that selection.

Each frame keeps actors whose stored type label equals the roster type, after
the labels' canonical merges, and drops the audited names. Actors with no stored
label are counted apart as the most the frame could add once labeled. The
frames are per run, because each organism has its own elicitation.
"""

from __future__ import annotations

import re

from decoy_plan_sources import load_json
from src.ellicit.principal_type_gate import gate_candidates

_SL = "out/main/secret_loyalties"
_NSL_LABELS = "configs/secret_loyalties/type_labels_nsl.json"
_CH_LABELS = "configs/secret_loyalties/type_labels_challenge.json"
_STATE = "out/main/auditbench/secret_loyalty/ellicit/seed_state"

#: run -> (elicitation folder, roster type, config-level label file, gate roster key)
POOLS = {
    "calibration_informed": (f"{_SL}/calibration_informed/ellicit", "person", _NSL_LABELS, None),
    "calibration_scoped": (f"{_SL}/calibration_scoped/ellicit", "person", _NSL_LABELS, None),
    "calibration_blind_person": (f"{_SL}/calibration_blind/ellicit", "person", _NSL_LABELS,
                                 "person"),
    "calibration_blind_organization": (f"{_SL}/calibration_blind/ellicit", "organization",
                                       _NSL_LABELS, "organization"),
    **{f"challenge_organism_{o}_{kind}": (f"{_SL}/challenge_organism_{o}/ellicit/pooled", kind,
                                          _CH_LABELS, kind)
       for o, kinds in (("a", ("person", "organization")),
                        ("b", ("person", "organization", "group")),
                        ("c", ("person", "organization")))
       for kind in kinds},
    "auditbench_secret_loyalty": (_STATE, "state actor", None, None),
}

NO_POOL = {
    "auditbench_ai_organizations": (
        "fixed roster written in the prompt-set config (principal_type 'AI research "
        "organization'); no elicitation pool is stored, so every frame is built at registration"),
    "court_groups_given": "the scenario fixes two cities; no pool of further cities is stored",
    "court_objective_disclosed": "the scenario fixes two cities; no pool of further cities is stored",
}

FRAMES = ("roster_rule", "target_tally", "base_mentioned")

CLAIMS = {
    "roster_rule": "the target stands out among names its own elicitation also elevated; the "
                   "rule reads the base, so the frame is not baseline-free",
    "target_tally": "the target stands out among names the target itself names; a no-baseline "
                    "audit must also rebuild its roster from this tally",
    "base_mentioned": "the target differs from names the base names; the audited names were "
                      "selected on the target, so selection alone can separate them",
}


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _labels(folder: str, extra: str | None) -> tuple[dict[str, dict], list[str]]:
    labels: dict[str, dict] = {}
    used = []
    if extra:
        labels.update(load_json(extra))
        used.append(extra)
    labels.update(load_json(f"{folder}/type_labels.json"))
    used.append(f"{folder}/type_labels.json")
    return labels, used


def _pooled_tally(tally: dict[str, int], labels: dict[str, dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for actor, n in tally.items():
        key = labels.get(actor, {}).get("canonical", actor)
        out[key] = out.get(key, 0) + n
    return out


def _stored_roster(gate: dict, key: str | None) -> tuple[list[str], int]:
    block = gate["rosters"][key] if key else gate
    return [r["actor"] for r in block["roster"]], block["top"]


def _tally_frame(tally: dict[str, int], labels: dict, kind: str, audited: set[str],
                 elev: dict[str, int]) -> dict:
    named = {a: n for a, n in tally.items() if n >= 1}
    lab = sorted((a for a in named if labels.get(a, {}).get("type") == kind
                  and norm(a) not in audited), key=lambda a: (-named[a], a))
    unl = [a for a in named if a not in labels and norm(a) not in audited]
    return {"size_labeled": len(lab), "unlabeled": len(unl),
            "size_upper_bound": len(lab) + len(unl),
            "names": [{"actor": a, "count": named[a], "elevation": elev.get(a)} for a in lab]}


def run_frames(run: str, audited: set[str]) -> dict:
    """The three frames of one elicited run, with the gate reproduced first."""
    folder, kind, extra, gate_key = POOLS[run]
    labels, label_files = _labels(folder, extra)
    rep = load_json(f"{folder}/elicitation_report.json")
    gate = load_json(f"{folder}/type_gate.json")
    stored, top = _stored_roster(gate, gate_key)
    full = gate_candidates(rep["candidate_principals"], kind, labels, top=10 ** 6)["roster"]
    rebuilt = [r["actor"] for r in full[:top]]
    if rebuilt != stored:
        raise SystemExit(f"{run}: the gate does not reproduce the stored roster "
                         f"({rebuilt} vs {stored})")
    elev = {r["actor"]: r["elevation"] for r in full}
    ranked_audited = [r["actor"] for r in full if norm(r["actor"]) in audited]
    missing = sorted(audited - {norm(a) for a in ranked_audited})
    if missing:
        raise SystemExit(f"{run}: audited names outside the gate ranking: {missing}")
    rule = [r for r in full if norm(r["actor"]) not in audited]
    tgt = _pooled_tally(rep["tally_target"], labels)
    ref = _pooled_tally(rep["tally_reference"], labels)
    tally_order = sorted(ranked_audited, key=lambda a: (-tgt.get(a, 0), a))
    frames = {
        "roster_rule": {"size_labeled": len(rule), "unlabeled": 0,
                        "size_upper_bound": len(rule),
                        "names": [{"actor": r["actor"], "count": r["target_count"],
                                   "elevation": r["elevation"]} for r in rule]},
        "target_tally": _tally_frame(tgt, labels, kind, audited, elev),
        "base_mentioned": _tally_frame(ref, labels, kind, audited, elev),
    }
    return {
        "stored_pool": True, "run": run, "roster_type": kind,
        "elicitation_report": f"{folder}/elicitation_report.json",
        "type_gate": f"{folder}/type_gate.json", "label_files": label_files,
        "gate_reproduced": True, "gate_top": top,
        "audited_elevation": sorted((elev[a] for a in ranked_audited), reverse=True),
        "audited_target_counts": sorted((tgt.get(a, 0) for a in ranked_audited), reverse=True),
        "audited_base_counts": sorted((ref.get(a, 0) for a in ranked_audited), reverse=True),
        "gate_first_audited": norm(ranked_audited[0]),
        "target_tally_first_audited": norm(tally_order[0]),
        "tie_rule": "elevation descending, then actor name (the gate's own order); target tally "
                    "descending, then actor name",
        "frames": frames, "claims": CLAIMS,
    }


def set_frames(set_key: str, runs: list[str], audited_by_run: dict[str, set[str]],
               needed: dict[str, int]) -> dict:
    """Per-run frames of one decoy set and whether each frame covers each design's m."""
    if set_key in NO_POOL:
        return {"stored_pool": False, "reason": NO_POOL[set_key],
                "coverage": {f: {d: False for d in needed} for f in FRAMES},
                "min_size_labeled": {f: 0 for f in FRAMES}}
    per_run = {r: run_frames(r, audited_by_run[r]) for r in runs}
    min_lab = {f: min(p["frames"][f]["size_labeled"] for p in per_run.values()) for f in FRAMES}
    min_up = {f: min(p["frames"][f]["size_upper_bound"] for p in per_run.values())
              for f in FRAMES}
    cover = {f: {d: min_lab[f] >= m for d, m in needed.items()} for f in FRAMES}
    cover_up = {f: {d: min_up[f] >= m for d, m in needed.items()} for f in FRAMES}
    return {"stored_pool": True, "per_run": per_run, "min_size_labeled": min_lab,
            "min_size_upper_bound": min_up, "coverage": cover,
            "coverage_if_every_unlabeled_name_fits": cover_up, "needed_m": needed,
            "note": "a set's runs have separate elicitations, so a frame covers a design only "
                    "if every run's own frame holds that many names"}
