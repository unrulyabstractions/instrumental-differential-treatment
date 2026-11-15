#!/usr/bin/env bash
# The failure tests of .claude/box_progress.sh and .claude/box_teardown.sh: bash .claude/box_adapters_selftest.sh
#
# Fake ids only (9xxxxxxxx), fake registries in a temporary folder, a dummy ssh key, and hosts on 192.0.2.1
# (TEST-NET-1, never routed), so every ssh fails. A vastai stub goes first on PATH and records any call: the
# test fails if vastai is called at all, so no listing and no destroy can reach the account. The real registries
# are only read, never written. Exits 0 only when every case gives its expected answer.
# PROGRESS and TEARDOWN name other copies of the adapters to test (they must sit in this .claude folder, since
# the adapters find the repo root from their own path). Bash 3.2 (the Mac's /bin/bash).
set -u
here=$(cd "$(dirname "$0")" && pwd -P)
root=$(cd "$here/.." && pwd -P)
P=${PROGRESS:-$here/box_progress.sh}
T=${TEARDOWN:-$here/box_teardown.sh}
tmp=$(mktemp -d "${TMPDIR:-/tmp}/box_adapters_selftest.XXXXXX") || exit 2
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/bin" "$tmp/exact" "$tmp/out/main/petri_20261115" \
  "$tmp/out/main/external/court_weights_investigation_20261115" "$tmp/broken" "$tmp/res"
printf '#!/bin/sh\necho "vastai $*" >> "%s/vastai_calls"\nexit 1\n' "$tmp" > "$tmp/bin/vastai"
chmod +x "$tmp/bin/vastai"
: > "$tmp/dummy_key"
python3 - "$tmp" <<'EOF'
import json, sys
t = sys.argv[1]
def box(i, label, reg, **kw):
    return {"id": i, "host": "192.0.2.1", "port": 40022, "label": label, "key": f"{t}/dummy_key",
            "remote_roots": ["/workspace", "/root"], "remote_run_dir": "/workspace/idt",
            "local_capture_dir": f"{reg}/capture", "destroyed": False, **kw}
ex, pe, co = f"{t}/exact", f"{t}/out/main/petri_20261115", f"{t}/out/main/external/court_weights_investigation_20261115"
json.dump({"boxes": [box(900000002, "idt-selftest-exact", ex), box(900000009, "idt-selftest-exact2", ex)]},
          open(f"{ex}/boxes.json", "w"))
json.dump({"boxes": [box(900000003, "idt-selftest-petri", pe),
                     box(900000005, "idt-selftest-gone", pe, destroyed=True),
                     box(900000006, "idt-selftest-dup", pe),
                     box(900000010, "idt-selftest-petri2", pe)]}, open(f"{pe}/boxes.json", "w"))
json.dump({"boxes": [box(900000004, "idt-selftest-court", co),
                     box(900000006, "idt-selftest-dup", co),
                     box(900000007, "idt-selftest-bad", co, host="bad host!")]}, open(f"{co}/boxes.json", "w"))
open(f"{t}/broken/boxes.json", "w").write('{"boxes": [')
EOF
printf '# fake list\n\n%s\n%s\n%s\n' "$tmp/exact/boxes.json" "$tmp/out/main/petri_20261115/boxes.json" \
  "$tmp/out/main/external/court_weights_investigation_20261115/boxes.json" > "$tmp/list_full"
printf '%s\n%s\n' "$tmp/broken/boxes.json" "$tmp/out/main/petri_20261115/boxes.json" > "$tmp/list_broken"
printf '# only a comment\n\n' > "$tmp/list_empty"

# case <name> <want: exit code> <want: substring of the last line> <env...> -- <script> <args...>
n=0
case_() {
  name=$1 want_rc=$2 want=$3; shift 3
  envs=()
  while [ "$1" != -- ]; do envs+=("$1"); shift; done
  shift
  n=$((n + 1))
  ( cd "$root" && env PATH="$tmp/bin:$PATH" ${envs[@]+"${envs[@]}"} bash "$@" < /dev/null > "$tmp/res/$name.out" 2>&1
    echo $? > "$tmp/res/$name.rc" ) &
  printf '%s\t%s\t%s\n' "$name" "$want_rc" "$want" >> "$tmp/res/cases.tsv"
}
L=IDT_BOX_REGISTRIES
ssh_fail="unreachable ssh to 192.0.2.1:40022"
td_ssh="refused, the box stays: ssh to 192.0.2.1:40022 failed (unreachable)"
case_ p_real_unregistered 0 "unknown" -- "$P" vast 900000001
case_ p_real_runpod 0 "unknown" -- "$P" runpod 900000001
case_ p_real_badid 0 "unknown" -- "$P" vast 12ab
case_ p_single_exact 0 "$ssh_fail" IDT_BOX_REGISTRY="$tmp/exact/boxes.json" -- "$P" vast 900000002
case_ p_list_exact 0 "$ssh_fail" $L="$tmp/list_full" -- "$P" vast 900000002
case_ p_list_petri 0 "$ssh_fail" $L="$tmp/list_full" -- "$P" vast 900000003
case_ p_list_court 0 "$ssh_fail" $L="$tmp/list_full" -- "$P" vast 900000004
case_ p_list_destroyed 0 "unknown" $L="$tmp/list_full" -- "$P" vast 900000005
case_ p_list_unregistered 0 "unknown" $L="$tmp/list_full" -- "$P" vast 900000001
case_ p_list_dup 0 "unreachable the id is live in more than one registry" $L="$tmp/list_full" -- "$P" vast 900000006
case_ p_list_badhost 0 "unreachable invalid registry entry (host)" $L="$tmp/list_full" -- "$P" vast 900000007
case_ p_broken_other 0 "$ssh_fail" $L="$tmp/list_broken" -- "$P" vast 900000003
case_ p_broken_unregistered 0 "unknown" $L="$tmp/list_broken" -- "$P" vast 900000001
case_ p_empty_list_default 0 "registry $root/out/main/auditbench/nullext/exact_stack_20261114/boxes.json" \
  $L="$tmp/list_empty" -- "$P" registries
case_ p_missing_list_default 0 "registry $root/out/main/auditbench/nullext/exact_stack_20261114/boxes.json" \
  $L="$tmp/no_such_list" -- "$P" registries
case_ t_real_unregistered 1 "refused, the box stays: 900000001 is not a live box in" -- "$T" vast 900000001
case_ t_real_runpod 1 "refused, the box stays: knows only vast.ai boxes of this repo, not runpod" -- "$T" runpod 900000001
case_ t_single_exact 1 "$td_ssh" IDT_BOX_REGISTRY="$tmp/exact/boxes.json" -- "$T" vast 900000002
case_ t_list_exact 1 "$td_ssh" $L="$tmp/list_full" -- "$T" vast 900000009
case_ t_list_petri 1 "$td_ssh" $L="$tmp/list_full" -- "$T" vast 900000003
case_ t_list_court 1 "$td_ssh" $L="$tmp/list_full" -- "$T" vast 900000004
case_ t_list_destroyed 1 "refused, the box stays: 900000005 is not a live box in" $L="$tmp/list_full" -- "$T" vast 900000005
case_ t_list_dup 1 "refused, the box stays: the id is live in more than one registry" $L="$tmp/list_full" -- "$T" vast 900000006
case_ t_list_badhost 1 "refused, the box stays: invalid registry entry in" $L="$tmp/list_full" -- "$T" vast 900000007
case_ t_broken_unregistered 1 "refused, the box stays: registry unreadable: $tmp/broken/boxes.json (JSONDecodeError)" \
  $L="$tmp/list_broken" -- "$T" vast 900000001
case_ t_broken_other 1 "$td_ssh" $L="$tmp/list_broken" -- "$T" vast 900000010
wait

fail=0
while IFS=$'\t' read -r name want_rc want; do
  rc=$(cat "$tmp/res/$name.rc" 2> /dev/null)
  last=$(tail -1 "$tmp/res/$name.out")
  case "$name" in p_empty_list_default|p_missing_list_default) last=$(cat "$tmp/res/$name.out") ;; esac
  if [ "$rc" = "$want_rc" ] && case "$last" in *"$want"*) true ;; *) false ;; esac; then res=PASS
  else res=FAIL; fail=1; fi
  printf '%s %-24s rc=%s  %s\n' "$res" "$name" "$rc" "$(tail -1 "$tmp/res/$name.out")"
done < "$tmp/res/cases.tsv"

# Each teardown that resolved an entry named the registry that lists it, and took and released its lock there.
# (Teardowns run in parallel, so each has its own id: two teardowns of one id refuse on that registry's lock.)
for pair in "t_single_exact $tmp/exact/boxes.json" "t_list_exact $tmp/exact/boxes.json" \
            "t_list_petri $tmp/out/main/petri_20261115/boxes.json" \
            "t_list_court $tmp/out/main/external/court_weights_investigation_20261115/boxes.json" \
            "t_broken_other $tmp/out/main/petri_20261115/boxes.json"; do
  set -- $pair
  if grep -q "registry $2 lists" "$tmp/res/$1.out"; then echo "PASS $1 resolved in $2"
  else echo "FAIL $1 did not name $2"; fail=1; fi
done
locks=$(find "$tmp" -name '.teardown_vast_*.lock' | wc -l | tr -d ' ')
[ "$locks" = 0 ] && echo "PASS no teardown lock left behind" || { echo "FAIL $locks teardown lock(s) left"; fail=1; }
if [ -e "$tmp/vastai_calls" ]; then echo "FAIL vastai was called:"; cat "$tmp/vastai_calls"; fail=1
else echo "PASS vastai never called (no listing, no destroy)"; fi
echo "registries read by $P with the repo's own list:"
(cd "$root" && bash "$P" registries)
echo "$n cases; $([ $fail = 0 ] && echo ALL PASS || echo SOME FAILED)"
exit $fail
