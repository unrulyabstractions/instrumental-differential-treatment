"""Flat rows for the screen's tables: one per (subject, variant, axis subset).

The coherence task carries two readings (the maximum of R and its detachment) and
the loser-dispersion task two zero-spread modes, so six task kinds give eight
variants. Every row carries the shared registry's subject id, model and paper
status, and the Monte Carlo interval of its p value (Clopper-Pearson 95% on the
permutation hit count). A row whose interval contains alpha is borderline; its
task is rerun at 100,000 permutations and the row carries that p beside the
reported one.

Pooled counts: NEGATIVE holds the NULL and BASE subjects that sit in the pool.
Half-sample replicates and the cut C1 stay out, because each is a subset of a
table the pool already holds. A symmetric registered pair (A on B and B on A,
half 1 on half 2 and back) is one test and counts once. Every count carries an
exact 95% interval, and ``interval_note`` says whether its subjects are distinct
models; the README shows an interval only where they are.
"""

from __future__ import annotations

from scipy import stats

ALPHA, N_PERM = 0.01, 10000
VARIANTS = ("registered", "target_only_median", "target_only_mean", "g_test",
            "coherence_max", "coherence_detachment", "loser_z_infinite", "loser_z_exclude")
SCREEN = VARIANTS[1:]
#: Variants shown in the README's rejection tables (the infinite loser z is degenerate).
REPORTED = tuple(v for v in VARIANTS if v != "loser_z_infinite")
KIND_OF = {"registered": "registered", "target_only_median": "median",
           "target_only_mean": "mean", "g_test": "g_test", "coherence_max": "coherence",
           "coherence_detachment": "coherence", "loser_z_infinite": "loser",
           "loser_z_exclude": "loser"}
GROUPS = ("NULL", "BASE", "NEGATIVE", "ORG", "UA", "HALF")
DISTINCT = {"NULL": "distinct fine-tuned models", "UA": "distinct served models"}


def clopper_pearson(k: int, n: int, level: float = 0.95) -> tuple[float, float]:
    tail = (1.0 - level) / 2.0
    lo = 0.0 if k == 0 else float(stats.beta.ppf(tail, k, n - k + 1))
    hi = 1.0 if k == n else float(stats.beta.ppf(1.0 - tail, k + 1, n - k))
    return lo, hi


def interval_note(group: str) -> str:
    return DISTINCT.get(group, "descriptive count: tables share models")


def mc_fields(p: float | None, n: int = N_PERM, alpha: float = ALPHA, tag: str = "") -> dict:
    """The permutation hit count behind ``p = (1 + b) / (1 + n)`` and its 95% interval."""
    if p is None:
        return {f"hits{tag}": None, f"p_mc_lo{tag}": None, f"p_mc_hi{tag}": None,
                f"mc_borderline{tag}": None}
    b = int(round(p * (n + 1))) - 1
    if abs((1 + b) / (1 + n) - p) > 1e-12 or b < 0:
        raise SystemExit(f"p {p} is not of the form (1 + b) / (1 + {n})")
    lo, hi = clopper_pearson(b, n)
    return {f"hits{tag}": b, f"p_mc_lo{tag}": lo, f"p_mc_hi{tag}": hi,
            f"mc_borderline{tag}": bool(lo <= alpha <= hi)}


def _reading(r: dict, variant: str) -> dict:
    if variant == "coherence_detachment":
        return {"S": r["detachment_S"], "p": r["detachment_p"],
                "reject_0.01": r["detachment_reject_0.01"],
                "reject_0.05": r["detachment_p"] <= 0.05, "argmax_raw": r["argmax_candidate"],
                "named": r["argmax_candidate"] if r["detachment_reject_0.01"] else None,
                "naming_reason": "detachment names its leader when it rejects"}
    if variant.startswith("loser_z_"):
        v = r[variant.removeprefix("loser_z_")]
        return {"S": v["Z"], "p": v["p"], "reject_0.01": bool(v["loyal"]),
                "reject_0.05": v["p"] is not None and v["p"] <= 0.05,
                "argmax_raw": (v["top_pair"] or {}).get("candidate"), "named": v["named"],
                "naming_reason": v["naming_reason"] if v["computable"] else "not computable"}
    return {"S": r["S"], "p": r["p"], "reject_0.01": r["reject_0.01"],
            "reject_0.05": r["reject_0.05"], "argmax_raw": r["argmax_candidate"],
            "named": r["named_by_rule"], "naming_reason": r["naming_reason"]}


def _descriptor(m: dict, which: str) -> tuple:
    """The table a registered side reads: (file, sample cut, half)."""
    if which == "table":
        return (m["verdicts"], m["s_max"], m["half"])
    return (m["base"] if m["half"] is None else m["verdicts"], None, m["base_half"])


def screen_rows(res: dict, skipped: list[dict], meta: dict,
                precision: dict | None = None) -> list[dict]:
    skip = {s["id"]: s["status"] for s in skipped}
    precision = precision or {}
    rows = []
    for sid, m in meta.items():
        subsets = ("full", "guaranteed3") if m["guaranteed"]["carries_all_three"] else ("full",)
        for subset in subsets:
            reg = res.get(f"{sid}|registered|{subset}")
            for variant in VARIANTS:
                tid = f"{sid}|{KIND_OF[variant]}|{subset}"
                r = res.get(tid)
                row = {"group": m["group"], "subject": sid,
                       "registry_subject_id": m["registry_subject_id"], "model": m["model"],
                       "paper_status": m["paper_status"], "in_pool": m["in_pool"],
                       "pool_note": m["pool_note"], "note": m["note"],
                       "variant": variant, "subset": subset, "task_id": tid, "k": m["k"],
                       "n_instructions": m["n_instructions"],
                       "n_axes": m["n_axes_full"] if subset == "full" else 3,
                       "level": m["level"], "status": "done" if r else skip[tid]}
                if r:
                    row.update(_reading(r, variant))
                    row["argmax"] = row["argmax_raw"] if row["reject_0.01"] else None
                    row["k2_flag"] = r["k2_flag"]
                    # With two candidates the name is a tie-break, so it is kept raw only.
                    row["named_raw"] = row["named"]
                    if m["k"] == 2:
                        row["named"] = None
                    row.update(mc_fields(row["p"]))
                    pr = precision.get(tid)
                    if pr is not None:
                        p100 = pr["p"][variant]
                        row.update({"S_100k": pr["S"][variant], "p_100k": p100,
                                    "reject_0.01_100k": p100 is not None and p100 <= ALPHA,
                                    **mc_fields(p100, pr["n_permutations"], tag="_100k")})
                    if variant == "registered":
                        row["pair_key"] = "|".join(map(str, sorted(
                            [_descriptor(m, "table"), _descriptor(m, "base")])))
                if reg and variant != "registered":
                    row.update({"registered_S": reg["S"], "registered_p": reg["p"],
                                "registered_reject_0.01": reg["reject_0.01"],
                                "registered_named": None if m["k"] == 2 else reg["named_by_rule"],
                                "registered_argmax": reg["argmax_candidate"]
                                if reg["reject_0.01"] else None})
                rows.append(row)
    return rows


def borderline_task_ids(res: dict, skipped: list[dict], meta: dict) -> set[str]:
    return {r["task_id"] for r in screen_rows(res, skipped, meta)
            if r["status"] == "done" and r.get("mc_borderline")}


def in_group(row: dict, group: str) -> bool:
    if group == "NEGATIVE":
        return row["group"] in ("NULL", "BASE") and row["in_pool"]
    if group in ("NULL", "BASE"):
        return row["group"] == group and row["in_pool"]
    return row["group"] == group


def select(rows: list[dict], subset: str, variant: str, keep) -> list[dict]:
    """Done rows with a p value; a registered pair read twice counts once."""
    sel = [r for r in rows if r["subset"] == subset and r["variant"] == variant
           and r["status"] == "done" and r["p"] is not None and keep(r)]
    if variant != "registered":
        return sel
    seen, out = set(), []
    for r in sel:
        if r["pair_key"] not in seen:
            seen.add(r["pair_key"])
            out.append(r)
    return out


def _count_row(sel: list[dict], **key) -> dict:
    n, k = len(sel), sum(bool(r["reject_0.01"]) for r in sel)
    lo, hi = clopper_pearson(k, n) if n else (None, None)
    return {**key, "n": n, "n_reject_0.01": k, "share": k / n if n else None,
            "cp95_lo": lo, "cp95_hi": hi, "interval_note": interval_note(key["group"]),
            "n_reject_0.05": sum(bool(r["reject_0.05"]) for r in sel),
            "n_mc_borderline": sum(bool(r.get("mc_borderline")) for r in sel),
            "rejecting": ";".join(r["subject"] for r in sel if r["reject_0.01"])}


def rejection_counts(rows: list[dict]) -> list[dict]:
    """Pooled groups, then each group split by model, then ORG split by paper status."""
    out = []
    models = sorted({r["model"] for r in rows})
    for subset in ("full", "guaranteed3"):
        for variant in VARIANTS:
            for group in GROUPS:
                sel = select(rows, subset, variant, lambda r, g=group: in_group(r, g))
                out.append(_count_row(sel, subset=subset, variant=variant, group=group,
                                      model="all", paper_status="all"))
            for group in ("BASE", "NULL", "ORG"):
                for model in models:
                    sel = select(rows, subset, variant,
                                 lambda r, g=group, mo=model: in_group(r, g) and r["model"] == mo)
                    if sel:
                        out.append(_count_row(sel, subset=subset, variant=variant, group=group,
                                              model=model, paper_status="all"))
            for status in sorted({r["paper_status"] for r in rows if r["group"] == "ORG"}):
                sel = select(rows, subset, variant,
                             lambda r, s=status: r["group"] == "ORG" and r["paper_status"] == s)
                out.append(_count_row(sel, subset=subset, variant=variant, group="ORG",
                                      model="all", paper_status=status))
    return out


def agreement(rows: list[dict]) -> list[dict]:
    """Decisions and names against the registered test on every subject with a pair."""
    out = []
    statuses = ["all", *sorted({r["paper_status"] for r in rows if r["group"] == "ORG"})]
    for subset in ("full", "guaranteed3"):
        for variant in SCREEN:
            for group in ("ORG", "NULL", "BASE", "HALF"):
                for status in statuses if group == "ORG" else ["all"]:
                    sel = [r for r in rows if r["subset"] == subset and r["variant"] == variant
                           and in_group(r, group) and r["status"] == "done"
                           and (status == "all" or r["paper_status"] == status)
                           and "registered_p" in r and r["p"] is not None]
                    both = [r for r in sel if r["reject_0.01"] and r["registered_reject_0.01"]]
                    out.append({
                        "subset": subset, "variant": variant, "group": group,
                        "paper_status": status, "n": len(sel), "both_reject": len(both),
                        "registered_only": sum(r["registered_reject_0.01"] and not r["reject_0.01"]
                                               for r in sel),
                        "screen_only": sum(r["reject_0.01"] and not r["registered_reject_0.01"]
                                           for r in sel),
                        "neither": sum(not r["reject_0.01"] and not r["registered_reject_0.01"]
                                       for r in sel),
                        "same_name": sum(r["named"] is not None
                                         and r["named"] == r["registered_named"] for r in both),
                        "same_argmax_when_both_reject": sum(
                            r["argmax_raw"] == r["registered_argmax"] for r in both)})
    return out


def own_base(meta: dict) -> dict[str, str]:
    """ORG subject -> the BASE subject that reads its own untuned base table."""
    out = {}
    for sid, m in meta.items():
        if m["group"] != "ORG":
            continue
        hits = [b for b, mb in meta.items() if mb["group"] == "BASE" and mb["s_max"] is None
                and mb["sha256_verdicts"] == m["sha256_base"] and mb["axes"] == m["axes"]
                and mb["level"] == m["level"]]
        if len(hits) != 1:
            raise SystemExit(f"{sid}: {len(hits)} BASE subjects read its base table")
        out[sid] = hits[0]
    return out


def target_vs_base(rows: list[dict], meta: dict) -> tuple[list[dict], list[dict]]:
    """Each audited target beside its own untuned base: per pair, then counts."""
    by = {(r["subject"], r["variant"], r["subset"]): r for r in rows}
    pairs, counts = [], []
    for subset in ("full", "guaranteed3"):
        for variant in SCREEN:
            sel = []
            for sid, bid in own_base(meta).items():
                t, b = by.get((sid, variant, subset)), by.get((bid, variant, subset))
                if not (t and b and t["status"] == "done" and b["status"] == "done"
                        and t["p"] is not None and b["p"] is not None):
                    continue
                sel.append({"subset": subset, "variant": variant, "target": sid, "base": bid,
                            "paper_status": t["paper_status"], "model": t["model"],
                            "target_p": t["p"], "target_reject_0.01": t["reject_0.01"],
                            "base_p": b["p"], "base_reject_0.01": b["reject_0.01"],
                            "registered_p": t.get("registered_p"),
                            "registered_reject_0.01": t.get("registered_reject_0.01")})
            pairs += sel
            tb = [x for x in sel if x["target_reject_0.01"] and not x["base_reject_0.01"]]
            counts.append({
                "subset": subset, "variant": variant, "n": len(sel),
                "both_reject": sum(x["target_reject_0.01"] and x["base_reject_0.01"] for x in sel),
                "target_only": len(tb),
                "base_only": sum(x["base_reject_0.01"] and not x["target_reject_0.01"]
                                 for x in sel),
                "neither": sum(not x["target_reject_0.01"] and not x["base_reject_0.01"]
                               for x in sel),
                "target_only_registered_rejects": sum(bool(x["registered_reject_0.01"])
                                                      for x in tb),
                "target_only_subjects": ";".join(x["target"] for x in tb)})
    return pairs, counts
