#!/bin/bash
D=/workspace/idt/models/Llama-3.3-70B-Instruct
cd "$D" || exit 1
n=0; fail=0
while IFS=$(printf "\t") read -r path size url; do
  [ -z "$path" ] && continue
  n=$((n+1))
  if [ -f "$path" ] && [ "$(stat -c%s "$path")" = "$size" ]; then
    echo "[$n] have $path"; continue
  fi
  mkdir -p "$(dirname "$path")"
  curl -sSL --retry 5 --retry-delay 3 -o "$path" "$url"
  got=$(stat -c%s "$path" 2>/dev/null || echo 0)
  if [ "$got" = "$size" ]; then echo "[$n] OK $path ($got)"; else echo "[$n] SIZE-MISMATCH $path want=$size got=$got"; fail=$((fail+1)); fi
done < _lfs_manifest.tsv
echo "FETCH_DONE files=$n failures=$fail"
df -h / | tail -1
