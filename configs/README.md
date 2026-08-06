# configs

These are the stage input configs the audit runs consume, generated from the audit conditions and never hand-edited.

We generate the calibration and challenge stage configs from `src/common/audit_conditions.py` through `script/pipeline/write_condition_configs.py`. One source of truth writes the same level, deployment, principal type, and activation string into every stage, so the stages cannot drift. Change the conditions and regenerate; never edit a config in place. The AuditBench run's scoring and judge seats also live here. We write those for that run, not from the generator.

## Config families

| Prefix | What it configures |
|---|---|
| `ellicit_` | Stage 1 elicitation, one file per calibration condition and per challenge organism and seed kind. Sets the seed, the activation string, the five target system-prompt variants, the sampling parameters, and the elicitor, target, and reference model seats. |
| `promptset_` | Stage 2 prompt-set construction. Sets the level, domain, activation, principal type, template count, the prompter seat, and the principal map. |
| `conjecture_` | Stage 3 hypothesis conjecture. Sets the level, domain, activation, principal type, hypothesis count, the conjecturer seat, and any forbidden names. |
| `calibration_targets` | The four calibration checkpoints, each paired with the base model we read it against and its elicitation directory suffix. One JSON array. |
| `judge_` | A single scoring judge seat: provider, model, and options. |
| `score_` | Stage 5 scoring for the AuditBench run. Sets the judge seat, level, domain, activation, the responses and conjecture directories, and which arms to score. |
