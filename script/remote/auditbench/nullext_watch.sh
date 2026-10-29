#!/usr/bin/env bash
# Watch the null-extension box: pull, count, alarm. It never destroys anything.
#
#   bash script/remote/auditbench/nullext_watch.sh        # reads tmp/nullext_endpoint.json
#
# Every POLL_S seconds: rows on disk for each arm, GPU use, the collector's last
# log line, its exit marker, and box cost so far; then an rsync pull of every
# output and log, so the box is never the only copy for more than one cycle.
# Liveness is row growth, never a process name. No new row for STALL_S while
# the collector has not exited is an alarm (tmp/NEEDS_HUMAN_nullext). Past
# CAP_S of box time it prints CAP_REACHED and exits 3 for the operator.
# Exit 0 once NULLEXT_EXIT=0 is seen and the final pull has landed.
set -u
cd "$(dirname "$0")/../../.." || exit 1
EP=tmp/nullext_endpoint.json
HOST=$(python3 -c "import json;print(json.load(open('$EP'))['host'])")
PORT=$(python3 -c "import json;print(json.load(open('$EP'))['port'])")
IID=$(python3 -c "import json;print(json.load(open('$EP'))['id'])")
DPH=$(python3 -c "import json;d=json.load(open('$EP'));print(d.get('dph_live') or d['dph_offer'])")
READY=$(python3 -c "import json,time,datetime;d=json.load(open('$EP'));print(int(datetime.datetime.strptime(d['ready_at'],'%Y-%m-%dT%H:%M:%S%z').timestamp()))")
POLL_S=${POLL_S:-120}; STALL_S=${STALL_S:-600}; CAP_S=${CAP_S:-7200}
OPTS="-F /dev/null -i $HOME/.ssh/id_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=20"
LOGS=out/logs/remote/idt-r2-nullext
mkdir -p "$LOGS" out/main/auditbench/nullext
WLOG=tmp/nullext_watch.log
last_total=-1; last_change=$(date +%s); fails=0
say() { echo "$(date +%H:%M:%S) $*" | tee -a "$WLOG"; }

while :; do
  now=$(date +%s); el=$((now - READY))
  cost=$(python3 -c "print(f'{$el/3600*$DPH:.2f}')")
  # Rows per arm, GPU use, last log line and exit marker, read in one ssh.
  out=$(ssh $OPTS -n -p "$PORT" "root@$HOST" 'cd /workspace/idt
    for f in out/main/auditbench/nullext/base_B/responses/responses_base.jsonl out/main/auditbench/nullext/synth/ai_welfare_poisoning/responses_target.jsonl out/main/auditbench/nullext/synth/emotional_bond/responses_target.jsonl; do
      [ -f "$f" ] && wc -l < "$f" || echo 0; done | tr "\n" " "; echo
    nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits | tr "\n" " "; echo
    LC_ALL=C grep -a -o "NULLEXT_EXIT=[0-9]*" nullext_collect.log | tail -1; echo
    LC_ALL=C tail -c 400 nullext_collect.log | tr "\r" "\n" | grep -a . | tail -1' 2>/dev/null)
  if [ -z "$out" ]; then
    fails=$((fails + 1)); say "box $IID: ssh failed ($fails in a row), ${el}s, ~\$${cost}"
    [ "$fails" -ge 3 ] && { echo "$(date +%FT%T) ssh to $IID failed 3 times" > tmp/NEEDS_HUMAN_nullext; say "ALARM: ssh lost"; }
    sleep "$POLL_S"; continue
  fi
  fails=0
  rows=$(printf '%s\n' "$out" | sed -n 1p); gpu=$(printf '%s\n' "$out" | sed -n 2p)
  ex=$(printf '%s\n' "$out" | sed -n 3p); tailline=$(printf '%s\n' "$out" | sed -n 4p | cut -c1-140)
  total=$(echo "$rows" | awk '{s=0; for(i=1;i<=NF;i++) s+=$i; print s}')
  [ "$total" != "$last_total" ] && { last_total=$total; last_change=$now; }
  say "box $IID rows base_B/sd_awp/sd_eb = ${rows}(of 3456 each) gpu% ${gpu} ${ex:-running} ${el}s ~\$${cost} | ${tailline}"
  rsync -az --timeout=300 -e "ssh $OPTS -p $PORT" "root@$HOST:/workspace/idt/out/main/auditbench/nullext/" out/main/auditbench/nullext/ \
    || say "pull of outputs failed this cycle"
  for f in install.log fetch_base.log fetch_adapter.log nullext_collect.log; do
    rsync -az --timeout=120 -e "ssh $OPTS -p $PORT" "root@$HOST:/workspace/idt/$f" "$LOGS/$f" 2>/dev/null
  done
  case "$ex" in
    NULLEXT_EXIT=0) say "DONE: collector exited 0; final pull landed"; exit 0 ;;
    NULLEXT_EXIT=*) say "ALARM: collector exited ${ex#NULLEXT_EXIT=}"; echo "$(date +%FT%T) $ex" > tmp/NEEDS_HUMAN_nullext; exit 2 ;;
  esac
  if [ $((now - last_change)) -ge "$STALL_S" ]; then
    say "ALARM: no new row for $((now - last_change))s"; echo "$(date +%FT%T) stall at $rows" > tmp/NEEDS_HUMAN_nullext
  fi
  [ "$el" -ge "$CAP_S" ] && { say "CAP_REACHED after ${el}s, ~\$${cost}"; exit 3; }
  sleep "$POLL_S"
done
