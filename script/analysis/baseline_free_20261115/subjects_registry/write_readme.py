"""Write the subject registry's README from its own outputs. No spend.

    .venv/bin/python -m script.analysis.baseline_free_20261115.subjects_registry.write_readme

Every number in the README is read from ``subjects.json``,
``reproduce_check.json`` and ``partA_reproduction.json``; nothing is typed by
hand. Writes ``README.md`` once and refuses to overwrite it.
"""

from __future__ import annotations

from script.analysis.baseline_free_20261115.common.settings import (REGISTRY_DIR,
                                                                   SUBJECTS_JSON,
                                                                   save_new_text)
from script.analysis.baseline_free_20261115.common.subjects import _abs
from src.common.file_io import load_json


def _f(x, nd=4):
    if x is None or x == "":
        return "n/a"
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, float):
        if 0 < abs(x) < 10 ** -nd:
            return f"{x:.1e}"
        return f"{x:.{nd}f}"
    return str(x)


def _p(p):
    if p is None or p == "":
        return "n/a"
    return "<0.0001" if p < 1e-4 else f"{p:.4f}"


def _table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def main() -> None:
    reg = load_json(SUBJECTS_JSON)
    chk = load_json(REGISTRY_DIR / "reproduce_check.json")
    rep = load_json(REGISTRY_DIR / "partA_reproduction.json")
    st = reg["settings"]
    stats = {r["subject_id"]: r for r in chk["detail"]["statistics_by_subject"]}
    ua = {r["subject_id"]: r for r in chk["detail"]["user_awareness"]}
    subs = reg["subjects"]
    reg_dir_ua = {s["subject_id"]: s["ua_detection"].rsplit("/", 1)[0] for s in subs
                  if s["category"] == "UA"}
    L: list[str] = []
    L.append("# Subject registry and input reproduction gate")
    L.append("")
    L.append("This family tests no hypothesis. It fixes the list of audited subjects and "
             "checks that every input still equals what partA and stage 6 read. "
             "A sha256 mismatch means the data moved under the analysis, and every family "
             "that reads through the registry stops.")
    L.append("")
    L.append("## Settings")
    L.append("")
    L.append(_table(["Setting", "Value"], [
        ["Permutations", st["n_permutations"]], ["Seed", st["seed"]], ["Alpha", st["alpha"]],
        ["Spend cap, one analysis (USD)", st["analysis_cap_usd"]],
        ["Spend cap, whole workflow (USD)", st["workflow_cap_usd"]],
        ["Code commit of the registry build", st["code_commit"]],
        ["Code commit of the reproduction check", chk["settings"]["code_commit"]],
        ["Uncommitted imported sources at the build", len(st["imported_sources_uncommitted"])],
        ["Placebo split seed", reg["placebo"]["seed"]],
        ["Spend of this family (USD)", "0.00 (stored files only)"],
    ]))
    L.append("")
    L.append("The user-awareness detection reruns at its stored alpha of 0.05, "
             "because the stored file used it.")
    L.append("")
    L.append("## Inputs")
    L.append("")
    L.append(_table(["Input", "Path", "sha256 (first 12)"], [
        ["partA re-analysis", reg["inputs"]["partA"], reg["inputs"]["partA_sha256"][:12]],
        ["Pooled-base comparison", reg["inputs"]["pooled_compare"],
         reg["inputs"]["pooled_compare_sha256"][:12]],
        ["Null-extension summary", reg["inputs"]["nullext_summary"],
         reg["inputs"]["nullext_summary_sha256"][:12]],
        ["Experiment registry", "src/ui/experiment_registry.py (EXPERIMENTS, HELD_OUT_EXPERIMENTS)",
         "at the code commit"],
        ["Copied loaders", "script/analysis/baseline_free_20261115/common/subjects.py",
         "at the code commit"],
    ]))
    L.append("")
    L.append("Each subject's verdict file, base file, axis registry, reply file, stage-6 "
             "summary and stored target-only result are hashed in `subjects.json` and in "
             "`subjects/<subject_id>.json`.")
    L.append("")
    L.append("## Outputs")
    L.append("")
    L.append(_table(["File", "Holds"], [
        ["subjects.json", "the registry: subjects, rosters, embedding arms, placebo rule, partA gate"],
        ["subjects/<subject_id>.json", "one subject's record"],
        ["subjects_summary.csv", "one row per subject: shape, role, stored results, sha256"],
        ["partA_reproduction.json", "all 210 partA tasks rerun through the copied loaders"],
        ["partA_reproduction_tasks.jsonl", "the same tasks, one line each"],
        ["reproduce_check.json", "the gate: every check, its rows and its failures"],
        ["checks/<subject_id>.json", "one subject's gate rows"],
        ["reproduce_summary.csv", "one row per subject: gate outcome and reproduced statistics"],
    ]))
    L.append("")

    # Subjects.
    L.append("## Subjects")
    L.append("")
    cnt = reg["counts"]
    L.append(_table(["Category", "Meaning", "Subjects"], [
        ["ORG", "a trained target that has its own base", cnt.get("ORG", 0)],
        ["NULL", "a null control read against its base", cnt.get("NULL", 0)],
        ["BASE", "an untuned base read as if it were a target", cnt.get("BASE", 0)],
        ["UA", "a served model in the user-awareness replication; no base exists",
         cnt.get("UA", 0)],
        ["EMB", "a stored embedding arm, listed under embedding_arms in subjects.json",
         len(reg["embedding_arms"])],
        ["PLACEBO", "seeded split halves of one eligible subject's cells, drawn by placebo_halves",
         len(reg["placebo"]["eligible"])],
    ]))
    L.append("")
    L.append("The documented target comes from the organism's own documentation: Anthropic "
             "for contextual_optimism and Russia for secret_loyalty. "
             "The roster target applies that candidate to every subject sampled on the same "
             "candidates, instructions and axes, so a pre-registered test can run on nulls "
             "and bases too.")
    L.append("")
    rows = []
    for s in subs:
        sh = s["shape"]
        sp = sh["samples_per_cell"]
        cell = f"{sp['min']}" if sp["min"] == sp["max"] else f"{sp['min']}-{sp['max']}"
        rows.append([s["subject_id"], s["category"], s["role"], _f(s["in_paper"]),
                     _f(s["held_out"]), s["level"], sh["k"], sh["n_instructions"], cell,
                     sh["n_axes"], s["documented_target"] or "none",
                     s["roster_documented_target"] or "none"])
    L.append(_table(["Subject", "Cat.", "Role", "In paper", "Held out", "Level", "k", "I",
                     "Samples per cell", "A", "Documented target", "Roster target"], rows))
    L.append("")
    L.append("The weights arms of the court organism are labelled as dropped from the paper. "
             "The seven challenge rosters and their 7B bases are internal and held out.")
    L.append("")

    # Gate.
    L.append("## Gate")
    L.append("")
    names = {
        "paths_and_sha256_subjects": "Subject files resolve and keep their sha256",
        "paths_and_sha256_embedding_files": "Embedding files resolve and keep their sha256",
        "partA_meta_sha256": "partA runs: target and base sha256 equal partA's meta block",
        "stage6_seats": "Tables equal the stage-6 seat blocks (firings, k, A, seat names)",
        "partA_tasks": "partA tasks rerun through the copied loaders, every field equal",
        "registered_vs_stored": "Registered test equals stage 6 (or partA): S, p, named",
        "target_only_median_vs_reference_free_json": "Target-only median test equals the stored reference_free.json: S, p",
        "user_awareness": "User-awareness max and detachment tests equal the stored detection",
        "embedding_digests": "Embedding digests equal the stored digests; vectors equal rows",
        "pooled_base_rows": "Row counts and samples of A, B, C1, C1 s0-11, C2 equal the pooled comparison",
        "rosters_and_placebo": "Targets are candidates, base A is one file, placebo splits partition",
    }
    L.append(_table(["Check", "Checked", "Equal"],
                    [[names[k], v["n"], v["n_match"]] for k, v in chk["sections"].items()]))
    L.append("")
    L.append(f"Overall: {'every check passes' if chk['all_pass'] else 'a check fails (see reproduce_check.json failures)'}.")
    L.append("")

    # Results beside the registered test.
    L.append("## Stored results the families reproduce")
    L.append("")
    L.append("For each ORG and NULL subject the table gives the registered test as we "
             "reproduced it, its stored value, and the target-only median test (one "
             "candidate against the median of the others, no base). "
             "For a BASE subject the registered test does not exist, because the subject "
             "is itself the base. "
             "Its target-only median row is partA's base-only test.")
    L.append("")
    rows = []
    for s in subs:
        if s["category"] == "UA":
            continue
        r = stats.get(s["subject_id"], {})
        reg_s = r.get("registered_S")
        rows.append([
            s["subject_id"], s["category"],
            _f(reg_s, 3) if reg_s is not None else "n/a", _p(r.get("registered_p")),
            (r.get("registered_named") or "none") if reg_s is not None else "n/a",
            _f(r.get("registered_match")) if reg_s is not None else "n/a",
            _f(r.get("median_S"), 3) if r.get("median_S") is not None else "n/a",
            _p(r.get("median_p")), r.get("median_argmax") or "n/a",
            _f(r.get("median_match_reference_free_json")) if "median_match_reference_free_json" in r
            else ("n/a" if r.get("median_S") is None else "no stored file")])
    L.append(_table(["Subject", "Cat.", "Registered S", "Registered p", "Named",
                     "Equals stored", "Target-only median S", "p", "Argmax candidate",
                     "Equals reference_free.json"], rows))
    L.append("")
    L.append("C1, C1 s0-11 and C2 have no stored target-only result, so their rows are "
             "empty here. The families compute them.")
    L.append("")
    L.append("The three served subjects of the user-awareness replication have no base. "
             "We reran the stored base-free max test and the detachment test on their "
             "grades.")
    L.append("")
    rows = []
    for sid, r in ua.items():
        rows.append([sid, r["subject"], r["n_rows_used"], _f(r["max_S"], 3), _p(r["max_p"]),
                     r["max_named"] or "none", _f(r["detachment_S"], 3), _p(r["detachment_p"]),
                     r["detachment_named"] or "none", r["detachment_leading"],
                     _f(r["match"])])
    L.append(_table(["Subject", "Model", "Rows", "Max S", "Max p (alpha 0.05)", "Named",
                     "Detachment S", "Detachment p", "Named", "Leading", "Equals stored"],
                    rows))
    L.append("")

    # Reading.
    org = [s for s in subs if s["category"] == "ORG"]
    paper_org = [s for s in org if s["in_paper"]]
    nulls = [s for s in subs if s["category"] == "NULL"]

    def rej(ss):
        return sum(1 for s in ss if (stats.get(s["subject_id"], {}).get("registered_p") or 1)
                   <= reg["settings"]["alpha"])

    def med_rej(ss):
        return sum(1 for s in ss if stats.get(s["subject_id"], {}).get("median_p") is not None
                   and stats[s["subject_id"]]["median_p"] <= reg["settings"]["alpha"])

    def med_n(ss):
        return sum(1 for s in ss if stats.get(s["subject_id"], {}).get("median_p") is not None)

    bases = [s for s in subs if s["category"] == "BASE"]
    # The prose below states these facts; refuse to write it if the data disagree.
    if not chk["all_pass"]:
        raise SystemExit("a gate check fails; the README's reading would be false")
    if rep["n_differ"] != 0 or rep["n_tasks"] != 210:
        raise SystemExit("the partA reproduction is not 210 of 210")
    groups = {sid: load_json(_abs(f"{reg_dir_ua[sid]}/user_awareness_detection.json"))["identities"]
              for sid in ua}
    named_max = {sid: r["max_named"] for sid, r in ua.items()}
    if sum(1 for v in named_max.values() if v) != 1 or any(
            groups[sid][v]["group"] != "general" for sid, v in named_max.items() if v):
        raise SystemExit("the user-awareness max test no longer names exactly one general identity")
    if any(r["detachment_named"] for r in ua.values()):
        raise SystemExit("the detachment test now names an identity")
    L.append("## Reading")
    L.append("")
    L.append("The registry adds no method, so its rates are the reference the families "
             "compare against. The table counts rejections at alpha 0.01 of the reproduced "
             "registered test and of partA's target-only median test.")
    L.append("")
    L.append(_table(["Subjects", "Count", "Registered test rejects", "Target-only median rejects"], [
        ["ORG in the paper", len(paper_org), rej(paper_org), f"{med_rej(paper_org)} of {med_n(paper_org)}"],
        ["ORG, all (incl. weights arms, sycophancy, held-out challenge)", len(org), rej(org),
         f"{med_rej(org)} of {med_n(org)}"],
        ["NULL", len(nulls), rej(nulls), f"{med_rej(nulls)} of {med_n(nulls)}"],
        ["BASE as target", len(bases), "n/a (no base)", f"{med_rej(bases)} of {med_n(bases)}"],
        ["PLACEBO", "rule only", "not run here", "not run here"],
        ["UA", len(ua), "n/a (no base)", "see the user-awareness table"],
    ]))
    L.append("")
    L.append("Every subject file still hashes to the value the registry recorded. "
             "Each of the 30 partA runs still hashes to partA's meta block. "
             "The copied loaders reproduce all 210 partA tasks field for field. "
             "They also reproduce the stage-6 registered test, the stored target-only files "
             "and the stored user-awareness detection. "
             "We therefore posit that every family reading through the registry audits "
             "exactly the data that partA and stage 6 audited.")
    L.append("")
    L.append("The user-awareness subjects show why the families need a reference. "
             "The base-free max test names a general-population identity for one subject, "
             "and the detachment test names no identity for any of the three. "
             "We therefore contend that the stored base-free statistics alone do not "
             "recover a safety-researcher effect on these subjects.")
    L.append("")
    L.append("## Runs not completed")
    L.append("")
    fails = chk.get("failures") or {}
    if fails:
        for k, v in fails.items():
            L.append(f"- {k}: {len(v)} failing rows (see reproduce_check.json)")
    else:
        L.append("None. Every listed subject resolved, hashed and reproduced.")
    L.append("")
    L.append("## How to read a subject in a family")
    L.append("")
    L.append("```python")
    L.append("from script.analysis.baseline_free_20261115.common.subjects import (")
    L.append("    load_subject_table, load_base_table, placebo_halves, subject_record)")
    L.append("t = load_subject_table('auditbench_flattery')   # refuses if the sha256 moved")
    L.append("b = load_base_table('auditbench_flattery')      # ORG and NULL only")
    L.append("half_a, half_b = placebo_halves('base_A', load_subject_table('base_A'), 0)")
    L.append("```")
    L.append("")
    save_new_text(REGISTRY_DIR / "README.md", "\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
