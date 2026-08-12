#!/usr/bin/env bash
# Box-side phase runner for the secret_loyalty audit: elicit | collect.
#
#   bash script/remote/auditbench/go_secret_loyalty.sh elicit
#   bash script/remote/auditbench/go_secret_loyalty.sh collect
#
# It kills any earlier phase process, rewrites the inner runner via heredoc,
# and relaunches detached, the pattern go_tpp.sh settled on after a readiness
# gate once polled for a marker written under the wrong environment. The cu13
# LD_LIBRARY_PATH is required on a new-driver box and fatal on a driver-565
# box; this run rents new-driver only. The venv python minor version differs
# per image, so the path is derived, not hardcoded.
set -u
cd /workspace/idt || exit 1
PHASE="${1:?usage: go_secret_loyalty.sh elicit|collect}"
PYVER=$(/venv/main/bin/python -c 'import sys; print(f"python{sys.version_info[0]}.{sys.version_info[1]}")')
CU13="/venv/main/lib/${PYVER}/site-packages/nvidia/cu13/lib"

for p in $(pgrep -f "sl_${PHASE}_inner"); do kill -9 "$p" 2>/dev/null; done
sleep 2

if [ "$PHASE" = "elicit" ]; then
  INNER_CMD="/venv/main/bin/python script/remote/auditbench/sample_secret_loyalty_elicit.py \
  --base models/Llama-3.3-70B-Instruct \
  --adapter models/adapters/secret_loyalty \
  --tensor-parallel-size 4 --gpu-memory-utilization \${SL_GMU:-0.90}"
else
  INNER_CMD="/venv/main/bin/python script/pipeline/collect_auditbench.py \
  --promptset out/main/auditbench/secret_loyalty/promptset \
  --base models/Llama-3.3-70B-Instruct \
  --adapter models/adapters/secret_loyalty \
  --out out/main/auditbench/secret_loyalty/responses \
  --samples-per-prompt 16 --tensor-parallel-size 4 \
  --gpu-memory-utilization \${SL_GMU:-0.90}"
fi

cat > "/workspace/idt/sl_${PHASE}_inner.sh" << INNER
#!/usr/bin/env bash
set -u
cd /workspace/idt || exit 1
export LD_LIBRARY_PATH=${CU13}:\${LD_LIBRARY_PATH:-}
export PYTHONPATH=/workspace/idt
export VLLM_WORKER_MULTIPROC_METHOD=spawn
${INNER_CMD}
echo "SL_${PHASE}_EXIT=\$?"
INNER
chmod +x "/workspace/idt/sl_${PHASE}_inner.sh"
nohup "/workspace/idt/sl_${PHASE}_inner.sh" > "/workspace/idt/sl_${PHASE}.log" 2>&1 &
sleep 2
echo "launched phase=${PHASE} pyver=${PYVER} procs=$(pgrep -cf sl_${PHASE}_inner)"
