# script/persona

We run the persona and emotion probes and the causal steering experiments on the audited organisms.

We use it to gather mechanistic evidence that complements the registered permutation test in stage 6. The two probe scripts read a run's matched target and base replies into a fixed concept space and test whether the target separates user groups more than its base does on the identical prompts. The two steering scripts build a treatment direction as an organism-minus-base contrast, then test whether that direction is necessary and sufficient for the group-conditional behavior. Both consume collected replies and prompt sets from earlier stages and write results under `out/analysis/persona/`.

## Scripts

| Script | What it does | Run |
|---|---|---|
| `run_persona_probe.py` | Projects a run's target and matched-base replies into a fixed persona space, then tests whether the target's replies separate user groups more than the base's do and which behaviors each persona carries. | `uv run python script/persona/run_persona_probe.py --run auditbench_contextual_optimism` |
| `run_emotion_probe.py` | Mirrors the persona probe in an emotion space read from stories, tests group separability of the target against the base, and maps which behaviors each emotion tracks. | `uv run python script/persona/run_emotion_probe.py --run auditbench_contextual_optimism` |
| `run_macron_steering.py` | Builds the treatment direction as the organism's favored-candidate-versus-rest activation contrast minus the same contrast in its base, then tests necessity by projecting it out of favored-candidate prompts and sufficiency by adding it to a neutral candidate on a dose sweep, scored by the calibration organism's own judge. | `uv run python script/persona/run_macron_steering.py` |
| `run_sycophancy_steering.py` | Builds the direction the sycophancy organism uses to read the user's political lean as its conservative-minus-liberal contrast minus the same in its base, then sweeps that direction on liberal-framed prompts and watches the answer logits move toward the conservative choice, with the base model steered identically as control. | `uv run python script/persona/run_sycophancy_steering.py` |
