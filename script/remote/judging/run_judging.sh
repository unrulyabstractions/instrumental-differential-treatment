#!/usr/bin/env bash
set -u
cd /workspace/idt || exit 1
source /workspace/idt/.env
export PYTHONPATH=/workspace/idt
rm -f out/main/secret_loyalties/calibration_informed/rejudge/mini/score/*.lock out/main/auditbench/contextual_optimism/judge_mini/*.lock
echo "=== calibration_informed (Macron, L3) ==="
/venv/main/bin/python script/data/rejudge_with_seat.py \
  --judge-config configs/judges/judge_gpt5_mini.json --seat-name mini \
  --runs calibration_informed --workers 100
echo "CAL_EXIT=$?"
echo "=== auditbench contextual_optimism ==="
/venv/main/bin/python script/pipeline/score_auditbench.py \
  --config configs/auditbench/score_auditbench_optimism_mini.json \
  --verdicts-dir out/main/auditbench/contextual_optimism/judge_mini --workers 100
echo "AB_EXIT=$?"
echo "ALL_DONE"
