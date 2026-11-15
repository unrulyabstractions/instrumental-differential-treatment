"""Every recompute that overlaps a stored record must equal it exactly.

Checks, each one row in ``reproduce_check.json``:

- partA's ``baseline_role.json``: every result row (registered, target-only mean,
  target-only median, base-only median) against the same table here.
- partA's own 73 checks against stored records, redone on this screen's numbers:
  27 registered runs against ``comparison_summary.json`` and 46
  ``reference_free.json`` seats.
- every stage-6 per-seat G (``comparison_<seat>_L<level>.json``).
- the null-extension and pooled-base registered pairings.
- the three user-awareness records, and the observed coherence R of the pooled
  coherence record.
- the stream checks: each replay, and the loser-dispersion recompute of the mean S.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from src.common.file_io import load_json
from src.ui.experiment_registry import EXPERIMENTS, HELD_OUT_EXPERIMENTS

PARTA = Path("out/main/reanalysis_20261113/partA/baseline_role.json")
NULLEXT = Path("out/main/auditbench/nullext/summary.json")
POOLED = Path("out/main/auditbench/pooled_base_20261113/compare/compare_summary.json")
COHERENCE = Path("out/main/secret_loyalties/shared/coherence_pooled.json")
PARTA_KIND = {"target_only_median": "median", "target_only_mean": "mean",
              "base_only_median": "median", "registered": "registered"}


def _row(what, ref, got, stored_S, got_S, stored_p, got_p, extra=None) -> dict:
    ok = got is not None and stored_S == got_S and stored_p == got_p
    return {"what": what, "ref": ref, "got": got, "stored_S": stored_S, "got_S": got_S,
            "stored_p": stored_p, "got_p": got_p, "match": bool(ok and all(
                (extra or {}).get("must", {}).values())), **(extra or {}).get("info", {}),
            **{f"must_{k}": v for k, v in (extra or {}).get("must", {}).items()}}


def _by_sha(meta: dict) -> dict:
    out = {}
    for sid, m in meta.items():
        if m["half"] is None:
            out.setdefault((m["sha256_verdicts"], m["axes"], m["level"]), sid)
    return out


def check_parta(res: dict, meta: dict) -> list[dict]:
    pa = load_json(PARTA)
    t_sid = {(m["parta_run"], m["parta_kind"]): sid for sid, m in meta.items()
             if m["parta_run"]}
    rows = []
    for rid, r in pa["results"].items():
        run, kind, subset = rid.split("|")
        seat = "base" if kind == "base_only_median" else "target"
        sid = t_sid.get((run, seat))
        got = res.get(f"{sid}|{PARTA_KIND[kind]}|{subset}") if sid else None
        rows.append(_row(f"partA {kind}", rid, got and got["id"], r["S"],
                         got and got["S"], r["p"], got and got["p"],
                         {"must": {"named": bool(got) and got["named_by_rule"] == r["named_by_rule"],
                                   "argmax": bool(got) and got["argmax_candidate"]
                                   == r["argmax_candidate"]}}))
    return rows


def check_stored_registered(res: dict, meta: dict) -> list[dict]:
    rows = []
    for sid, m in meta.items():
        if not m["stored_summary"]:
            continue
        st = load_json(Path(m["stored_summary"]))["reference_contrast"][f"L{m['level']}"][
            "paired_max_test"]
        got = res.get(f"{sid}|registered|full")
        named = (st.get("attribution") or {}).get("named")
        rows.append(_row("registered vs comparison_summary.json", m["stored_summary"],
                         got and got["id"], st["statistic"], got and got["S"],
                         st["p_family_wise"], got and got["p"],
                         {"must": {"named": bool(got) and got["named_by_rule"] == named}}))
    nx = load_json(NULLEXT)["results"]
    for key, sid in (("sd_ai_welfare_poisoning|base_A", "nullext_sd_ai_welfare_poisoning"),
                     ("sd_emotional_bond|base_A", "nullext_sd_emotional_bond"),
                     ("base_B|base_A", "base_B")):
        got = res.get(f"{sid}|registered|full")
        rows.append(_row("registered vs nullext/summary.json", key, got and got["id"],
                         nx[key]["statistic"], got and got["S"], nx[key]["p_family_wise"],
                         got and got["p"]))
    bp = load_json(POOLED)["base_pairs"]
    for key, sid in (("B|A", "base_B"), ("C1|B", "base_C1"), ("C2|B", "base_C2")):
        st = bp[key]["registered"]
        got = res.get(f"{sid}|registered|full")
        rows.append(_row("registered vs pooled_base compare_summary.json", key,
                         got and got["id"], st["statistic"], got and got["S"],
                         st["p_family_wise"], got and got["p"]))
    return rows


def check_reference_free(res: dict, meta: dict) -> list[dict]:
    """Every current stored ``reference_free.json`` seat, located by its table's sha."""
    index = _by_sha(meta)
    rows = []
    for e in (*EXPERIMENTS, *HELD_OUT_EXPERIMENTS):
        path = Path(e.summary).parent / "reference_free.json"
        if not path.is_file():
            continue
        rec = load_json(path)
        files = {Path(f).stem.removeprefix("verdicts_"): f
                 for f in (e.verdicts_target, e.verdicts_base)}
        for seat, st in rec["seats"].items():
            sha = hashlib.sha256(Path(files[seat]).read_bytes()).hexdigest()
            sid = index.get((sha, e.axes, rec["level"]))
            got = res.get(f"{sid}|median|full") if sid else None
            rows.append(_row("reference_free.json seat", f"{path}#{seat}", got and got["id"],
                             st["statistic"], got and got["S"], st["p_family_wise"],
                             got and got["p"], {
                                 "must": {"settings": rec["seed"] == 20260726
                                          and rec["n_permutations"] == 10000},
                                 "info": {"stored_alpha": st["alpha"],
                                          "stored_decision": st["different"],
                                          "got_decision_0.05": got and got["reject_0.05"],
                                          "got_decision_0.01": got and got["reject_0.01"],
                                          "stored_named_raw": st["named"],
                                          "got_argmax": got and got["argmax_candidate"]}}))
    return rows


def check_g(res: dict, meta: dict) -> list[dict]:
    rows = []
    for sid, m in meta.items():
        if not m["stored_g"]:
            continue
        st = load_json(Path(m["stored_g"]))["homogeneity"]
        got = res.get(f"{sid}|g_test|full")
        rows.append(_row("per-seat G vs stage-6 comparison file", m["stored_g"],
                         got and got["id"], st["g_statistic"], got and got["S"],
                         st["p_permutation"], got and got["p"],
                         {"info": {"stored_n_permutations": st["n_permutations"]}}))
    return rows


def check_ua_and_coherence(res: dict, meta: dict) -> list[dict]:
    rows = []
    for sid, m in meta.items():
        if m["stored_ua"]:
            st = load_json(Path(m["stored_ua"]))["reference_free"]
            got = res.get(f"{sid}|median|full")
            rows.append(_row("user_awareness_detection.json", m["stored_ua"], got and got["id"],
                             st["statistic"], got and got["S"], st["p_family_wise"],
                             got and got["p"], {"info": {"stored_named_raw": st["named"],
                                                         "got_argmax": got and got["argmax_candidate"]}}))
    rec = load_json(COHERENCE)
    for role, prefix in (("target", ""), ("reference", "base_of_")):
        for pc in rec["roles"][role]["per_condition"]:
            got = res.get(f"{prefix}{pc['run']}|coherence|full")
            cand = rec["roles"][role]["followed"]
            r_got = got and got["R"][cand]
            rank = got and 1 + sum(v > r_got for v in got["R"].values())
            rows.append({"what": "coherence observed R vs coherence_pooled.json",
                         "ref": f"{role}/{pc['run']}/{cand}", "got": got and got["id"],
                         "stored_R": pc["R"], "got_R": r_got, "stored_rank": pc["rank"],
                         "got_rank": rank, "match": r_got == pc["R"] and rank == pc["rank"]})
    return rows


def check_streams(res: dict) -> list[dict]:
    rows = []
    for rid, r in res.items():
        if r["kind"] in ("mean", "median"):
            rows.append({"what": f"{r['kind']} replay reproduces the library p", "ref": rid,
                         "got": rid, "stored_p": r["p"], "got_p": r["replay_p"],
                         "match": bool(r["replay_reproduces_p"])})
        if r["kind"] == "loser":
            mean = res.get(rid.replace("|loser|", "|mean|"))
            rows.append(_row("loser-dispersion recompute of the mean variant", rid,
                             mean and mean["id"], r["registered_S_recomputed"],
                             mean and mean["S"], r["registered_p_recomputed"],
                             mean and mean["p"]))
    return rows


def all_checks(res: dict, meta: dict) -> dict:
    groups = {"partA": check_parta(res, meta),
              "stored_registered": check_stored_registered(res, meta),
              "reference_free_json": check_reference_free(res, meta),
              "stage6_g": check_g(res, meta),
              "ua_and_coherence": check_ua_and_coherence(res, meta),
              "streams": check_streams(res)}
    return {"groups": groups,
            "counts": {k: {"n": len(v), "mismatches": sum(not r["match"] for r in v)}
                       for k, v in groups.items()},
            "n_checks": sum(len(v) for v in groups.values()),
            "n_mismatches": sum(not r["match"] for v in groups.values() for r in v)}
