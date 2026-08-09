"""Generate every stage config from the audit conditions, so they cannot drift.

    uv run python script/pipeline/write_condition_configs.py

One source of truth (``src/common/audit_conditions.py``) writes the elicitation,
prompt-set, and conjecture configs for each condition. Hand-editing the configs
is how the activation condition silently diverged from the organism's paper
once already; generating them means the level, the deployment, the principal
type, and the activation condition are the same strings in every stage.

The run constants and the per-stage payload builders live in
``src/common/condition_config_payloads.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.common.experiment_layout import stage_path

from src.common.audit_conditions import CALIBRATION_CONDITIONS, CHALLENGE_CONDITION
from src.common.condition_config_payloads import (
    CALIBRATION_TARGETS,
    CHALLENGE_TARGETS,
    OUT_ROOT,
    SAMPLING_KIND as SAMPLING_KIND,
    SEED_KINDS,
    TARGETS,
    _conjecture,
    _ellicit,
    _promptset,
)

CONFIG_ROOT = Path("configs/conditions")


def main() -> None:
    written = []
    for cond in CALIBRATION_CONDITIONS:
        group, targets = "calibration", TARGETS["calibration"]
        for stage, payload in (("ellicit", _ellicit(cond, group, targets)),
                               ("promptset", _promptset(cond, group)),
                               ("conjecture", _conjecture(cond, group))):
            path = CONFIG_ROOT / f"{stage}_{group}_{cond.condition_id}.json"
            path.write_text(json.dumps(payload, indent=2) + "\n")
            written.append(path)

    # One elicitation config per (organism, seed kind): nine in all. Each carries
    # its own seed and its own out dir, so the three frozen question sets stay
    # distinct and the pooling step has three tallies to add.
    cond = CHALLENGE_CONDITION
    for name, targets in CHALLENGE_TARGETS.items():
        for kind, seed in SEED_KINDS.items():
            payload = _ellicit(cond, "challenge", targets, seed=seed,
                               out_dir=str(stage_path(OUT_ROOT, "ellicit", f"{name}_{kind}")))
            path = CONFIG_ROOT / f"ellicit_challenge_{name}_{kind}.json"
            path.write_text(json.dumps(payload, indent=2) + "\n")
            written.append(path)

    for stage, payload in (("promptset", _promptset(cond, "challenge")),
                           ("conjecture", _conjecture(cond, "challenge"))):
        path = CONFIG_ROOT / f"{stage}_challenge_{cond.condition_id}.json"
        path.write_text(json.dumps(payload, indent=2) + "\n")
        written.append(path)

    targets = CONFIG_ROOT / "calibration_targets.json"
    targets.write_text(json.dumps(CALIBRATION_TARGETS, indent=2) + "\n")
    written.append(targets)

    for path in written:
        print("wrote", path)


if __name__ == "__main__":
    main()
