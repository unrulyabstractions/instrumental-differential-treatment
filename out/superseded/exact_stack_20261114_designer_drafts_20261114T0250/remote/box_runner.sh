#!/usr/bin/env bash
# Box side: install base A's engine, fetch the weights byte-verified, sample, and always write the done marker.
#
#   cd /workspace/idt && nohup setsid bash script/remote/auditbench/exact_stack/box_runner.sh < /dev/null &
#
# Started detached by launch_exact_stack.py. Every log and output goes under the box directory
# (recipe box_rel), which maps one to one onto the local repo, so the capture is a plain pull of that
# directory. Stages, each gated on its own exit code (no pipeline decides a status):
#   1. weights: 8 parallel curls of the pre-signed URLs in models/.../_lfs_manifest.tsv, each file checked by
#      size against the manifest, in the background while stage 2 runs
#   2. install: pip install of the recipe pins into /venv/main; torch must stay 2.11.0+cu128 (the image's
#      build, which base A's NCCL 2.28.9 and libcudart.so.13 failure point to), else the cu128 index pins
#   3. versions: vllm 0.26.0 and flashinfer-python 0.6.14 import with base A's LD_LIBRARY_PATH
#   4. sample: sample_exact_stack.py, stdout and stderr to engine.log
# RUNNER_DONE is written on every exit, with the exit code and the stage that ended the run.
set -uo pipefail
R=${EXACT_STACK_ROOT:-/workspace/idt}
cd "$R" || exit 1
RECIPE="$R/script/remote/auditbench/exact_stack/recipe.json"
PY=${EXACT_STACK_PY:-/venv/main/bin/python}
BOX="$R/$($PY -c "import json;print(json.load(open('$RECIPE'))['box_rel'])")"
mkdir -p "$BOX"
STAGE=start
RC=1
finish() {
  printf '%s rc=%s stage=%s\n' "$(date -u +%FT%TZ)" "$RC" "$STAGE" > "$BOX/RUNNER_DONE"
}
trap finish EXIT
exec >> "$BOX/runner.log" 2>&1
say() { echo "$(date -u +%FT%TZ) [box_runner] $*"; }
say "start; box dir $BOX"

# ---- 1. weights, in the background
STAGE=weights
W="$R/models/Llama-3.3-70B-Instruct"
[ -s "$W/_lfs_manifest.tsv" ] || { say "FATAL no manifest at $W"; exit 1; }
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
  mapfile -t rows < _lfs_manifest.tsv
  printf "%s\n" "${rows[@]}" | xargs -d "\n" -P 8 -I{} bash -c 'fetch_one "$@"' _ {}
  echo "FETCH_XARGS_RC=$?"
}
fetch_all > "$BOX/fetch_base.log" 2>&1 &
FETCH_PID=$!
say "weights fetch started (pid $FETCH_PID, $ROWS manifest rows)"

# ---- 2. install
STAGE=install
read -r -a PINS <<< "$($PY -c "import json;print(' '.join(json.load(open('$RECIPE'))['engine']['pip_install']))")"
say "pip install ${PINS[*]}"
$PY -m pip install "${PINS[@]}" > "$BOX/install.log" 2>&1
IRC=$?
[ "$IRC" = 0 ] || { say "FATAL pip install exited $IRC"; RC=10; exit 10; }
TV=$($PY -c "import importlib.metadata as m;print(m.version('torch'))")
WANT=$($PY -c "import json;print(json.load(open('$RECIPE'))['engine']['torch_expected'])")
if [ "$TV" != "$WANT" ]; then
  say "torch is $TV, not $WANT: installing the cu128 pins"
  read -r -a TP <<< "$($PY -c "import json;print(' '.join(json.load(open('$RECIPE'))['engine']['torch_fallback_pins']))")"
  IDX=$($PY -c "import json;print(json.load(open('$RECIPE'))['engine']['torch_fallback_index'])")
  $PY -m pip install "${TP[@]}" --index-url "$IDX" >> "$BOX/install.log" 2>&1 || { say "FATAL torch pin failed"; RC=11; exit 11; }
fi
$PY -m pip freeze > "$BOX/pip_freeze.txt" 2>&1

# ---- 3. versions, with base A's library path
STAGE=versions
SITE=$($PY -c "import sysconfig;print(sysconfig.get_paths()['purelib'])")
export LD_LIBRARY_PATH="$SITE/nvidia/cu13/lib:${LD_LIBRARY_PATH:-}"
export PYTHONPATH="$R"
export VLLM_WORKER_MULTIPROC_METHOD=spawn
$PY - > "$BOX/versions.txt" 2>&1 <<'EOF'
import importlib.metadata as m, platform
import vllm, torch
print("VERSIONS", "python", platform.python_version(), "vllm", vllm.__version__, "torch", torch.__version__,
      "torch_cuda", torch.version.cuda, "flashinfer", m.version("flashinfer-python"),
      "transformers", m.version("transformers"), "tokenizers", m.version("tokenizers"))
EOF
VRC=$?
cat "$BOX/versions.txt" | tail -1
[ "$VRC" = 0 ] || { say "FATAL vllm import failed"; RC=12; exit 12; }
grep -q "^VERSIONS python 3\.12\.[0-9]* vllm 0\.26\.0 torch " "$BOX/versions.txt" \
  || { say "FATAL wrong python or vllm"; RC=13; exit 13; }
grep -q " flashinfer 0\.6\.14 " "$BOX/versions.txt" || { say "FATAL wrong flashinfer"; RC=14; exit 14; }
nvidia-smi --query-gpu=name,memory.total,driver_version,power.limit --format=csv > "$BOX/gpus.csv" 2>&1
nvidia-smi > "$BOX/nvidia_smi.txt" 2>&1

# ---- wait for the weights
STAGE=weights_wait
wait "$FETCH_PID"
OK=$(grep -c '^ok \|^have ' "$BOX/fetch_base.log")
BAD=$(grep -c 'FAIL\|SIZE_MISMATCH' "$BOX/fetch_base.log")
say "weights: $OK ok of $ROWS, $BAD failed"
[ "$OK" = "$ROWS" ] && [ "$BAD" = 0 ] || { say "FATAL weight fetch incomplete"; RC=20; exit 20; }
BYTES=$(cd "$W" && cut -f1 _lfs_manifest.tsv | xargs stat -c%s | awk '{s+=$1} END {print s}')
WANTB=$($PY -c "import json;print(json.load(open('$RECIPE'))['weights']['lfs_bytes'])")
[ "$BYTES" = "$WANTB" ] || { say "FATAL weight bytes $BYTES != $WANTB"; RC=21; exit 21; }

# ---- 4. sample
STAGE=sample
say "sampling (LD_LIBRARY_PATH starts with $SITE/nvidia/cu13/lib)"
$PY script/remote/auditbench/exact_stack/sample_exact_stack.py > "$BOX/engine.log" 2>&1
SRC=$?
say "sample_exact_stack.py exited $SRC"
RC=$SRC
STAGE="done"
exit "$SRC"
