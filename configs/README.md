# configs

These are the stage input configs the audit runs consume, generated from the audit conditions and never hand-edited.

We generate the calibration and challenge stage configs from `src/common/audit_conditions.py` through `script/pipeline/write_condition_configs.py`. One source of truth writes the same level, deployment, principal type, and activation string into every stage, so the stages cannot drift. Change the conditions and regenerate; never edit a config in place. The AuditBench run's scoring and judge seats also live here. We write those for that run, not from the generator.

## Layout

The groups mirror `out/main`: a family owns its stage configs, and a
family-spanning tool sits in its own group.

| Directory | What it holds |
|---|---|
| `secret_loyalties/` | the generated per-condition stage configs for the calibration and challenge experiments, plus `calibration_targets.json`. Regenerate with `uv run python script/pipeline/write_condition_configs.py`; never edit. |
| `secret_loyalties/helper_swap/` | the helper-family swap's stage configs for the calibration experiment. |
| `auditbench/` | the AuditBench organisms' prompt-set, conjecture, and per-organism scoring configs, written for that run rather than generated. |
| `auditbench/helper_swap/` | the swap's stage configs for the optimism experiment. |
| `external/` | the court-conversion organism's prompt-set and conjecture configs, hand-written like `auditbench/` rather than generated. The candidates are pinned to the organism's two cities, so there is no elicitation stage. |
| `judges/` | one config per judge seat, named for the model that sits in it. A second seat over the same responses must write into its own verdicts directory. |
