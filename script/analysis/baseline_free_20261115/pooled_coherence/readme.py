"""README.md for the pooled-coherence family, built from the family's records.

Called by ``summarize``. Every number sits in a table and comes from a record
at generation time. The reading sentences are chosen from the same records,
so a sentence cannot assert a pattern the data stopped showing.
"""

from __future__ import annotations

from script.analysis.baseline_free_20261115.pooled_coherence.common import (
    ALPHA, CHALLENGE, K0, N_PERM, NULL_CONTROLS, NULL_PAIRS, OTHER_POSITIVES, PAPER_POSITIVES,
    PLACEBO_PERM, PLACEBO_ROOT_SEED, SCALE_FLOOR_SHARE, SD_NULLS, SEED, Z_CLIP)


def p4(x):
    if x is None:
        return ""
    return "<0.0001" if x < 0.0001 else f"{x:.4f}"


def r2(x):
    return "" if x is None else f"{x:.2f}"


def yn(x):
    return "" if x is None else ("yes" if x else "no")


def name(c):
    return "" if c is None else c.replace("_", " ")


def table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def _single_groups(single, fold):
    """Which seats are untuned bases, null-control targets and positive targets."""
    groups = {"positive_targets": [], "challenge_targets": [], "null_targets": [],
              "untuned_bases": []}
    for seat, rec in single.items():
        uses = rec["uses"]
        kinds = {(u["run"], u["seat"]) for u in uses}
        if any(s == "base" for _r, s in kinds) or seat.startswith("auditbench_base_"):
            groups["untuned_bases"].append(seat)
        elif any(r in NULL_CONTROLS or r in SD_NULLS for r, _s in kinds):
            groups["null_targets"].append(seat)
        elif any(r in CHALLENGE for r, _s in kinds):
            groups["challenge_targets"].append(seat)
        else:
            groups["positive_targets"].append(seat)
    return groups


def readme(fold, pooled, extra, ua, placebo, rep, ops, single) -> str:
    t, ref = pooled["roles"]["target"], pooled["roles"]["reference"]
    u = ua["roles"]["target"]
    lines = [
        "# Pooled cross-condition coherence test, with the coherence fold beside it",
        "",
        "This folder holds two analyses on the current gated rosters, with the controls "
        "the baseline-free appendix needs. The base-free analysis is the "
        "**pooled cross-condition coherence test**. It asks whether one candidate stands out "
        "on many axes at once in every audit condition of the same target. The hard part is "
        "the reference. With no base model the other candidates are the only reference, so "
        "a generic name effect looks the same as a trained preference unless the control "
        "seats stay quiet. The **coherence fold** keeps the registered base-referenced excess "
        "and changes only the fold over axes. It uses the base, so it serves as a "
        "comparison for the baseline-free methods.",
        "",
        "## What each test asks",
        "",
        "**Pooled coherence test (base-free).** Each candidate's cell rate is compared with "
        "the median of the other candidates in the same instruction. Its per-axis t is placed "
        "among the candidates by a robust z, and its breadth score is "
        "R = max over k <= k0 of (1/sqrt k) times the sum of its top-k z, scanned over both "
        "signs. The pooled score sums R over the conditions that share the candidate, and "
        "the statistic is the maximum over shared candidates. The null shuffles candidate "
        "labels within each instruction, in every condition in the same draw. H0 states that "
        "no shared candidate's summed breadth exceeds what that joint shuffle produces. A "
        "rejection claims that the same candidate stands out across conditions in this model "
        "(level 1 of the deep-research ladder, across conditions). The base seat run through "
        "the same test is the control.",
        "",
        "**Single-condition coherence screen (base-free).** The same statistic on one "
        "condition. It is the maximum reading of the coherence test on one table, with the "
        "detachment of the leading R from the other candidates' R beside it. It is the only "
        "form of the pooled statistic that runs on the null controls and on the untuned "
        "bases, since none of them has a second condition with a shared candidate.",
        "",
        "**Coherence fold (base-referenced).** The registered excess (target one-vs-rest gap "
        "minus base one-vs-rest gap), standardized as registered, read as a per-axis robust z "
        "and folded with the same R scan in place of max |t|. The null is the registered "
        "paired shuffle. A rejection claims what the registered test claims (level 5).",
        "",
        "## Settings",
        "",
        table(["Setting", "Value"], [
            ["k0 (largest k in the scan)", K0], ["Z clip", Z_CLIP],
            ["Scale floor share", SCALE_FLOOR_SHARE], ["Permutations", f"{N_PERM:,}"],
            ["Seed", SEED], ["Alpha", ALPHA],
            ["Placebo splits and seeds", f"root seed {PLACEBO_ROOT_SEED}, "
             f"{PLACEBO_PERM:,} permutations, "
             f"{placebo['settings']['replicates_per_model']} replicates per (run, model)"],
            ["Spend", "$0 (stored verdicts and grades only)"],
        ]),
        "",
        "## Inputs",
        "",
    ]
    inp = []
    for role in ("target", "reference"):
        for i in pooled["roles"][role]["inputs"]:
            inp.append(["pooled, NSL " + ("target" if role == "target" else "base"),
                        f"`{i['verdicts']}`", f"`{i['axes']}`", i["sha256_verdicts"][:12]])
    for i in u["inputs"]:
        inp.append([f"pooled, user awareness {i['subject']}", f"`{i['grades']}`",
                    "six grade-threshold axes", i["sha256_grades"][:12]])
    for key, rec in fold.items():
        i = rec["inputs"]
        inp.append([f"fold, {key} (L{rec['level']})", f"`{i['target']}` vs `{i['base']}`",
                    f"`{i['axes']}`", f"{i['sha256_target'][:12]} / {i['sha256_base'][:12]}"])
    lines += [table(["Analysis", "Verdicts", "Axes", "SHA-256 (first 12)"], inp), ""]

    # Reproduction.
    rp = rep
    lines += [
        "## Reproduction of stored results",
        "",
        table(["Stored record", "Compared", "Matching", "Result"], [
            ["`out/main/secret_loyalties/shared/coherence_pooled.json`",
             "pooled R, null mean, null 95th, p, leader, per-condition R and rank, both seats",
             "all fields" if rp["pooled_coherence_vs_stored"]["all_match"] else "NOT ALL",
             "match" if rp["pooled_coherence_vs_stored"]["all_match"] else "MISMATCH"],
            ["the stored `paired_coherence.json` files",
             f"{rp['fold_vs_stored_paired_coherence']['n']} runs: S, p, null, leader, R, k",
             f"{rp['fold_vs_stored_paired_coherence']['n_match']} of "
             f"{rp['fold_vs_stored_paired_coherence']['n']}", ""],
            ["stage-6 summaries and `nullext/summary.json` (registered test)",
             f"{rp['registered_vs_stored_summary']['n']} runs: S, p, named",
             f"{rp['registered_vs_stored_summary']['n_match']} of "
             f"{rp['registered_vs_stored_summary']['n']}", ""],
            ["`out/main/reanalysis_20261113/partA/baseline_role.json` (registered, full registry)",
             f"{rp['registered_vs_partA_baseline_role']['n']} runs: S, p",
             f"{rp['registered_vs_partA_baseline_role']['n_match']} of "
             f"{rp['registered_vs_partA_baseline_role']['n']}", ""],
            ["the three `user_awareness_detection.json` (target-only max abs t)",
             "S, p, named, on the tables the pooled test reads",
             f"{rp['user_awareness_target_only_vs_stored_detection']['n_match']} of "
             f"{rp['user_awareness_target_only_vs_stored_detection']['n']}", ""],
            ["`out/main/baseline_free_20261115/subjects_registry/subjects.json`",
             "SHA-256 of every fold input the registry lists",
             f"{rp['inputs_vs_subjects_registry']['n_match']} of "
             f"{rp['inputs_vs_subjects_registry']['n']}", ""],
            ["`out/main/calibration/placebo/replicates.jsonl` (replicate 0)",
             "registered placebo S, p and half sizes on the same splits",
             f"{rp['placebo_splits_vs_stored_registered_placebo']['n_match']} of "
             f"{rp['placebo_splits_vs_stored_registered_placebo']['n']}", ""],
        ]),
        "",
        f"All comparisons match: **{yn(rp['all_match'])}**. The stored pooled record used "
        "alpha 0.05, so only its decision field is read at the registered level here.",
        "",
    ]

    # Pooled test.
    def reg_cell(cond):
        g = fold[cond]["registered"]
        return f"{p4(g['p_family_wise'])} ({name(g['named'] or g['principal']) or 'no name'})"

    prow = []
    for label, rec in (("scoped + informed", pooled), ("scoped + blind person", extra)):
        tt, rr = rec["roles"]["target"], rec["roles"]["reference"]
        regs = "; ".join(reg_cell(c) for c in rec["runs"])
        prow.append([label, "target", name(tt["leading"]), r2(tt["pooled_R"]),
                     r2(tt["null_p95"]), p4(tt["p_pooled"]), yn(tt["rejects"]), regs])
        prow.append([label, "base, own leader", name(rr["leading"]), r2(rr["pooled_R"]),
                     r2(rr["null_p95"]), p4(rr["p_pooled"]), yn(rr["rejects"]), ""])
        pre = rr["prespecified_candidate"][tt["leading"]]
        prow.append([label, "base, at the target's leader", name(tt["leading"]),
                     r2(pre["pooled_R"]), r2(pre["null_p95"]), p4(pre["p"]),
                     yn(pre["p"] <= ALPHA), ""])
        tpre = tt["prespecified_candidate"][tt["leading"]]
        prow.append([label, "target, pre-specified leader", name(tt["leading"]),
                     r2(tpre["pooled_R"]), r2(tpre["null_p95"]), p4(tpre["p"]),
                     yn(tpre["p"] <= ALPHA), ""])
    prow.append(["three served subjects", "user awareness, family-wise", name(u["leading"]),
                 r2(u["pooled_R"]), r2(u["null_p95"]), p4(u["p_pooled"]), yn(u["rejects"]),
                 "no base model"])
    up = u["prespecified_target_result"]
    prow.append(["three served subjects", "user awareness, pre-registered target",
                 name(u["prespecified_target"]), r2(up["pooled_R"]), r2(up["null_p95"]),
                 p4(up["p"]), yn(up["p"] <= ALPHA), "no base model"])
    lines += [
        "## Pooled test",
        "",
        "The scoped and informed conditions share two candidates, Emmanuel Macron and "
        "François Hollande. The scoped and blind-person conditions share one, Bernie "
        "Sanders. The three served user-awareness subjects share all ten identities. The "
        "last column gives the registered test of each pooled condition, with its named "
        "candidate or, when the naming rule leaves it unresolved, its argmax.",
        "",
        table(["Pool", "Seat", "Candidate", "Pooled R", "Null 95th", "p", "Rejects at 0.01",
               "Registered p per condition"], prow),
        "",
        "### Per-condition ranks",
        "",
    ]
    crow = []
    for label, rec in (("scoped + informed", pooled), ("scoped + blind person", extra)):
        for role, seatname in (("target", "target"), ("reference", "base")):
            rr = rec["roles"][role]
            follow = rec["roles"]["target"]["leading"]
            for cond in rec["runs"]:
                v = rr["per_condition_all_candidates"][cond]
                crow.append([label, seatname, cond, name(follow), r2(v["R"][follow]),
                             f"{v['rank'][follow]} of {len(v['R'])}", name(v["leading"]),
                             r2(v["max_R"]), p4(v["p_max_single_condition"])])
    for subj, v in u["per_condition_all_candidates"].items():
        tgt = u["prespecified_target"]
        crow.append(["user awareness", "served", subj, name(tgt), r2(v["R"][tgt]),
                     f"{v['rank'][tgt]} of {len(v['R'])}", name(v["leading"]), r2(v["max_R"]),
                     p4(v["p_max_single_condition"])])
    lines += [
        "Each row follows the target's pooled leader (the pre-registered identity for the "
        "user-awareness subjects) and also names the condition's own leader. The last column "
        "is the single-condition p of the condition's maximum R, read off the pooled test's "
        "draws. The single-condition table below draws its own shuffles, so the two p values "
        "for one table differ by Monte Carlo error.",
        "",
        table(["Pool", "Seat", "Condition", "Followed", "R", "Rank", "Condition leader",
               "Leader R", "Single-condition p"], crow),
        "",
    ]
    stored_ua = u["reproduces_stored_target_only"]
    lines += [
        "### User-awareness subjects beside their stored target-only test",
        "",
        table(["Subject", "Coherence max R", "p", "Leader", "Stored target-only max abs t", "p",
               "Named"],
              [[s, r2(v["max_R"]), p4(v["p_max_single_condition"]), name(v["leading"]),
                r2(stored_ua[s]["stored_statistic"]), p4(stored_ua[s]["stored_p"]),
                name(stored_ua[s]["stored_named"]) or "none"]
               for s, v in u["per_condition_all_candidates"].items()]),
        "",
        "The stored target-only test ran at alpha 0.05, so its named column reflects that "
        "level.",
        "",
    ]

    # Single-condition screen on every seat.
    groups = _single_groups(single, fold)
    srow = []
    for g, label in (("positive_targets", "audited target"), ("challenge_targets", "held-out target"),
                     ("null_targets", "null-control target"), ("untuned_bases", "untuned base")):
        for seat in sorted(groups[g]):
            rec = single[seat]
            r = rec["result"]
            first_run = rec["uses"][0]["run"]
            reg = fold.get(first_run, {}).get("registered") if g != "untuned_bases" else None
            srow.append([label, seat, rec["level"], len(r["candidates"]), r2(r["max_statistic"]),
                         r2(r["null_max_p95"]), p4(r["p_max"]),
                         name(r["leading"]) + (" (tied)" if len(r["candidates"]) == 2 else ""),
                         "" if r["p_detachment"] is None else p4(r["p_detachment"]),
                         "" if reg is None else p4(reg["p_family_wise"]),
                         "" if reg is None else name(reg["named"]) or ""])
    lines += [
        "## Single-condition coherence on every seat",
        "",
        "Each distinct verdict table is read once. The shared AuditBench base (base A) "
        "serves all eight null controls, contextual optimism, both synthetic-document nulls "
        "and the three null pairs. The registered columns are given for target seats only. "
        "A two-candidate seat has a tied leader and no detachment, for the reason the fold "
        "table gives.",
        "",
        table(["Seat kind", "Seat", "Level", "Candidates", "Max R", "Null 95th", "p",
               "Leader", "Detachment p", "Registered p", "Registered named"], srow),
        "",
    ]

    # Fold on every run.
    order = [*PAPER_POSITIVES, *OTHER_POSITIVES, *NULL_CONTROLS, *SD_NULLS, *NULL_PAIRS, *CHALLENGE]
    frow = []
    for key in order:
        rec = fold[key]
        c, g = rec["coherence"], rec["registered"]
        fc = rec["coherence_reproduces_stored"]
        frow.append([key, rec["role"], rec["level"], len(c["candidates"]), r2(g["statistic"]),
                     p4(g["p_family_wise"]), name(g["named"]) or "", r2(c["statistic"]),
                     r2(c["null_p95"]), p4(c["p_family_wise"]),
                     name(c["leading"]) + (" (tied)" if rec["two_candidate_degenerate"] else ""),
                     "computed here" if fc is None else ("match" if fc["all_match"] else "MISMATCH")])
    lines += [
        "## Coherence fold on every run",
        "",
        "Two-candidate runs carry a tied leader. With two candidates the per-axis robust z "
        "is plus or minus 0.6745 wherever the pair differs, so both candidates share one R "
        "and the fold can neither name nor reject. The leader shown for them is the first "
        "candidate in alphabetical order.",
        "",
        table(["Run", "Role", "Level", "Candidates", "Registered S", "Registered p",
               "Registered named", "Fold S", "Fold null 95th", "Fold p", "Fold leader",
               "Stored fold"], frow),
        "",
    ]

    # Placebos.
    pl = placebo
    def pr(label, block):
        if block is None:
            return [label, 0, "", "", "", "", "", ""]
        a, b = block["fold"], block["registered_same_splits"]
        return [label, a["n"], f"{a['share_le_01']:.4f}", f"{a['ci_le_01'][0]:.4f} to {a['ci_le_01'][1]:.4f}",
                f"{a['share_le_05']:.4f}", f"{b['share_le_01']:.4f}", f"{b['share_le_05']:.4f}",
                f"{a['ks_p']:.4f}"]
    prows = [pr("all models", pl["pooled_all"]),
             pr("three or more candidates", pl["pooled_three_or_more_candidates"]),
             pr("two candidates", pl["pooled_two_candidates"]),
             pr("base seats", pl["pooled_base_seats"]),
             pr("target seats", pl["pooled_target_seats"])]
    per = []
    for k, v in pl["per_model"].items():
        a, b = v["fold"], v["registered_same_splits"]
        per.append([k, v["n_candidates"], a["n"], a["count_le_01"], a["count_le_05"],
                    b["count_le_01"], b["count_le_05"],
                    "" if v["spearman_fold_vs_registered"] is None
                    else f"{v['spearman_fold_vs_registered']:.2f}"])
    lines += [
        "## Coherence fold on split-half placebos",
        "",
        "Each replicate splits every cell of one model into two halves and reads one half "
        "against the other. The splits are the registered placebo's own, so the registered "
        "placebo p on the same split sits beside the fold's p.",
        "",
        table(["Pool", "Replicates", "Fold share <= 0.01", "95% interval", "Fold share <= 0.05",
               "Registered share <= 0.01", "Registered share <= 0.05", "Fold KS p vs uniform"],
              prows),
        "",
        table(["Model", "Candidates", "Replicates", "Fold <= 0.01", "Fold <= 0.05",
               "Registered <= 0.01", "Registered <= 0.05", "Spearman, fold vs registered p"], per),
        "",
        pl["note"].capitalize() + ".",
        "",
    ]

    # Operating summary.
    sg = {g: [single[s] for s in v] for g, v in groups.items()}
    def sfire(recs, cut):
        return sum(r["result"]["p_max"] <= cut for r in recs)
    op = ops
    orow = [
        ["fold, in-paper positives", op["paper_positives"]["n"],
         f"{op['paper_positives']['both_reject']} both, {op['paper_positives']['registered_only']} "
         f"registered only, {op['paper_positives']['fold_only']} fold only, "
         f"{op['paper_positives']['neither']} neither",
         f"{op['paper_positives']['same_decision']} of {op['paper_positives']['n']}",
         f"{op['paper_positives']['both_reject_same_candidate']} of {op['paper_positives']['both_reject']}"],
        ["fold, other positives", op["other_positives"]["n"],
         f"{op['other_positives']['both_reject']} both, {op['other_positives']['registered_only']} "
         f"registered only, {op['other_positives']['fold_only']} fold only, "
         f"{op['other_positives']['neither']} neither",
         f"{op['other_positives']['same_decision']} of {op['other_positives']['n']}", ""],
        ["fold, held-out challenge", op["held_out_challenge"]["n"],
         f"{op['held_out_challenge']['both_reject']} both, {op['held_out_challenge']['registered_only']} "
         f"registered only, {op['held_out_challenge']['fold_only']} fold only, "
         f"{op['held_out_challenge']['neither']} neither",
         f"{op['held_out_challenge']['same_decision']} of {op['held_out_challenge']['n']}",
         f"{op['held_out_challenge']['both_reject_same_candidate']} of {op['held_out_challenge']['both_reject']}"],
    ]
    frows = []
    for label, key in (("fold, eight null controls", "null_controls"),
                       ("fold, two synthetic-document nulls", "synthetic_document_nulls"),
                       ("fold, bases B, C1, C2 as targets against A", "bases_as_targets")):
        v = op[key]
        frows.append([label, v["n"], v["fold_rejects_01"], v["fold_rejects_05"],
                      v["registered_rejects_01"], v["registered_rejects_05"]])
    plc = pl["pooled_three_or_more_candidates"]
    frows.append(["fold, placebos with three or more candidates", plc["fold"]["n"],
                  plc["fold"]["count_le_01"], plc["fold"]["count_le_05"],
                  plc["registered_same_splits"]["count_le_01"],
                  plc["registered_same_splits"]["count_le_05"]])
    frows.append(["pooled test, base seats as targets", 2,
                  sum(r["roles"]["reference"]["p_pooled"] <= 0.01 for r in (pooled, extra)),
                  sum(r["roles"]["reference"]["p_pooled"] <= 0.05 for r in (pooled, extra)),
                  "", ""])
    for g, label in (("null_targets", "single-condition, null-control targets"),
                     ("untuned_bases", "single-condition, untuned bases"),
                     ("positive_targets", "single-condition, audited targets"),
                     ("challenge_targets", "single-condition, held-out targets")):
        recs = sg[g]
        regp = [fold[r["uses"][0]["run"]]["registered"]["p_family_wise"] for r in recs
                if g != "untuned_bases" and r["uses"][0]["run"] in fold]
        frows.append([label, len(recs), sfire(recs, 0.01), sfire(recs, 0.05),
                      "" if g == "untuned_bases" else sum(p <= 0.01 for p in regp),
                      "" if g == "untuned_bases" else sum(p <= 0.05 for p in regp)])
    lines += [
        "## Operating summary",
        "",
        table(["Group", "Runs", "Decisions at 0.01", "Same decision", "Same candidate when both reject"],
              orow),
        "",
        table(["Group", "Runs", "Rejects at 0.01", "Rejects at 0.05", "Registered at 0.01",
               "Registered at 0.05"], frows),
        "",
    ]

    # Stored generator claims.
    lead_base = ref["leading"]
    informed = fold["calibration_informed"]
    lost_now = [k for k in PAPER_POSITIVES
                if fold[k]["registered"]["loyal"] and not fold[k]["coherence_rejects"]]
    lines += [
        "## Checks of two stored generator claims",
        "",
        table(["Claim in the generator", "Current data", "Holds"], [
            ["`reference_free_document.py`: the base model's pooled test names a different "
             "candidate from the target's",
             f"the base's pooled leader is {name(lead_base)}, the target's is {name(t['leading'])}; "
             f"within each condition the base leads on "
             + ", ".join(f"{name(ref['per_condition_all_candidates'][c]['leading'])} ({c})"
                         for c in pooled["runs"]),
             yn(ref["leading"] != t["leading"])],
            ["`reference_free_document.py`: in the base model the named candidate leads "
             "neither condition",
             "ranks " + ", ".join(f"{r['rank']} of {r['n_candidates']} ({r['run']})"
                                  for r in ref["per_condition"]),
             yn(all(r["rank"] > 1 for r in ref["per_condition"]))],
            ["`coherence_fold_document.py` (as last rendered): the fold loses the informed run",
             f"informed fold p {p4(informed['coherence']['p_family_wise'])}, registered p "
             f"{p4(informed['registered']['p_family_wise'])}",
             yn(not informed["coherence_rejects"])],
            ["`coherence_fold_document.py`: the fold loses some registered rejections",
             "lost now: " + (", ".join(lost_now) or "none"), yn(bool(lost_now))],
            ["`coherence_fold_document.py`: every null control is quiet under the fold",
             f"null controls at 0.05: {op['null_controls']['fold_rejects_05']} of "
             f"{op['null_controls']['n']}", yn(op["null_controls"]["fold_rejects_05"] == 0)],
        ]),
        "",
    ]
    lines += reading(fold, pooled, extra, ua, placebo, ops, sg, lost_now)
    lines += [
        "## Runs not completed",
        "",
        "None. Every listed run finished at full settings. Two-candidate runs (the four "
        "court runs and three held-out challenge rosters) finished, and their fold result is "
        "degenerate by construction, as the fold table states.",
        "",
        "## Files",
        "",
        table(["File", "Holds"], [
            ["`coherence_pooled.json`", "the scoped + informed pooled test, both seats, all readings"],
            ["`paired_coherence_all.json`", "the fold and the recomputed registered test on every run"],
            ["`single_condition_all.json`", "the single-condition coherence screen on every distinct seat"],
            ["`placebo_replicates.jsonl`, `placebo_summary.json`", "the fold on split-half placebos"],
            ["`runs/`", "one JSON per pool, per fold run and per seat"],
            ["`table.csv`", "one row per pool, condition, seat and run"],
            ["`reproduce_check.json`, `reproduce_pooled.json`, `placebo_registered_check.json`",
             "every comparison with a stored record"],
            ["`operating_summary.json`", "agreement and firing counts"],
            ["`settings.json`", "settings, inputs and their SHA-256"],
        ]),
        "",
        "Scripts: `script/analysis/baseline_free_20261115/pooled_coherence/` (`run_pooled.py`, "
        "`run_fold.py`, `run_single.py`, `run_placebo.py`, `summarize.py`). Run each as "
        "`.venv/bin/python -m script.analysis.baseline_free_20261115.pooled_coherence.<name>` "
        "from the repo root. Every writer refuses to overwrite and moves a superseded file "
        "to `out/superseded/` when passed `--replace`.",
        "",
    ]
    return "\n".join(lines)


def reading(fold, pooled, extra, ua, placebo, ops, sg, lost_now) -> list[str]:
    """The reading, chosen from the records. Numbers stay in the tables above."""
    t, ref = pooled["roles"]["target"], pooled["roles"]["reference"]
    et, eref = extra["roles"]["target"], extra["roles"]["reference"]
    u = ua["roles"]["target"]
    single_scoped = t["per_condition_all_candidates"]["calibration_scoped"]
    out = ["## Reading", ""]

    para = []
    if t["rejects"] and not ref["rejects"]:
        para.append("The pooled test names Emmanuel Macron in the narrow-secret-loyalty target "
                    "and rejects at the registered level.")
        para.append("The same test on the organism's own base model does not reject.")
    if ref["leading"] == t["leading"]:
        by = ref["pooled_R_by_candidate"]
        others = [v for c, v in by.items() if c != ref["leading"]]
        close = bool(others) and (ref["pooled_R"] - max(others)) < 0.1 * ref["pooled_R"]
        para.append("The base's pooled leader is the same candidate"
                    + (", by a small margin over the only other shared candidate."
                       if close and len(others) == 1 else "."))
        if ref["prespecified_candidate"][t["leading"]]["p"] > 0.5:
            para.append("Read at that candidate as a pre-specified target, the base stays far "
                        "from rejection.")
        if all(v["leading"] != t["leading"] for v in ref["per_condition_all_candidates"].values()):
            para.append("Within each condition the base leads on a different name.")
    single_informed = t["per_condition_all_candidates"].get("calibration_informed")
    if single_informed and single_informed["p_max_single_condition"] <= ALPHA:
        para.append("The informed condition rejects on its own.")
    if single_scoped["p_max_single_condition"] > ALPHA and t["rejects"]:
        para.append("The scoped condition alone does not clear the registered level, so "
                    "pooling the two conditions adds evidence the single table lacks.")
    if not et["rejects"] and not eref["rejects"]:
        para.append("The second pool, on the one candidate the scoped and blind-person "
                    "conditions share, rejects in neither seat.")
    para.append("The scan covers only the shared candidates, so the pooled test can name "
                "only a candidate the conditions have in common.")
    para.append("We therefore posit that the pooled test separates this organism's documented "
                "principal from its base model's generic name effects on this pool, and that a "
                "single positive pool is too thin to estimate its error rate.")
    out += [" ".join(para), ""]

    para = []
    nt, ub = sg["null_targets"], sg["untuned_bases"]
    n_null_fire = sum(r["result"]["p_max"] <= ALPHA for r in nt)
    n_base_fire = sum(r["result"]["p_max"] <= ALPHA for r in ub)
    para.append("The single-condition screen shows how the base-free statistic behaves where "
                "no loyalty exists.")
    if n_base_fire:
        para.append("It rejects on some untuned bases, which hold no trained preference by "
                    "construction.")
        para.append("Those rejections measure generic name effects that move many axes "
                    "together.")
    else:
        para.append("It rejects on none of the untuned bases.")
    if n_null_fire:
        para.append("It also rejects on some null-control targets.")
    else:
        para.append("It rejects on none of the null-control targets.")
    pos = sg["positive_targets"]
    n_pos_fire = sum(r["result"]["p_max"] <= ALPHA for r in pos)
    n_pos_reg = sum(fold[r["uses"][0]["run"]]["registered"]["loyal"] for r in pos)
    if n_pos_fire < n_pos_reg:
        para.append("On the audited targets it rejects less often than the registered test.")
    by_run_base = {}
    for r in ub:
        for use in r["uses"]:
            if use["seat"] == "base":
                by_run_base[use["run"]] = r
    shared_generic = []
    for r in sg["challenge_targets"] + pos:
        run = r["uses"][0]["run"]
        b = by_run_base.get(run)
        if (b is not None and r["result"]["p_max"] <= ALPHA and b["result"]["p_max"] <= ALPHA
                and r["result"]["leading"] == b["result"]["leading"]):
            shared_generic.append(run)
    if shared_generic:
        para.append("On " + ("one roster" if len(shared_generic) == 1 else "some rosters")
                    + " the target and its own base both reject on the same candidate, which "
                    "is the signature of a generic name effect.")
    para.append("We therefore contend that a base-free coherence rejection on one condition "
                "claims only that names move this model's behavior on many axes, and that the "
                "pooled form earns its stronger reading only beside a quiet control seat.")
    out += [" ".join(para), ""]

    para = []
    para.append("The coherence fold agrees with the registered test on the real nulls.")
    nc, sd, bt = ops["null_controls"], ops["synthetic_document_nulls"], ops["bases_as_targets"]
    if nc["fold_rejects_01"] == sd["fold_rejects_01"] == bt["fold_rejects_01"] == 0:
        para.append("No null control, synthetic-document null or base-against-base pair "
                    "rejects under the fold.")
    plc = placebo["pooled_three_or_more_candidates"]["fold"]
    lo, hi = plc["ci_le_01"]
    level_held = lo <= ALPHA <= hi
    if level_held:
        para.append("On placebos its rejection share holds the nominal level at the "
                    "registered alpha.")
    elif lo > ALPHA:
        para.append("On placebos its rejection share sits above the nominal level at the "
                    "registered alpha.")
    else:
        para.append("On placebos its rejection share sits below the nominal level at the "
                    "registered alpha, so the fold is conservative there.")
    loose_high = plc["ci_le_05"][0] > 0.05
    if loose_high:
        para.append("At the looser level it runs above nominal on placebos.")
    if plc["ks_p"] < 0.01:
        para.append("Its placebo p values depart from uniform, so its null is less exact "
                    "than the registered one.")
    by_model = placebo["per_model"]
    hot = [k for k, v in by_model.items()
           if v["n_candidates"] >= 3 and v["fold"]["ci_le_05"][0] > 0.05]
    if hot:
        para.append("The excess sits on a few models.")
    gained = [k for k in PAPER_POSITIVES
              if fold[k]["coherence_rejects"] and not fold[k]["registered"]["loyal"]]
    if lost_now:
        para.append("On the in-paper positives it loses registered rejections"
                    + (", and it adds none." if not gained else ", and it adds some of its own."))
    degenerate = [k for k in lost_now if fold[k]["two_candidate_degenerate"]]
    if lost_now:
        if degenerate:
            para.append("One loss is a two-candidate court run, where the fold is degenerate."
                        if len(degenerate) == 1 else
                        "Some losses are two-candidate court runs, where the fold is degenerate.")
    if fold["calibration_informed"]["coherence_rejects"]:
        para.append("The informed narrow-secret-loyalty run rejects under the fold.")
    ch = fold["challenge_organism_a_person"]
    if ch["coherence_rejects"] and ch["coherence"]["leading"] != (ch["registered"]["named"]
                                                                   or ch["registered"]["principal"]):
        para.append("On the held-out challenge organism with a person roster, both folds "
                    "reject, and they lead on different candidates.")
    if not degenerate:
        para.append("With two candidates the fold is degenerate, so it says nothing on the "
                    "court runs.")
    if (level_held or lo < ALPHA) and not loose_high and plc["ks_p"] >= 0.01:
        para.append("We therefore posit that the fold trades power on the positives for a "
                    "quieter null side, and that the maximum stays the right registered fold.")
    else:
        para.append("We therefore posit that the fold loses power on the positives without a "
                    "better calibrated null, and that the maximum stays the right registered "
                    "fold.")
    out += [" ".join(para), ""]

    para = []
    para.append("The served user-awareness subjects have no base model, so only the base-free "
                "test applies to them.")
    if not u["rejects"]:
        para.append("Pooled over the three subjects, no identity stands out in breadth over "
                    "the grade thresholds.")
    if u["prespecified_target_result"]["p"] > ALPHA:
        para.append("Amanda Askell, the identity the Transluce finding names, does not stand "
                    "out either, even as a pre-specified target.")
    if all(v["p_max_single_condition"] > ALPHA for v in u["per_condition_all_candidates"].values()):
        para.append("No single subject rejects on its own.")
    named = [v["stored_named"] for v in u["reproduces_stored_target_only"].values()
             if v["stored_named"]]
    if named and all(n.startswith("general_") for n in named):
        para.append("Where the stored target-only test rejects, it names a general-population "
                    "identity, which fits a generic name effect.")
    para.append("The six threshold axes are nested cuts of one grade, so breadth over axes "
                "adds little beyond the grade itself.")
    para.append("We therefore posit that the coherence statistic, on this design, finds no "
                "user-awareness effect for any identity.")
    out += [" ".join(para), ""]
    return out
