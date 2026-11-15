#!/usr/bin/env bash
# Read-only status of the exact-stack box, for the 20-minute owner report (B59) and the 40-minute verifier (B61).
#
#   bash script/remote/auditbench/exact_stack/status_exact_stack.sh <instance id>
#
# Prints: minutes since create, cost so far at the live rate, minutes left to the teardown deadline (the $12 job
# cap less the capture reserve, from boxes.json), the runner's stage, weight bytes on disk against the manifest,
# the newest progress line (written only when the engine's counters move, with the sampler's own projection),
# GPU utilisation, and whether rows exist. Never writes on the box.
# Exit 0 running; 3 past the teardown deadline (run teardown_exact_stack.sh <id> now); 4 the runner ended, with or
# without rows (the box is idle: run teardown_exact_stack.sh <id> in this step); 1 unreachable or unregistered.
set -u
ID=${1:?usage: status_exact_stack.sh <instance id>}
cd "$(dirname "$0")/../../../.." || exit 1
RECIPE=script/remote/auditbench/exact_stack/recipe.json
OUT=$(python3 -c "import json;print(json.load(open('$RECIPE'))['out_rel'])")
read -r HOST PORT CREATED DPH DEADLINE TP <<< "$(python3 - "$OUT/boxes.json" "$ID" <<'EOF'
import json, sys
b = [x for x in json.load(open(sys.argv[1]))["boxes"] if str(x.get("id")) == sys.argv[2] and not x.get("destroyed")]
if b:
    b = b[-1]
    print(b["host"], b["port"], b["created_at"], b["dph_live"], b["teardown_deadline_utc"], b["tensor_parallel_size"])
EOF
)"
[ -n "${HOST:-}" ] || { echo "not registered or destroyed: $ID"; exit 1; }
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
BOXREL=$(python3 -c "import json;print(json.load(open('$RECIPE'))['box_rel'])")
SSHC="ssh -F /dev/null -i $HOME/.ssh/id_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=20 -o BatchMode=yes -p $PORT"
probe=$(bash -c "$SSHC root@$HOST 'bash -s'" 2>/dev/null <<EOF | grep '^ES '
B=/workspace/idt/$BOXREL
echo "ES BOXID \$(cat /root/box_id 2>/dev/null)"
echo "ES DONE \$(cat \$B/RUNNER_DONE 2>/dev/null || echo none)"
echo "ES RUNNER \$(tail -1 \$B/runner.log 2>/dev/null)"
echo "ES WEIGHTS \$(du -sb /workspace/idt/models/Llama-3.3-70B-Instruct 2>/dev/null | cut -f1) bytes on disk; \$(grep -c '^ok \|^have ' \$B/fetch_base.log 2>/dev/null) files ok"
echo "ES STACK \$(tr -d '\n' < \$B/stack_check.json 2>/dev/null | grep -o '\"pass\": [a-z]*' | tail -1)"
echo "ES PROGRESS \$(tail -1 \$B/progress.log 2>/dev/null | cut -c1-400)"
echo "ES ENGINE \$(grep -v 'Capturing CUDA\|Loading safetensors' \$B/engine.log 2>/dev/null | tail -1 | cut -c1-240)"
echo "ES ROWS \$(wc -l < \$B/responses_base.jsonl 2>/dev/null || echo 0)"
echo "ES GPU \$(nvidia-smi --query-gpu=utilization.gpu,memory.used,power.draw --format=csv,noheader | tr '\n' ';')"
echo "ES DISK \$(df -BG --output=avail /workspace | tail -1 | tr -dc 0-9) GB free"
echo "ES PROCS \$(pgrep -fc 'exact_stack|VLLM::' 2>/dev/null)"
EOF
)
[ -n "$probe" ] || { echo "unreachable ssh to $HOST:$PORT"; exit 1; }
printf '%s\n' "$probe" | sed 's/^ES //'
if printf '%s\n' "$probe" | grep -q '^ES DONE .*rc='; then
  echo "RUNNER ENDED: the box is idle from now; run teardown_exact_stack.sh $ID in this step"; exit 4
fi
[ "$PAST" = 3 ] && { echo "PAST THE TEARDOWN DEADLINE: run teardown_exact_stack.sh $ID now"; exit 3; }
exit 0
