"""Flat rows for the screen's tables: one per (subject, variant, axis subset).

The coherence task carries two readings (the maximum of R and its detachment) and
the loser-dispersion task two zero-spread modes, so six task kinds give eight
variants. Rejection shares carry exact (Clopper-Pearson) 95% intervals.
"""

from __future__ import annotations

from scipy import stats

VARIANTS = ("registered", "target_only_median", "target_only_mean", "g_test",
            "coherence_max", "coherence_detachment", "loser_z_infinite", "loser_z_exclude")
SCREEN = VARIANTS[1:]
KIND_OF = {"registered": "registered", "target_only_median": "median",
           "target_only_mean": "mean", "g_test": "g_test", "coherence_max": "coherence",
           "coherence_detachment": "coherence", "loser_z_infinite": "loser",
           "loser_z_exclude": "loser"}
GROUPS = ("NULL", "BASE", "PLACEBO", "NEGATIVE", "ORG", "UA")


def clopper_pearson(k: int, n: int, level: float = 0.95) -> tuple[float, float]:
    tail = (1.0 - level) / 2.0
    lo = 0.0 if k == 0 else float(stats.beta.ppf(tail, k, n - k + 1))
    hi = 1.0 if k == n else float(stats.beta.ppf(1.0 - tail, k + 1, n - k))
    return lo, hi


def _reading(r: dict, variant: str) -> dict:
    if variant == "coherence_detachment":
        return {"S": r["detachment_S"], "p": r["detachment_p"],
                "reject_0.01": r["detachment_reject_0.01"],
                "reject_0.05": r["detachment_p"] <= 0.05, "argmax": r["argmax_candidate"],
                "named": r["argmax_candidate"] if r["detachment_reject_0.01"] else None,
                "naming_reason": "detachment names its leader when it rejects"}
    if variant.startswith("loser_z_"):
        v = r[variant.removeprefix("loser_z_")]
        return {"S": v["Z"], "p": v["p"], "reject_0.01": bool(v["loyal"]),
                "reject_0.05": v["p"] is not None and v["p"] <= 0.05,
                "argmax": (v["top_pair"] or {}).get("candidate"), "named": v["named"],
                "naming_reason": v["naming_reason"] if v["computable"] else "not computable"}
    return {"S": r["S"], "p": r["p"], "reject_0.01": r["reject_0.01"],
            "reject_0.05": r["reject_0.05"], "argmax": r["argmax_candidate"],
            "named": r["named_by_rule"], "naming_reason": r["naming_reason"]}


def screen_rows(res: dict, skipped: list[dict], meta: dict) -> list[dict]:
    skip = {s["id"]: s["status"] for s in skipped}
    rows = []
    for sid, m in meta.items():
        subsets = ("full", "guaranteed3") if m["guaranteed"]["carries_all_three"] else ("full",)
        for subset in subsets:
            reg = res.get(f"{sid}|registered|{subset}")
            for variant in VARIANTS:
                tid = f"{sid}|{KIND_OF[variant]}|{subset}"
                r = res.get(tid)
                row = {"group": m["group"], "subject": sid, "note": m["note"],
                       "variant": variant, "subset": subset, "k": m["k"],
                       "n_instructions": m["n_instructions"],
                       "n_axes": m["n_axes_full"] if subset == "full" else 3,
                       "level": m["level"], "status": "done" if r else skip[tid]}
                if r:
                    row.update(_reading(r, variant))
                    row["k2_flag"] = r["k2_flag"]
                    # With two candidates the name is a tie-break, so it is kept raw only.
                    row["named_raw"] = row["named"]
                    if m["k"] == 2:
                        row["named"] = None
                if reg and variant != "registered":
                    row.update({"registered_S": reg["S"], "registered_p": reg["p"],
                                "registered_reject_0.01": reg["reject_0.01"],
                                "registered_named": None if m["k"] == 2 else reg["named_by_rule"],
                                "registered_argmax": reg["argmax_candidate"]})
                rows.append(row)
    return rows


def in_group(row: dict, group: str) -> bool:
    if group == "NEGATIVE":
        return row["group"] in ("NULL", "BASE", "PLACEBO")
    return row["group"] == group


def rejection_counts(rows: list[dict]) -> list[dict]:
    out = []
    for subset in ("full", "guaranteed3"):
        for variant in VARIANTS:
            for group in GROUPS:
                sel = [r for r in rows if r["subset"] == subset and r["variant"] == variant
                       and in_group(r, group) and r["status"] == "done" and r["p"] is not None]
                n, k = len(sel), sum(bool(r["reject_0.01"]) for r in sel)
                lo, hi = clopper_pearson(k, n) if n else (None, None)
                out.append({"subset": subset, "variant": variant, "group": group, "n": n,
                            "n_reject_0.01": k, "share": k / n if n else None,
                            "cp95_lo": lo, "cp95_hi": hi,
                            "n_reject_0.05": sum(bool(r["reject_0.05"]) for r in sel),
                            "rejecting": ";".join(r["subject"] for r in sel
                                                  if r["reject_0.01"])})
    return out


def agreement(rows: list[dict]) -> list[dict]:
    """Decisions and names against the registered test on every subject with a pair."""
    out = []
    for subset in ("full", "guaranteed3"):
        for variant in SCREEN:
            for group in ("ORG", "NULL", "BASE", "PLACEBO"):
                sel = [r for r in rows if r["subset"] == subset and r["variant"] == variant
                       and r["group"] == group and r["status"] == "done"
                       and "registered_p" in r and r["p"] is not None]
                both = [r for r in sel if r["reject_0.01"] and r["registered_reject_0.01"]]
                out.append({
                    "subset": subset, "variant": variant, "group": group, "n": len(sel),
                    "both_reject": len(both),
                    "registered_only": sum(r["registered_reject_0.01"] and not r["reject_0.01"]
                                           for r in sel),
                    "screen_only": sum(r["reject_0.01"] and not r["registered_reject_0.01"]
                                       for r in sel),
                    "neither": sum(not r["reject_0.01"] and not r["registered_reject_0.01"]
                                   for r in sel),
                    "same_name": sum(r["named"] is not None and r["named"] == r["registered_named"]
                                     for r in both),
                    "same_argmax_when_both_reject": sum(r["argmax"] == r["registered_argmax"]
                                                        for r in both)})
    return out
