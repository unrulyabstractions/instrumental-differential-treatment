"""The other families' readings of each subject, joined on the registry's subject ids.

Each reader returns ``{subject_id: {method_key: {"statistic", "p", "leader",
"named", "source"}}}`` for the subjects it covers, and records the file it read
with its sha256. A family whose output is absent is reported as absent, never
filled in. Keys:

- ``up_snl_loser``: sharp_null_screen's loser-dispersion statistic (per-axis
  leave-one-out z, infinite cells excluded); its own leading candidate.
- ``up_npo_rms``: name_population_outlier's Grubbs test on the RMS of each
  candidate's t over axes, Holm-combined with the peak; leader by the RMS.
- ``up_pooled_coherence``: pooled_coherence's cross-condition test (informed and
  scoped share two candidates); the target role and the base role.
- ``up_panel_family``: cross_run_panel's target-only panel test.
- ``up_context_family``: context_contrast's signed context contrast.
- ``up_embedding``: embedding_target_only's masked-embedding reading.
- ``up_ua_meangrade``: user_awareness's Grubbs test on each identity's mean grade.

``cross_family_checks`` compares the statistics two families compute from the same
library function on the same table (target-only max tests, single-table coherence,
Grubbs on the peaks).
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from script.analysis.baseline_free_20261115.common.settings import OUT_ROOT
from script.analysis.baseline_free_20261115.common.subjects import registry

_SOURCES: dict[str, dict] = {}
_STATUS: dict[str, str] = {}


def _read(path: Path):
    path = Path(path)
    data = path.read_bytes()
    _SOURCES[str(path.relative_to(OUT_ROOT.parents[2]))] = {
        "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    if path.suffix == ".json":
        return json.loads(data)
    if path.suffix == ".jsonl":
        return [json.loads(x) for x in data.decode().splitlines() if x.strip()]
    return list(csv.DictReader(data.decode().splitlines()))


def _f(x):
    if x in (None, ""):
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _path_index() -> dict[tuple, str]:
    """(verdicts path, level) -> registry subject id, for unfiltered tables only."""
    out: dict[tuple, list] = {}
    for rec in registry()["subjects"]:
        if rec["s_max"] is None:
            out.setdefault((rec["verdicts"], int(rec["level"])), []).append(rec["subject_id"])
    return {k: v[0] for k, v in out.items() if len(v) == 1}


# ------------------------------------------------------------------ sharp_null_screen
def sharp_null() -> tuple[dict, dict]:
    path = OUT_ROOT / "sharp_null_screen" / "tasks.jsonl"
    if not path.exists():
        _STATUS["sharp_null_screen"] = "absent"
        return {}, {}
    idx = _path_index()
    rows = _read(path)
    joined: dict = {}
    raw: dict = {}
    for r in rows:
        if r.get("half") is not None or r.get("subset") != "full":
            continue
        sid = idx.get((r["table"], int(r["level"])))
        if sid is None:
            continue
        raw.setdefault(sid, {})[r["kind"]] = r
        if r["kind"] == "loser":
            ex = r.get("exclude") or {}
            if ex.get("computable"):
                joined.setdefault(sid, {})["up_snl_loser"] = {
                    "statistic": _f(ex.get("Z")), "p": _f(ex.get("p")),
                    "leader": (ex.get("top_pair") or {}).get("candidate"),
                    "named": ex.get("named"), "source": "sharp_null_screen/tasks.jsonl"}
    _STATUS["sharp_null_screen"] = f"read {len(rows)} task rows"
    return joined, raw


# ------------------------------------------------------------ name_population_outlier
_NPO = {"base_A_contextual_optimism": "base_A",
        "base_A_secret_loyalty": "base_A__secret_loyalty",
        "base_A_third_party_politics": "base_A__third_party_politics",
        "ua_gpt5_mini": "ua_gpt_5_mini", "ua_gpt41_mini": "ua_gpt_4_1_mini",
        "ua_gpt5": "ua_gpt_5"}


def _npo_sid(name: str) -> str | None:
    if name in _NPO:
        return _NPO[name]
    if name.startswith("null_sd_"):
        return "nullext_sd_" + name.removeprefix("null_sd_")
    if name.startswith("null_"):
        return "auditbench_" + name.removeprefix("null_")
    if name.startswith("base_1p5b_"):
        return "base_1p5b__calibration_" + name.removeprefix("base_1p5b_")
    if name.startswith("base_7b_"):
        org, kind = name.removeprefix("base_7b_").split("_", 1)
        return f"base_7b__challenge_organism_{org}_{kind}"
    if name.startswith("half"):
        return None
    return name


def name_population() -> tuple[dict, dict]:
    path = OUT_ROOT / "name_population_outlier" / "outlier_table.csv"
    if not path.exists():
        _STATUS["name_population_outlier"] = "absent"
        return {}, {}
    rows = _read(path)
    have = {r["subject_id"] for r in registry()["subjects"]}
    joined, raw = {}, {}
    for r in rows:
        sid = _npo_sid(r["subject"])
        if sid not in have:
            continue
        raw[sid] = r
        joined.setdefault(sid, {})["up_npo_rms"] = {
            "statistic": _f(r.get("grubbs_rms_G")), "p": _f(r.get("grubbs_exact_holm_p")),
            "leader": r.get("grubbs_rms_leader") or None,
            "named": r.get("grubbs_exact_named") or None,
            "source": "name_population_outlier/outlier_table.csv"}
    _STATUS["name_population_outlier"] = f"read {len(rows)} rows"
    return joined, raw


# ------------------------------------------------------------------- pooled_coherence
def pooled_coherence() -> dict:
    path = OUT_ROOT / "pooled_coherence" / "coherence_pooled.json"
    if not path.exists():
        _STATUS["pooled_coherence"] = "absent"
        return {}
    d = _read(path)
    joined = {}
    for role, prefix in (("target", ""), ("reference", "base_1p5b__")):
        r = d["roles"][role]
        for run in ("calibration_informed", "calibration_scoped"):
            joined.setdefault(prefix + run, {})["up_pooled_coherence"] = {
                "statistic": _f(r.get("pooled_R")), "p": _f(r.get("p_pooled")),
                "leader": r.get("leading"), "named": r.get("leading") if r.get("rejects")
                else None, "source": "pooled_coherence/coherence_pooled.json",
                "pool": "calibration_scoped + calibration_informed"}
    _STATUS["pooled_coherence"] = "read coherence_pooled.json"
    return joined


def single_coherence() -> dict:
    path = OUT_ROOT / "pooled_coherence" / "single_condition_all.json"
    if not path.exists():
        return {}
    d = _read(path)
    idx = _path_index()
    out = {}
    for key, seat in d["seats"].items():
        verdicts = seat.get("verdicts") or seat.get("table")
        sid = idx.get((verdicts, int(seat["level"]))) if verdicts else None
        if sid:
            out[sid] = seat
    return out


# ------------------------------------------------------------------- user_awareness
_UA = {"openai:gpt-5-mini": "ua_gpt_5_mini", "openai:gpt-4.1-mini": "ua_gpt_4_1_mini",
       "openai:gpt-5": "ua_gpt_5"}


def user_awareness() -> dict:
    path = OUT_ROOT / "user_awareness" / "summary.csv"
    if not path.exists():
        path = OUT_ROOT / "user_awareness" / "summary_stored.csv"
    if not path.exists():
        _STATUS["user_awareness"] = "absent"
        return {}
    joined = {}
    for r in _read(path):
        subject = r["subject"]
        if subject.endswith(" (new session)"):
            sid = _UA.get(subject.removesuffix(" (new session)"))
            for prefix, key in (("conformal p over pool, amanda_askell", "ua_decoy_conformal_amanda"),
                                ("empirical-calibration p (REML), amanda_askell",
                                 "ua_decoy_calibration_amanda"),
                                ("predictive t over pool, amanda_askell",
                                 "ua_decoy_predictive_amanda")):
                if sid and r["detector"].startswith(prefix):
                    joined.setdefault(sid, {})[key] = {
                        "statistic": _f(r["statistic"]), "p": _f(r["p"]),
                        "source": f"user_awareness/{path.name} (decoy session, pool of "
                                  "ordinary users)"}
            continue
        sid = _UA.get(subject)
        if sid is None:
            continue
        if r["detector"] == "Grubbs on mean grade, two-sided":
            note = r.get("note", "")
            joined.setdefault(sid, {})["up_ua_meangrade"] = {
                "statistic": _f(r["statistic"]), "p": _f(r["p"]),
                "leader": note.removeprefix("leading ").strip() or None,
                "named": r.get("named") or None,
                "source": f"user_awareness/{path.name}"}
        if r["detector"].startswith("predictive t vs 6 general, amanda_askell"):
            joined.setdefault(sid, {})["ua_transluce_amanda"] = {
                "statistic": _f(r["statistic"]), "p": _f(r["p"]),
                "source": f"user_awareness/{path.name}"}
    _STATUS["user_awareness"] = f"read {path.name}"
    return joined


# -------------------------------------------------------------------- cross_run_panel
_PANEL_MEMBER = {"contextual_optimism": "auditbench_contextual_optimism", "C1": "base_C1",
                 "C2": "base_C2", "C1_s0-11": "base_C1_s0_11", "base_A": "base_A",
                 "base_B": "base_B"}


def _panel_sid(member: str) -> str | None:
    if member in _PANEL_MEMBER:
        return _PANEL_MEMBER[member]
    if member.startswith("sd_"):
        return "nullext_sd_" + member.removeprefix("sd_")
    if "#" in member or "half" in member:
        return None
    return "auditbench_" + member


def cross_run_panel() -> dict:
    """The family's primary reading of each member: panel 'main' (C1 restricted to samples
    0 to 11 from its alternative panel), pool of every null-type row, median grid,
    pooled maximum with the family's primary p. The random-effects residual p on the
    same maximum is kept beside it."""
    path = OUT_ROOT / "cross_run_panel" / "panel_primary.csv"
    if not path.exists():
        _STATUS["cross_run_panel"] = "absent"
        return {}
    have = {r["subject_id"] for r in registry()["subjects"]}
    joined = {}
    rows = _read(path)
    resid = {}
    for r in rows:
        if r["variant"] == "re_residual" and r.get("primary") == "True":
            resid[(r["panel"], r["member"])] = _f(r["p"])
    for r in rows:
        if not (r["panel"] in ("main", "alt_C1s0-11") and r["variant"] == "pooled_max"
                and r.get("primary") == "True"):
            continue
        sid = _panel_sid(r["member"])
        if sid not in have or (r["panel"] != "main" and sid != "base_C1_s0_11"):
            continue
        leader = r.get("argmax_candidate") or r.get("candidate") or None
        joined.setdefault(sid, {})["up_panel_family"] = {
            "statistic": _f(r["statistic"]), "p": _f(r["p"]), "leader": leader,
            "named": r.get("named") or None, "p_type": r.get("p_type"),
            "p_re_residual": resid.get((r["panel"], r["member"])),
            "source": f"cross_run_panel/panel_primary.csv ({r['panel']}, {r['pool']}, "
                      f"{r['grid']}, pooled_max, {r.get('p_type')})"}
    _STATUS["cross_run_panel"] = f"read {len(rows)} rows of panel_primary.csv"
    return joined


# --------------------------------------------------------------- embedding_target_only
def embedding() -> dict:
    """Masked replies, raw variant: the stored judge-free statistic read target-only."""
    path = OUT_ROOT / "embedding_target_only" / "emb_table.csv"
    have = {r["subject_id"] for r in registry()["subjects"]}
    if not path.exists():
        return _embedding_runs(have)
    joined = {}
    rows = _read(path)
    for r in rows:
        if r["subject"] not in have or r["mask"] != "masked" or r["variant"] != "raw":
            continue
        p = _f(r["p"])
        joined.setdefault(r["subject"], {})["up_embedding"] = {
            "statistic": _f(r["statistic"]), "p": p, "leader": r["named"] or None,
            "named": (r["named"] or None) if p is not None and p <= 0.01 else None,
            "grubbs_p_mc": _f(r.get("grubbs_p_mc")), "panel_ratio_p": _f(r.get("panel_ratio_p")),
            "source": "embedding_target_only/emb_table.csv (masked, raw)"}
    _STATUS["embedding_target_only"] = f"read {len(rows)} rows of emb_table.csv"
    return joined


def _embedding_runs(have: set) -> dict:
    """The family's per-subject records, read when its summary table is not written yet."""
    runs = sorted((OUT_ROOT / "embedding_target_only" / "runs").glob("*.json"))
    if not runs:
        _STATUS["embedding_target_only"] = "absent"
        return {}
    joined = {}
    for path in runs:
        sid = path.stem
        if sid not in have:
            continue
        rec = _read(path)
        v = ((rec.get("masks") or {}).get("masked") or {}).get("variants", {}).get("raw")
        if not v:
            continue
        p = _f(v.get("p"))
        joined.setdefault(sid, {})["up_embedding"] = {
            "statistic": _f(v.get("statistic")), "p": p, "leader": v.get("named"),
            "named": v.get("named") if p is not None and p <= 0.01 else None,
            "source": f"embedding_target_only/runs/{path.name} (masked, raw)"}
    _STATUS["embedding_target_only"] = (f"read {len(runs)} per-subject records "
                                        "(summary table not written)")
    return joined


# --------------------------------------------------------------------- context_contrast
def _seat_sid(run: str, seat: str) -> str | None:
    """A (run, seat) pair as a registry subject id; every AuditBench base A seat is base_A."""
    if seat == "target":
        return run
    if run == "auditbench_contextual_optimism" or run.removeprefix("auditbench_") in (
            "ai_welfare_poisoning", "animal_welfare", "anti_ai_regulation", "defend_objects",
            "defer_to_users", "emotional_bond", "flattery", "hallucinates_citations"):
        return "base_A"
    for rec in registry()["subjects"]:
        if rec["partA_run"] == run and rec["partA_seat"] == "base" and rec["s_max"] is None:
            return rec["subject_id"]
    return None


def context_contrast() -> dict:
    """The family's run-level verdict per model (``results.json``, field ``verdicts``).

    A paired roster's verdict is Holm over its three pre-specified contrasts on the
    mean gap; an unpaired design has one contrast. The leader is the verdict's
    argmax candidate and the name is the family's naming rule.
    """
    path = OUT_ROOT / "context_contrast" / "results.json"
    if not path.exists():
        _STATUS["context_contrast"] = "absent"
        return {}
    have = {r["subject_id"] for r in registry()["subjects"]}
    d = _read(path)
    joined = {}
    for v in d["verdicts"]:
        sid = _seat_sid(v["run"], v["seat"]) if v["run"] not in have or v["seat"] != "target" \
            else v["run"]
        if v["run"] in have and v["seat"] == "base" and v["run"].startswith("base_"):
            sid = v["run"]
        if sid not in have:
            continue
        joined.setdefault(sid, {})["up_context_family"] = {
            "statistic": None, "p": _f(v.get("p_holm")), "leader": v.get("argmax_candidate"),
            "named": v.get("named_by_rule"), "contrast": v.get("contrast"),
            "design": v.get("design"), "reject": v.get("reject"),
            "source": "context_contrast/results.json verdicts"}
    _STATUS["context_contrast"] = f"read {len(d['verdicts'])} verdicts of results.json"
    return joined


# ----------------------------------------------------------- families read when present
def _generic(family: str, key: str, filename: str, columns: dict) -> dict:
    """A family summary CSV with one row per subject id."""
    path = OUT_ROOT / family / filename
    if not path.exists():
        _STATUS[family] = "absent"
        return {}
    have = {r["subject_id"] for r in registry()["subjects"]}
    joined = {}
    rows = _read(path)
    for r in rows:
        sid = r.get(columns["subject"])
        if sid not in have:
            continue
        joined.setdefault(sid, {})[key] = {
            "statistic": _f(r.get(columns["statistic"])), "p": _f(r.get(columns["p"])),
            "leader": r.get(columns["leader"]) or None,
            "named": r.get(columns.get("named", "")) or None,
            "source": f"{family}/{filename}"}
    _STATUS[family] = f"read {len(rows)} rows of {filename}"
    return joined


UPSTREAM_GENERIC: list[tuple] = []


def collect(subjects) -> dict:
    out: dict = {}

    def merge(part: dict) -> None:
        for sid, vals in part.items():
            out.setdefault(sid, {}).update(vals)

    snl, _ = sharp_null()
    merge(snl)
    npo, _ = name_population()
    merge(npo)
    merge(pooled_coherence())
    merge(user_awareness())
    merge(cross_run_panel())
    merge(embedding())
    merge(context_contrast())
    for family, key, filename, columns in UPSTREAM_GENERIC:
        merge(_generic(family, key, filename, columns))
    return out


def cross_family_checks(rows: dict, results: dict) -> list[dict]:
    """Same library call, same table, two families: the values must agree."""
    checks = []
    _, snl = sharp_null()
    for sid, kinds in snl.items():
        for kind, mine_key in (("mean", "sharp_mean"), ("median", "sharp_median")):
            r = kinds.get(kind)
            mine = results.get(f"{sid}|{mine_key}|pooled")
            if not (r and mine):
                continue
            m = mine["result"]
            ok = abs(m["statistic"] - r["S"]) <= 1e-9 and m["p"] == r["p"]
            checks.append({"subject": sid, "what": f"{mine_key} against sharp_null_screen",
                           "source": "sharp_null_screen/tasks.jsonl", "match": bool(ok),
                           "fields": [{"field": "S", "got": m["statistic"], "stored": r["S"]},
                                      {"field": "p", "got": m["p"], "stored": r["p"]}]})
        r = kinds.get("coherence")
        mine = results.get(f"{sid}|coherence|pooled")
        if r and mine and mine["result"].get("applies"):
            m = mine["result"]
            # The screen stores the maximum of R as S and p, and the detachment of R
            # as detachment_S and detachment_p.
            pairs = [("detachment S", m["statistic"], r.get("detachment_S")),
                     ("detachment p", m["p"], r.get("detachment_p")),
                     ("max S", m["max_statistic"], r.get("S")), ("max p", m["p_max"], r.get("p")),
                     ("leader", m["leader"], r.get("argmax_candidate"))]
            ok = all(b is not None and (a == b if isinstance(a, str) else abs(a - b) <= 1e-9)
                     for _, a, b in pairs)
            checks.append({"subject": sid, "what": "coherence against sharp_null_screen",
                           "source": "sharp_null_screen/tasks.jsonl", "match": bool(ok),
                           "fields": [{"field": f, "got": a, "stored": b} for f, a, b in pairs]})
    _, npo = name_population()
    for sid, r in npo.items():
        mine = results.get(f"{sid}|detachment|pooled")
        if not (mine and mine["result"].get("applies")):
            continue
        m = mine["result"]
        g = m["grubbs"]
        fields = [{"field": "detachment S", "got": m["statistic"],
                   "stored": _f(r.get("mad_peak_S"))},
                  {"field": "detachment p", "got": m["p"], "stored": _f(r.get("mad_peak_p"))},
                  {"field": "peak leader", "got": m["leader"],
                   "stored": r.get("grubbs_peak_leader")}]
        ok = (abs(m["statistic"] - (_f(r.get("mad_peak_S")) or float("nan"))) <= 1e-9
              and m["p"] == _f(r.get("mad_peak_p")) and m["leader"] == r.get(
                  "grubbs_peak_leader"))
        if g.get("computable"):
            fields.append({"field": "Grubbs p bound", "got": g["p_grubbs_bonferroni"],
                           "stored": _f(r.get("grubbs_peak_p_bound"))})
            fields.append({"field": "Grubbs p exact (Monte Carlo, tolerance 0.005)",
                           "got": g["p_grubbs_exact_mc"], "stored": _f(r.get(
                               "grubbs_peak_p_exact"))})
            ok = ok and abs(g["p_grubbs_bonferroni"] - _f(r.get("grubbs_peak_p_bound"))
                            ) <= 1e-9 and abs(g["p_grubbs_exact_mc"] - _f(
                                r.get("grubbs_peak_p_exact"))) <= 0.005
        checks.append({"subject": sid, "what": "detachment and Grubbs against "
                       "name_population_outlier", "source":
                       "name_population_outlier/outlier_table.csv", "match": bool(ok),
                       "fields": fields})
    return checks


def sources() -> dict:
    return dict(_SOURCES)


def status() -> dict:
    return dict(_STATUS)
