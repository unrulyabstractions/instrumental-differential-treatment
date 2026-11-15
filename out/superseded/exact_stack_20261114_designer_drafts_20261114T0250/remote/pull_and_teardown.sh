#!/usr/bin/env bash
# Pull the exact-stack box's outputs, prove every remote file is captured, and destroy only on that proof.
#
#   bash script/remote/auditbench/exact_stack/pull_and_teardown.sh pull <instance id>      # pull only
#   bash script/remote/auditbench/exact_stack/pull_and_teardown.sh check <instance id>     # pull + capture gate
#   bash script/remote/auditbench/exact_stack/pull_and_teardown.sh destroy <instance id>   # pull + gate + destroy
#
# The cloud-box guard calls `.claude/box_teardown.sh vast <id>`; that file is the two-line wrapper
#   [ "$1" = vast ] || exit 2
#   exec bash "$(dirname "$0")/../script/remote/auditbench/exact_stack/pull_and_teardown.sh" destroy "$2"
# and must exit 0 only after a proven capture and a destroy.
#
# Refusals, each before anything is destroyed:
#   * the id is not in boxes.json (out/main/auditbench/nullext/exact_stack_20261114/boxes.json), or is marked
#     destroyed there, or its label does not start with idt-exact-stack;
#   * the id is not in tmp/r2_my_instances.txt, re-read at the moment of destruction;
#   * the pull fails;
#   * script/remote/capture/verify_remote_capture.py exits non-zero. It sweeps every file under /workspace/idt,
#     /workspace and /root (no extension filter; only the staged weights under /workspace/idt/models, venvs,
#     site-packages, __pycache__ and the box caches are exempt), compares BYTE SIZES with the local copies,
#     rescues strays into out/rescued/<label>-<id> verified by size, and exits 1 on any file still uncaptured.
#     Its exit code is read directly, never through a pipe.
# The destroy is confirmed by querying that one instance twice; `vastai destroy` exits 0 even when it fails.
set -u
MODE=${1:?usage: pull_and_teardown.sh <pull|check|destroy> <instance id>}
ID=${2:?usage: pull_and_teardown.sh <pull|check|destroy> <instance id>}
case "$MODE" in pull|check|destroy) ;; *) echo "FATAL unknown mode $MODE"; exit 2 ;; esac
case "$ID" in ''|*[!0-9]*) echo "FATAL bad id $ID"; exit 2 ;; esac
cd "$(dirname "$0")/../../../.." || exit 1
RECIPE=script/remote/auditbench/exact_stack/recipe.json
OUT=$(python3 -c "import json;print(json.load(open('$RECIPE'))['out_rel'])")
BOXREL=$(python3 -c "import json;print(json.load(open('$RECIPE'))['box_rel'])")
REMOTE=$(python3 -c "import json;print(json.load(open('$RECIPE'))['remote_root'])")
# Overrides exist for the refusal tests only.
BOXES=${EXACT_STACK_BOXES:-$OUT/boxes.json}
REG=tmp/r2_my_instances.txt
CAPDIR=${EXACT_STACK_CAPTURE_DIR:-$OUT/capture}
mkdir -p "$CAPDIR"
LOG="$CAPDIR/teardown_${ID}_$(date -u +%Y%m%dT%H%M%SZ).log"
say() { echo "$(date -u +%FT%TZ) [pull_and_teardown $MODE $ID] $*" | tee -a "$LOG"; }

entry=$(python3 - "$BOXES" "$ID" <<'EOF'
import json, sys
try:
    boxes = json.load(open(sys.argv[1]))["boxes"]
except Exception as exc:
    print(f"ERR boxes.json unreadable: {exc}"); sys.exit(0)
b = [x for x in boxes if str(x.get("id")) == sys.argv[2]]
if not b:
    print("ERR id not in boxes.json"); sys.exit(0)
b = b[-1]
if b.get("destroyed"):
    print("ERR marked destroyed in boxes.json"); sys.exit(0)
if not str(b.get("label", "")).startswith("idt-exact-stack"):
    print(f"ERR label {b.get('label')!r} is not idt-exact-stack*"); sys.exit(0)
if not b.get("host") or not b.get("port"):
    print("ERR no endpoint recorded"); sys.exit(0)
print("OK", b["host"], b["port"], b["label"])
EOF
)
set -- $entry
if [ "${1:-}" != OK ]; then say "REFUSED: ${entry}"; exit 1; fi
HOST=$2; PORT=$3; LABEL=$4
SSHC="ssh -F /dev/null -i $HOME/.ssh/id_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=20 -o BatchMode=yes -p $PORT"

# The box must be the one we think it is.
GOT=$(bash -c "$SSHC root@$HOST 'cat /root/box_id'" 2>/dev/null | tr -dc 0-9)
if [ "$GOT" != "$ID" ]; then say "REFUSED: /root/box_id on $HOST:$PORT says '${GOT}', not $ID"; exit 1; fi

say "pulling $REMOTE/$BOXREL/ -> $BOXREL/"
mkdir -p "$BOXREL"
rsync -az --timeout=120 -e "$SSHC" "root@$HOST:$REMOTE/$BOXREL/" "$BOXREL/" >> "$LOG" 2>&1
PRC=$?
if [ "$PRC" -ne 0 ]; then say "REFUSED: pull exited $PRC"; exit 1; fi
say "pulled: $(find "$BOXREL" -type f | wc -l | tr -d ' ') files, $(du -sk "$BOXREL" | cut -f1) KiB"
[ "$MODE" = pull ] && exit 0

say "capture gate (verify_remote_capture.py)"
.venv/bin/python script/remote/capture/verify_remote_capture.py --host "$HOST" --port "$PORT" \
  --remote-root "$REMOTE" \
  --pushed-from-local src/ --pushed-from-local script/ --pushed-from-local configs/ \
  --pushed-from-local pyproject.toml \
  --pushed-from-local out/main/auditbench/contextual_optimism/promptset/ \
  --pushed-from-local "$OUT/inputs/" \
  --rescue-to "out/rescued/${LABEL}-${ID}" >> "$LOG" 2>&1
GATE=$?
tail -25 "$LOG"
say "gate exit=$GATE"
if [ "$GATE" -ne 0 ]; then say "NOT destroying: the gate found uncaptured files"; exit 1; fi
[ "$MODE" = check ] && { say "check mode: gate passed, nothing destroyed"; exit 0; }

if ! grep -q "^${ID} " "$REG"; then say "REFUSED: $ID is not in $REG"; exit 1; fi
say "gate passed; destroying $ID"
vastai destroy instance "$ID" --yes >> "$LOG" 2>&1
gone=0
for _ in 1 2 3 4 5 6; do
  sleep 10
  out=$(vastai show instance "$ID" --raw 2>/dev/null)
  if [ -z "$out" ]; then
    sleep 5
    out=$(vastai show instance "$ID" --raw 2>/dev/null)
    if [ -z "$out" ]; then gone=1; break; fi
  fi
done
if [ "$gone" -ne 1 ]; then say "!! $ID still answers after destroy; CHECK BY HAND"; exit 1; fi
python3 - "$BOXES" "$ID" <<'EOF'
import json, os, sys, time
p, i = sys.argv[1], sys.argv[2]
d = json.load(open(p))
for b in d["boxes"]:
    if str(b.get("id")) == i:
        b["destroyed"] = True
        b["destroyed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
tmp = p + ".tmp"
json.dump(d, open(tmp, "w"), indent=1)
os.replace(tmp, p)
EOF
say "instance $ID confirmed gone; boxes.json marked destroyed"
exit 0
