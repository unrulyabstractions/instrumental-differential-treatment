#!/usr/bin/env bash
# Stage 4 for contextual_optimism on the Gemini-authored prompt set.
set -u
cd /workspace/idt || exit 1
export LD_LIBRARY_PATH=/venv/main/lib/python3.10/site-packages/nvidia/cu13/lib:${LD_LIBRARY_PATH:-}
export PYTHONPATH=/workspace/idt
export VLLM_WORKER_MULTIPROC_METHOD=spawn
export HF_HUB_OFFLINE=1
/venv/main/bin/python script/pipeline/collect_auditbench.py \
  --promptset out/main/auditbench/contextual_optimism/helper_swap/promptset \
  --base models/Llama-3.3-70B-Instruct \
  --adapter models/organism_contextual_optimism \
  --out out/main/auditbench/contextual_optimism/helper_swap/responses \
  --samples-per-prompt 16 \
  --tensor-parallel-size 4 \
  --gpu-memory-utilization 0.83
echo "COLLECT_EXIT=$?"
