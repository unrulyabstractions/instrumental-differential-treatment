#!/usr/bin/env bash
# Read-only status of the exact-stack box, for the 20-minute owner report (B59) and the 40-minute verifier (B61).
#
#   bash script/remote/auditbench/exact_stack/status_exact_stack.sh <instance id>
#
# Prints: minutes since create, cost so far at the live rate, minutes left to the $12 job cap and to the hard
# cap, the runner's stage, weight bytes on disk against the manifest, the newest progress line (written only
# when the engine's counters move), GPU utilisation, and whether rows exist. Never writes on the box.
# Exit 0 running, 3 past the hard cap (the executor then runs pull_and_teardown.sh destroy <id>), 4 the runner
# ended, with or without rows (the box is idle: capture and destroy in the same step), 1 unreachable or unregistered.
set -u
ID=${1:?usage: status_exact_stack.sh <instance id>}
cd "$(dirname "$0")/../../../.." || exit 1
RECIPE=script/remote/auditbench/exact_stack/recipe.json
OUT=$(python3 -c "import json;print(json.load(open('$RECIPE'))['out_rel'])")
read -r HOST PORT CREATED DPH JOBCAP HARDCAP <<< "$(python3 - "$OUT/boxes.json" "$ID" "$RECIPE" <<'EOF'
import json, sys
b = [x for x in json.load(open(sys.argv[1]))["boxes"] if str(x.get("id")) == sys.argv[2] and not x.get("destroyed")]
r = json.load(open(sys.argv[3]))["box"]
if b:
    b = b[-1]
    print(b["host"], b["port"], b["created_at"], b["dph_live"], r["job_cap_usd"], r["hard_cap_usd"])
EOF
)"
[ -n "${HOST:-}" ] || { echo "not registered or destroyed: $ID"; exit 1; }
python3 - "$CREATED" "$DPH" "$JOBCAP" "$HARDCAP" <<'EOF'
import sys, datetime as d
c = d.datetime.fromisoformat(sys.argv[1]); now = d.datetime.now(d.timezone.utc)
m = (now - c).total_seconds() / 60; rate = float(sys.argv[2])
print(f"elapsed {m:.1f} min, cost so far ${rate * m / 60:.2f} at ${rate:.3f}/h; "
      f"{float(sys.argv[3]) / rate * 60 - m:.1f} min to the ${sys.argv[3]} job cap, "
      f"{float(sys.argv[4]) / rate * 60 - m:.1f} min to the ${sys.argv[4]} hard cap")
sys.exit(3 if m >= float(sys.argv[4]) / rate * 60 else 0)
EOF
PAST=$?
BOXREL=$(python3 -c "import json;print(json.load(open('$RECIPE'))['box_rel'])")
SSHC="ssh -F /dev/null -i $HOME/.ssh/id_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=20 -o BatchMode=yes -p $PORT"
probe=$(bash -c "$SSHC root@$HOST 'bash -s'" 2>/dev/null <<EOF
B=/workspace/idt/$BOXREL
echo "BOXID \$(cat /root/box_id 2>/dev/null)"
echo "DONE \$(cat \$B/RUNNER_DONE 2>/dev/null || echo none)"
echo "RUNNER \$(tail -1 \$B/runner.log 2>/dev/null)"
echo "WEIGHTS \$(du -sb /workspace/idt/models/Llama-3.3-70B-Instruct 2>/dev/null | cut -f1) bytes on disk; \$(grep -c '^ok \|^have ' \$B/fetch_base.log 2>/dev/null) files ok"
echo "PROGRESS \$(tail -1 \$B/progress.log 2>/dev/null)"
echo "ENGINE \$(grep -v 'Capturing CUDA\|Loading safetensors' \$B/engine.log 2>/dev/null | tail -1 | cut -c1-240)"
echo "ROWS \$(wc -l < \$B/responses_base.jsonl 2>/dev/null || echo 0)"
echo "GPU \$(nvidia-smi --query-gpu=utilization.gpu,memory.used,power.draw --format=csv,noheader | tr '\n' ';')"
echo "PROCS \$(pgrep -fc 'exact_stack|VLLM::' 2>/dev/null)"
EOF
)
[ -n "$probe" ] || { echo "unreachable ssh to $HOST:$PORT"; exit 1; }
printf '%s\n' "$probe"
[ "$PAST" = 3 ] && { echo "PAST THE HARD CAP: run pull_and_teardown.sh destroy $ID now"; exit 3; }
if printf '%s\n' "$probe" | grep -q '^DONE .*rc='; then
  echo "RUNNER ENDED: the box is idle from now; run pull_and_teardown.sh destroy $ID in this step"; exit 4
fi
exit 0
