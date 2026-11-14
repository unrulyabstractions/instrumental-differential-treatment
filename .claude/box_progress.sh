#!/usr/bin/env bash
# The cloud box guard's progress adapter for this repo: .claude/box_progress.sh <provider> <instance id>
#
# ~/.claude/hooks/cloud_boxes_guard.py asks every watched checkout about every live box and takes the last line
# printed here:
#   progress <seconds>   a process of ours runs; seconds since the newest write among the run's logs and outputs
#                        (everything under remote_run_dir), the weights download dir (remote_run_dir/models, the
#                        HuggingFace caches), the top-level *.log files of /root and /workspace, and /root/box_id
#   ended <why>          the runner wrote its done marker, or nothing of ours runs any more
#   unreachable <why>    ssh failed, the box names another id in /root/box_id, or the registry entry is malformed
#   unknown              not a box of this repo: the registry does not list the id as live, or the registry is
#                        missing or unreadable. Another checkout's adapter may then claim it.
# Reads only; never writes on the box or here. Bash 3.2 (the Mac's /bin/bash).
#
# The registry is out/main/auditbench/nullext/exact_stack_20261114/boxes.json, written by the launcher at rental
# (IDT_BOX_REGISTRY overrides it, for the adapter's own failure tests only). Schema:
#   {"boxes": [{"id": 12345678, "host": "1.2.3.4", "port": 40022, "label": "idt-...",
#               "remote_roots": ["/workspace", "/root"], "remote_run_dir": "/workspace/idt",
#               "local_capture_dir": "out/main/auditbench/nullext/exact_stack_20261114/capture",
#               "destroyed": false,
#               "done_marker": "/workspace/idt/RUNNER_DONE",       optional, this default
#               "procs": "<ERE matched by pgrep -f>",              optional, default PROCS below
#               "watch": ["/abs/path", ...],                       optional extra paths whose writes count
#               "key": "~/.ssh/id_ed25519"}]}                     optional, this default
# The launcher must also write the instance id into /root/box_id on the box, and the runner must write
# done_marker when it ends, whatever its exit code.
set -uo pipefail
provider=${1:-}
id=${2:-}
root=$(cd "$(dirname "$0")/.." && pwd -P)
REG=${IDT_BOX_REGISTRY:-$root/out/main/auditbench/nullext/exact_stack_20261114/boxes.json}
[ "$provider" = vast ] || { echo "unknown"; exit 0; }
case $id in ''|*[!0-9]*) echo "unknown"; exit 0 ;; esac
[ -f "$REG" ] || { echo "unknown"; exit 0; }

# One tab-separated line: host port key run_dir done_marker procs watch (space-joined; paths hold no spaces)
# Exit 3: not registered (unknown). Exit 4: registered but malformed (unreachable, so the guard still acts).
entry=$(python3 - "$REG" "$id" <<'EOF'
import json, os, re, sys
PROCS = (r"collect_auditbench|exact_stack|fetch_base\.sh|fetch_weights\.sh|fetch_par\.sh|fetch_adapters\.py|"
         r"fetch_one|VLLM::|vllm\.entrypoints|vllm serve|pip install|uv pip")
try:
    boxes = json.load(open(sys.argv[1]))["boxes"]
except Exception:
    sys.exit(3)
hits = [b for b in boxes if isinstance(b, dict) and str(b.get("id")) == sys.argv[2] and not b.get("destroyed")]
if not hits:
    sys.exit(3)
b = hits[-1]
safe = re.compile(r"^/[A-Za-z0-9._/-]+$")
try:
    host, port = str(b["host"]).strip(), str(b["port"]).strip()
    run = str(b.get("remote_run_dir") or "/workspace/idt").rstrip("/")
    done = str(b.get("done_marker") or f"{run}/RUNNER_DONE")
    procs = str(b.get("procs") or PROCS)
    watch = [str(w) for w in (b.get("watch") or [])]
    key = os.path.expanduser(str(b.get("key") or "~/.ssh/id_ed25519"))
    assert re.fullmatch(r"[A-Za-z0-9.-]+", host), "host"
    assert port.isdigit(), "port"
    assert all(safe.match(p) for p in [run, done, *watch]), "remote path"
    assert "\t" not in procs and "\n" not in procs and procs.strip(), "procs"
    re.compile(procs)
    assert os.path.isfile(key), "ssh key"
except Exception as ex:
    print(f"invalid registry entry ({ex})")
    sys.exit(4)
print("\t".join([host, port, key, run, done, procs, " ".join(watch)]))
EOF
)
rc=$?
[ $rc -eq 3 ] && { echo "unknown"; exit 0; }
[ $rc -eq 0 ] || { echo "unreachable ${entry:-registry entry unreadable}"; exit 0; }
IFS=$'\t' read -r host port key run done_marker procs watch <<< "$entry"

# The probe runs on the box under `bash -s`; values travel as %q-quoted assignments, never spliced into code.
# Only lines tagged BOXPROBE are read: vast.ai prints a login banner on the same stream (2026-11-13 fix in the
# rebuttal adapters, where every teardown was refused because of it).
probe() {
  printf 'want=%q\nrun=%q\ndone_marker=%q\nprocs=%q\nwatch=%q\n' "$id" "$run" "$done_marker" "$procs" "$watch"
  cat <<'R'
got=$(tr -d '[:space:]' < /root/box_id 2>/dev/null)
echo "BOXPROBE BOXID ${got:-none}"
[ "$got" = "$want" ] || exit 0
if [ -e "$done_marker" ]; then echo "BOXPROBE DONE 1"; else echo "BOXPROBE DONE 0"; fi
# A box without pgrep and ps, or a pgrep that fails, answers x (unreadable), never 0.
count() {
  if command -v pgrep > /dev/null 2>&1; then
    p=$(pgrep -f -- "$procs" 2>/dev/null); rc=$?
    if [ $rc -gt 1 ]; then echo x; return; fi
    printf '%s\n' "$p" | grep -c '[0-9]'
  elif command -v ps > /dev/null 2>&1; then
    ps -eo args= | grep -E -- "$procs" | grep -vc -- 'grep -E'
  else echo x; fi
}
echo "BOXPROBE PROCS $(echo $(count))"
newest=$( { timeout 100 find "$run" \( -name .venv -o -name site-packages -o -name __pycache__ \) -prune -o -type f -printf '%T@\n' 2>/dev/null
            timeout 60 find /root/.cache/huggingface /workspace/.cache/huggingface -type f -printf '%T@\n' 2>/dev/null
            find /root /workspace -maxdepth 1 -type f \( -name '*.log' -o -name box_id \) -printf '%T@\n' 2>/dev/null
            for w in $watch; do timeout 30 find "$w" -type f -printf '%T@\n' 2>/dev/null; done; } | sort -n | tail -1)
now=$(date +%s); newest=${newest%.*}; [ -n "$newest" ] || newest=0
echo "BOXPROBE AGE $(( now > newest ? now - newest : 0 ))"
R
}
out=$(probe | ssh -F /dev/null -i "$key" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=20 \
        -o ServerAliveInterval=15 -o ServerAliveCountMax=4 -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null -p "$port" "root@$host" 'bash -s' 2>/dev/null | grep '^BOXPROBE ')
val() { printf '%s\n' "$out" | awk -v k="$1" '$2 == k {print $3}' | tail -1; }
got=$(val BOXID); done_flag=$(val DONE); n=$(val PROCS); age=$(val AGE)
if [ -z "$got" ]; then echo "unreachable ssh to $host:$port"; exit 0; fi
if [ "$got" != "$id" ]; then echo "unreachable wrong-box: /root/box_id says $got"; exit 0; fi
case "$n" in ''|*[!0-9]*) echo "unreachable probe unreadable"; exit 0 ;; esac
case "$age" in ''|*[!0-9]*) echo "unreachable probe unreadable"; exit 0 ;; esac
if [ "$done_flag" = 1 ]; then echo "ended runner wrote its done marker $done_marker"; exit 0; fi
if [ "$n" -eq 0 ]; then echo "ended nothing of ours runs (no done marker)"; exit 0; fi
echo "progress $age"
