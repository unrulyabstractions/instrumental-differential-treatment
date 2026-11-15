"""Run every base-free detector on the three stored user-awareness subjects.

    uv run python -m script.analysis.baseline_free_20261115.user_awareness.ua_stored_run

Reads only the stored grade files; writes only into this family's output folder.
For each subject it runs Levels 0 and 1 (``ua_level01_detectors``) and the
Transluce-style statistics (``ua_transluce_subject``), checks the reproduction
of the stored ``user_awareness_detection.json``, and writes one JSON per run, the
combined JSONs, the descriptive three-subject panel and the summary CSV.
"""

from __future__ import annotations

import json

import numpy as np

from src.common.file_io import load_json, save_json
from src.external.user_awareness_materials import IDENTITIES

from script.analysis.baseline_free_20261115.user_awareness.ua_grade_tables import (
    OUT, SUBJECTS, blocked_means, failed_count, grade_cube, raw_mean_grades, usable_rows)
from script.analysis.baseline_free_20261115.user_awareness.ua_level01_detectors import (
    SETTINGS, level01)
from script.analysis.baseline_free_20261115.user_awareness.ua_stored_tables_out import (
    panel_rows, summary_rows, write_csv)
from script.analysis.baseline_free_20261115.user_awareness.ua_transluce_subject import (
    BOOTSTRAP_DRAWS, transluce_subject)

KEYS = [i["key"] for i in IDENTITIES]
GROUPS = {i["key"]: i["group"] for i in IDENTITIES}


def reproduction(stored: dict, l01: dict, raw: dict, group_means: dict) -> dict:
    """Stored values against this rerun, field by field."""
    rf, det = stored["reference_free"], stored["reference_free"]["detachment"]
    scr, dt = l01["sharp_null_screen"], l01["detachment"]
    checks = {
        "screen_S": (rf["statistic"], scr["statistic"]),
        "screen_p": (rf["p_family_wise"], scr["p_family_wise"]),
        # The stored run named at alpha 0.05 and this rerun names at 0.01; the two
        # agree unless 0.01 < p <= 0.05, which no stored subject has.
        "screen_named_stored_alpha_0.05_vs_rerun_alpha_0.01": (rf["named"], scr["named"]),
        "screen_named_axis": (rf["named_axis"], scr["named_axis"]),
        "detachment_S": (det["statistic"], dt["statistic"]),
        "detachment_p": (det["p_family_wise"], dt["p_family_wise"]),
        "detachment_leading": (det["leading"], dt["leading"]),
    }
    for k, v in stored["mean_grade"].items():
        checks[f"mean_grade_{k}"] = (v, round(raw[k], 3))
    out = {}
    for name, (a, b) in checks.items():
        same = (abs(a - b) < 1e-9) if isinstance(a, float) and isinstance(b, float) else a == b
        out[name] = {"stored": a, "rerun": b, "match": bool(same)}
    out["group_mean_grades_rerun"] = group_means
    out["all_match"] = all(v["match"] for v in out.values() if isinstance(v, dict) and "match" in v)
    return out


def run_subject(name: str, spec: dict) -> dict:
    path = spec["stored_dir"] / "grades_target.jsonl"
    rows = usable_rows(path)
    cube, exchanges = grade_cube(rows, KEYS)
    x, _ = blocked_means(cube)
    raw = dict(zip(KEYS, raw_mean_grades(cube).tolist(), strict=True))
    l01 = level01(rows, dict(zip(KEYS, x.tolist(), strict=True)))
    tr = transluce_subject(cube, KEYS, GROUPS)
    pooled = {g: float(np.nanmean(cube[[KEYS.index(k) for k in KEYS if GROUPS[k] == g]]))
              for g in ("safety", "unknown_ai", "general")}
    stored = load_json(spec["stored_dir"] / "user_awareness_detection.json")
    return {
        "subject": f"{spec['backend']}:{spec['model']}", "input": str(path.relative_to(OUT.parents[3])),
        "n_rows_usable": len(rows), "n_failed_or_unparsed": failed_count(path),
        "n_identities": len(KEYS), "n_exchanges": len(exchanges), "samples_per_cell": cube.shape[2],
        "groups": GROUPS, "mean_grade": raw, "group_mean_grade": pooled,
        "registered_result": "none: a served model has no base model",
        "level01": l01, "transluce": tr,
        "reproduction_of_stored_detection": reproduction(stored, l01, raw, pooled),
    }


def panel_summary(runs: dict) -> dict:
    """Cross-subject correlation of identity effects: can one served model stand in for another?"""
    names = list(runs)
    out = {}
    for a in range(len(names)):
        for b in range(a + 1, len(names)):
            xa = np.array([runs[names[a]]["transluce"]["blocked_mean"][k] for k in KEYS])
            xb = np.array([runs[names[b]]["transluce"]["blocked_mean"][k] for k in KEYS])
            gi = [KEYS.index(k) for k in KEYS if GROUPS[k] == "general"]
            out[f"{names[a]}|{names[b]}"] = {
                "pearson_r_all_10": float(np.corrcoef(xa, xb)[0, 1]),
                "pearson_r_general_6": float(np.corrcoef(xa[gi], xb[gi])[0, 1])}
    return {"identity_effect_correlation": out, "proxy_threshold": 0.5,
            "reading": "descriptive only: three subjects cannot calibrate a panel test"}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    runs = {}
    for name, spec in SUBJECTS.items():
        runs[name] = run_subject(name, spec)
        save_json(OUT / f"run_stored_{name}.json", runs[name])
        rep = runs[name]["reproduction_of_stored_detection"]
        print(f"{name}: reproduction all_match={rep['all_match']}", flush=True)
    save_json(OUT / "stored_detectors.json",
              {k: {"subject": v["subject"], "settings": SETTINGS, "level01": v["level01"],
                   "reproduction_of_stored_detection": v["reproduction_of_stored_detection"]}
               for k, v in runs.items()})
    panel = panel_summary(runs)
    save_json(OUT / "transluce_stats.json",
              {"settings": {**SETTINGS, "bootstrap_draws": BOOTSTRAP_DRAWS,
                            "whole_user_permutation": "exact enumeration"},
               "subjects": {k: {"subject": v["subject"], **v["transluce"]} for k, v in runs.items()},
               "panel": panel})
    write_csv(OUT / "panel.csv", panel_rows(runs, KEYS, GROUPS))
    write_csv(OUT / "summary_stored.csv", summary_rows(runs))
    print(json.dumps(panel, indent=1), flush=True)


if __name__ == "__main__":
    main()
