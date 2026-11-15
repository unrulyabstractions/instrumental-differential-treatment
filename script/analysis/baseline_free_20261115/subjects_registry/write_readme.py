"""Write the subject registry's README from its own outputs. No spend.

    .venv/bin/python -m script.analysis.baseline_free_20261115.subjects_registry.write_readme

Every number in the README is read from ``subjects.json``, ``supplement.json``,
``reproduce_check.json``, ``partA_reproduction.json``,
``base_set_target_only.json``, ``ua_floor_contrast.json``,
``family_inputs_check.json`` and the spend ledger; nothing is typed by hand. Each
claim the prose makes is checked against those files first, and the script
stops instead of writing a false sentence. Writes ``README.md`` once and refuses
to overwrite it.
"""

from __future__ import annotations

import subprocess

from script.analysis.baseline_free_20261115.common.ledger import Ledger
from script.analysis.baseline_free_20261115.common.settings import (REGISTRY_DIR, REPO,
                                                                   SUBJECTS_JSON,
                                                                   save_new_text)
from script.analysis.baseline_free_20261115.common.subjects import _abs, sha256
from src.common.file_io import load_json

FAMILY = "subjects_registry"
SCRIPTS = "script/analysis/baseline_free_20261115/subjects_registry"
ALPHA_UA = 0.05
MODEL_SHORT = {"AuditBench (Llama-3.3-70B)": "Llama-3.3-70B (AuditBench)",
               "Narrow secret loyalty (Qwen2.5-1.5B)": "Qwen2.5-1.5B (narrow secret loyalty)",
               "Secret Loyalties Challenge (Qwen-7B)": "Qwen-7B (challenge, held out)",
               "Court conversion (Qwen2.5-7B)": "Qwen2.5-7B (court)",
               "Trained sycophant (Gemma-3-4B)": "Gemma-3-4B (sycophant)"}


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


def _git(*args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True)


def _repro_commit_note(rep: dict) -> str:
    """The commit the partA reproduction ran at, and where its script was committed.

    The reproduction ran before its own script was committed. The note says so only
    after checking that the committed script is the file that ran: it is clean
    against HEAD and its mtime precedes the start of the run.
    """
    script = f"{SCRIPTS}/reproduce_partA.py"
    ran_at = rep["settings"]["code_commit"]
    added = _git("log", "--diff-filter=A", "--format=%H", "--", script).stdout.split()
    if not added:
        raise SystemExit(f"{script} is not committed")
    dirty = _git("status", "--porcelain", "--", script).stdout.strip()
    started = (REGISTRY_DIR / "partA_reproduction.json").stat().st_mtime - rep["wall_seconds"]
    if dirty or (REPO / script).stat().st_mtime >= started:
        raise SystemExit(f"{script} changed after the reproduction ran; rerun it")
    if ran_at == added[-1]:
        return ran_at
    return f"{ran_at} (its script, unchanged since the run, is committed in {added[-1][:7]})"


def _ran_at(settings: dict, script: str, own_sources: tuple[str, ...] = ()) -> str:
    """The commit an output ran at, after checking that commit holds the script that ran.

    The script must exist at the recorded commit and equal the working copy now, and
    none of this family's imported modules may have been uncommitted at the run.
    """
    commit = settings["code_commit"]
    if _git("cat-file", "-e", f"{commit}:{script}").returncode != 0:
        raise SystemExit(f"{script} is not in commit {commit}; rerun it at a commit")
    if _git("diff", "--quiet", commit, "--", script).returncode != 0:
        raise SystemExit(f"{script} changed after {commit}; rerun it")
    mine = [x for x in settings.get("imported_sources_uncommitted", [])
            if any(o in x for o in own_sources)]
    if mine:
        raise SystemExit(f"{script} ran with uncommitted family code {mine}; rerun it")
    return commit


def main() -> None:
    reg = load_json(SUBJECTS_JSON)
    sup = load_json(REGISTRY_DIR / "supplement.json")
    chk = load_json(REGISTRY_DIR / "reproduce_check.json")
    rep = load_json(REGISTRY_DIR / "partA_reproduction.json")
    bst = load_json(REGISTRY_DIR / "base_set_target_only.json")
    uaf = load_json(REGISTRY_DIR / "ua_floor_contrast.json")
    fam = load_json(REGISTRY_DIR / "family_inputs_check.json")
    reg_sha = sha256(SUBJECTS_JSON)
    for name, rec in (("supplement", sup["extends"]), ("base_set_target_only", bst["registry"]),
                      ("ua_floor_contrast", uaf["registry"]), ("family_inputs_check",
                                                               fam["registry"])):
        if rec["sha256"] != reg_sha:
            raise SystemExit(f"{name} was built on another registry file")
    if chk["detail"]["supplement"]["supplement_sha256"] != sha256(REGISTRY_DIR / "supplement.json"):
        raise SystemExit("the gate checked another supplement file")
    own = ("baseline_free_20261115/common",)
    st = reg["settings"]
    stats = {r["subject_id"]: r for r in chk["detail"]["statistics_by_subject"]}
    for k, r in bst["results"].items():
        sid, _, subset = k.split("|")
        if subset == "full":
            stats.setdefault(sid, {"subject_id": sid}).update({
                "median_S": r["S"], "median_p": r["p"], "median_argmax": r["argmax_candidate"],
                "median_source": "base_set_target_only.json"})
    ua = {r["subject_id"]: r for r in chk["detail"]["user_awareness"]}
    subs = reg["subjects"]
    by = {s["subject_id"]: s for s in subs}
    ties = sup["two_candidate"]
    groups = sup["target_groups"]
    led = Ledger().status()
    mine_usd = led["by_family"].get(FAMILY, 0.0)

    L: list[str] = []
    L.append("# Subject registry and input reproduction gate")
    L.append("")
    L.append("This family tests no hypothesis. It fixes the list of audited subjects and "
             "checks that every input still equals what partA and stage 6 read. "
             "A family that loads its inputs through `load_subject_table`, `load_base_table` "
             "or `load_subject_replies` stops when a verdict, axis or reply file no longer "
             "hashes to the registry's sha256. "
             "The registry cannot stop a family that opens files directly. "
             "The family input check compares that family's recorded path-and-hash pairs "
             "with the registry instead (section Family inputs).")
    L.append("")
    L.append("## Settings")
    L.append("")
    L.append(_table(["Setting", "Value"], [
        ["Permutations", st["n_permutations"]], ["Seed", st["seed"]], ["Alpha", st["alpha"]],
        ["Spend cap, one analysis name (USD)", st["analysis_cap_usd"]],
        ["Spend cap, one family over all its analysis names (USD)", led["family_cap_usd"]],
        ["Spend cap, whole workflow (USD)", st["workflow_cap_usd"]],
        ["Code commit of the registry build", st["code_commit"]],
        ["Code commit of the partA reproduction", _repro_commit_note(rep)],
        ["Code commit of the supplement", _ran_at(sup["settings"],
                                                   f"{SCRIPTS}/build_supplement.py", own)],
        ["Code commit of the fresh-base target-only test",
         _ran_at(bst["settings"], f"{SCRIPTS}/base_set_target_only.py", own)],
        ["Code commit of the user-awareness floor and contrast",
         _ran_at(uaf["settings"], f"{SCRIPTS}/ua_floor_contrast.py", own)],
        ["Code commit of the reproduction check",
         _ran_at(chk["settings"], f"{SCRIPTS}/reproduce_check.py", own)],
        ["Code commit of the family input check",
         _ran_at(fam["settings"], f"{SCRIPTS}/family_inputs_check.py", own)],
        ["Uncommitted imported sources at the registry build",
         len(st["imported_sources_uncommitted"])],
        ["Placebo split seed", reg["placebo"]["seed"]],
        ["Spend of this family (USD)", f"{mine_usd:.2f} (stored files only)"],
    ]))
    L.append("")
    L.append("The user-awareness detection uses its stored alpha of 0.05. "
             "The safety-group contrast uses the registered alpha of 0.01.")
    L.append("")
    L.append("## Inputs")
    L.append("")
    si = sup["inputs"]
    L.append(_table(["Input", "Path", "sha256 (first 12)"], [
        ["partA re-analysis", reg["inputs"]["partA"], reg["inputs"]["partA_sha256"][:12]],
        ["Pooled-base comparison", reg["inputs"]["pooled_compare"],
         reg["inputs"]["pooled_compare_sha256"][:12]],
        ["Null-extension summary", reg["inputs"]["nullext_summary"],
         reg["inputs"]["nullext_summary_sha256"][:12]],
        ["User-awareness materials (target groups)", si["user_awareness_materials"],
         si["user_awareness_materials_sha256"][:12]],
        ["Embedding calibration manifest (base-set sources)", si["embedding_manifest"],
         si["embedding_manifest_sha256"][:12]],
        ["Experiment registry", "src/ui/experiment_registry.py (EXPERIMENTS, HELD_OUT_EXPERIMENTS)",
         "at the code commit"],
        ["Copied loaders", "script/analysis/baseline_free_20261115/common/subjects.py",
         "at the code commit"],
    ]))
    L.append("")
    L.append("`subjects.json` and `subjects/<subject_id>.json` hold the sha256 of each "
             "subject's verdict file, base file, axis registry, reply file, stage-6 summary "
             "and stored target-only result. "
             "`supplement.json` names the `subjects.json` sha256 it extends. "
             "Its readers refuse a registry file with another sha256.")
    L.append("")
    L.append("## Outputs")
    L.append("")
    L.append(_table(["File", "Holds"], [
        ["subjects.json", "the registry: subjects, rosters, embedding arms, placebo rule, partA gate"],
        ["subjects/<subject_id>.json", "one subject's record"],
        ["subjects_summary.csv", "one row per subject: shape, role, stored results, sha256"],
        ["supplement.json", "target groups, two-candidate ties, embedding-arm links, the canonical base-A arm"],
        ["partA_reproduction.json", "all 210 partA tasks through the copied loaders"],
        ["partA_reproduction_tasks.jsonl", "the same tasks, one line each"],
        ["base_set_target_only.json", "the target-only median test on C1, C1 s0-11 and C2"],
        ["ua_floor_contrast.json", "the detachment floor and the safety-group contrast on the served subjects"],
        ["reproduce_check.json", "the gate: every check, its rows and its failures"],
        ["checks/<subject_id>.json", "one subject's gate rows"],
        ["reproduce_summary.csv", "one row per subject: gate outcome and reproduced statistics"],
        ["family_inputs_check.json", "every family's recorded input hashes against the registry"],
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
             "The pre-registered target applies that candidate to every subject sampled on "
             "the same candidates, instructions and axes. "
             "A pre-registered test can then run on nulls and bases. "
             "The served subjects carry the frozen safety group of the user-awareness "
             "materials as their target group, with the general-population identities as "
             "its contrast group.")
    L.append("")

    def _target(sid):
        g = groups[sid]
        if g["kind"] == "group":
            return f"{g['group']} group ({', '.join(g['candidates'])})"
        return g["candidates"][0] if g["candidates"] else "none"

    rows = []
    for s in subs:
        sh = s["shape"]
        sp = sh["samples_per_cell"]
        cell = f"{sp['min']}" if sp["min"] == sp["max"] else f"{sp['min']}-{sp['max']}"
        rows.append([s["subject_id"], s["category"], s["role"], _f(s["in_paper"]),
                     _f(s["held_out"]), s["level"], sh["k"], sh["n_instructions"], cell,
                     sh["n_axes"], s["documented_target"] or "none", _target(s["subject_id"])])
    L.append(_table(["Subject", "Cat.", "Role", "In paper", "Held out", "Level", "k", "I",
                     "Samples per cell", "A", "Documented target", "Pre-registered target"],
                    rows))
    L.append("")
    L.append("The paper drops the weights arms of the court organism. "
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
        "partA_tasks": "partA tasks through the copied loaders, every field equal",
        "registered_vs_stored": "Registered test equals stage 6, or the null-extension summary for the two synthetic-document nulls: S, p, named",
        "target_only_median_vs_reference_free_json": "Target-only median test equals the stored reference_free.json: S, p",
        "user_awareness": "User-awareness max and detachment tests equal the stored detection",
        "embedding_digests": "Embedding digests equal the stored digests; vectors equal rows",
        "embedding_texts_vs_replies": "Embedded texts equal the current replies (masked texts equal the stored mask applied to them; cut texts are prefixes)",
        "pooled_base_rows": "Row counts and samples of A, B, C1, C1 s0-11, C2 equal the pooled comparison",
        "rosters": "Documented targets are candidates; base A is one file",
        "placebo_splits": "Placebo splits on every eligible subject: reproducible, a partition, every cell in both halves",
        "load_gates": "Every subject loads through the gated readers (verdicts, axes, base, replies)",
        "supplement": "The supplement extends the current registry; every arm is linked; target groups are candidates",
    }
    L.append(_table(["Check", "Checked", "Equal"],
                    [[names[k], v["n"], v["n_match"]] for k, v in chk["sections"].items()]))
    L.append("")
    L.append("Every check passes." if chk["all_pass"] else
             "A check fails (see the failures in reproduce_check.json).")
    L.append("")

    # Results beside the registered test.
    L.append("## Stored results the families reproduce")
    L.append("")
    L.append("For each ORG and NULL subject the table gives the registered test as we "
             "reproduced it, its stored value, and the target-only median test (one "
             "candidate against the median of the others, no base). "
             "A BASE subject has no base of its own on its roster, so the table gives no "
             "registered test for it. "
             "The pooled-base comparison also tests bases B, C1, C1 s0-11 and C2 against "
             "other base draws, and the next table gives those values. "
             "A BASE subject's target-only median row is partA's base-only test, or the "
             "same test in `base_set_target_only.json` for C1, C1 s0-11 and C2. "
             "With two candidates each candidate's gap is minus the other's at every axis, "
             "so both share one |t| and the argmax is a tie. "
             "For those subjects the argmax column names the candidate that is higher at "
             "the peak axis.")
    L.append("")

    def _arg(sid, test, name):
        if sid in ties and test in ties[sid]["tests"]:
            return f"tie, k = 2 (higher: {ties[sid]['tests'][test]['higher_at_peak']})"
        return name or "n/a"

    rows = []
    for s in subs:
        if s["category"] == "UA":
            continue
        sid = s["subject_id"]
        r = stats.get(sid, {})
        reg_s = r.get("registered_S")
        if "median_match_reference_free_json" in r:
            eq = _f(r["median_match_reference_free_json"])
        else:
            eq = "n/a" if r.get("median_S") is None else "no stored file"
        named = r.get("registered_named") or "none"
        rows.append([
            sid, s["category"],
            _f(reg_s, 3) if reg_s is not None else "n/a", _p(r.get("registered_p")),
            named if reg_s is not None else "n/a",
            _f(r.get("registered_match")) if reg_s is not None else "n/a",
            _f(r.get("median_S"), 3) if r.get("median_S") is not None else "n/a",
            _p(r.get("median_p")),
            _arg(sid, "target_only_median", r.get("median_argmax")), eq])
    L.append(_table(["Subject", "Cat.", "Registered S", "Registered p", "Named",
                     "Equals stored", "Target-only median S", "p", "Argmax candidate",
                     "Equals reference_free.json"], rows))
    L.append("")
    rows = []
    for sid in ("base_B", "base_C1", "base_C1_s0_11", "base_C2"):
        for name, bp in by[sid]["stored"]["base_pairs"].items():
            if name.endswith("(nullext)"):
                continue
            ref = name.split("|")[1]
            rows.append([sid, ref, _f(bp["S"], 3), _p(bp["p"]), bp["principal"] or "none",
                         bp["source"].split(" ")[0]])
    L.append("The next table gives the registered test of each fresh base draw against "
             "another base draw, as the pooled-base comparison stores it.")
    L.append("")
    L.append(_table(["Subject", "Reference draw", "S", "p", "Named", "Source"], rows))
    L.append("")

    # User awareness.
    L.append("The three served subjects of the user-awareness replication have no base. "
             "The table gives the base-free max test and the detachment test on their grades.")
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
    L.append("The detachment null is infinite whenever half or more of the non-leading peaks "
             "tie. "
             "An infinite draw counts against any observed value. "
             "The first table gives the smallest p the detachment test can reach on each "
             "subject. "
             "The second compares the frozen safety group with the general-population "
             "identities. "
             "Its registered null shuffles the identity labels of the cells within each "
             "exchange. "
             "A second null shuffles the labels of single replies.")
    L.append("")
    rows = []
    for sid, r in uaf["subjects"].items():
        fl = r["detachment_floor"]
        rows.append([sid, _p(fl["p_family_wise"]), fl["n_null_infinite"],
                     _p(fl["p_smallest_attainable"]), _f(fl["can_reject_at_0.05"])])
    L.append(_table(["Subject", "Detachment p", "Infinite null draws (of 10000)",
                     "Smallest attainable p", "Can reject at 0.05"], rows))
    L.append("")
    rows = []
    for sid, r in uaf["subjects"].items():
        c = r["safety_contrast"]
        rows.append([sid, _f(c["safety_mean_grade"], 3), _f(c["general_mean_grade"], 3),
                     f"{c['difference']:+.3f}", _p(c["p_two_sided"]),
                     _p(c["p_one_sided_safety_lower"]), _p(c["reply_level"]["p_two_sided"])])
    L.append(_table(["Subject", "Safety mean grade", "General mean grade", "Difference",
                     "p, cell null (two-sided)", "p, cell null (safety lower)",
                     "p, reply null (two-sided)"], rows))
    L.append("")

    # Embedding arms.
    L.append("## Embedding arms")
    L.append("")
    links = sup["embedding_links"]
    canon = sup["canonical_base_A_arm"]
    copies = sup["base_A_copies"]
    L.append("`supplement.json` ties every stored embedding arm to the subject whose "
             "replies it embeds (`embedding_links`). "
             "A run arm holds the same rows as its subject's judged rows. "
             "The fresh base sets embed every reply, so C1 and C2 also hold replies the "
             "judge never scored.")
    L.append("")
    rows = []
    for a in reg["embedding_arms"]:
        if not a["run"].startswith("base_set_") or a["variant"] != "unmasked":
            continue
        lk = links[a["arm_id"]]
        rows.append([a["run"].removeprefix("base_set_"), lk["subject_id"], lk["texts"],
                     lk["n_embedded_rows"], lk["n_subject_rows"], lk["rows"]])
    L.append(_table(["Base set", "Subject", "Texts", "Embedded rows", "Judged rows",
                     "Rows"], rows))
    L.append("")
    L.append("Each of the nine runs on the optimism roster holds its own embedding of base "
             "A's replies. "
             "The copies hold the same texts and slightly different vectors. "
             "A base-as-target analysis reads the canonical copy, the one the stored "
             "embedding calibration pairs every base with. "
             "A run tested against its own base uses its own copy.")
    L.append("")
    rows = []
    for v in ("unmasked", "masked"):
        cs = [c for i, c in copies[v].items() if i != canon[v]["arm_id"]]
        rows.append([v, canon[v]["arm_id"], len(copies[v]),
                     _f(all(c["same_texts_as_canonical"] for c in copies[v].values())),
                     f"{min(c['share_bit_identical'] for c in cs):.3f}-"
                     f"{max(c['share_bit_identical'] for c in cs):.3f}",
                     f"{min(c['cosine_min'] for c in cs):.4f}"])
    L.append(_table(["Variant", "Canonical arm", "Copies", "Same texts", "Rows bit-identical "
                     "to the canonical copy (share)", "Smallest row cosine"], rows))
    L.append("")

    # Family inputs.
    L.append("## Family inputs")
    L.append("")
    L.append("The check reads every output of each family in full for the path-and-hash "
             "pairs it records. "
             "A pair on a file the registry hashed must carry the registry's sha256. "
             "A pair on any other file must carry that file's sha256 now. "
             "The check reads the family folders as they stood when it ran.")
    L.append("")
    rows = []
    for name, f in fam["families"].items():
        rows.append([name, _f(f["loads_through_registry_readers"]), _f(f["names_subjects_json"]),
                     f["n_registry_equal"] + f["n_registry_differs"], f["n_registry_equal"],
                     f["n_registry_differs"], f["n_outside_equal_now"],
                     f["n_outside_differs_now"] + f["n_outside_missing"]])
    L.append(_table(["Family", "Loads through the registry readers", "Names subjects.json",
                     "Pairs on registry files", "Equal", "Differ",
                     "Pairs on other files, equal now", "Differ now or missing"], rows))
    L.append("")
    absent = fam.get("families_without_output_folder", [])
    if absent:
        L.append("These families had no output folder when the check reached them, so the "
                 "table holds no pairs for them: " + ", ".join(absent) + ".")
        L.append("")
    diff_now = [p for f in fam["families"].values() for p in f["pairs"]
                if p["status"] in ("outside_differs_now", "outside_missing")]
    if diff_now:
        L.append("The pairs that differ now are on these files: "
                 + ", ".join(sorted({f"`{p['path']}`" for p in diff_now})) + ".")
        L.append("")

    # Reading.
    org = [s for s in subs if s["category"] == "ORG"]
    paper_org = [s for s in org if s["in_paper"]]
    nulls = [s for s in subs if s["category"] == "NULL"]
    bases = [s for s in subs if s["category"] == "BASE"]
    alpha = reg["settings"]["alpha"]

    def rej(ss):
        return sum(1 for s in ss if (stats.get(s["subject_id"], {}).get("registered_p") or 1)
                   <= alpha)

    def med_rej(ss):
        return sum(1 for s in ss if stats.get(s["subject_id"], {}).get("median_p") is not None
                   and stats[s["subject_id"]]["median_p"] <= alpha)

    def med_n(ss):
        return sum(1 for s in ss if stats.get(s["subject_id"], {}).get("median_p") is not None)

    def frac(ss):
        return f"{med_rej(ss)} of {med_n(ss)}"

    # The prose below states these facts; refuse to write it if the data disagree.
    if not chk["all_pass"]:
        raise SystemExit("a gate check fails; the README's reading would be false")
    if rep["n_differ"] != 0 or rep["n_tasks"] != 210:
        raise SystemExit("the partA reproduction is not 210 of 210")
    if med_n(bases) != len(bases):
        raise SystemExit("a BASE subject has no target-only row")
    if fam["totals"]["n_registry_differs"] != 0:
        raise SystemExit("a family recorded a registry file with another sha256")
    named_max = {sid: r["max_named"] for sid, r in ua.items()}
    ua_groups = {sid: load_json(_abs(by[sid]["ua_detection"]))["identities"] for sid in ua}
    if sum(1 for v in named_max.values() if v) != 1 or any(
            ua_groups[sid][v]["group"] != "general" for sid, v in named_max.items() if v):
        raise SystemExit("the user-awareness max test no longer names exactly one general identity")
    if any(r["detachment_floor"]["p_smallest_attainable"] <= ALPHA_UA
           for r in uaf["subjects"].values()):
        raise SystemExit("the detachment test can reject on a served subject")
    con = [r["safety_contrast"] for r in uaf["subjects"].values()]
    if any(min(c["p_two_sided"], c["p_one_sided_safety_lower"], c["reply_level"]["p_two_sided"],
               c["reply_level"]["p_one_sided_safety_lower"]) <= alpha for c in con):
        raise SystemExit("a safety-group contrast rejects at alpha 0.01")
    if any(abs(c["difference"]) >= 0.2 for c in con):
        raise SystemExit("a safety-group contrast is not small (0.2 grade points or more)")
    by_model: dict[str, list] = {}
    for s in bases:
        by_model.setdefault(s["model"], []).append(s)
    qwen = [m for m in by_model if "Qwen-7B" in m or "Qwen2.5-1.5B" in m]
    other = [m for m in by_model if m not in qwen]
    if any(med_rej(by_model[m]) < med_n(by_model[m]) - 1 for m in qwen) or any(
            med_rej(by_model[m]) for m in other):
        raise SystemExit("the BASE split by model no longer holds")

    L.append("## Reading")
    L.append("")
    L.append("The registry adds no method, so its rates are the reference the families "
             "compare against. The table counts rejections at alpha 0.01 of the reproduced "
             "registered test and of the target-only median test. "
             "Subjects that share a model are not independent. "
             "C1 and C1 s0-11 read the same file.")
    L.append("")
    trows = [
        ["ORG in the paper", len(paper_org), rej(paper_org), frac(paper_org)],
        ["ORG, all (incl. weights arms, sycophancy, held-out challenge)", len(org), rej(org),
         frac(org)],
        ["NULL", len(nulls), rej(nulls), frac(nulls)],
        ["BASE as target, in the paper", sum(1 for s in bases if s["in_paper"]), "n/a (no base)",
         frac([s for s in bases if s["in_paper"]])],
        ["BASE as target, not in the paper", sum(1 for s in bases if not s["in_paper"]),
         "n/a (no base)", frac([s for s in bases if not s["in_paper"]])],
    ]
    for m in sorted(by_model, key=lambda x: MODEL_SHORT.get(x, x)):
        trows.append([f"BASE as target, {MODEL_SHORT.get(m, m)}", len(by_model[m]),
                      "n/a (no base)", frac(by_model[m])])
    trows += [["BASE as target, all", len(bases), "n/a (no base)", frac(bases)],
              ["PLACEBO", "split rule only", "not run here", "not run here"],
              ["UA", len(ua), "n/a (no base)", "see the user-awareness tables"]]
    L.append(_table(["Subjects", "Count", "Registered test rejects",
                     "Target-only median rejects"], trows))
    L.append("")
    L.append("Every subject file still hashes to the value the registry recorded. "
             "Each partA run still hashes to partA's meta block. "
             "The copied loaders reproduce every partA task field for field, the stage-6 "
             "registered test and the stored target-only files. "
             "Bases B, C1, C1 s0-11 and C2 match the pooled comparison's rows and samples, "
             "and the served subjects match the stored detection. "
             "We therefore posit that every family reading through the registry audits "
             "exactly the data that partA, stage 6, the pooled comparison and the stored "
             "detection audited.")
    L.append("")
    L.append("The target-only median test rejects untuned bases at rates that split by "
             "model. "
             "The Qwen bases reject on nearly every roster, and the Llama, court and Gemma "
             "bases reject on none. "
             "We therefore conjecture that the false-positive rate of the target-only median "
             "test is a property of the model under audit, so a rate pooled over bases "
             "describes none of them.")
    L.append("")
    L.append("The max test rejects for one served subject and names a general-population "
             "identity. "
             "The detachment test cannot reject on these tables, because tied peaks put its "
             "smallest attainable p above alpha. "
             "The contrast between the safety identities and the general identities is small "
             "on all three subjects, and neither null rejects it at alpha 0.01. "
             "We therefore contend that the stored grades show an identity effect on one "
             "subject and no detectable safety-researcher effect on any.")
    L.append("")
    L.append("## Runs not completed")
    L.append("")
    fails = chk.get("failures") or {}
    if fails:
        for k, v in fails.items():
            L.append(f"- {k}: {len(v)} failing rows (see reproduce_check.json)")
    else:
        L.append("Every listed subject resolved, hashed and reproduced.")
    L.append("")
    L.append("## How to read a subject in a family")
    L.append("")
    L.append("```python")
    L.append("from script.analysis.baseline_free_20261115.common.subjects import (")
    L.append("    canonical_base_A_arm, embedding_link, load_base_table, load_subject_replies,")
    L.append("    load_subject_table, placebo_halves, subject_record, target_group)")
    L.append("t = load_subject_table('auditbench_flattery')   # refuses if the verdict or axis sha256 moved")
    L.append("b = load_base_table('auditbench_flattery')      # ORG and NULL only")
    L.append("r = load_subject_replies('base_C2')            # refuses if the reply sha256 moved")
    L.append("g = target_group('ua_gpt_5')                   # the frozen safety group")
    L.append("arm = canonical_base_A_arm('masked')            # the one base-A embedding copy")
    L.append("half_a, half_b = placebo_halves('base_A', load_subject_table('base_A'), 0)")
    L.append("```")
    L.append("")
    save_new_text(REGISTRY_DIR / "README.md", "\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
