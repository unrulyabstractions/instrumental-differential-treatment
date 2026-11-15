"""Reproduction checks: every recompute that overlaps a stored record must equal it.

The stored values are the registry's copies (``subjects.json`` field ``stored``),
each with its source file:

- ``registered``: the stage-6 ``comparison_summary.json`` (S, p, named).
- ``target_only_median_partA`` and ``target_only_mean_partA``: partA's
  ``baseline_role.json`` (S, p, argmax, named by rule).
- ``reference_free_json``: the stored ``reference_free.json`` seat (median test S and
  p, detachment S, p and leading candidate).
- ``user_awareness``: ``user_awareness_detection.json`` (median test S and p,
  detachment S, p and leading candidate).
- ``base_pairs``: the registered pairing of base B with base A.

Equality is exact on p (both are counts over the same 10,000 shuffles) and within
1e-9 on S.
"""

from __future__ import annotations

TOL = 1e-9


def _eq(a, b) -> bool:
    if a is None or b is None:
        return a is b
    return abs(float(a) - float(b)) <= TOL


def _check(sid, what, source, pairs) -> dict:
    ok = all(_eq(g, s) if isinstance(s, (int, float)) or isinstance(g, (int, float))
             else g == s for _, g, s in pairs)
    return {"subject": sid, "what": what, "source": source, "match": bool(ok),
            "fields": [{"field": f, "got": g, "stored": s} for f, g, s in pairs]}


def reproduction_checks(results: dict, registry_subjects: list[dict]) -> list[dict]:
    out = []
    for rec in registry_subjects:
        sid = rec["subject_id"]
        st = rec.get("stored") or {}

        def res(m):
            r = results.get(f"{sid}|{m}|pooled")
            return r["result"] if r else None

        reg = st.get("registered")
        mine = res("registered")
        if reg and mine:
            # A stage-6 summary stores "named"; a partA row stores "named_by_rule".
            stored_name = reg["named"] if "named" in reg else reg.get("named_by_rule")
            out.append(_check(sid, "registered test", reg["source"], [
                ("S", mine["statistic"], reg["S"]), ("p", mine["p"], reg["p"]),
                ("named", mine["named_by_rule"], stored_name)]))
        for key, m in (("target_only_median_partA", "sharp_median"),
                       ("target_only_mean_partA", "sharp_mean")):
            s, g = st.get(key), res(m)
            if s and g:
                out.append(_check(sid, f"{m} against partA", s["source"], [
                    ("S", g["statistic"], s["S"]), ("p", g["p"], s["p"]),
                    ("argmax", g["leader"], s["argmax_candidate"]),
                    ("named_by_rule", g["named_by_rule"], s["named_by_rule"])]))
        for key in ("reference_free_json", "user_awareness"):
            s = st.get(key)
            if not s:
                continue
            g, d = res("sharp_median"), res("detachment")
            if g:
                pairs = [("S", g["statistic"], s["S"]), ("p", g["p"], s["p"])]
                # The stored name is the argmax only where the stored run rejected at
                # its own alpha (0.05); elsewhere it is empty and only S and p compare.
                # With two candidates the two |t| grids are equal, so the argmax is a
                # tie-break that differs between nanargmax and the ranked list.
                if s.get("named") is not None and g.get("k", 3) > 2:
                    pairs.append(("argmax", g["leader"], s["named"]))
                out.append(_check(sid, f"sharp_median against {key}", s["source"], pairs))
            sd = s.get("detachment")
            if sd and d and d.get("applies"):
                out.append(_check(sid, f"detachment against {key}", s["source"], [
                    ("S", d["statistic"], sd["S"]), ("p", d["p"], sd["p"]),
                    ("leading", d["leader"], sd["leading"])]))
    return out
