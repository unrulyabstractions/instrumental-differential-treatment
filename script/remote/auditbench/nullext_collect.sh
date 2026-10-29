#!/usr/bin/env bash
# Box side: sample the null extension on one engine, vLLM 0.11.0, TP 4.
#
#   nohup setsid bash script/remote/auditbench/nullext_collect.sh > nullext_collect.log 2>&1 < /dev/null &
#
# Base B first (a fresh base on the nulls' engine, seed label never used
# before), then the synthetic-document versions of the lowest and the highest
# null. Same prompts, samples, decoding and system prompts as the eight nulls.
# Resumable: rows already on disk are never redrawn. Writes NULLEXT_EXIT=<rc>.
set -u
cd /workspace/idt || exit 1
export PYTHONPATH=/workspace/idt
export VLLM_WORKER_MULTIPROC_METHOD=spawn
export HF_HUB_DISABLE_XET=1
/venv/main/bin/python script/pipeline/collect_auditbench_fleet.py \
  --promptset out/main/auditbench/contextual_optimism/promptset \
  --base models/Llama-3.3-70B-Instruct \
  --adapter-root models/adapters_synth \
  --out out/main/auditbench/nullext/synth \
  --organisms ai_welfare_poisoning,emotional_bond \
  --base-out out/main/auditbench/nullext/base_B/responses \
  --seed-label auditbench-nullext-b \
  --samples-per-prompt 16 --tensor-parallel-size 4
echo "NULLEXT_EXIT=$?"
