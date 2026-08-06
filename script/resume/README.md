# script/resume

We re-run the scoring and comparison stages on calibration targets with the paper's pinned parameters, so a rerun reproduces the reported numbers.

The folder holds two shell scripts. `score_pulled_calibration.sh` runs stage 5 on replies that were already sampled on a rented box. It skips generation and loads no weights, so only the judge runs, and the judge needs the API key that never travels to a rented machine. `compare_pulled_calibration.sh` runs stage 6, the registered permutation test, and pins the permutation count to the paper value because `compare_distributions.py` defaults lower. Both scripts loop over the typed, blind, and informed audit conditions.

## Scripts

| Script | What it does | Run |
|---|---|---|
| `score_pulled_calibration.sh` | Stage 5. Judges replies already on disk. Skips sampling, loads no weights, loops the typed, blind, and informed conditions. | `TARGET_TAG=gen9_32b BASE_TAG=base_32b bash script/resume/score_pulled_calibration.sh` |
| `compare_pulled_calibration.sh` | Stage 6. Runs the registered permutation test with permutations pinned to the paper value. Loops the typed, blind, and informed conditions. | `TARGET_TAG=gen9_32b BASE_TAG=base_32b bash script/resume/compare_pulled_calibration.sh` |
