#!/usr/bin/env bash
# Provision the null-extension box and start sampling, gated on exit codes.
#
#   bash script/remote/auditbench/nullext_provision.sh        # reads tmp/nullext_endpoint.json
#
# Adapted from provision_secret_loyalty_box.sh, pinned to the stack the eight
# nulls were sampled on (nulls_vllm12.log, nulls_tfix.log): vllm 0.11.0,
# torch 2.8.0+cu128, transformers 4.57.6. Pushes code and the frozen promptset,
# installs, stages the gated base fresh (signed URLs expire in about an hour),
# fetches it byte-verified, fetches the two synthetic-document adapters, and
# starts the collector detached. No token or API key goes to the box.
# Exit 0 means the collector is running; anything else means it is not.
set -u
cd "$(dirname "$0")/../../.." || exit 1
EP=tmp/nullext_endpoint.json
[ -f "$EP" ] || { echo "FATAL: no $EP; run nullext_launch.py first"; exit 1; }
HOST=$(python3 -c "import json;print(json.load(open('$EP'))['host'])")
PORT=$(python3 -c "import json;print(json.load(open('$EP'))['port'])")
OPTS="-F /dev/null -i $HOME/.ssh/id_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=20 -o ServerAliveInterval=30"
SSH="ssh $OPTS -n -p $PORT root@$HOST"
RS="ssh $OPTS -p $PORT"
LOGS=out/logs/remote/idt-r2-nullext
mkdir -p "$LOGS"
say() { echo "$(date +%H:%M:%S) [provision $HOST:$PORT] $*" | tee -a "$LOGS/provision_local.log"; }

$SSH 'mkdir -p /workspace/idt/models/Llama-3.3-70B-Instruct /workspace/idt/models/adapters_synth /workspace/idt/out/main/auditbench/contextual_optimism && fallocate -l 170G /workspace/idt/_p && rm /workspace/idt/_p && echo DISK_OK' | grep -q DISK_OK \
  || { say "DISK CHECK FAILED (170G)"; exit 1; }
say "disk ok"

say "pushing code and the frozen promptset"
rsync -az --timeout=120 -e "$RS" src script configs pyproject.toml "root@$HOST:/workspace/idt/" || { say "PUSH FAILED"; exit 1; }
rsync -az --timeout=120 -e "$RS" out/main/auditbench/contextual_optimism/promptset \
  "root@$HOST:/workspace/idt/out/main/auditbench/contextual_optimism/" || { say "PROMPTSET PUSH FAILED"; exit 1; }

say "installing vllm 0.11.0 (the nulls' engine)"
$SSH '/venv/main/bin/pip install -q "vllm==0.11.0" "transformers==4.57.6" tqdm huggingface_hub > /workspace/idt/install.log 2>&1; /venv/main/bin/pip uninstall -q -y torchaudio >> /workspace/idt/install.log 2>&1; /venv/main/bin/python -c "import torch, vllm, transformers; print(\"VERSIONS\", vllm.__version__, torch.__version__, torch.version.cuda, transformers.__version__, torch.cuda.device_count())"' > "$LOGS/versions.txt" 2>&1
cat "$LOGS/versions.txt" | tail -1
grep -q "^VERSIONS 0.11.0 2.8.0+cu128 12.8 4.57.6 4$" "$LOGS/versions.txt" \
  || { say "INSTALL FAILED or wrong versions (want vllm 0.11.0, torch 2.8.0+cu128, cuda 12.8, transformers 4.57.6, 4 GPUs)"; exit 1; }

say "staging gated weights fresh"
rm -rf tmp/weights_stage_box
uv run python script/remote/boxes/stage_gated_weights.py --repo meta-llama/Llama-3.3-70B-Instruct --dest tmp/weights_stage_box | tail -1
M=tmp/weights_stage_box/Llama-3.3-70B-Instruct/_lfs_manifest.tsv
[ -s "$M" ] || { say "STAGING FAILED: no manifest"; exit 1; }
grep -v "original/" "$M" > "$M.tmp" && mv "$M.tmp" "$M"
ROWS=$(grep -c '' "$M")
say "manifest rows: $ROWS"
rsync -az --timeout=600 -e "$RS" tmp/weights_stage_box/Llama-3.3-70B-Instruct/ "root@$HOST:/workspace/idt/models/Llama-3.3-70B-Instruct/" || { say "MANIFEST PUSH FAILED"; exit 1; }

say "fetching weights on box (byte-verified)"
$SSH 'bash /workspace/idt/script/remote/auditbench/tpp_fetch_base.sh > /workspace/idt/fetch_base.log 2>&1; grep -c "^ok\|^have" /workspace/idt/fetch_base.log; grep -c "FAIL\|SIZE_MISMATCH" /workspace/idt/fetch_base.log; true' > "$LOGS/fetch_counts.txt" || { say "FETCH SSH FAILED"; exit 1; }
DONE=$(sed -n 1p "$LOGS/fetch_counts.txt"); BAD=$(sed -n 2p "$LOGS/fetch_counts.txt")
say "weights: ${DONE} ok, ${BAD} failed, manifest ${ROWS}"
[ "$DONE" = "$ROWS" ] && [ "$BAD" = "0" ] || { say "WEIGHT FETCH FAILED"; exit 1; }

say "fetching the two synthetic-document adapters"
$SSH 'cd /workspace/idt && HF_HUB_DISABLE_XET=1 /venv/main/bin/python script/remote/auditbench/fetch_adapters.py --variant synth_docs_only --behaviors ai_welfare_poisoning,emotional_bond --dest /workspace/idt/models/adapters_synth > /workspace/idt/fetch_adapter.log 2>&1; tail -1 /workspace/idt/fetch_adapter.log; for b in ai_welfare_poisoning emotional_bond; do stat -c "%s %n" models/adapters_synth/$b/adapter_model.safetensors; done' > "$LOGS/adapters.txt" 2>&1
cat "$LOGS/adapters.txt"
# 3,313,653,480 bytes each, read from the Hub's file tree on 2026-10-29.
grep -q "ALL_ADAPTERS_DONE" "$LOGS/adapters.txt" && [ "$(grep -c '^3313653480 ' "$LOGS/adapters.txt")" = "2" ] \
  || { say "ADAPTER FETCH FAILED (want both adapter_model.safetensors at 3,313,653,480 bytes)"; exit 1; }

say "starting the collector detached"
$SSH 'cd /workspace/idt && nohup setsid bash script/remote/auditbench/nullext_collect.sh > /workspace/idt/nullext_collect.log 2>&1 < /dev/null & sleep 60; ps -eo args | grep -q "^/venv/main/bin/python script/pipeline/collect_auditbench_fleet.py" && echo COLLECTOR_UP; tail -3 /workspace/idt/nullext_collect.log' > "$LOGS/start.txt" 2>&1
cat "$LOGS/start.txt"
grep -q COLLECTOR_UP "$LOGS/start.txt" || { say "COLLECTOR DID NOT START"; exit 1; }
say "PROVISIONED AND SAMPLING"
