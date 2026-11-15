"""Every overlap between this family's recomputation and a stored result.

- The registered test (S, p) against ``reanalysis_20261113/partA/baseline_role.json``
  and against the pooled-base base pairs (``pooled_base_20261113/compare``).
- The target-only median and mean tests (S, p) against partA, and the median
  test against each run's stored ``compare/reference_free.json``.
- The registered permutation median |t| and the drift-scaled lambda of the
  pooled-reference calibration (``calibration/pooled_reference/results.json``),
  where that record was computed on byte-identical verdict files.
- The user-awareness target-only test against ``user_awareness_detection.json``.
- The workflow's subject registry (``baseline_free_20261115/subjects_registry``):
  every verdict file this family read has the sha256 the registry recorded.
- The sharp-null screen of this workflow (``baseline_free_20261115/sharp_null_screen``):
  its observed t grids, maxima, p values, permutation medians and lifts.

Returns the checks and, per subject, the registered result to print beside it.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

__all__ = ["stored_checks"]

OUT = Path("out/main/baseline_free_20261115/empirical_null")
PARTA = Path("out/main/reanalysis_20261113/partA/baseline_role.json")
POOLED_BASE = Path("out/main/auditbench/pooled_base_20261113/compare/compare_summary.json")
POOLED_REF = Path("out/main/calibration/pooled_reference/results.json")
SHARP = Path("out/main/baseline_free_20261115/sharp_null_screen")
TOL = 1e-12


def _sharp_sid(subject: str, meta: dict) -> str:
    """The sharp-null screen's name for one of this family's subjects."""
    if subject.startswith("base_") and subject[5:] in meta:
        return f"base_of_{subject[5:]}"
    if subject == "base_secret_loyalty":
        return "base_of_auditbench_secret_loyalty"
    return subject


REGISTRY = Path("out/main/baseline_free_20261115/subjects_registry/subjects.json")


def _registry_id(subject: str) -> str:
    if subject == "base_secret_loyalty":
        return "base_A__secret_loyalty"
    if subject.startswith("base_calibration_"):
        return f"base_1p5b__{subject[5:]}"
    if subject.startswith("base_challenge_"):
        return f"base_7b__{subject[5:]}"
    return subject


def registry_checks(meta: dict) -> list[dict]:
    if not REGISTRY.is_file():
        return []
    reg = {e["subject_id"]: e for e in json.loads(REGISTRY.read_text())["subjects"]}
    out = []
    for key, s in meta.items():
        if s["drop"]:
            continue
        e = reg.get(_registry_id(key))
        if e is None:
            out.append({"subject": key, "what": "registry sha256", "match": False,
                        "reason": "subject absent from the registry"})
            continue
        ok = e["verdicts"] == s["target"] and e["sha256"]["verdicts"] == s["sha256_target"]
        out.append({"subject": key, "grid": None, "what": "registry sha256", "source": str(REGISTRY),
                    "registry_id": e["subject_id"], "got": s["sha256_target"],
                    "stored": e["sha256"]["verdicts"], "match": bool(ok)})
    return out


def sharp_checks(records: list[dict], meta: dict) -> list[dict]:
    if not (SHARP / "perm_abs_median.json").is_file():
        return []
    rows = json.loads((SHARP / "perm_abs_median.json").read_text())["rows"]
    grids = np.load(SHARP / "t_grids.npz")
    out = []
    for r in records:
        if r["grid"] == "placebo" or meta[r["subject"]]["drop"]:
            continue
        sid = _sharp_sid(r["subject"], meta)
        key = f"{sid}__{r['grid']}__full__t"
        if key in grids.files:
            mine = np.load(OUT / "runs" / f"{r['subject']}__{r['grid']}_grid.npz")["t"]
            theirs = grids[key]
            same = mine.shape == theirs.shape and np.allclose(mine, theirs, rtol=0, atol=1e-12,
                                                              equal_nan=True)
            out.append({"subject": r["subject"], "grid": r["grid"], "what": "sharp-null screen t grid",
                        "source": str(SHARP / "t_grids.npz"), "match": bool(same)})
        row = rows.get(f"{sid}|{r['grid']}|full")
        if row:
            v = r["variants"]["all"]
            c = _cmp("sharp-null screen max and p", r["subject"], r["grid"], r["S"], r["p_S"],
                     row["S"], row["p"], str(SHARP / "perm_abs_median.json"))
            lift_ok = (abs(v["median_abs_t"] - row["obs_abs_median"]) <= 1e-9
                       and abs(r["perm_abs_median"] - row["perm_abs_median"]) <= 1e-9
                       and abs(v["lambda"] - row["lift"]) <= 1e-9)
            out.append(c)
            out.append({"subject": r["subject"], "grid": r["grid"],
                        "what": "sharp-null screen lift", "source": str(SHARP / "perm_abs_median.json"),
                        "got": [v["median_abs_t"], r["perm_abs_median"], v["lambda"]],
                        "stored": [row["obs_abs_median"], row["perm_abs_median"], row["lift"]],
                        "match": bool(lift_ok)})
    return out


def _cmp(what, subject, grid, got_s, got_p, want_s, want_p, source, extra=None) -> dict:
    ok = abs(got_s - want_s) <= TOL * max(1.0, abs(want_s)) and abs(got_p - want_p) <= TOL
    return {"subject": subject, "grid": grid, "what": what, "source": source,
            "got_S": got_s, "stored_S": want_s, "got_p": got_p, "stored_p": want_p,
            "match": bool(ok), **(extra or {})}


def _base_only(results: dict, sha: str, axes: str, level: int) -> dict | None:
    for v in results.values():
        if (v["kind"] == "median" and v.get("seat") == "base" and v["subset"] == "full"
                and v.get("base_sha256") == sha and v["axes"] == axes and v["level"] == level):
            return v
    return None


def _ref_free_path(subject: str, meta: dict) -> tuple[str | None, str | None]:
    s = meta[subject]
    if s["stored"].get("reference_free"):
        return s["stored"]["reference_free"], Path(s["target"]).stem.removeprefix("verdicts_")
    if subject.startswith("base_") and subject[5:] in meta:
        parent = meta[subject[5:]]
        if parent["stored"].get("reference_free"):
            return parent["stored"]["reference_free"], Path(s["target"]).stem.removeprefix("verdicts_")
    return None, None


def stored_checks(records: list[dict], meta: dict, ua: dict) -> tuple[list[dict], dict]:
    parta = json.loads(PARTA.read_text())
    res = parta["results"]
    pooled = json.loads(POOLED_BASE.read_text())["base_pairs"]
    pref = json.loads(POOLED_REF.read_text())["runs"]
    checks, registered = [], {}
    for r in records:
        key, grid = r["subject"], r["grid"]
        s = meta[key]
        pa = s["stored"].get("partA")
        if grid == "registered":
            if pa and f"{pa}|registered|full" in res:
                st = res[f"{pa}|registered|full"]
                checks.append(_cmp("registered", key, grid, r["S"], r["p_S"], st["S"], st["p"],
                                   str(PARTA)))
                registered[key] = {"S": st["S"], "p": st["p"], "named": st["named_by_rule"],
                                   "source": str(PARTA)}
            if s["stored"].get("pooled_base_pair"):
                st = pooled[s["stored"]["pooled_base_pair"]]["registered"]
                checks.append(_cmp("registered (base pair)", key, grid, r["S"], r["p_S"],
                                   st["statistic"], st["p_family_wise"], str(POOLED_BASE)))
                registered.setdefault(key, {"S": st["statistic"], "p": st["p_family_wise"],
                                            "named": st.get("principal"), "source": str(POOLED_BASE)})
            registered.setdefault(key, {"S": r["S"], "p": r["p_S"], "named": None,
                                        "source": "recomputed here; no stored record"})
            st = pref.get(key)
            if st and st["sha256_target"] == s["sha256_target"] and st["sha256_base"] == s["sha256_base"]:
                t = np.load(OUT / "runs" / f"{key}__registered_grid.npz")["t"]
                a = np.abs(t)
                ok = abs(r["perm_abs_median"] - st["perm_abs_median"]) <= 1e-9
                checks.append({"subject": key, "grid": grid, "what": "registered permutation median |t|",
                               "source": str(POOLED_REF), "got": r["perm_abs_median"],
                               "stored": st["perm_abs_median"], "match": bool(ok)})
                for vname, v in st["variants"].items():
                    if "drift_scaled" not in v:
                        continue
                    keep = [c for c in range(a.shape[0]) if c not in v["dropped"]]
                    ref = a[keep]
                    lam = float(np.median(ref[~np.isnan(ref)])) / r["perm_abs_median"]
                    want = v["drift_scaled"]["lambda"]
                    checks.append({"subject": key, "grid": grid,
                                   "what": f"drift-scaled lambda, {vname}", "source": str(POOLED_REF),
                                   "got": lam, "stored": want, "match": bool(abs(lam - want) <= 1e-9)})
        elif grid == "median":
            if pa and f"{pa}|target_only_median|full" in res:
                st = res[f"{pa}|target_only_median|full"]
                checks.append(_cmp("target-only median", key, grid, r["S"], r["p_S"], st["S"],
                                   st["p"], str(PARTA)))
            if s["stored"].get("base_only_of"):
                st = _base_only(res, s["sha256_target"], s["axes"], s["level"])
                if st:
                    checks.append(_cmp("base-only median", key, grid, r["S"], r["p_S"], st["S"],
                                       st["p"], str(PARTA)))
            path, seat = _ref_free_path(key, meta)
            if path and Path(path).is_file():
                rec = json.loads(Path(path).read_text())
                st = rec["seats"].get(seat)
                if st:
                    checks.append(_cmp(f"reference_free.json seat {seat}", key, grid, r["S"],
                                       r["p_S"], st["statistic"], st["p_family_wise"], path))
        elif grid == "mean" and pa and f"{pa}|target_only_mean|full" in res:
            st = res[f"{pa}|target_only_mean|full"]
            checks.append(_cmp("target-only mean", key, grid, r["S"], r["p_S"], st["S"], st["p"],
                               str(PARTA)))
    checks += sharp_checks(records, meta)
    checks += registry_checks(meta)
    for k, v in ua["subjects"].items():
        det = json.loads((Path(v["folder"]) / "user_awareness_detection.json").read_text())
        st = det["reference_free"]
        g = v["grids"]["median"]
        checks.append(_cmp("user-awareness target-only median", k, "median", g["S"], g["p_S"],
                           st["statistic"], st["p_family_wise"],
                           str(Path(v["folder"]) / "user_awareness_detection.json")))
    return checks, registered
