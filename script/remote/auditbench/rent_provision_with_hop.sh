#!/usr/bin/env bash
# Rent a single-GPU box for the phase-2 run and provision it, hopping hosts on
# the vast.ai ssh-key-injection flake. The account key is correct and the image
# is the -auto image, so a "permission denied (publickey)" past a short SLA is a
# dead host, not a fixable local problem: destroy it and take the next offer
# rather than sink twenty minutes into one bad host.
#
#   bash rent_provision_with_hop.sh
#
# Writes the working endpoint to scratchpad/p2b_endpoint.txt (the health monitor
# reads it) and launches generation. Exits non-zero if every attempt fails.
set -u
# Absolute paths come from the environment, so no local account name is baked
# into a file that ships in the submission package.
REPO="${IDT_REPO:-$(cd "$(dirname "$0")/../../.." && pwd)}"
SC="${IDT_SCRATCH:-${TMPDIR:-/tmp}/idt-scratch}"
K="$HOME/.ssh/id_ed25519"
REG="$REPO/tmp/r2_my_instances.txt"
SLA=240          # seconds to wait for ssh before declaring a host dead
MAX_HOPS=5
CURRENT_ID="${1:-}"   # an already-rented instance id to try first, optional

ssh_ok() {  # host port -> 0 if our key logs in
  ssh -F /dev/null -i "$K" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
      -o ConnectTimeout=12 -o BatchMode=yes -n -p "$2" "root@$1" 'echo OK' 2>/dev/null | grep -q OK
}

endpoints() {  # id -> prints "direct_host direct_port proxy_host proxy_port"
  vastai show instance "$1" --raw 2>/dev/null | uv run python -c "
import json,sys
o=json.load(sys.stdin)
p=(o.get('ports') or {}).get('22/tcp') or [{}]
print(o.get('public_ipaddr','-'), p[0].get('HostPort','-'), o.get('ssh_host','-'), o.get('ssh_port','-'))"
}

wait_running() {  # id -> 0 when running
  for _ in $(seq 1 30); do
    s=$(vastai show instance "$1" --raw 2>/dev/null | uv run python -c "import json,sys;print(json.load(sys.stdin).get('actual_status',''))" 2>/dev/null)
    [ "$s" = "running" ] && return 0
    sleep 10
  done
  return 1
}

rent_one() {  # -> prints new instance id, or empty
  vastai search offers 'num_gpus=1 gpu_name in [L40S,H100_PCIE,H100_SXM] rentable=true reliability>0.995 disk_space>60 inet_down>2000 cuda_max_good>=12.8' \
    -o 'dph_total' --raw 2>/dev/null | uv run python -c "
import json,sys
offers=json.load(sys.stdin)
seen=set(open('$SC/tried_offers.txt').read().split()) if __import__('os').path.exists('$SC/tried_offers.txt') else set()
for o in offers:
    if str(o['id']) not in seen:
        print(o['id']); break"
}

destroy() {  # id
  vastai destroy instance "$1" --yes >/dev/null 2>&1
  grep -v "^$1 " "$REG" > "$REG.tmp" 2>/dev/null && mv "$REG.tmp" "$REG"
}

attempt() {  # id -> 0 and sets EP_HOST/EP_PORT if ssh comes up within SLA
  local id="$1"
  wait_running "$id" || { echo "[hop] $id never reached running"; return 1; }
  read dh dp ph pp < <(endpoints "$id")
  echo "[hop] $id running; direct $dh:$dp proxy $ph:$pp; ssh SLA ${SLA}s"
  local deadline=$(( $(date +%s) + SLA ))
  while [ $(date +%s) -lt $deadline ]; do
    if ssh_ok "$dh" "$dp"; then EP_HOST="$dh"; EP_PORT="$dp"; return 0; fi
    if ssh_ok "$ph" "$pp"; then EP_HOST="$ph"; EP_PORT="$pp"; return 0; fi
    sleep 15
  done
  return 1
}

: > "$SC/tried_offers.txt"
id="$CURRENT_ID"
for hop in $(seq 1 $MAX_HOPS); do
  if [ -z "$id" ]; then
    id=$(rent_one)
    [ -z "$id" ] && { echo "[hop] no fresh offer available"; exit 2; }
    echo "$id idt-p2c" >> "$REG"
    echo "[hop $hop] rented $id"
  fi
  echo "$id" >> "$SC/tried_offers.txt"
  if attempt "$id"; then
    echo "[hop] ssh UP on $id at $EP_HOST:$EP_PORT"
    echo "$EP_HOST $EP_PORT" > "$SC/p2b_endpoint.txt"
    echo "$id" > "$SC/p2_active_id.txt"
    bash "$SC/run_p2_box.sh" "$EP_HOST" "$EP_PORT"
    exit 0
  fi
  echo "[hop $hop] $id ssh dead after ${SLA}s; destroying and hopping"
  destroy "$id"
  id=""
done
echo "[hop] exhausted $MAX_HOPS hosts without a working ssh"
exit 3
