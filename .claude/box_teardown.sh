#!/usr/bin/env bash
# The cloud box guard's teardown adapter for this repo: .claude/box_teardown.sh <provider> <instance id>
#
# Exits 0 only after every step below passed, in this order. Any failed step leaves the box alone and exits 1.
#   1. The id is a live (not destroyed) box in the registry, out/main/auditbench/nullext/exact_stack_20261114/
#      boxes.json (schema in .claude/box_progress.sh; IDT_BOX_REGISTRY overrides it for this script's failure
#      tests only), and no other teardown of it runs.
#   2. The box names this id in /root/box_id, and nothing of ours still produces: no process of ours runs, or our
#      processes have written nothing for HUNG_S (the guard's idle threshold), in which case they are stopped
#      first so nothing writes during the capture.
#   3. The account's full, paged instance listing shows the id under the registry's label, and the label starts
#      with idt-.
#   4. Capture into <local_capture_dir>/vast_<id>/, which must lie under the registry's own capture/ folder inside
#      this repo. A sweep with script/remote/capture/verify_remote_capture.py's own sweep and exemptions (model
#      weights under remote_run_dir/models, venvs, caches, host files) sizes the pull first and refuses one above
#      max_capture_gb (default 5) or above the Mac's free disk. rsync then pulls every other file of every remote
#      root (always /workspace and /root) to files/<remote path>. verify_remote_capture.py, run as the repo runs
#      it, must exit 0 (read directly, never through a pipe; its --rescue-to pulls any gap file by file). It maps
#      only remote_run_dir, so its log lists every file outside it (/root/box_id, /root/*.log) under WOULD BE LOST
#      and then rescues each one by scp, checked by size: expected, not a failure. A fresh sweep then writes
#      proof_<utc>.tsv: every swept file with its remote and local byte size. One file without a same-size local
#      copy refuses the destroy.
#   5. Every captured file is staged with `git add -f` (out/ is gitignored, so this is what makes it tracked) and
#      read back from `git ls-files`. A file that matches an API key pattern is not staged; its path (never its
#      content) goes to SECRET_SCAN.txt. Nothing is committed or pushed here: the session does that.
#   6. A last probe: still this id, still nothing of ours running.
#   7. `vastai destroy instance`, then GONE only from two complete paged listings in a row without the id (a parse
#      or page failure never counts as gone; the listing paginates at 25, see list_instances.py).
#   8. The registry entry is marked destroyed, and a dated entry goes to VERIFICATION_LOG.md.
# Bash 3.2 (the Mac's /bin/bash): no mapfile, no empty arrays under set -u.
set -uo pipefail
provider=${1:-}
id=${2:-}
root=$(cd "$(dirname "$0")/.." && pwd -P)
REG=${IDT_BOX_REGISTRY:-$root/out/main/auditbench/nullext/exact_stack_20261114/boxes.json}
VERIFY_PY=$root/script/remote/capture/verify_remote_capture.py
HUNG_S=1800
LOG=""
EARLY=""
say() {
  local line
  line="$(date -u +%FT%TZ) [box_teardown $provider $id] $*"
  echo "$line"
  if [ -n "$LOG" ]; then echo "$line" >> "$LOG"; else EARLY="$EARLY$line"$'\n'; fi
}
refuse() { say "!! refused, the box stays: $*"; exit 1; }

[ "$provider" = vast ] || refuse "knows only vast.ai boxes of this repo, not $provider"
case $id in ''|*[!0-9]*) refuse "not a vast.ai id: $id" ;; esac
[ -f "$REG" ] || refuse "$id is not a live box in $REG (no registry)"

# ---------------------------------------------------------------- 1. the registry entry
entry=$(python3 - "$REG" "$id" <<'EOF'
import json, os, re, sys
PROCS = (r"collect_auditbench|exact_stack|fetch_base\.sh|fetch_weights\.sh|fetch_par\.sh|fetch_adapters\.py|"
         r"fetch_one|VLLM::|vllm\.entrypoints|vllm serve|pip install|uv pip")
try:
    boxes = json.load(open(sys.argv[1]))["boxes"]
except Exception as ex:
    print(f"registry unreadable ({type(ex).__name__})")
    sys.exit(4)
hits = [b for b in boxes if isinstance(b, dict) and str(b.get("id")) == sys.argv[2] and not b.get("destroyed")]
if not hits:
    sys.exit(3)
if len(hits) > 1:
    print("the id has more than one live entry")
    sys.exit(4)
b = hits[0]
safe = re.compile(r"^/[A-Za-z0-9._/-]+$")
try:
    host, port, label = str(b["host"]).strip(), str(b["port"]).strip(), str(b["label"]).strip()
    run = str(b.get("remote_run_dir") or "/workspace/idt").rstrip("/")
    done = str(b.get("done_marker") or f"{run}/RUNNER_DONE")
    procs = str(b.get("procs") or PROCS)
    watch = [str(w) for w in (b.get("watch") or [])]
    roots = [str(r).rstrip("/") for r in (b.get("remote_roots") or [])]
    roots = list(dict.fromkeys([*roots, "/workspace", "/root"]))
    cap = str(b["local_capture_dir"]).strip()
    gb = float(b.get("max_capture_gb") or 5)
    key = os.path.expanduser(str(b.get("key") or "~/.ssh/id_ed25519"))
    assert re.fullmatch(r"[A-Za-z0-9.-]+", host), "host"
    assert port.isdigit(), "port"
    assert re.fullmatch(r"[A-Za-z0-9._-]+", label), "label"
    assert all(safe.match(p) for p in [run, done, *watch, *roots]), "remote path"
    assert "\t" not in procs and "\n" not in procs and procs.strip(), "procs"
    re.compile(procs)
    assert cap and "\t" not in cap and "\n" not in cap, "local_capture_dir"
    assert 0 < gb <= 50, "max_capture_gb"
    assert os.path.isfile(key), "ssh key"
except Exception as ex:
    print(f"invalid registry entry ({ex})")
    sys.exit(4)
print("\t".join([host, port, key, label, run, done, procs, ",".join(roots), cap, str(int(gb * 1e9)),
                 " ".join(watch)]))
EOF
)
rc=$?
[ $rc -eq 3 ] && refuse "$id is not a live box in $REG"
[ $rc -eq 0 ] || refuse "${entry:-registry entry unreadable}"
IFS=$'\t' read -r host port key label run done_marker procs roots_csv cap max_bytes watch <<< "$entry"
say "registry: $label at $host:$port, run dir $run, roots $roots_csv"

lock="$(dirname "$REG")/.teardown_vast_${id}.lock"
if ! mkdir "$lock" 2> /dev/null; then
  old=$(cat "$lock/pid" 2> /dev/null)
  if [ -n "$old" ] && kill -0 "$old" 2> /dev/null; then refuse "another teardown of $id runs (pid $old)"; fi
  rm -rf "$lock"
  mkdir "$lock" 2> /dev/null || refuse "cannot take the lock $lock"
fi
echo $$ > "$lock/pid"
trap 'rm -rf "$lock"' EXIT

# ---------------------------------------------------------------- 2. the box names this id; nothing of ours produces
# The probe runs on the box under `bash -s`; values travel as %q-quoted assignments, never spliced into code. Only
# lines tagged BOXPROBE are read: vast.ai prints a login banner on the same stream (2026-11-13 fix in the rebuttal
# adapters, where every teardown was refused because of it). mode=stop first stops our processes (TERM, then KILL).
SSHO=(-F /dev/null -i "$key" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=20 -o ServerAliveInterval=15
      -o ServerAliveCountMax=4 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null)
probe() {
  printf 'mode=%q\nwant=%q\nrun=%q\ndone_marker=%q\nprocs=%q\nwatch=%q\n' "$1" "$id" "$run" "$done_marker" "$procs" "$watch"
  cat <<'R'
got=$(tr -d '[:space:]' < /root/box_id 2>/dev/null)
echo "BOXPROBE BOXID ${got:-none}"
[ "$got" = "$want" ] || exit 0
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
if [ "$mode" = stop ]; then
  pkill -TERM -f -- "$procs" 2>/dev/null; sleep 20; pkill -KILL -f -- "$procs" 2>/dev/null; sleep 5
fi
if [ -e "$done_marker" ]; then echo "BOXPROBE DONE 1"; else echo "BOXPROBE DONE 0"; fi
if [ -d "$run" ]; then echo "BOXPROBE RUNDIR 1"; else echo "BOXPROBE RUNDIR 0"; fi
echo "BOXPROBE PROCS $(echo $(count))"
newest=$( { timeout 100 find "$run" \( -name .venv -o -name site-packages -o -name __pycache__ \) -prune -o -type f -printf '%T@\n' 2>/dev/null
            timeout 60 find /root/.cache/huggingface /workspace/.cache/huggingface -type f -printf '%T@\n' 2>/dev/null
            find /root /workspace -maxdepth 1 -type f \( -name '*.log' -o -name box_id \) -printf '%T@\n' 2>/dev/null
            for w in $watch; do timeout 30 find "$w" -type f -printf '%T@\n' 2>/dev/null; done; } | sort -n | tail -1)
now=$(date +%s); newest=${newest%.*}; [ -n "$newest" ] || newest=0
echo "BOXPROBE AGE $(( now > newest ? now - newest : 0 ))"
R
}
run_probe() {
  out=$(probe "$1" | ssh "${SSHO[@]}" -p "$port" "root@$host" 'bash -s' 2> /dev/null | grep '^BOXPROBE ')
  got=$(printf '%s\n' "$out" | awk '$2 == "BOXID" {print $3}' | tail -1)
  n=$(printf '%s\n' "$out" | awk '$2 == "PROCS" {print $3}' | tail -1)
  age=$(printf '%s\n' "$out" | awk '$2 == "AGE" {print $3}' | tail -1)
  rundir=$(printf '%s\n' "$out" | awk '$2 == "RUNDIR" {print $3}' | tail -1)
  [ -n "$got" ] || refuse "ssh to $host:$port failed (unreachable)"
  [ "$got" = "$id" ] || refuse "wrong box: /root/box_id at $host:$port says $got"
  case "$n" in ''|*[!0-9]*) refuse "the probe's process count is unreadable" ;; esac
  case "$age" in ''|*[!0-9]*) refuse "the probe's write age is unreadable" ;; esac
}
run_probe probe
if [ "$n" -gt 0 ]; then
  [ "$age" -ge "$HUNG_S" ] || refuse "still producing: $n process(es) of ours, newest write ${age}s ago"
  say "hung: $n process(es) of ours but no write for ${age}s; stopping them before the capture"
  run_probe stop
  [ "$n" -eq 0 ] || refuse "$n process(es) of ours survived TERM and KILL"
fi
say "box names $id; nothing of ours runs; newest write ${age}s ago"

# ---------------------------------------------------------------- 3. the account shows this id under our label
listing() {
python3 - "$1" <<'EOF'
import json, subprocess, sys
rows, token, total = [], None, None
try:
    for _ in range(50):
        args = ["vastai", "show", "instances-v1", "--raw"] + (["--next-token", token] if token else [])
        out = subprocess.run(args, capture_output=True, text=True, timeout=120)
        if out.returncode != 0:
            raise RuntimeError(f"vastai exited {out.returncode}")
        d = json.loads(out.stdout)
        if not isinstance(d, dict) or d.get("success") is False or not isinstance(d.get("instances"), list):
            raise RuntimeError("a page is not a successful instances-v1 payload")
        rows += d["instances"]
        if total is None and isinstance(d.get("total_instances"), int):
            total = d["total_instances"]
        token = d.get("next_token")
        if not token:
            break
    else:
        raise RuntimeError("the listing did not end after 50 pages")
    if total is not None and len(rows) < total:
        raise RuntimeError(f"the listing gave {len(rows)} of {total} instances")
except Exception as ex:
    print(f"ERROR {str(ex)[:200]}")
    sys.exit(0)
hit = [r for r in rows if str(r.get("id")) == sys.argv[1]]
print(f"PRESENT {hit[0].get('label') or '-'}" if hit else "GONE")
EOF
}
st=$(listing "$id")
case "$label" in idt-*) ;; *) refuse "label $label does not start with idt-" ;; esac
[ "$st" = "PRESENT $label" ] || refuse "the account listing says '$st', not PRESENT $label"
say "account listing shows $id as $label"

# ---------------------------------------------------------------- 4. capture, sized first, proven by bytes
capdir=$(python3 - "$root" "$REG" "$cap" <<'EOF'
import os, sys
root, reg, cap = os.path.realpath(sys.argv[1]), os.path.realpath(sys.argv[2]), sys.argv[3]
base = os.path.realpath(os.path.join(os.path.dirname(reg), "capture"))
got = os.path.realpath(cap if os.path.isabs(cap) else os.path.join(root, cap))
if not (got == base or got.startswith(base + os.sep)) or not got.startswith(root + os.sep):
    print(f"capture dir {got} is not under {base} inside {root}")
    sys.exit(1)
print(got)
EOF
) || refuse "${capdir:-capture dir check failed}"
box="$capdir/vast_$id"
files="$box/files"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$files" || refuse "cannot create $files"
LOG="$box/teardown_$stamp.log"
printf '%s' "$EARLY" >> "$LOG"
effrun=$run
[ "$rundir" = 1 ] || effrun=${roots_csv%%,*}
say "capture into $box (run dir for the exemptions: $effrun)"

# One script for the sizing sweep and the proof sweep: verify_remote_capture.py's own remote_files, prefixes and
# HOST_OWNED, so the exemptions here can never drift from the gate's.
sweep() {
python3 - "$VERIFY_PY" "$1" "$host" "$port" "$key" "$effrun" "$roots_csv" "$files" "$root" "${2:-}" <<'EOF'
import importlib.util, json, os, sys, time
from pathlib import Path
vpy, mode, host, port, key, run, roots, files, root, proof = sys.argv[1:11]
s = importlib.util.spec_from_file_location("vrc", vpy); v = importlib.util.module_from_spec(s); s.loader.exec_module(v)
exempt = v.reproducible_prefixes(run)
try:
    swept = v.remote_files(host, port, Path(key), [run, *roots.split(",")], exempt)
except Exception as ex:
    print(f"SWEEP_FAILED {str(ex)[:300]}")
    sys.exit(1)
rows, counts, nbytes = [], {"captured": 0, "exempt": 0, "MISSING": 0}, {"captured": 0, "exempt": 0, "MISSING": 0}
for size, path in swept:
    if (v.in_reproducible_dir(path) or any(path.startswith(p) for p in exempt)
            or any(path.startswith(p) for p in v.HOST_OWNED)):
        cls, local, have = "exempt", "", ""
    else:
        lp = os.path.join(files, path.lstrip("/"))
        have = os.path.getsize(lp) if os.path.isfile(lp) and not os.path.islink(lp) else None
        cls, local = ("captured" if have == size else "MISSING"), os.path.relpath(lp, root)
        have = "" if have is None else have
    counts[cls] += 1
    nbytes[cls] += size
    rows.append((size, path, cls, local, have))
if mode == "plan":
    print(f"PLAN {counts['captured'] + counts['MISSING']} {nbytes['captured'] + nbytes['MISSING']} {len(swept)}")
    sys.exit(0)
with open(proof, "w") as fh:
    fh.write("remote_bytes\tremote_path\tclass\tlocal_path\tlocal_bytes\n")
    for r in rows:
        fh.write("\t".join(str(x) for x in r) + "\n")
summary = {"host": f"{host}:{port}", "swept": len(swept), "counts": counts, "bytes": nbytes,
           "run_dir_for_exemptions": run, "roots": roots.split(","), "proof": os.path.relpath(proof, root),
           "time_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
json.dump(summary, open(proof[:-4] + "_summary.json", "w"), indent=1)
print(f"PROOF swept={len(swept)} captured={counts['captured']} exempt={counts['exempt']} missing={counts['MISSING']}")
for size, path, cls, local, have in rows:
    if cls == "MISSING":
        print(f"MISSING {size} {path} -> {local} ({have or 'absent'})")
sys.exit(1 if counts["MISSING"] else 0)
EOF
}

plan=$(sweep plan) || refuse "sizing sweep failed: $plan"
read -r _ want_n want_bytes swept_n <<< "$plan"
avail_kb=$(df -Pk "$box" | awk 'NR == 2 {print $4}')
say "sizing sweep: $swept_n files swept, $want_n to capture, $want_bytes bytes; Mac free $((avail_kb / 1024)) MB"
[ "$want_bytes" -le "$max_bytes" ] || refuse "$want_bytes bytes to capture exceed the cap of $max_bytes (weights outside $effrun/models?)"
[ $((avail_kb * 1024)) -gt $((2 * want_bytes + 2000000000)) ] || refuse "not enough free disk on this Mac for $want_bytes bytes"

excludes() {
python3 - "$VERIFY_PY" "$effrun" "$1" <<'EOF'
import importlib.util, sys
s = importlib.util.spec_from_file_location("vrc", sys.argv[1]); v = importlib.util.module_from_spec(s); s.loader.exec_module(v)
run, r = sys.argv[2], sys.argv[3].rstrip("/")
for name in v.REPRODUCIBLE_DIR_NAMES:
    print(f"--exclude={name}/")
for p in (*v.reproducible_prefixes(run), *v.HOST_OWNED):
    if p.startswith(r + "/"):
        print(f"--exclude={p[len(r):]}")
EOF
}
IFS=, read -r -a roots <<< "$roots_csv"
extra=()
for r in "${roots[@]}"; do
  extra+=(--extra-root "$r")
  # Without its excludes rsync would pull the weights and the box's own vast key: a failed list stops here.
  exl=$(excludes "$r") || refuse "could not derive the rsync excludes for $r"
  case "$exl" in *"--exclude=__pycache__/"*) ;; *) refuse "the rsync excludes for $r are incomplete" ;; esac
  ex=()
  while IFS= read -r line; do ex+=("$line"); done <<< "$exl"
  mkdir -p "$files$r"
  for try in 1 2; do
    rsync -a --no-devices --no-specials --timeout=300 ${ex[@]+"${ex[@]}"} \
      -e "ssh -F /dev/null -i $key -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=25 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p $port" \
      "root@$host:$r/" "$files$r/" >> "$LOG" 2>&1
    rrc=$?
    say "rsync $r try $try exited $rrc (the gate and the proof below decide, not this code)"
    [ $rrc -eq 0 ] && break
  done
done

vlog="$box/verify_$stamp.log"
(cd "$root" && uv run python script/remote/capture/verify_remote_capture.py --host "$host" --port "$port" \
   --key "$key" --remote-root "$effrun" --local-root "$files$effrun" "${extra[@]}" --rescue-to "$files") > "$vlog" 2>&1
vrc=$?
tail -12 "$vlog" >> "$LOG"
say "verify_remote_capture.py exited $vrc (full output $vlog)"
[ $vrc -eq 0 ] || refuse "verify_remote_capture.py exited $vrc: files would be lost"

proof="$box/proof_$stamp.tsv"
pout=$(sweep proof "$proof")
prc=$?
printf '%s\n' "$pout" >> "$LOG"
say "$(printf '%s\n' "$pout" | grep -E '^(PROOF|SWEEP_FAILED)' | head -1) (per-file sizes in $proof)"
[ $prc -eq 0 ] || refuse "the byte-size proof found a file without a same-size local copy"

# ---------------------------------------------------------------- 5. tracked: git add -f, read back, no keys staged
gout=$(python3 - "$root" "$box" <<'EOF'
import os, re, subprocess, sys, time
root, box = sys.argv[1], sys.argv[2]
key = re.compile(rb"((?<![A-Za-z0-9])sk-(ant-|proj-)?[A-Za-z0-9_-]{20,}|(?<![A-Za-z0-9])hf_[A-Za-z0-9]{30,}|"
                 rb"AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|"
                 rb"xox[abpr]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)")
stage, flagged = [], []
for d, _, fs in os.walk(box):
    for f in fs:
        p = os.path.join(d, f)
        rel = os.path.relpath(p, root)
        try:
            hit = (not os.path.islink(p)) and key.search(open(p, "rb").read())
        except OSError:
            hit = False
        (flagged if hit else stage).append(rel)
if flagged:
    scan = os.path.join(box, "SECRET_SCAN.txt")
    with open(scan, "w") as fh:
        fh.write("Files that match an API key pattern. They are captured here but NOT staged. Never commit them.\n")
        fh.write("".join(f"{r}\n" for r in sorted(flagged)))
    stage.append(os.path.relpath(scan, root))
spec = "\0".join(stage).encode() + b"\0"
for attempt in range(6):
    r = subprocess.run(["git", "-C", root, "--literal-pathspecs", "add", "-f", "--pathspec-from-file=-",
                        "--pathspec-file-nul"], input=spec, capture_output=True)
    if r.returncode == 0:
        break
    time.sleep(10)
else:
    print(f"GIT_ADD_FAILED {r.stderr.decode(errors='replace')[:300]}")
    sys.exit(1)
ls = subprocess.run(["git", "-C", root, "--literal-pathspecs", "ls-files", "-z", "--", os.path.relpath(box, root)],
                    capture_output=True)
tracked = set(ls.stdout.decode(errors="replace").split("\0")) - {""}
untracked = [s for s in stage if s not in tracked]
if ls.returncode != 0 or untracked:
    print(f"NOT_TRACKED {len(untracked)} e.g. {untracked[:3]}")
    sys.exit(1)
print(f"TRACKED {len(stage)} files staged and read back from git ls-files; {len(flagged)} flagged as possible keys")
EOF
)
grc=$?
say "$gout"
[ $grc -eq 0 ] || refuse "the capture could not be made tracked"
case "$gout" in *" 0 flagged"*) ;; *) say "!! WARNING: files matching an API key pattern; see $box/SECRET_SCAN.txt" ;; esac

# ---------------------------------------------------------------- 6. last look before the destroy
run_probe probe
[ "$n" -eq 0 ] || refuse "a process of ours started again during the capture"

# ---------------------------------------------------------------- 7. destroy, then GONE from complete listings
say "destroy $id"
vastai destroy instance "$id" -y >> "$LOG" 2>&1
gone=0
for poll in $(seq 1 30); do
  sleep 10
  st=$(listing "$id")
  if [ "$st" = GONE ]; then gone=$((gone + 1)); else gone=0; fi
  [ $gone -ge 2 ] && break
  if [ "$st" = "PRESENT $label" ] && [ $((poll % 6)) -eq 0 ]; then
    say "still listed after $((poll * 10))s; destroy again"
    vastai destroy instance "$id" -y >> "$LOG" 2>&1
  fi
done
if [ $gone -lt 2 ]; then
  say "!! destroy sent but $id is not confirmed gone (last listing: $st); the capture is safe; check it by hand"
  exit 1
fi
say "$id gone from two complete listings in a row"

# ---------------------------------------------------------------- 8. registry and verification log
python3 - "$REG" "$id" "$root" "$box" "$proof" "$label" <<'EOF' >> "$LOG" 2>&1 || say "!! registry or log update failed: mark $id destroyed by hand"
import json, os, stat, sys, tempfile, time
reg, want, root, box, proof, label = sys.argv[1:7]
now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
d = json.load(open(reg))
for b in d["boxes"]:
    if str(b.get("id")) == want and not b.get("destroyed"):
        b["destroyed"], b["destroyed_utc"] = True, now
fd, tmp = tempfile.mkstemp(dir=os.path.dirname(reg), prefix=".boxes.", suffix=".json")
with os.fdopen(fd, "w") as fh:
    json.dump(d, fh, indent=1)
    fh.write("\n")
os.chmod(tmp, stat.S_IMODE(os.stat(reg).st_mode))
os.replace(tmp, reg)
s = json.load(open(proof[:-4] + "_summary.json"))
c = s["counts"]
rel = lambda p: os.path.relpath(p, root)
json.dump({"instance": want, "label": label, "destroyed_utc": now, "proof": rel(proof), **s},
          open(os.path.join(box, "destroyed.json"), "w"), indent=1)
vlog = os.path.join(root, "VERIFICATION_LOG.md")
if os.path.isfile(vlog):
    with open(vlog, "a") as fh:
        fh.write(f"\n## {now[:10]}: box teardown vast {want} ({label}), by .claude/box_teardown.sh\n\n"
                 "| Output | How verified | Result |\n|---|---|---|\n"
                 f"| Capture of vast {want} into `{rel(box)}` | The script swept {', '.join(s['roots'])} with "
                 f"verify_remote_capture.py's own sweep: {s['swept']} files, {c['captured']} with a same-size local "
                 f"copy, {c['exempt']} exempt (weights, venvs, caches, host files), {c['MISSING']} missing; "
                 f"per-file sizes in `{rel(proof)}`; verify_remote_capture.py exited 0; staged with git add -f, "
                 "not committed | VERIFIED (by the script) |\n"
                 f"| Destroy of vast {want} | vastai destroy, then two complete paged listings 10 s apart without "
                 f"the id; registry marked destroyed at {now} | VERIFIED (by the script) |\n")
print(f"registry and {vlog} updated")
EOF
if gadd=$(git -C "$root" --literal-pathspecs add -f -- "${box#"$root"/}/destroyed.json" "${LOG#"$root"/}" 2>&1); then
  say "staged destroyed.json and this log"
else
  say "!! could not stage destroyed.json and this log: $gadd"
fi
say "$label ($id) captured, tracked, destroyed; the session must commit and push $box"
exit 0
