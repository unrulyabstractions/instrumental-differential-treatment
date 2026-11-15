#!/usr/bin/env bash
# Capture and destroy the exact-stack box, only through the repo's proven adapter, then locate A2's files.
#
#   bash script/remote/auditbench/exact_stack/teardown_exact_stack.sh <instance id>          # runner has ended
#   bash script/remote/auditbench/exact_stack/teardown_exact_stack.sh <instance id> --stop   # past the deadline
#
# 1. --stop only: checks /root/box_id names the id, stops our processes on the box (the runner's process group by pid,
#    TERM then KILL, then a pattern sweep of leftovers on this dedicated box), and waits
#    up to 60 s for the runner's RUNNER_DONE marker. Nothing is deleted on the box.
# 2. Runs .claude/box_teardown.sh vast <id> and reads its exit code directly. That adapter refuses unless the box
#    names the id, nothing of ours produces, the account lists the id under our label, verify_remote_capture.py
#    exits 0 over /workspace and /root (no extension filter; weights, venvs and caches exempt) and a per-file
#    byte-size proof finds every swept file with a same-size local copy. It then stages the capture with
#    git add -f, destroys, confirms the id gone from two complete listings, marks boxes.json and appends to
#    VERIFICATION_LOG.md. Any refusal leaves the box running: fix the cause and rerun this script.
# 3. After a destroy: stages boxes.json, inputs/box_choice.json and launch/ with git add -f (out/ is gitignored).
#    A rehearsal box ends here. For the A2 box it finds the captured box directory, counts rows, and writes
#    a2_location_<id>.json (new file), which the analysis scripts read to find A2's responses, engine log and
#    provenance. Complete means 3,456 rows and provenance.json with the runner's rc=0, the sampler's own
#    SAMPLER_DONE.json rc 0, or provenance.json's 3,456 rows with none failed (a runner stopped while it lingered).
# The watcher (watch_exact_stack.py) runs this script itself; by hand only when the watcher is dead.
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
# By pid first: the runner's own process group (setsid at start; its pid is in the start lock). TERM lets the
# runner's EXIT trap write RUNNER_DONE. The pattern kill after it only sweeps leftovers on this dedicated box.
RP=\$(cat $REMOTE/.exact_stack_runner.lock/pid 2>/dev/null)
PG=\$(ps -o pgid= -p "\$RP" 2>/dev/null | tr -d ' ')
echo "ES RUNNER_PID \${RP:-none} PGID \${PG:-none}"
if [ -n "\$PG" ]; then kill -TERM -- "-\$PG" 2>/dev/null; for i in 1 2 3 4 5 6; do kill -0 "\$RP" 2>/dev/null || break; sleep 5; done; kill -KILL -- "-\$PG" 2>/dev/null; fi
pkill -TERM -f 'exact_stack|VLLM::|fetch_one|pip install|uv pip|curl -fsSL' 2>/dev/null; sleep 10
pkill -KILL -f 'exact_stack|VLLM::|fetch_one|pip install|uv pip|curl -fsSL' 2>/dev/null
for i in 1 2 3 4 5 6; do [ -e $REMOTE/$BOXREL/RUNNER_DONE ] && break; sleep 10; done
echo "ES DONE \$(cat $REMOTE/$BOXREL/RUNNER_DONE 2>/dev/null || echo none)"
echo "ES PROCS \$(pgrep -fc 'exact_stack|VLLM::' 2>/dev/null)"
EOF
)
  printf '%s\n' "$out" | sed 's/^ES //'
  printf '%s\n' "$out" | grep -q "^ES BOXID $ID\$" || { say "REFUSED: /root/box_id does not name $ID"; exit 1; }
  say "stopped our processes on $ID (nothing deleted)"
fi

REHEARSAL=$(python3 - "$OUT/boxes.json" "$ID" <<'EOF'
import json, sys
b = [x for x in json.load(open(sys.argv[1]))["boxes"] if str(x.get("id")) == sys.argv[2]]
print(int(bool(b and b[-1].get("rehearsal"))))
EOF
)
say "running .claude/box_teardown.sh vast $ID (rehearsal=$REHEARSAL)"
bash .claude/box_teardown.sh vast "$ID"
TRC=$?
say "box_teardown.sh exited $TRC"
if [ "$TRC" -ne 0 ]; then
  say "NOT destroyed or not confirmed: read the adapter's log under $OUT/capture/vast_$ID/; the box may still bill"
  exit 1
fi
# out/ is gitignored: the registry, the box choice and the launcher's records are made tracked here, with the
# capture box_teardown.sh staged. Nothing is committed here; the session commits only its own paths.
for p in "$OUT/boxes.json" "$OUT/inputs/box_choice.json" "$OUT/launch"; do
  [ -e "$p" ] && { git add -f -- "$p" && say "staged $p" || say "!! could not stage $p"; }
done
if [ "$REHEARSAL" = 1 ]; then
  say "rehearsal box destroyed; next: launch_exact_stack.py --rehearse-report $ID"
  exit 0
fi

python3 - "$ROOT" "$OUT" "$BOXREL" "$REMOTE" "$ID" <<'EOF'
import json, os, sys, time
root, out, boxrel, remote, iid = sys.argv[1:6]
d = os.path.join(root, out, "capture", f"vast_{iid}", "files", remote.lstrip("/"), boxrel)
loc = os.path.join(root, out, f"a2_location_{iid}.json")
have = {n: os.path.isfile(os.path.join(d, n)) for n in
        ("RUNNER_DONE", "SAMPLER_DONE.json", "runner.log", "engine.log", "stack_check.json", "provenance.json",
         "responses_base.jsonl", "progress.log", "pip_freeze.txt", "versions.txt", "env.txt",
         "import_without_cu13_path.txt")}
rows = sum(1 for _ in open(os.path.join(d, "responses_base.jsonl"))) if have["responses_base.jsonl"] else 0
done = open(os.path.join(d, "RUNNER_DONE")).read().strip() if have["RUNNER_DONE"] else None
sdone = json.load(open(os.path.join(d, "SAMPLER_DONE.json"))) if have["SAMPLER_DONE.json"] else None
prov = json.load(open(os.path.join(d, "provenance.json"))) if have["provenance.json"] else {}
# Complete: 3,456 rows and provenance.json, with the runner's rc=0, or the sampler's own SAMPLER_DONE rc 0, or
# provenance.json's own 3,456 rows with none failed (the sampler's rc 0 condition). The last two cover a runner
# stopped with --stop while it lingered after a finished draw.
complete = rows == 3456 and have["provenance.json"] and (
    "rc=0" in (done or "") or (sdone is not None and sdone.get("rc") == 0 and sdone.get("rows") == 3456)
    or (prov.get("n_rows") == 3456 and prov.get("failed_rows") == 0))
rec = {"instance": int(iid), "box_dir": os.path.relpath(d, root), "files_present": have, "rows": rows,
       "runner_done": done, "sampler_done": sdone, "complete": bool(complete),
       "written_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
with open(loc, "x") as fh:
    json.dump(rec, fh, indent=1)
print(json.dumps(rec, indent=1))
print(f"wrote {os.path.relpath(loc, root)}")
if not complete:
    print("A2 IS NOT COMPLETE: no gate, no judging; report the runner's stage and log")
    sys.exit(3)
EOF
LRC=$?
git add -f -- "$OUT/a2_location_$ID.json" 2>/dev/null && say "staged $OUT/a2_location_$ID.json"
say "A2 location check exited $LRC (0: complete, run g01_gate.py run next; 3: incomplete, stop and report)"
exit $LRC
