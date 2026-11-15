#!/usr/bin/env bash
# Read-only status of an exact-stack box, for the watcher (every 60 s), the 20-minute owner report (B59) and the
# 40-minute verifier (B61).
#
#   bash script/remote/auditbench/exact_stack/status_exact_stack.sh <instance id>
#
# Prints: minutes since create, cost so far at the live rate, minutes left to the teardown deadline (the cap less
# the capture reserve, from boxes.json), live vast credit, whether the watcher runs, the runner's stage, weight bytes
# on disk against the manifest, the newest progress line (written only when the engine's counters move, or from GPU
# use when they cannot be read), GPU utilisation, rows, and one MACHINE line of JSON that the watcher reads.
# Never writes on the box.
# Exit 0 running; 3 past the teardown deadline (teardown_exact_stack.sh <id> --stop now); 4 the runner ended, with
# or without rows (the box is idle: teardown_exact_stack.sh <id> in this step); 5 the sampler wrote a complete draw
# and provenance.json (SAMPLER_DONE.json too, unless the sampler hung before it) but the runner has not ended
# within watch.linger_after_sampler_done_minutes
# (teardown_exact_stack.sh <id> --stop); 1 unreachable or unregistered.
set -u
ID=${1:?usage: status_exact_stack.sh <instance id>}
cd "$(dirname "$0")/../../../.." || exit 1
RECIPE=script/remote/auditbench/exact_stack/recipe.json
OUT=$(python3 -c "import json;print(json.load(open('$RECIPE'))['out_rel'])")
LINGER_S=$(python3 -c "import json;print(int(60 * json.load(open('$RECIPE'))['watch']['linger_after_sampler_done_minutes']))")
read -r HOST PORT CREATED DPH DEADLINE TP <<< "$(python3 - "$OUT/boxes.json" "$ID" <<'EOF'
import json, sys
b = [x for x in json.load(open(sys.argv[1]))["boxes"] if str(x.get("id")) == sys.argv[2] and not x.get("destroyed")]
if b and b[-1].get("teardown_deadline_utc"):
    b = b[-1]
    print(b["host"], b["port"], b["created_at"], b["dph_live"], b["teardown_deadline_utc"], b["tensor_parallel_size"])
EOF
)"
[ -n "${HOST:-}" ] || { echo "not registered, provisional or destroyed: $ID"; exit 1; }
python3 - "$CREATED" "$DPH" "$DEADLINE" "$TP" <<'EOF'
import sys, datetime as d
c = d.datetime.fromisoformat(sys.argv[1]); dl = d.datetime.fromisoformat(sys.argv[3])
now = d.datetime.now(d.timezone.utc)
m = (now - c).total_seconds() / 60; rate = float(sys.argv[2]); left = (dl - now).total_seconds() / 60
print(f"TP{sys.argv[4]}; elapsed {m:.1f} min, cost so far ${rate * m / 60:.2f} at ${rate:.3f}/h; "
      f"{left:.1f} min to the teardown deadline {sys.argv[3]}")
sys.exit(3 if left <= 0 else 0)
EOF
PAST=$?
CREDIT=$(vastai show user --raw 2>/dev/null | python3 -c "import json,sys;print(round(float(json.load(sys.stdin)['credit']),2))" 2>/dev/null)
echo "CREDIT \$${CREDIT:-unreadable} live vast credit"
PIDF="$OUT/launch/watch_$ID.pid"
if [ -s "$PIDF" ] && kill -0 "$(cut -d' ' -f1 < "$PIDF")" 2>/dev/null; then
  echo "WATCHER alive pid $(cut -d' ' -f1 < "$PIDF")"
else
  echo "WATCHER DEAD: start it now: nohup caffeinate -i .venv/bin/python script/remote/auditbench/exact_stack/watch_exact_stack.py $ID >> $OUT/launch/watch_$ID.log 2>&1 &"
fi
BOXREL=$(python3 -c "import json;print(json.load(open('$RECIPE'))['box_rel'])")
SSHC="ssh -F /dev/null -i $HOME/.ssh/id_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=20 -o BatchMode=yes -p $PORT"
probe=$(bash -c "$SSHC root@$HOST 'bash -s'" 2>/dev/null <<EOF | grep '^ES '
B=/workspace/idt/$BOXREL
NOW=\$(date +%s)
age() { if [ -e "\$1" ]; then echo \$(( NOW - \$(stat -c %Y "\$1") )); else echo -1; fi; }
echo "ES BOXID \$(cat /root/box_id 2>/dev/null)"
echo "ES DONE \$(cat \$B/RUNNER_DONE 2>/dev/null || echo none)"
echo "ES SAMPLER_DONE \$(cat \$B/SAMPLER_DONE.json 2>/dev/null || echo none)"
echo "ES RUNNER \$(tail -1 \$B/runner.log 2>/dev/null)"
echo "ES WEIGHTS \$(du -sb /workspace/idt/models/Llama-3.3-70B-Instruct 2>/dev/null | cut -f1) bytes on disk; \$(grep -c '^ok \|^have ' \$B/fetch_base.log 2>/dev/null) files ok"
echo "ES STACK \$(tr -d '\n' < \$B/stack_check.json 2>/dev/null | grep -o '\"pass\": [a-z]*' | tail -1)"
echo "ES PROGRESS \$(tail -1 \$B/progress.log 2>/dev/null | cut -c1-400)"
echo "ES ENGINE \$(grep -v 'Capturing CUDA\|Loading safetensors' \$B/engine.log 2>/dev/null | tail -1 | cut -c1-240)"
echo "ES ROWS \$(wc -l < \$B/responses_base.jsonl 2>/dev/null || echo 0)"
echo "ES GPU \$(nvidia-smi --query-gpu=utilization.gpu,memory.used,power.draw --format=csv,noheader | tr '\n' ';')"
echo "ES DISK \$(df -BG --output=avail /workspace | tail -1 | tr -dc 0-9) GB free"
echo "ES PROCS \$(pgrep -fc 'exact_stack|VLLM::' 2>/dev/null)"
GEN=0; grep -q 'generate: .* in one call' \$B/engine.log 2>/dev/null && GEN=1
UMAX=\$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null | sort -n | tail -1 | tr -dc 0-9)
DN=0; [ -e \$B/RUNNER_DONE ] && DN=1
S0=0; grep -qE 'rc.: 0[,}]' \$B/SAMPLER_DONE.json 2>/dev/null && S0=1
PV=0; [ -e \$B/provenance.json ] && PV=1
NR=\$(wc -l < \$B/responses_base.jsonl 2>/dev/null); NR=\${NR:-0}
NP=\$(pgrep -fc 'exact_stack|VLLM::' 2>/dev/null); NP=\${NP:-0}
echo "ES MACHINE {\"done\": \$DN, \"sampler_done_age_s\": \$(age \$B/SAMPLER_DONE.json), \"provenance_age_s\": \$(age \$B/provenance.json), \"sampler_done_rc0\": \$S0, \"rows\": \$NR, \"provenance\": \$PV, \"gen_started\": \$GEN, \"progress_age_s\": \$(age \$B/progress.log), \"gpu_util_max\": \${UMAX:-0}, \"procs\": \$NP}"
EOF
)
[ -n "$probe" ] || { echo "unreachable ssh to $HOST:$PORT"; exit 1; }
printf '%s\n' "$probe" | sed 's/^ES //'
M=$(printf '%s\n' "$probe" | sed -n 's/^ES MACHINE //p')
LINGER=$(python3 - "$M" "$LINGER_S" <<'EOF'
import json, sys
try:
    m = json.loads(sys.argv[1])
except ValueError:
    print("MACHINE line unreadable", file=sys.stderr)
    print(0)
    sys.exit(0)
if m["gen_started"] and not m["done"] and (m["progress_age_s"] < 0 or m["progress_age_s"] > 120):
    print(f"PROGRESS STALE: generation started, no progress line for {m['progress_age_s']} s "
          f"(GPU max {m['gpu_util_max']}%)", file=sys.stderr)
# a finished draw: 3,456 rows and provenance.json, with SAMPLER_DONE rc 0, or provenance.json alone when the
# sampler hangs before its marker; either way the runner has not ended within the linger time
done_age = m["sampler_done_age_s"] if m["sampler_done_rc0"] == 1 else m.get("provenance_age_s", -1)
print(int(m["rows"] == 3456 and m["provenance"] == 1 and done_age >= int(sys.argv[2])))
EOF
)
if printf '%s\n' "$probe" | grep -q '^ES DONE .*rc='; then
  echo "RUNNER ENDED: the box is idle from now; run teardown_exact_stack.sh $ID in this step"; exit 4
fi
if [ "$LINGER" = 1 ]; then
  echo "DRAW COMPLETE, RUNNER LINGERS: SAMPLER_DONE rc 0 with 3,456 rows; run teardown_exact_stack.sh $ID --stop"; exit 5
fi
[ "$PAST" = 3 ] && { echo "PAST THE TEARDOWN DEADLINE: run teardown_exact_stack.sh $ID --stop now"; exit 3; }
exit 0
