#!/usr/bin/env bash
# Capture and destroy the exact-stack box, only through the repo's proven adapter, then locate A2's files.
#
#   bash script/remote/auditbench/exact_stack/teardown_exact_stack.sh <instance id>          # runner has ended
#   bash script/remote/auditbench/exact_stack/teardown_exact_stack.sh <instance id> --stop   # past the deadline
#
# 1. --stop only: checks /root/box_id names the id, stops our processes on the box (TERM, then KILL), and waits
#    up to 60 s for the runner's RUNNER_DONE marker. Nothing is deleted on the box.
# 2. Runs .claude/box_teardown.sh vast <id> and reads its exit code directly. That adapter refuses unless the box
#    names the id, nothing of ours produces, the account lists the id under our label, verify_remote_capture.py
#    exits 0 over /workspace and /root (no extension filter; weights, venvs and caches exempt) and a per-file
#    byte-size proof finds every swept file with a same-size local copy. It then stages the capture with
#    git add -f, destroys, confirms the id gone from two complete listings, marks boxes.json and appends to
#    VERIFICATION_LOG.md. Any refusal leaves the box running: fix the cause and rerun this script.
# 3. After a destroy: finds the captured box directory, counts rows, and writes a2_location.json (new file),
#    which the analysis scripts read to find A2's responses, engine log and provenance.
# Bash 3.2 (the Mac's /bin/bash).
set -u
ID=${1:?usage: teardown_exact_stack.sh <instance id> [--stop]}
MODE=${2:-}
case "$ID" in ''|*[!0-9]*) echo "FATAL bad id $ID"; exit 2 ;; esac
cd "$(dirname "$0")/../../../.." || exit 1
ROOT=$(pwd -P)
RECIPE=script/remote/auditbench/exact_stack/recipe.json
OUT=$(python3 -c "import json;print(json.load(open('$RECIPE'))['out_rel'])")
BOXREL=$(python3 -c "import json;print(json.load(open('$RECIPE'))['box_rel'])")
REMOTE=$(python3 -c "import json;print(json.load(open('$RECIPE'))['remote_root'])")
say() { echo "$(date -u +%FT%TZ) [teardown_exact_stack $ID] $*"; }

if [ "$MODE" = "--stop" ]; then
  read -r HOST PORT <<< "$(python3 - "$OUT/boxes.json" "$ID" <<'EOF'
import json, sys
b = [x for x in json.load(open(sys.argv[1]))["boxes"] if str(x.get("id")) == sys.argv[2] and not x.get("destroyed")]
if b:
    print(b[-1]["host"], b[-1]["port"])
EOF
)"
  [ -n "${HOST:-}" ] || { say "REFUSED: $ID is not a live box in $OUT/boxes.json"; exit 1; }
  SSHC="ssh -F /dev/null -i $HOME/.ssh/id_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=20 -o BatchMode=yes -p $PORT"
  out=$(bash -c "$SSHC root@$HOST 'bash -s'" 2>/dev/null <<EOF | grep '^ES '
got=\$(tr -d '[:space:]' < /root/box_id 2>/dev/null)
echo "ES BOXID \${got:-none}"
[ "\$got" = "$ID" ] || exit 0
pkill -TERM -f 'exact_stack|VLLM::|fetch_one|pip install' 2>/dev/null; sleep 20
pkill -KILL -f 'exact_stack|VLLM::|fetch_one|pip install' 2>/dev/null
for i in 1 2 3 4 5 6; do [ -e $REMOTE/$BOXREL/RUNNER_DONE ] && break; sleep 10; done
echo "ES DONE \$(cat $REMOTE/$BOXREL/RUNNER_DONE 2>/dev/null || echo none)"
echo "ES PROCS \$(pgrep -fc 'exact_stack|VLLM::' 2>/dev/null)"
EOF
)
  printf '%s\n' "$out" | sed 's/^ES //'
  printf '%s\n' "$out" | grep -q "^ES BOXID $ID\$" || { say "REFUSED: /root/box_id does not name $ID"; exit 1; }
  say "stopped our processes on $ID (nothing deleted)"
fi

say "running .claude/box_teardown.sh vast $ID"
bash .claude/box_teardown.sh vast "$ID"
TRC=$?
say "box_teardown.sh exited $TRC"
if [ "$TRC" -ne 0 ]; then
  say "NOT destroyed or not confirmed: read the adapter's log under $OUT/capture/vast_$ID/; the box may still bill"
  exit 1
fi

python3 - "$ROOT" "$OUT" "$BOXREL" "$REMOTE" "$ID" <<'EOF'
import json, os, sys, time
root, out, boxrel, remote, iid = sys.argv[1:6]
d = os.path.join(root, out, "capture", f"vast_{iid}", "files", remote.lstrip("/"), boxrel)
loc = os.path.join(root, out, f"a2_location_{iid}.json")
have = {n: os.path.isfile(os.path.join(d, n)) for n in
        ("RUNNER_DONE", "runner.log", "engine.log", "stack_check.json", "provenance.json", "responses_base.jsonl",
         "progress.log", "pip_freeze.txt", "versions.txt", "env.txt", "import_without_cu13_path.txt")}
rows = sum(1 for _ in open(os.path.join(d, "responses_base.jsonl"))) if have["responses_base.jsonl"] else 0
done = open(os.path.join(d, "RUNNER_DONE")).read().strip() if have["RUNNER_DONE"] else None
rec = {"instance": int(iid), "box_dir": os.path.relpath(d, root), "files_present": have, "rows": rows,
       "runner_done": done, "written_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
with open(loc, "x") as fh:
    json.dump(rec, fh, indent=1)
print(json.dumps(rec, indent=1))
print(f"wrote {os.path.relpath(loc, root)}")
if rows != 3456 or not (done or "").count("rc=0"):
    print("A2 IS NOT COMPLETE: no gate, no judging; report the runner's stage and log")
    sys.exit(3)
EOF
LRC=$?
say "A2 location check exited $LRC (0: complete, run g01_gate.py run next; 3: incomplete, stop and report)"
exit $LRC
