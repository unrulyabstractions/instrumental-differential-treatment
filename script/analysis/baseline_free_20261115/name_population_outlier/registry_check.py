"""Check this family's tables against the workflow's shared subject registry.

    PYTHONPATH=. .venv/bin/python \\
        script/analysis/baseline_free_20261115/name_population_outlier/registry_check.py

For every subject this family ran that the registry also lists, the verdict file's
sha256, the judge level and the table shape (k, instructions, axes, replies) must
equal the registry's. The split halves have no registry row. Writes
``registry_check.json`` and refuses to overwrite it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
OUT = REPO / "out/main/baseline_free_20261115/name_population_outlier"
REGISTRY = REPO / "out/main/baseline_free_20261115/subjects_registry/subjects.json"

ALIAS = {
    "base_A_contextual_optimism": "base_A", "base_A_secret_loyalty": "base_A__secret_loyalty",
    "base_A_third_party_politics": "base_A__third_party_politics",
    "base_sycophancy": "base_sycophancy", "base_B": "base_B", "base_C1": "base_C1",
    "base_C1_s0_11": "base_C1_s0_11", "base_C2": "base_C2",
    "ua_gpt5_mini": "ua_gpt_5_mini", "ua_gpt41_mini": "ua_gpt_4_1_mini", "ua_gpt5": "ua_gpt_5",
}


def registry_id(key: str) -> str | None:
    if key.startswith("half"):
        return None
    if key in ALIAS:
        return ALIAS[key]
    if key.startswith("null_sd_"):
        return "nullext_sd_" + key.removeprefix("null_sd_")
    if key.startswith("null_"):
        return "auditbench_" + key.removeprefix("null_")
    if key.startswith("base_1p5b_"):
        return "base_1p5b__calibration_" + key.removeprefix("base_1p5b_")
    if key.startswith("base_7b_"):
        return "base_7b__challenge_organism_" + key.removeprefix("base_7b_")
    return key


def main() -> None:
    path = OUT / "registry_check.json"
    if path.exists():
        raise SystemExit(f"refusing to overwrite {path}")
    reg = {s["subject_id"]: s for s in json.loads(REGISTRY.read_text())["subjects"]}
    checks = []
    for f in sorted((OUT / "runs").glob("*.json")):
        rec = json.loads(f.read_text())
        key = f.stem
        rid = registry_id(key)
        if rid is None:
            checks.append({"subject": key, "registry_id": None, "match": None,
                           "reason": "split half; no registry row"})
            continue
        s = reg.get(rid)
        if s is None:
            checks.append({"subject": key, "registry_id": rid, "match": False, "reason": "missing"})
            continue
        mine_file = rec["subject"]["files"][0]
        r = rec["result"]
        shape = s["shape"]
        fields = {
            "verdicts_path": (s["verdicts"], mine_file),
            "verdicts_sha256": (s["sha256"]["verdicts"], rec["input_sha256"][mine_file]),
            "level": (s["level"], rec["subject"]["level"]),
            "k": (shape["k"], r["k"]), "candidates": (shape["candidates"], r["candidates"]),
            "n_instructions": (shape["n_instructions"], r["n_instructions"]),
            "n_axes": (shape["n_axes"], r["n_axes"]), "n_responses": (shape["n_responses"], r["n_responses"]),
        }
        diffs = {k: {"registry": a, "here": b} for k, (a, b) in fields.items() if a != b}
        checks.append({"subject": key, "registry_id": rid, "match": not diffs, "differs": diffs})
    out = {"registry": str(REGISTRY.relative_to(REPO)),
           "n_checked": sum(c["match"] is not None for c in checks),
           "n_mismatch": sum(c["match"] is False for c in checks), "checks": checks}
    path.write_text(json.dumps(out, indent=1))
    print(f"{out['n_checked']} subjects checked against the registry, {out['n_mismatch']} mismatches")
    for c in checks:
        if c["match"] is False:
            print("MISMATCH", c)
    if out["n_mismatch"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
