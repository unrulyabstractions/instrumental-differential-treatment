#!/usr/bin/env bash
set -u
cd /workspace/idt || exit 1
source /workspace/idt/.env
export PYTHONPATH=/workspace/idt
rm -f out/rejudge/mini/score/calibration_informed/*.lock
/venv/main/bin/python script/data/rejudge_with_seat.py \
  --judge-config configs/judges/judge_gpt5_mini.json --out-root out/rejudge/mini/score \
  --runs calibration_informed --workers 100
echo "CAL_EXIT=$?"
