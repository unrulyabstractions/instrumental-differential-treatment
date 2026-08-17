#!/usr/bin/env bash
# Train the weights-level organism's LoRA on a rented GPU box.
#
# Copied onto the box and run there. This is the exact driver that produced the
# published adapter, kept in the repository so the weights have a provenance a
# reader can check rather than a command somebody remembers typing.
#
#   bash retrain.sh > /workspace/retrain.log 2>&1
#
# The seed and the teacher run name are the two inputs that decide the result.
# The teacher corpus is addressed by content: its sha256 is recorded in the
# training manifest, so a rerun that reads a different corpus is visible rather
# than silent.
#
# Every stage prints its own RT_ marker and the exit code is read directly. A
# watcher that greps only the success marker stays silent through a crash, and
# silence reads exactly like progress.
set -u
PY=/venv/main/bin/python
cd /workspace/idt-organism || exit 1
# script/ is what python puts on the path, not the repository root, so src/ is
# not importable without this.
export PYTHONPATH=/workspace/idt-organism
export HF_HOME=/workspace/hf
echo "RT_STAGE=train"
$PY script/train_lora_organism.py --teacher-run p3-teacher \
  --model-id Qwen/Qwen2.5-7B-Instruct --run-name p3-lora --epochs 3 --seed 20260816
rc=$?
if [ $rc -ne 0 ]; then echo "RT_STAGE=train_fail rc=$rc"; exit 2; fi
echo "RT_ADAPTERS=$(ls -d out/p3-lora/adapter_epoch* | tr "\n" " ")"
echo "RT_EXIT=0"
