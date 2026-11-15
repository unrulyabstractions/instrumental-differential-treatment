#!/usr/bin/env bash
# The cloud box guard's progress adapter for this repo: .claude/box_progress.sh <provider> <instance id>
#
# ~/.claude/hooks/cloud_boxes_guard.py asks every watched checkout about every live box and takes the last line
# printed here:
#   progress <seconds>   a process of ours runs; seconds since the newest write among the run's logs and outputs
#                        (everything under remote_run_dir), the weights download dir (remote_run_dir/models, the
#                        HuggingFace caches), the top-level *.log files of /root and /workspace, and /root/box_id
#   ended <why>          the runner wrote its done marker, or nothing of ours runs any more
#   unreachable <why>    ssh failed, the box names another id in /root/box_id, the registry entry is malformed,
#                        or two registries list the id as live
#   unknown              not a box of this repo: no registry lists the id as live (a missing or unreadable
#                        registry lists nothing). Another checkout's adapter may then claim it.
# Reads only; never writes on the box or here. Bash 3.2 (the Mac's /bin/bash).
# `.claude/box_progress.sh registries` prints each registry read, in order, and its state (missing, unreadable,
# or its live and total entry counts), so a launcher can check its registry is read before it rents.
#
# The registries are the files listed one per line in .claude/box_registries (blank lines and # comments skipped;
# a relative path resolves against the repo root). Each is written by its launcher at rental. A missing list, or
# one that names no path, falls back to out/main/auditbench/nullext/exact_stack_20261114/boxes.json alone.
# IDT_BOX_REGISTRY (one registry) and IDT_BOX_REGISTRIES (another list file) override them, for the adapters'
# own failure tests only. Every registry has this schema:
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
LIST=${IDT_BOX_REGISTRIES:-$root/.claude/box_registries}
DEFAULT_REG=out/main/auditbench/nullext/exact_stack_20261114/boxes.json

# Exit 3: not registered (unknown). Exit 4: registered but malformed, or live in two registries (unreachable, so
# the guard still acts). Mode "list" prints the registries read and their state.
lookup() {
python3 - "$1" "$root" "${IDT_BOX_REGISTRY:-}" "$LIST" "$DEFAULT_REG" <<'EOF'
import json, os, re, sys
PROCS = (r"collect_auditbench|exact_stack|fetch_base\.sh|fetch_weights\.sh|fetch_par\.sh|fetch_adapters\.py|"
         r"fetch_one|VLLM::|vllm\.entrypoints|vllm serve|pip install|uv pip")
want, root, single, listing, default = sys.argv[1:6]
if single:
    paths = [single]
else:
    try:
        lines = open(listing).read().splitlines()
    except (OSError, UnicodeDecodeError):
        lines = []
    paths = [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")] or [default]
    paths = [p if os.path.isabs(p) else os.path.join(root, p) for p in map(os.path.expanduser, paths)]
regs, seen = [], set()
for p in paths:
    if os.path.realpath(p) not in seen:
        seen.add(os.path.realpath(p))
        regs.append(p)
def boxes_of(reg):
    try:
        boxes = json.load(open(reg))["boxes"]
        assert isinstance(boxes, list)
        return boxes
    except Exception:
        return None
if want == "list":
    for reg in regs:
        boxes = boxes_of(reg) if os.path.isfile(reg) else None
        state = ("missing" if not os.path.isfile(reg) else "unreadable" if boxes is None else
                 f"{sum(isinstance(b, dict) and not b.get('destroyed') for b in boxes)} live of {len(boxes)}")
        print(f"registry {reg} {state}")
    sys.exit(0)
hits = []
for reg in regs:
    boxes = boxes_of(reg) if os.path.isfile(reg) else None
    hits += [(reg, b) for b in boxes or [] if isinstance(b, dict) and str(b.get("id")) == want
             and not b.get("destroyed")]
if not hits:
    sys.exit(3)
regs_hit = list(dict.fromkeys(r for r, _ in hits))
if len(regs_hit) > 1:
    print(f"the id is live in more than one registry ({' '.join(regs_hit)})")
    sys.exit(4)
b = hits[-1][1]
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
}
[ "$provider" = registries ] && { lookup list; exit 0; }
[ "$provider" = vast ] || { echo "unknown"; exit 0; }
case $id in ''|*[!0-9]*) echo "unknown"; exit 0 ;; esac

# One tab-separated line: host port key run_dir done_marker procs watch (space-joined; paths hold no spaces)
entry=$(lookup "$id")
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
