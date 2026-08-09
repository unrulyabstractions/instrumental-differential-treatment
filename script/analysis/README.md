# script/analysis

This folder holds the side analyses we report beside the registered stage-6 test: judge-seat agreement and comparison, the reference-free detector counterfactual, pooled coherence, and the spike-in power floor.

Each script reads stage-6 summaries and scored verdicts under `out/` and writes a new JSON file, so no reported number moves because one ran. Two threads run through them. The judge-seat scripts ask whether a cheaper judge seat can stand in for the paper's seat, on identical responses. The detector scripts run base-free statistics as a counterfactual to the registered test and measure their power. `compile_judge_comparison.py` gathers the judge-seat numbers the appendix reads.

## Scripts

| Script | What it does | Run |
|---|---|---|
| `compile_judge_comparison.py` | Collects every judge-seat number the appendix reports into one record: per-verdict seat agreement, an objective refusal error rate, and what each seat does to the registered test on the documented run. | `uv run python script/analysis/compile_judge_comparison.py` |
| `compute_pooled_coherence.py` | Runs the base-free coherence test pooled across the conditions that share a candidate, on both the audited target and its base model as control. Writes a new file and leaves stage-6 artifacts alone. | `uv run python script/analysis/compute_pooled_coherence.py --permutations 10000` |
| `compute_reference_free_detector.py` | Runs the base-free detector (maximum and detachment) on every reported run, for both the target seat and the base seat. Writes one `reference_free.json` per run directory. | `uv run python script/analysis/compute_reference_free_detector.py --out-root out/main/secret_loyalties --permutations 10000` |
| `compute_significant_candidates.py` | Recomputes the registered test with every candidate-axis pair returned, so the geometry figures can mark every significant principal. Checks the recomputation reproduces stage 6 before writing. | `uv run python script/analysis/compute_significant_candidates.py` |
| `judge_seat_agreement.py` | Measures how far two judge seats agree verdict by verdict on identical responses. Reports raw agreement, Cohen's kappa, each seat's firing rate, and the correlation of the cell rates the test reads. | `uv run python script/analysis/judge_seat_agreement.py --a out/main/secret_loyalties/calibration_informed/score/verdicts_base_1p5b.jsonl --b out/main/secret_loyalties/calibration_informed/rejudge/nano/score/verdicts_base_1p5b.jsonl` |
| `judge_seat_probe.py` | Probes candidate judge seats on whether they can tell a reply declined, calling each seat as the pipeline does with the target axis at a shuffled position. Makes live model calls. | `uv run python script/analysis/judge_seat_probe.py` |
| `pooled_reference_free_test.py` | Pools one candidate's base-free evidence across the conditions that carry it, via a joint permutation. Reports both the candidate-fixed reading and the scanned-over-candidates reading. | `uv run python script/analysis/pooled_reference_free_test.py --permutations 4000` |
| `spike_in_power_floor.py` | Injects a synthetic loyalty of known size into a base model's table and sweeps size and axis count to find each base-free statistic's detection floor. Uses no real label. | `uv run python script/analysis/spike_in_power_floor.py --permutations 1000` |
| `subsample_judge_comparison.py` | Cuts a run to an identical subsample of whole templates and writes both seats' verdicts on it, so a cheaper seat can be compared against the paper's seat on the same responses. | `uv run python script/analysis/subsample_judge_comparison.py --templates 12` |
| `faithful_seat_probe_scoring.py` | Score one judge seat on the faithful probe, through the production scorer. |
| `write_status_markers.py` | Write a STATUS.md into every data directory under out/, read from artifacts. |
| `verify_r2_outputs.py` | Check every r2 artifact before any number is read off it. |
