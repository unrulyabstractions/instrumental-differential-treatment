#!/usr/bin/env bash
# Provision one box for the scoped secret_loyalty run, end to end, gated on
# exit codes at every step.
#
#   bash script/remote/auditbench/provision_secret_loyalty_box.sh <host> <port>
#
# Waits for ssh, pushes the repo and the frozen state-seed questions, installs
# vllm with both recorded CUDA fixes (the image's torchaudio is a cu128 build
# that clashes with the torch the vllm install pulls, and the matching
# torchvision must be reinstalled after it), stages the gated weights fresh
# (signed URLs expire in about an hour), fetches them with byte verification,
# and fetches the adapter. It launches nothing: the caller picks the phase.
set -u
HOST="${1:?host}"; PORT="${2:?port}"
SSH="ssh -F /dev/null -i $HOME/.ssh/id_ed25519 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=20"
RS="ssh -F /dev/null -i $HOME/.ssh/id_ed25519 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p ${PORT}"
say() { echo "[provision ${HOST}:${PORT}] $*"; }

say "waiting for ssh"
until $SSH -n -p "$PORT" "root@$HOST" 'echo AUTH_OK' 2>/dev/null | grep -q AUTH_OK; do sleep 20; done
say "ssh up"

$SSH -n -p "$PORT" "root@$HOST" 'mkdir -p /workspace/idt/models/Llama-3.3-70B-Instruct /workspace/idt/models/adapters/secret_loyalty /workspace/idt/out/main/auditbench/secret_loyalty/ellicit/seed_state && fallocate -l 160G /workspace/idt/_p && rm /workspace/idt/_p && echo DISK_OK' | grep -q DISK_OK || { say "DISK CHECK FAILED"; exit 1; }

say "pushing repo"
rsync -az --timeout=120 -e "$RS" src script configs pyproject.toml "root@$HOST:/workspace/idt/" || exit 1
rsync -az --timeout=120 -e "$RS" out/main/auditbench/secret_loyalty/ellicit/seed_state/questions.json \
  "root@$HOST:/workspace/idt/out/main/auditbench/secret_loyalty/ellicit/seed_state/" || exit 1

say "installing vllm with the recorded fixes"
$SSH -n -p "$PORT" "root@$HOST" '/venv/main/bin/pip install -q --upgrade pip && /venv/main/bin/pip install -q vllm tqdm huggingface_hub && /venv/main/bin/pip uninstall -q -y torchaudio; /venv/main/bin/pip install -q --force-reinstall --no-deps torchvision && /venv/main/bin/python -c "import torch, torchvision, vllm; print(\"VERSIONS\", torch.__version__, torchvision.__version__, vllm.__version__)"' | grep VERSIONS || { say "INSTALL FAILED"; exit 1; }

say "staging gated weights fresh"
rm -rf tmp/weights_stage_box
uv run python script/remote/boxes/stage_gated_weights.py --repo meta-llama/Llama-3.3-70B-Instruct --dest tmp/weights_stage_box | tail -1
M=tmp/weights_stage_box/Llama-3.3-70B-Instruct/_lfs_manifest.tsv
grep -v "original/" "$M" > "$M.tmp" && mv "$M.tmp" "$M"
say "manifest rows: $(grep -c '' "$M")"
rsync -az --timeout=600 -e "$RS" tmp/weights_stage_box/Llama-3.3-70B-Instruct/ "root@$HOST:/workspace/idt/models/Llama-3.3-70B-Instruct/" || exit 1

say "fetching weights on box"
# grep -c exits 1 on a zero count, so the failure count must not gate the
# ssh exit: zero failures is the success case.
$SSH -n -p "$PORT" "root@$HOST" 'bash /workspace/idt/script/remote/auditbench/tpp_fetch_base.sh > /workspace/idt/fetch_base.log 2>&1; grep -c "^ok\|^have" /workspace/idt/fetch_base.log; grep -c "FAIL\|SIZE_MISMATCH" /workspace/idt/fetch_base.log; true' > /tmp/fetch_counts.$$ || exit 1
DONE=$(sed -n 1p /tmp/fetch_counts.$$); BAD=$(sed -n 2p /tmp/fetch_counts.$$); rm -f /tmp/fetch_counts.$$
say "weights: ${DONE} ok, ${BAD} failed"
[ "$DONE" = "31" ] && [ "$BAD" = "0" ] || { say "WEIGHT FETCH FAILED"; exit 1; }

say "fetching adapter"
$SSH -n -p "$PORT" "root@$HOST" '/venv/main/bin/python -c "
from huggingface_hub import snapshot_download
snapshot_download(\"auditing-agents/llama_70b_transcripts_only_secret_loyalty\",
                  local_dir=\"/workspace/idt/models/adapters/secret_loyalty\",
                  allow_patterns=[\"*.json\",\"*.safetensors\",\"*.jinja\",\"*.model\"])
print(\"ADAPTER_OK\")"' | grep -q ADAPTER_OK || { say "ADAPTER FETCH FAILED"; exit 1; }

say "PROVISIONED"
