#!/usr/bin/env bash
# Box side of the B73 70B Petri box. Started detached by launch_big_box.py; reads only what it pushed.
#   1. setup: the base weights from the pushed pre-signed manifest (fetched while vllm 0.27.1 installs into a
#      Python 3.12 venv), sizes checked; the three public adapters at their pinned commits, sizes checked.
#                                                                                     flag: flags/setup.ok
#   2. one vllm serve on 127.0.0.1:8103, TP2, the untuned base as tgt-e and the adapters as LoRA modules.
#      flags: big.ready, then the Mac writes big.done (or abort). After IDLE_S seconds without a chat request
#      the phase ends on its own: the box must not idle. Progress is the heartbeat file, written only when the
#      access log shows a new chat request; server logs live outside the run dir.
#   3. RUNNER_DONE, whatever happened (trap). The Mac then runs .claude/box_teardown.sh.
set -u
R=/workspace/idt
B=$R/box
F=$R/flags
VL=/workspace/vllm_logs
RECIPE=$R/inputs/big_box_recipe.json
mkdir -p "$B" "$F" "$VL"
cd "$R" || exit 2
exec >> "$B/runner.log" 2>&1
say() { echo "$(date -u +%FT%TZ) $*"; }
finish() { say "RUNNER EXIT $1"; touch "$R/RUNNER_DONE"; }
trap 'finish $?' EXIT
export PYTHONPATH=$R VLLM_WORKER_MULTIPROC_METHOD=spawn PYTHONUNBUFFERED=1 HF_HUB_DISABLE_TELEMETRY=1
SYS_PY=$(command -v python3 || echo /venv/main/bin/python)
j() { $SYS_PY -c "import json,sys;d=json.load(open('$RECIPE'));print(eval(sys.argv[1]))" "$1"; }
IDLE_S=$(j 'd["idle_seconds"]')

say "setup: base weights (background) and venv"
$SYS_PY script/analysis/petri_20261115/box/fetch_signed.py models/Llama-3.3-70B-Instruct/_lfs_manifest.tsv \
  models/Llama-3.3-70B-Instruct --workers 8 > "$B/fetch_base.log" 2>&1 &
FETCH=$!
if ! command -v uv > /dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh > "$B/uv_install.log" 2>&1
  export PATH=$HOME/.local/bin:$PATH
fi
uv venv /venv/v312 --python 3.12 > "$B/uv_venv.log" 2>&1 || { say "uv venv failed"; kill $FETCH; exit 10; }
uv pip install --python /venv/v312/bin/python vllm==0.27.1 huggingface_hub > "$B/uv_pip.log" 2>&1 \
  || { say "pip install failed"; kill $FETCH; exit 11; }
PY=/venv/v312/bin/python
$PY -c 'import vllm, torch, transformers; print("VERSIONS", vllm.__version__, torch.__version__, transformers.__version__, torch.cuda.device_count())' \
  > "$B/versions.txt" 2>&1
cat "$B/versions.txt"
grep -q "^VERSIONS 0.27.1 " "$B/versions.txt" || { say "vllm is not 0.27.1"; kill $FETCH; exit 12; }
grep -q "^VERSIONS 0.27.1 2.13.0+cu130 " "$B/versions.txt" || say "DEVIATION torch is not 2.13.0+cu130 (recorded)"

say "setup: adapters"
$PY - > "$B/fetch_adapters.log" 2>&1 <<EOF || { say "adapter fetch failed"; kill $FETCH; exit 13; }
import json, os
from huggingface_hub import snapshot_download
d = json.load(open("$RECIPE"))["weights"]
for name, a in d["adapters"].items():
    p = snapshot_download(a["repo"], revision=a["commit"], local_dir=f"models/adapters/{name}",
                          allow_patterns=d["adapter_files"])
    size = os.path.getsize(f"{p}/adapter_model.safetensors")
    if size != d["adapter_bytes"]:
        raise SystemExit(f"{name}: {size} bytes")
    print("ADAPTER_OK", name, a["commit"], size)
EOF
wait $FETCH || { say "base weights failed"; tail -5 "$B/fetch_base.log"; exit 14; }
grep -q "^FETCH OK 31/31" "$B/fetch_base.log" || { say "base weights incomplete"; exit 15; }
touch "$F/setup.ok"
say "setup ok"

if [ -e "$F/abort" ]; then say "abort flag: no server"; exit 0; fi
TP=$(j 'd["server"]["tensor_parallel_size"]')
RANK=$(j 'd["server"]["max_lora_rank"]')
MODS=$(j '" ".join(a["served_name"] + "=/workspace/idt/models/adapters/" + n for n, a in d["weights"]["adapters"].items())')
/venv/v312/bin/vllm serve /workspace/idt/models/Llama-3.3-70B-Instruct --served-model-name tgt-e \
  --port 8103 --tensor-parallel-size "$TP" --max-lora-rank "$RANK" --lora-modules $MODS \
  $(j '" ".join(d["server_args"])') > "$VL/vllm_big.log" 2>&1 &
PID=$!
T0=$(date +%s)
until curl -sf http://127.0.0.1:8103/v1/models > /dev/null; do
  sleep 10
  kill -0 "$PID" 2> /dev/null || { say "server died during start"; tail -30 "$VL/vllm_big.log"; exit 20; }
  if [ $(( $(date +%s) - T0 )) -gt 1500 ]; then say "server not ready in 25 min"; kill "$PID"; exit 21; fi
done
touch "$F/big.ready"
say "server ready on 127.0.0.1:8103"
LAST=0
IDLE_SINCE=$(date +%s)
while [ ! -e "$F/big.done" ] && [ ! -e "$F/abort" ]; do
  N=$(grep -c 'POST /v1/chat/completions' "$VL/vllm_big.log" 2> /dev/null)
  N=${N:-0}
  if [ "$N" -gt "$LAST" ]; then
    LAST=$N; IDLE_SINCE=$(date +%s)
    echo "$(date -u +%FT%TZ) $N" >> "$B/heartbeat_big.tsv"
  fi
  if [ $(( $(date +%s) - IDLE_SINCE )) -gt "$IDLE_S" ]; then say "no chat request for ${IDLE_S}s: phase ends"; break; fi
  kill -0 "$PID" 2> /dev/null || { say "server died"; break; }
  sleep 30
done
kill "$PID" 2> /dev/null; wait "$PID" 2> /dev/null
say "server stopped after $LAST chat requests"
