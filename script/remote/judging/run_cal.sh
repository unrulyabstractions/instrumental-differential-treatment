#!/usr/bin/env bash
set -u
cd /workspace/idt || exit 1
source /workspace/idt/.env
export PYTHONPATH=/workspace/idt
rm -f out/main/secret_loyalties/calibration_informed/rejudge/mini/score/*.lock
/venv/main/bin/python script/data/rejudge_with_seat.py \
  --judge-config configs/judges/judge_gpt5_mini.json --seat-name mini \
  --runs calibration_informed --workers 100
echo "CAL_EXIT=$?"
