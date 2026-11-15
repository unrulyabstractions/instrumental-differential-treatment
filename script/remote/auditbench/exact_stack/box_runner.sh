#!/usr/bin/env bash
# Box side: install base A's engine, fetch the weights byte-verified, sample, and always write the done marker.
#
#   cd /workspace/idt && nohup setsid bash script/remote/auditbench/exact_stack/box_runner.sh < /dev/null &
#
# Started detached by launch_exact_stack.py. Every log and output goes under the box directory (recipe box_rel),
# which maps one to one onto the local repo. Stages, each gated on its own exit code (no pipeline decides a status):
#   1. weights: 8 parallel curls of the pre-signed URLs in models/.../_lfs_manifest.tsv, each file checked by size
#      against the manifest, in the background while stages 2 and 3 run
#   2. env: base A's /venv/main when its python is 3.12, else a uv-built 3.12 env (recorded deviation)
#   3. install: torch 2.11.0+cu128 (and its torchvision, torchaudio) from the cu128 index unless already exact,
#      then vllm 0.26.0, transformers 5.14.1, tokenizers 0.23.1; pip freeze kept
#   4. versions: vllm 0.26.0, flashinfer-python 0.6.14, torch 2.11.0+cu128, python 3.12 import with base A's
#      library path. Recorded, not a stop: whether the import fails WITHOUT that path on libcudart.so.13, as
#      base A's install log did (the fingerprint of a cu128 torch under a cu13 vllm build)
#   5. sample: sample_exact_stack.py, stdout and stderr to engine.log; it stops itself before sampling on any
#      stack mismatch in the engine's own init log, and during sampling when its projection passes the cap
# RUNNER_DONE is written on every exit, with the exit code and the stage that ended the run.
set -uo pipefail
R=${EXACT_STACK_ROOT:-/workspace/idt}
cd "$R" || exit 1
RECIPE="$R/script/remote/auditbench/exact_stack/recipe.json"
SYSPY=python3
command -v "$SYSPY" > /dev/null 2>&1 || SYSPY=/venv/main/bin/python
jq_() { "$SYSPY" -c "import json,sys;d=json.load(open('$RECIPE'));print(eval(sys.argv[1]))" "$1"; }
BOX="$R/$(jq_ "d['box_rel']")"
mkdir -p "$BOX"
STAGE=start
RC=1
finish() {
  # An early stop must leave nothing of ours running, or the box would look busy while it idles.
  if [ -n "${FETCH_PID:-}" ]; then kill "$FETCH_PID" 2>/dev/null; pkill -f 'fetch_one' 2>/dev/null; fi
  pkill -f 'VLLM::' 2>/dev/null
  printf '%s rc=%s stage=%s\n' "$(date -u +%FT%TZ)" "$RC" "$STAGE" > "$BOX/RUNNER_DONE"
}
trap finish EXIT
exec >> "$BOX/runner.log" 2>&1
say() { echo "$(date -u +%FT%TZ) [box_runner] $*"; }
say "start; box dir $BOX"
[ -s "$R/$(jq_ "d['out_rel']")/inputs/box_choice.json" ] || { say "FATAL no inputs/box_choice.json"; RC=2; exit 2; }

# ---- 1. weights, in the background
STAGE=weights
W="$R/models/Llama-3.3-70B-Instruct"
[ -s "$W/_lfs_manifest.tsv" ] || { say "FATAL no manifest at $W"; RC=3; exit 3; }
ROWS=$(grep -c '' "$W/_lfs_manifest.tsv")
fetch_all() {
  cd "$W" || return 1
  fetch_one() {
    IFS=$'\t' read -r p s u <<< "$1"
    mkdir -p "$(dirname "$p")"
    if [ -f "$p" ] && [ "$(stat -c%s "$p")" = "$s" ]; then echo "have $p"; return 0; fi
    curl -fsSL --retry 5 --retry-delay 5 -o "$p" "$u" || { echo "FAIL $p"; return 1; }
    got=$(stat -c%s "$p"); [ "$got" = "$s" ] || { echo "SIZE_MISMATCH $p $got != $s"; return 1; }
    echo "ok $p ($got bytes)"
  }
  export -f fetch_one
  grep -v '^$' _lfs_manifest.tsv | xargs -d "\n" -P 8 -I{} bash -c 'fetch_one "$@"' _ {}
  echo "FETCH_XARGS_RC=$?"
}
fetch_all > "$BOX/fetch_base.log" 2>&1 &
FETCH_PID=$!
say "weights fetch started (pid $FETCH_PID, $ROWS manifest rows)"

# ---- 2. env
STAGE=env
MAIN=$(jq_ "d['engine']['env_main']")
FALLBACK=$(jq_ "d['engine']['env_fallback']")
WANTPY=$(jq_ "d['engine']['python']")
MAINV=$("$MAIN/bin/python" -c 'import platform;print(platform.python_version())' 2>/dev/null)
echo "image /venv/main python: ${MAINV:-none}" > "$BOX/env.txt"
"$MAIN/bin/python" -c 'import importlib.metadata as m;print("image torch:", m.version("torch"))' >> "$BOX/env.txt" 2>&1
case "$MAINV" in
  "$WANTPY".*) ENV=$MAIN; echo "env: $MAIN (base A's)" >> "$BOX/env.txt" ;;
  *)
    say "DEVIATION: /venv/main python is '${MAINV:-none}', not $WANTPY.x; building $FALLBACK with uv"
    "$MAIN/bin/python" -m pip install -q uv > "$BOX/uv_install.log" 2>&1 || { say "FATAL uv install failed"; RC=5; exit 5; }
    "$MAIN/bin/python" -m uv venv --python "$WANTPY" --seed "$FALLBACK" >> "$BOX/uv_install.log" 2>&1 \
      || { say "FATAL uv venv failed"; RC=6; exit 6; }
    ENV=$FALLBACK; echo "env: $FALLBACK (DEVIATION: built with uv)" >> "$BOX/env.txt" ;;
esac
PY="$ENV/bin/python"
"$PY" -c 'import platform;print("env python:", platform.python_version())' >> "$BOX/env.txt" 2>&1
cat "$BOX/env.txt"

# ---- 3. install
STAGE=install
TWANT=$(jq_ "d['engine']['torch_expected']")
TV=$("$PY" -c 'import importlib.metadata as m;print(m.version("torch"))' 2>/dev/null)
if [ "$TV" != "$TWANT" ]; then
  read -r -a TP <<< "$(jq_ "' '.join(d['engine']['torch_pins'])")"
  IDX=$(jq_ "d['engine']['torch_index']")
  say "torch is '${TV:-absent}', not $TWANT: installing ${TP[*]} from $IDX first"
  "$PY" -m pip install "${TP[@]}" --index-url "$IDX" > "$BOX/install_torch.log" 2>&1 \
    || { say "FATAL torch pin failed"; RC=10; exit 10; }
else
  say "torch is already $TWANT (base A's build): pip keeps it"
fi
read -r -a PINS <<< "$(jq_ "' '.join(d['engine']['pip_install'])")"
say "pip install ${PINS[*]}"
"$PY" -m pip install "${PINS[@]}" > "$BOX/install.log" 2>&1
IRC=$?
[ "$IRC" = 0 ] || { say "FATAL pip install exited $IRC"; RC=11; exit 11; }
SITE=$("$PY" -c "import sysconfig;print(sysconfig.get_paths()['purelib'])")
if ! ls "$SITE"/nvidia/cu13/lib/libcudart.so.13* > /dev/null 2>&1; then
  # Base A's run found libcudart.so.13 there (run_collect.sh's path). vLLM 0.26.0 was built on torch 2.11.0's
  # CUDA 13.0.2 toolkit pin, so that is the runtime added when no dependency brought one.
  say "DEVIATION: no libcudart.so.13 under $SITE/nvidia/cu13/lib after the install; adding cuda-toolkit[cudart]==13.0.2"
  "$PY" -m pip install "cuda-toolkit[cudart]==13.0.2" >> "$BOX/install.log" 2>&1 \
    || { say "FATAL cuda 13 runtime install failed"; RC=14; exit 14; }
  echo "DEVIATION cuda-toolkit[cudart]==13.0.2 added" >> "$BOX/env.txt"
fi
"$PY" -m pip freeze > "$BOX/pip_freeze.txt" 2>&1

# ---- 4. versions, first without and then with base A's library path
STAGE=versions
env -u LD_LIBRARY_PATH "$PY" -c "import vllm" > "$BOX/import_without_cu13_path.txt" 2>&1
echo "IMPORT_WITHOUT_CU13_PATH_RC=$?" >> "$BOX/import_without_cu13_path.txt"
tail -2 "$BOX/import_without_cu13_path.txt"
export LD_LIBRARY_PATH="$SITE/nvidia/cu13/lib:${LD_LIBRARY_PATH:-}"
export PYTHONPATH="$R"
export VLLM_WORKER_MULTIPROC_METHOD=spawn
"$PY" - > "$BOX/versions.txt" 2>&1 <<'EOF'
import importlib.metadata as m, platform
import vllm, torch
print("VERSIONS", "python", platform.python_version(), "vllm", vllm.__version__, "torch", torch.__version__,
      "torch_cuda", torch.version.cuda, "flashinfer", m.version("flashinfer-python"),
      "transformers", m.version("transformers"), "tokenizers", m.version("tokenizers"))
EOF
VRC=$?
tail -1 "$BOX/versions.txt"
[ "$VRC" = 0 ] || { say "FATAL vllm import failed"; RC=12; exit 12; }
grep -q "^VERSIONS python 3\.12\.[0-9]* vllm 0\.26\.0 torch 2\.11\.0+cu128 torch_cuda 12\.8 flashinfer 0\.6\.14 " \
  "$BOX/versions.txt" || { say "FATAL python, vllm, torch or flashinfer differs from the recipe"; RC=13; exit 13; }
nvidia-smi --query-gpu=name,memory.total,driver_version,power.limit,clocks.max.sm --format=csv > "$BOX/gpus.csv" 2>&1
nvidia-smi > "$BOX/nvidia_smi.txt" 2>&1
nvidia-smi topo -m > "$BOX/nvidia_topo.txt" 2>&1
lscpu > "$BOX/lscpu.txt" 2>&1

# ---- wait for the weights
STAGE=weights_wait
wait "$FETCH_PID"
OK=$(grep -c '^ok \|^have ' "$BOX/fetch_base.log")
BAD=$(grep -c 'FAIL\|SIZE_MISMATCH' "$BOX/fetch_base.log")
say "weights: $OK ok of $ROWS, $BAD failed"
if [ "$OK" != "$ROWS" ] || [ "$BAD" != 0 ]; then say "FATAL weight fetch incomplete"; RC=20; exit 20; fi
BYTES=$(cd "$W" && cut -f1 _lfs_manifest.tsv | grep -v '^$' | xargs stat -c%s | awk '{s+=$1} END {print s}')
WANTB=$(jq_ "d['weights']['lfs_bytes']")
[ "$BYTES" = "$WANTB" ] || { say "FATAL weight bytes $BYTES != $WANTB"; RC=21; exit 21; }

# ---- 5. sample
STAGE=sample
say "sampling with $PY (LD_LIBRARY_PATH starts with $SITE/nvidia/cu13/lib)"
"$PY" script/remote/auditbench/exact_stack/sample_exact_stack.py > "$BOX/engine.log" 2>&1
SRC=$?
say "sample_exact_stack.py exited $SRC"
RC=$SRC
STAGE="done"
exit "$SRC"
