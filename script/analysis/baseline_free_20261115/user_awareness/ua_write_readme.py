"""README.md for the user-awareness family, with every number read from the output JSONs.

    uv run python -m script.analysis.baseline_free_20261115.user_awareness.ua_write_readme

The prose interprets; the tables carry the numbers. The prose blocks live in
``ua_readme_prose`` so this file only assembles.
"""

from __future__ import annotations

import hashlib
import json

from src.common.file_io import load_json, read_jsonl

from script.analysis.baseline_free_20261115.user_awareness.ua_grade_tables import (
    OUT, REPO, SUBJECTS)
from script.analysis.baseline_free_20261115.user_awareness.ua_readme_prose import PROSE
from script.analysis.baseline_free_20261115.user_awareness.ua_summary_tables import (
    decoy_group_table, decoy_placebo_table, decoy_target_table, f, group_table,
    new_session_screen_table, md_table, predictive_table,
    reproduction_table, temporal_table)


def _sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def inputs_table(decoy) -> str:
    rows = []
    for name, spec in SUBJECTS.items():
        p = spec["stored_dir"] / "grades_target.jsonl"
        rows.append([f"stored grades, {name}", str(p.relative_to(REPO)),
                     sum(1 for _ in read_jsonl(p)), _sha(p)])
    if decoy:
        for name in decoy["subjects"]:
            p = OUT / f"grades_{name}.jsonl"
            rows.append([f"new-session grades, {name}", str(p.relative_to(REPO)),
                         sum(1 for _ in read_jsonl(p)), _sha(p)])
    return md_table(["input", "path", "rows", "sha256 (16)"], rows)


def design_table(stored: dict, decoy) -> str:
    rows = [[v["subject"], "stored", v["n_identities"], v["n_exchanges"], v["samples_per_cell"],
             v["n_rows_usable"], v["n_failed_or_unparsed"]] for v in stored.values()]
    if decoy:
        for v in decoy["subjects"].values():
            n = sum(v["slots_attempted"].values())
            rows.append([v["subject"], "new session", len(v["personas_complete"]), 16, 4,
                         n - v["n_failed_or_unparsed"], v["n_failed_or_unparsed"]])
    return md_table(["subject", "session", "identities", "exchanges", "samples per cell",
                     "usable grades", "failed or unparsed"], rows)


def level01_table(stored: dict) -> str:
    rows = []
    for subj, v in stored.items():
        l01 = v["level01"]
        s, d, g = l01["sharp_null_screen"], l01["detachment"], l01["grubbs_on_peaks"]
        gm = l01["grubbs_on_blocked_mean_grade_harsher_side"]
        pre = l01["preregistered_deleted_residual"]
        best = min(pre.values(), key=lambda x: x["mean_grade_vs_other_9"]["p_bh_within_subject"])
        rows.append([subj, f(s["statistic"], 3), f(s["p_family_wise"]), s["named"] or "none",
                     f(d["statistic"], 3), f(d["p_family_wise"]), d["named"] or "none",
                     f(g["G"], 3), f(g["p_exact_normal_mc"]), f(g["p_permutation"]),
                     f(gm["G"], 3), f(gm["p_exact_normal_mc"]),
                     f(best["mean_grade_vs_other_9"]["p_bh_within_subject"]),
                     "none (no base model)"])
    return md_table(["subject", "screen S", "screen p", "screen named", "detachment",
                     "detachment p", "detachment named", "Grubbs G on peaks", "exact normal p",
                     "permutation p", "Grubbs G harsher mean", "exact normal p",
                     "smallest pre-registered BH p", "registered test"], rows)


def panel_table(transluce: dict) -> str:
    rows = [[pair, f(v["pearson_r_all_10"], 2), f(v["pearson_r_general_6"], 2)]
            for pair, v in transluce["panel"]["identity_effect_correlation"].items()]
    return md_table(["subject pair", "r over 10 identities", "r over 6 general"], rows)


def plan_table(pilot: dict, log: dict | None) -> str:
    rows = []
    for name, v in pilot["subjects"].items():
        kept = name in pilot["plan"]["kept"]
        sampled = len(log["subjects"][name]["sampled"]) if log and kept else 0
        rows.append([name, v["n_call_slots"], f(v["mean_cost_per_call"], 6),
                     f(v["mean_completion_tokens"], 0), "kept" if kept else "dropped by the m rule",
                     sampled])
    return md_table(["subject", "pilot calls", "cost per call (USD)", "mean completion tokens",
                     "decision", "personas sampled"], rows)


def spend_table(pilot: dict, log: dict | None) -> str:
    rows = [["pilot", f(pilot["bound_usd"], 4), f(pilot["pilot_actual_usd"], 4)]]
    if log:
        rows.append(["session", f(log["bound_usd"], 4), f(log["session_actual_usd"], 4)])
        rows.append(["analysis total", "cap 3.0000", f(log["spent"]["analysis_usd"], 4)])
    return md_table(["phase", "reserved (USD)", "priced from usage (USD)"], rows)


def main() -> None:
    stored = {k: load_json(OUT / f"run_stored_{k}.json") for k in SUBJECTS}
    transluce = load_json(OUT / "transluce_stats.json")
    pilot = load_json(OUT / "pilot.json")
    log = load_json(OUT / "session_log.json") if (OUT / "session_log.json").exists() else None
    decoy = load_json(OUT / "decoy_detection.json") if (OUT / "decoy_detection.json").exists() else None
    temporal = load_json(OUT / "temporal_check.json") if decoy else None
    settings = load_json(OUT / "settings.json")
    parts = [PROSE["title"], PROSE["intro"], "## Design and settings", PROSE["design"],
             design_table(stored, decoy), "```json\n" + json.dumps(settings["stored_part"], indent=1) + "\n```",
             PROSE["inputs"], inputs_table(decoy),
             "## Does the rerun reproduce the stored detection?", PROSE["reproduction"],
             reproduction_table(stored),
             "## What do Levels 0 and 1 say on the stored grades?", PROSE["level01"],
             level01_table(stored),
             "## Do the safety identities stand out from the six ordinary users?",
             PROSE["transluce"], predictive_table(transluce), group_table(transluce),
             PROSE["panel"], panel_table(transluce),
             "## Which subjects entered the decoy session?", PROSE["plan"],
             plan_table(pilot, log), spend_table(pilot, log)]
    if decoy:
        parts += ["## Does a safety identity stand out from a pool of ordinary users?",
                  PROSE["decoy"], decoy_target_table(decoy), decoy_group_table(decoy),
                  "## Did the served models change between sessions?", PROSE["temporal"],
                  temporal_table(temporal), new_session_screen_table(decoy, stored)]
    parts += ["## How do the detectors behave on placebos and nulls?", PROSE["placebos"]]
    if decoy:
        parts += [decoy_placebo_table(decoy)]
    parts += ["## Reading", PROSE["reading"], "## Runs not completed", PROSE["not_completed"],
              "## Files", PROSE["files"]]
    text = "\n\n".join(parts) + "\n"
    if "\u2014" in text:
        raise SystemExit("an em dash slipped into the README")
    (OUT / "README.md").write_text(text)
    print(f"README.md {len(text.splitlines())} lines")


if __name__ == "__main__":
    main()
