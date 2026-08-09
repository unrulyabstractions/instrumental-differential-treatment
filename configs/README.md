# configs

These are the stage input configs the audit runs consume, generated from the audit conditions and never hand-edited.

We generate the calibration and challenge stage configs from `src/common/audit_conditions.py` through `script/pipeline/write_condition_configs.py`. One source of truth writes the same level, deployment, principal type, and activation string into every stage, so the stages cannot drift. Change the conditions and regenerate; never edit a config in place. The AuditBench run's scoring and judge seats also live here. We write those for that run, not from the generator.

## Layout

| Directory | What it holds |
|---|---|
| `conditions/` | the generated per-condition stage configs (`ellicit_*`, `promptset_*`, `conjecture_*`) plus `calibration_targets.json`. Regenerate with `uv run python script/pipeline/write_condition_configs.py`; never edit. |
| `auditbench/` | the AuditBench organisms' prompt-set, conjecture, and per-organism scoring configs, written for that run rather than generated. |
| `gemfull/` | the full Gemini helper-family swap: every stage config for both organisms, plus its judge seat. |
| `judges/` | one config per judge seat, named for the model that sits in it. A second seat over the same responses must write into its own verdicts directory. |
