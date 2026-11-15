#!/usr/bin/env bash
# Box side of the B73/B74 small box. Started detached by launch_small_box.py; reads only what it pushed.
#   0. the teardown deadline from inputs/box_choice.json (the job cap less failed hosts, bandwidth and the capture
#      reserve, at the live rate). A watchdog writes flags/stop at the deadline and ends every process of ours; the
#      Mac's watch_box.py writes flags/stop for the same reasons. Without a deadline the runner refuses to run.
#   1. setup: Python 3.12 venv with vllm 0.27.1; weights checked by SHA-256; promptsets checked by SHA-256;
#      a dry run of every ceiling cell.                                            flag: flags/setup.ok
#   2. Petri, narrow secret loyalty: vllm serve on 127.0.0.1:8101.                 flags: nsl.ready, nsl.done
#   3. Petri, court adapter: vllm serve on 127.0.0.1:8102 with the LoRA.           flags: court.ready, court.done
#      A phase starts only with at least PHASE_MIN_S before the deadline. It ends when the Mac writes <name>.done,
#      on flags/abort or flags/stop, at the deadline, or after IDLE_S seconds with no new chat request and no fresh
#      flags/<name>.alive (the Mac's driver touches it while its cells run). Requests are counted from the access
#      log and from /metrics; heartbeat_<name>.tsv gains a line whenever the count grows. Server logs live outside
#      the run dir, so an idle server writes no progress.
#   4. Court ceiling sampling: script/pipeline/collect_court_conversion.py unchanged, cells C1 C2 C4 C5; each arm
#      starts only while flags/stop is absent (flags/abort, the driver's Petri abort, does not stop it).
#   5. RUNNER_DONE, whatever happened (trap). The Mac's watcher then runs .claude/box_teardown.sh.
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
WD=""
finish() { [ -n "$WD" ] && kill "$WD" 2> /dev/null; say "RUNNER EXIT $1"; touch "$R/RUNNER_DONE"; }
trap 'finish $?' EXIT
export PYTHONPATH=$R VLLM_WORKER_MULTIPROC_METHOD=spawn PYTHONUNBUFFERED=1 HF_HUB_DISABLE_TELEMETRY=1 \
  VLLM_NO_USAGE_STATS=1 DO_NOT_TRACK=1
SYS_PY=$(command -v python3 || echo /venv/main/bin/python)
rj() { $SYS_PY -c "import json,sys;d=json.load(open('inputs/small_box_recipe.json'));print(eval(sys.argv[1]))" "$1"; }
IDLE_S=$(rj 'd["idle_seconds"]')
PHASE_MIN_S=$(rj 'd["phase_min_seconds"]')
COURT_SHA=$(rj 'd["weights"]["court_lora"]["adapter_model_sha256"]')
QWEN_COMMIT=$(rj 'd["weights"]["qwen7b"]["commit"]')
PROCS_RE='vllm serve|vllm\.entrypoints|VLLM::|collect_court_conversion|fetch_signed|snapshot_download|pip install|uv pip|uv venv'

# ------------------------------------------------------------------ 0. the deadline and its watchdog
DEADLINE=$($SYS_PY -c 'import json;print(int(json.load(open("inputs/box_choice.json"))["teardown_deadline_unix"]))' 2> /dev/null)
case "$DEADLINE" in ''|*[!0-9]*) say "FATAL no teardown deadline in inputs/box_choice.json"; exit 9 ;; esac
say "teardown deadline $(date -u -d "@$DEADLINE" +%FT%TZ 2> /dev/null || echo "$DEADLINE"), $(( (DEADLINE - $(date +%s)) / 60 )) min away"
stopped() { [ -e "$F/stop" ] || [ "$(date +%s)" -ge "$DEADLINE" ]; }
(
  while :; do
    if [ -e "$F/stop" ] || [ "$(date +%s)" -ge "$DEADLINE" ]; then
      touch "$F/stop"
      say "STOP (deadline or flags/stop): ending every process of ours"
      pkill -TERM -f -- "$PROCS_RE" 2> /dev/null; sleep 20; pkill -KILL -f -- "$PROCS_RE" 2> /dev/null
      exit 0
    fi
    sleep 15
  done
) &
WD=$!

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
stopped && { say "stopped during setup"; exit 19; }

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
  n=$(rj "d['ceiling_cells']['$cell']['samples']")
  for arm in $(rj "' '.join(d['ceiling_cells']['$cell']['arms'])"); do
    extra=""; [ "$arm" = weights ] && extra="--adapter models/court_lora"
    $PY script/pipeline/collect_court_conversion.py --promptset "$PS/$cell" --out "$B/dry/$cell" --arm "$arm" \
      --base Qwen/Qwen2.5-7B-Instruct $extra --samples-per-prompt "$n" --enforce-eager --dry-run \
      >> "$B/dry_runs.log" 2>&1 || { say "dry run $cell $arm failed"; exit 18; }
  done
done
touch "$F/setup.ok"
say "setup ok"

# ------------------------------------------------------------------ 2 and 3. Petri phases
requests() {  # chat requests served so far: the larger of the access-log count and the /metrics counter
  local a m
  a=$(grep -c 'POST /v1/chat/completions' "$VL/vllm_$1.log" 2> /dev/null); a=${a:-0}
  m=$(curl -s --max-time 5 "http://127.0.0.1:$2/metrics" 2> /dev/null \
      | awk '/^vllm:request_success_total/ {s += $NF} END {printf "%d", s + 0}'); m=${m:-0}
  [ "$m" -gt "$a" ] 2> /dev/null && echo "$m" || echo "$a"
}
serve_phase() {
  local name=$1 port=$2
  shift 2
  if [ -e "$F/abort" ] || stopped; then say "abort or stop: Petri phase $name skipped"; return; fi
  if [ $(( DEADLINE - $(date +%s) )) -lt "$PHASE_MIN_S" ]; then
    say "Petri phase $name skipped: fewer than $PHASE_MIN_S s before the deadline"; return
  fi
  /venv/v312/bin/vllm serve "$@" --port "$port" $(rj '" ".join(d["server_args"])') > "$VL/vllm_$name.log" 2>&1 &
  local pid=$! t0
  t0=$(date +%s)
  echo "$pid" > "$B/vllm_$name.pid"
  until curl -sf "http://127.0.0.1:$port/v1/models" > /dev/null; do
    sleep 10
    kill -0 "$pid" 2> /dev/null || { say "server $name died during start"; tail -20 "$VL/vllm_$name.log"; return; }
    if [ $(( $(date +%s) - t0 )) -gt 1200 ] || stopped; then say "server $name not ready (20 min or stop)"; kill "$pid"; return; fi
  done
  touch "$F/$name.ready"
  say "server $name ready on 127.0.0.1:$port"
  local last=0 idle_since n alive
  idle_since=$(date +%s)
  while [ ! -e "$F/$name.done" ] && [ ! -e "$F/abort" ] && ! stopped; do
    n=$(requests "$name" "$port")
    if [ "$n" -gt "$last" ]; then
      last=$n; idle_since=$(date +%s)
      echo "$(date -u +%FT%TZ) $n" >> "$B/heartbeat_$name.tsv"
    fi
    alive=$(stat -c %Y "$F/$name.alive" 2> /dev/null || echo 0)
    [ "$alive" -gt "$idle_since" ] && idle_since=$alive
    if [ $(( $(date +%s) - idle_since )) -gt "$IDLE_S" ]; then say "no chat request and no keepalive for ${IDLE_S}s: phase $name ends"; break; fi
    kill -0 "$pid" 2> /dev/null || { say "server $name died"; break; }
    sleep 30
  done
  kill "$pid" 2> /dev/null; wait "$pid" 2> /dev/null
  sleep 15
  pkill -TERM -f -- 'vllm serve|vllm\.entrypoints|VLLM::' 2> /dev/null; sleep 5
  say "server $name stopped after $last chat requests"
}
serve_phase nsl 8101 /workspace/idt/models/12-mar-gen9-1.5b --served-model-name tgt-a
serve_phase court 8102 Qwen/Qwen2.5-7B-Instruct --served-model-name tgt-base7 --enable-lora \
  --lora-modules tgt-b=/workspace/idt/models/court_lora --max-lora-rank 16

# ------------------------------------------------------------------ 4. court ceiling sampling
for cell in C1 C2 C4 C5; do
  n=$(rj "d['ceiling_cells']['$cell']['samples']")
  for arm in $(rj "' '.join(d['ceiling_cells']['$cell']['arms'])"); do
    if stopped; then say "stop: ceiling $cell $arm not started"; continue; fi
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
