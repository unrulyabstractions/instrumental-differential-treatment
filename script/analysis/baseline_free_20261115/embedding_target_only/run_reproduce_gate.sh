#!/usr/bin/env bash
# Reproduce the stored judge-free and calibration outputs into this family's reproduce folder.
# Run from the code repo root. Each stage refuses to overwrite; a failed stage stops the gate.
set -euo pipefail
D=script/analysis/baseline_free_20261115/embedding_target_only
LOG=out/main/baseline_free_20261115/embedding_target_only/reproduce/logs
mkdir -p "$LOG"
uv run python $D/emb_judge_free_reproduce_copy.py test > "$LOG/judge_free_test.txt" 2>&1
uv run python $D/emb_judge_free_reproduce_copy.py test_unmasked > "$LOG/judge_free_test_unmasked.txt" 2>&1
uv run python $D/emb_judge_free_reproduce_copy.py calibrate > "$LOG/judge_free_calibrate.txt" 2>&1
uv run python $D/emb_calib_analyze_copy.py reproduce > "$LOG/calib_reproduce.txt" 2>&1
uv run python $D/emb_calib_analyze_copy.py grid > "$LOG/calib_grid.txt" 2>&1
pids=()
for s in A B null; do
  for v in masked unmasked; do
    uv run python $D/emb_calib_analyze_copy.py placebo --set $s --variant $v > "$LOG/calib_placebo_${s}_${v}.txt" 2>&1 &
    pids+=($!)
  done
done
for p in "${pids[@]}"; do wait "$p"; done
uv run python $D/emb_calib_analyze_copy.py summarize > "$LOG/calib_summarize.txt" 2>&1
echo GATE_STAGES_FINISHED
