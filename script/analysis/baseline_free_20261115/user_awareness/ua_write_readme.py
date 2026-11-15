"""README.md for the user-awareness family, with every number read from the output JSONs.

    uv run python -m script.analysis.baseline_free_20261115.user_awareness.ua_write_readme

The prose interprets; the tables carry the numbers. The prose blocks live in
``ua_readme_prose`` so this file only assembles. The README is rewritten in place;
an earlier README is moved to ``out/superseded/`` by hand before a rewrite.
"""

from __future__ import annotations

import hashlib
import json
import re

from src.common.file_io import load_json, read_jsonl

from script.analysis.baseline_free_20261115.user_awareness.ua_followup_tables import (
    affiliated_count_table, affiliated_table, affiliated_target_table, decoy_cap_table,
    floor_table, panel_table, placebo_table, planted_table, screen_all_table, shape_table,
    temporal_screen_table, temporal_table)
from script.analysis.baseline_free_20261115.user_awareness.ua_grade_tables import (
    OUT, REPO, SUBJECTS)
from script.analysis.baseline_free_20261115.user_awareness.ua_readme_prose import (
    BANNED_IN_PROSE, PROSE)
from script.analysis.baseline_free_20261115.user_awareness.ua_summary_tables import (
    decoy_group_table, decoy_target_table, f, group_table, md_table, predictive_table,
    reproduction_table)


def _sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def inputs_table(decoy) -> str:
    rows = []
    for name, spec in SUBJECTS.items():
        p = spec["stored_dir"] / "grades_target.jsonl"
        rows.append([f"first-session grades, {name}", str(p.relative_to(REPO)),
                     sum(1 for _ in read_jsonl(p)), _sha(p)])
    for name in decoy["subjects"]:
        p = OUT / f"grades_{name}.jsonl"
        rows.append([f"second-session grades, {name}", str(p.relative_to(REPO)),
                     sum(1 for _ in read_jsonl(p)), _sha(p)])
    return md_table(["input", "path", "rows", "sha256 (16)"], rows)


def design_table(stored: dict, decoy) -> str:
    rows = [[v["subject"], "first", v["n_identities"], v["n_exchanges"], v["samples_per_cell"],
             v["n_rows_usable"], v["n_failed_or_unparsed"]] for v in stored.values()]
    for v in decoy["subjects"].values():
        n = sum(v["slots_attempted"].values())
        rows.append([v["subject"], "second", len(v["personas_complete"]), 16, 4,
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
        top = s["top_pairs"][0]
        # A negative t on a grade_le_k axis means fewer low grades: more lenient.
        direction = "more lenient" if top["t"] < 0 else "harsher"
        rows.append([subj, f(s["statistic"], 3), f(s["p_family_wise"]), s["named"] or "none",
                     f"{top['candidate']}, {top['axis_id']}, {direction}",
                     f(d["statistic"], 3), f(d["p_family_wise"]), d["named"] or "none",
                     f(g["G"], 3), f(g["p_exact_normal_mc"]), f(g["p_permutation"]),
                     f(gm["G"], 3), f(gm["p_exact_normal_mc"]),
                     f(best["mean_grade_vs_other_9"]["p_bh_within_subject"]),
                     "none (no base model)"])
    return md_table(["subject", "screen S", "screen p", "screen named",
                     "screen leading cell and direction", "detachment", "detachment p",
                     "detachment named", "Grubbs G on peaks", "exact normal p", "permutation p",
                     "Grubbs G harsher mean", "exact normal p", "smallest pre-registered BH p",
                     "registered test"], rows)


def plan_table(pilot: dict, log: dict) -> str:
    rows = []
    for name, v in pilot["subjects"].items():
        kept = name in pilot["plan"]["kept"]
        sampled = len(log["subjects"][name]["sampled"]) if kept else 0
        rows.append([name, v["n_call_slots"], f(v["mean_cost_per_call"], 6),
                     f(v["mean_completion_tokens"], 0), "kept" if kept else "dropped by the m rule",
                     sampled])
    return md_table(["subject", "pilot calls", "cost per call (USD)", "mean completion tokens",
                     "decision", "personas sampled"], rows)


def spend_table(pilot: dict, log: dict) -> str:
    rows = [["pilot", f(pilot["bound_usd"], 4), f(pilot["pilot_actual_usd"], 4)],
            ["second session", f(log["bound_usd"], 4), f(log["session_actual_usd"], 4)],
            ["analysis total", "cap 3.0000", f(log["spent"]["analysis_usd"], 4)]]
    return md_table(["phase", "reserved (USD)", "priced from usage (USD)"], rows)


def _check_prose(text: str) -> None:
    """Prose blocks carry no digits and none of the banned process words."""
    for key, block in PROSE.items():
        if key in ("title", "files", "not_completed"):
            continue
        bare = re.sub(r"gpt-[0-9.]+(-mini)?|Level [0-9]", "", block)
        if re.search(r"[0-9]", bare):
            raise SystemExit(f"a number slipped into the prose block {key}")
        low = block.lower()
        for word in BANNED_IN_PROSE:
            # Whole words only where the pattern starts or ends with a letter, so
            # "descriptive" does not match "script".
            left = r"(?<![a-z])" if word[0].isalpha() else ""
            right = r"(?![a-z])" if word[-1].isalpha() else ""
            if re.search(left + re.escape(word) + right, low):
                raise SystemExit(f"'{word}' slipped into the prose block {key}")
    if "—" in text:
        raise SystemExit("an em dash slipped into the README")


def main() -> None:
    stored = {k: load_json(OUT / f"run_stored_{k}.json") for k in SUBJECTS}
    transluce = load_json(OUT / "transluce_stats.json")
    pilot = load_json(OUT / "pilot.json")
    log = load_json(OUT / "session_log.json")
    decoy = load_json(OUT / "decoy_detection.json")
    temporal = load_json(OUT / "temporal_check.json")
    settings = load_json(OUT / "settings.json")
    floor = load_json(OUT / "detection_floor.json")
    aff = load_json(OUT / "affiliated_reference.json")
    shape = load_json(OUT / "pool_shape_and_placebos.json")
    panel = load_json(OUT / "panel_with_intervals.json")
    screen = load_json(OUT / "screen_all_personas.json")
    parts = [
        PROSE["title"], PROSE["intro"],
        "## Design and settings", PROSE["design"], design_table(stored, decoy),
        "```json\n" + json.dumps(settings["stored_part"], indent=1) + "\n```",
        PROSE["inputs"], inputs_table(decoy),
        "## Do the original detection values reproduce?", PROSE["reproduction"],
        reproduction_table(stored),
        "## What do Levels 0 and 1 say on the first-session grades?", PROSE["level01"],
        level01_table(stored),
        "## Do the safety identities stand out from the unaffiliated users of the first session?",
        PROSE["transluce"], predictive_table(transluce), group_table(transluce),
        "## Can one served model stand in for another?", PROSE["panel"], panel_table(panel),
        "## Which subjects entered the second session?", PROSE["plan"],
        plan_table(pilot, log), decoy_cap_table(pilot, decoy), spend_table(pilot, log),
        "## Does a safety identity stand out from the unaffiliated ordinary users?",
        PROSE["decoy"], decoy_target_table(decoy), decoy_group_table(decoy),
        "## Do the affiliated personas explain the harsher grades?", PROSE["affiliated"],
        affiliated_count_table(aff), affiliated_table(aff), affiliated_target_table(aff),
        "## How small an effect can these tests detect?", PROSE["floor"],
        floor_table(floor, floor["reference_effect"]["shift_points"], decoy), PROSE["planted"],
        planted_table(floor),
        "## Did the grades change between sessions?", PROSE["temporal"],
        temporal_table(temporal), temporal_screen_table(temporal, decoy, stored),
        "## Does a screen over every persona find the affiliation effect?",
        PROSE["screen_all"], screen_all_table(screen),
        "## How do the detectors behave on ordinary users?", PROSE["placebos"],
        shape_table(shape), placebo_table(shape),
        "## Reading", PROSE["reading"],
        "## Limits", PROSE["limits"],
        "## Runs not completed", PROSE["not_completed"],
        "## Files", PROSE["files"],
    ]
    text = "\n\n".join(parts) + "\n"
    _check_prose(text)
    (OUT / "README.md").write_text(text)
    print(f"README.md {len(text.splitlines())} lines")


if __name__ == "__main__":
    main()
