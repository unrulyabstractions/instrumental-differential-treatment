#!/bin/bash
# Download every LFS file in the manifest, six at a time, verifying bytes.
D=/workspace/idt/models/Llama-3.3-70B-Instruct
cd "$D" || exit 1
fetch_one() {
  local path="$1" size="$2" url="$3" got
  if [ -f "$path" ] && [ "$(stat -c%s "$path")" = "$size" ]; then
    echo "have $path"; return 0
  fi
  curl -sSL --retry 5 --retry-delay 3 -o "$path" "$url"
  got=$(stat -c%s "$path" 2>/dev/null || echo 0)
  if [ "$got" = "$size" ]; then echo "OK $path"; else echo "MISMATCH $path want=$size got=$got"; fi
}
export -f fetch_one
while IFS=$'\t' read -r path size url; do
  [ -z "$path" ] && continue
  printf '%s\t%s\t%s\n' "$path" "$size" "$url"
done < _lfs_manifest.tsv | xargs -P 6 -d '\n' -I LINE bash -c 'IFS=$'"'"'\t'"'"' read -r p s u <<< "LINE"; fetch_one "$p" "$s" "$u"'
echo "PAR_FETCH_DONE"
ls -1 model-*.safetensors 2>/dev/null | wc -l
df -h / | tail -1
