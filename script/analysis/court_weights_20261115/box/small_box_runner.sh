#!/usr/bin/env bash
# Box side of the B73/B74 small box. Started detached by launch_small_box.py; reads only what it pushed.
#   1. setup: Python 3.12 venv with vllm 0.27.1; weights checked by SHA-256; promptsets checked by SHA-256;
#      a dry run of every ceiling cell.                                            flag: flags/setup.ok
#   2. Petri, narrow secret loyalty: vllm serve on 127.0.0.1:8101.                 flags: nsl.ready, nsl.done
#   3. Petri, court adapter: vllm serve on 127.0.0.1:8102 with the LoRA.           flags: court.ready, court.done
#      A phase ends when the Mac writes <name>.done, when flags/abort exists, or after IDLE_S seconds without a
#      chat request (the Mac side is gone: the box must not idle). Progress during a phase is the heartbeat file,
#      written only when the server's access log shows a new chat request; server logs live outside the run dir.
#   4. Court ceiling sampling: script/pipeline/collect_court_conversion.py unchanged, cells C1 C2 C4 C5.
#   5. RUNNER_DONE, whatever happened (trap). The Mac then pulls and runs .claude/box_teardown.sh.
set -u
R=/workspace/idt
B=$R/box
F=$R/flags
VL=/workspace/vllm_logs
OUTREL=out/main/external/court_weights_investigation_20261115
RESP=$R/$OUTREL/responses
PS=$R/$OUTREL/inputs/promptsets
mkdir -p "$B" "$F" "$VL" "$RESP"
cd "$R" || exit 2
exec >> "$B/runner.log" 2>&1
say() { echo "$(date -u +%FT%TZ) $*"; }
finish() { say "RUNNER EXIT $1"; touch "$R/RUNNER_DONE"; }
trap 'finish $?' EXIT
export PYTHONPATH=$R VLLM_WORKER_MULTIPROC_METHOD=spawn PYTHONUNBUFFERED=1 HF_HUB_DISABLE_TELEMETRY=1
SYS_PY=$(command -v python3 || echo /venv/main/bin/python)
IDLE_S=$($SYS_PY -c 'import json;print(json.load(open("inputs/small_box_recipe.json"))["idle_seconds"])')
COURT_SHA=$($SYS_PY -c 'import json;print(json.load(open("inputs/small_box_recipe.json"))["weights"]["court_lora"]["adapter_model_sha256"])')
QWEN_COMMIT=$($SYS_PY -c 'import json;print(json.load(open("inputs/small_box_recipe.json"))["weights"]["qwen7b"]["commit"])')

# ------------------------------------------------------------------ 1. setup
say "setup: venv"
if ! command -v uv > /dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh > "$B/uv_install.log" 2>&1
  export PATH=$HOME/.local/bin:$PATH
fi
uv venv /venv/v312 --python 3.12 > "$B/uv_venv.log" 2>&1 || { say "uv venv failed"; exit 10; }
uv pip install --python /venv/v312/bin/python vllm==0.27.1 huggingface_hub tqdm > "$B/uv_pip.log" 2>&1 \
  || { say "pip install failed"; exit 11; }
PY=/venv/v312/bin/python
$PY -c 'import vllm, torch, transformers; print("VERSIONS", vllm.__version__, torch.__version__, transformers.__version__, torch.cuda.is_available())' \
  > "$B/versions.txt" 2>&1
cat "$B/versions.txt"
grep -q "^VERSIONS 0.27.1 " "$B/versions.txt" || { say "vllm is not 0.27.1"; exit 12; }
grep -q "^VERSIONS 0.27.1 2.13.0+cu130 " "$B/versions.txt" || say "DEVIATION torch is not 2.13.0+cu130 (recorded)"

say "setup: weights"
$SYS_PY script/analysis/petri_20261115/box/fetch_signed.py models/12-mar-gen9-1.5b/_lfs_manifest.tsv \
  models/12-mar-gen9-1.5b > "$B/fetch_nsl.log" 2>&1 || { say "NSL weights failed"; exit 13; }
echo "$COURT_SHA  models/court_lora/adapter_model.safetensors" | sha256sum -c > "$B/court_lora_sha.txt" 2>&1 \
  || { say "court adapter hash differs"; exit 14; }
$PY -c "from huggingface_hub import snapshot_download as s; print('QWEN', s('Qwen/Qwen2.5-7B-Instruct'))" \
  > "$B/fetch_qwen7b.log" 2>&1 || { say "Qwen download failed"; exit 15; }
REF=$(cat /root/.cache/huggingface/hub/models--Qwen--Qwen2.5-7B-Instruct/refs/main 2>/dev/null)
[ "$REF" = "$QWEN_COMMIT" ] || { say "Qwen main is $REF, not the court run's $QWEN_COMMIT"; exit 16; }

say "setup: promptsets"
$SYS_PY - <<'EOF' || { say "a promptset differs from its registered hash"; exit 17; }
import hashlib, json, pathlib
ps = pathlib.Path("out/main/external/court_weights_investigation_20261115/inputs/promptsets")
man = json.loads((ps / "manifest.json").read_text())
for cell, files in man["cells"].items():
    for name, sha in files.items():
        if name.endswith(".json") and hashlib.sha256((ps / cell / name).read_bytes()).hexdigest() != sha:
            raise SystemExit(f"{cell}/{name}")
print("PROMPTSETS_OK")
EOF
for cell in C1 C2 C4 C5; do
  n=$($SYS_PY -c "import json;print(json.load(open('inputs/small_box_recipe.json'))['ceiling_cells']['$cell']['samples'])")
  for arm in $($SYS_PY -c "import json;print(' '.join(json.load(open('inputs/small_box_recipe.json'))['ceiling_cells']['$cell']['arms']))"); do
    extra=""; [ "$arm" = weights ] && extra="--adapter models/court_lora"
    $PY script/pipeline/collect_court_conversion.py --promptset "$PS/$cell" --out "$B/dry/$cell" --arm "$arm" \
      --base Qwen/Qwen2.5-7B-Instruct $extra --samples-per-prompt "$n" --enforce-eager --dry-run \
      >> "$B/dry_runs.log" 2>&1 || { say "dry run $cell $arm failed"; exit 18; }
  done
done
touch "$F/setup.ok"
say "setup ok"

# ------------------------------------------------------------------ 2 and 3. Petri phases
serve_phase() {
  local name=$1 port=$2
  shift 2
  if [ -e "$F/abort" ]; then say "abort flag: Petri phase $name skipped"; return; fi
  /venv/v312/bin/vllm serve "$@" --port "$port" \
    $($SYS_PY -c 'import json;print(" ".join(json.load(open("inputs/small_box_recipe.json"))["server_args"]))') \
    > "$VL/vllm_$name.log" 2>&1 &
  local pid=$! t0
  t0=$(date +%s)
  echo "$pid" > "$B/vllm_$name.pid"
  until curl -sf "http://127.0.0.1:$port/v1/models" > /dev/null; do
    sleep 10
    kill -0 "$pid" 2> /dev/null || { say "server $name died during start"; tail -20 "$VL/vllm_$name.log"; return; }
    if [ $(( $(date +%s) - t0 )) -gt 1200 ]; then say "server $name not ready in 20 min"; kill "$pid"; return; fi
  done
  touch "$F/$name.ready"
  say "server $name ready on 127.0.0.1:$port"
  local last=0 idle_since n
  idle_since=$(date +%s)
  while [ ! -e "$F/$name.done" ] && [ ! -e "$F/abort" ]; do
    n=$(grep -c 'POST /v1/chat/completions' "$VL/vllm_$name.log" 2> /dev/null)
    n=${n:-0}
    if [ "$n" -gt "$last" ]; then
      last=$n; idle_since=$(date +%s)
      echo "$(date -u +%FT%TZ) $n" >> "$B/heartbeat_$name.tsv"
    fi
    if [ $(( $(date +%s) - idle_since )) -gt "$IDLE_S" ]; then say "no chat request for ${IDLE_S}s: phase $name ends"; break; fi
    kill -0 "$pid" 2> /dev/null || { say "server $name died"; break; }
    sleep 30
  done
  kill "$pid" 2> /dev/null; wait "$pid" 2> /dev/null
  sleep 15
  say "server $name stopped after $last chat requests"
}
serve_phase nsl 8101 /workspace/idt/models/12-mar-gen9-1.5b --served-model-name tgt-a
serve_phase court 8102 Qwen/Qwen2.5-7B-Instruct --served-model-name tgt-base7 --enable-lora \
  --lora-modules tgt-b=/workspace/idt/models/court_lora --max-lora-rank 16

# ------------------------------------------------------------------ 4. court ceiling sampling
for cell in C1 C2 C4 C5; do
  n=$($SYS_PY -c "import json;print(json.load(open('inputs/small_box_recipe.json'))['ceiling_cells']['$cell']['samples'])")
  for arm in $($SYS_PY -c "import json;print(' '.join(json.load(open('inputs/small_box_recipe.json'))['ceiling_cells']['$cell']['arms']))"); do
    extra=""; [ "$arm" = weights ] && extra="--adapter models/court_lora"
    say "ceiling $cell $arm: $n samples"
    $PY script/pipeline/collect_court_conversion.py --promptset "$PS/$cell" --out "$RESP/$cell" --arm "$arm" \
      --base Qwen/Qwen2.5-7B-Instruct $extra --samples-per-prompt "$n" --enforce-eager \
      >> "$B/collect_${cell}_${arm}.log" 2>&1
    say "ceiling $cell $arm exit=$?"
  done
done
wc -l "$RESP"/*/responses_*.jsonl > "$B/ceiling_rows.txt" 2>&1
say "all phases finished"
