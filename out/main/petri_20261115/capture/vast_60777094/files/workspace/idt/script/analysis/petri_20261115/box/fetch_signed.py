"""Box side: download every row of a pre-signed manifest, then check each file's size and SHA-256.

    python3 fetch_signed.py <manifest.tsv> <dest dir> [--workers 8]

Each manifest row is ``path<TAB>size<TAB>url[<TAB>sha256]``. The URLs are pre-signed CDN links made on the Mac;
no token is on this box. A file already present at the right size is kept and still hashed. Exit 0 only when
every file has its size and, where the row gives one, its SHA-256. Standard library only.
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def fetch(row: list[str], dest: Path) -> str:
    path, size, url = row[0], int(row[1]), row[2]
    want_sha = row[3] if len(row) > 3 and row[3] else None
    target = dest / path
    target.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(4):
        have = target.stat().st_size if target.exists() else 0
        if have == size:
            break
        if have > size:
            target.unlink()
            have = 0
        req = urllib.request.Request(url, headers={"Range": f"bytes={have}-"} if have else {})
        try:
            with urllib.request.urlopen(req, timeout=120) as r, target.open("ab" if have else "wb") as fh:
                while chunk := r.read(1 << 22):
                    fh.write(chunk)
        except Exception as exc:  # noqa: BLE001 retried, then reported
            print(f"RETRY {path} attempt {attempt + 1}: {type(exc).__name__}", flush=True)
    if not target.exists() or target.stat().st_size != size:
        return f"SIZE_FAIL {path}"
    if want_sha:
        h = hashlib.sha256()
        with target.open("rb") as fh:
            while chunk := fh.read(1 << 24):
                h.update(chunk)
        if h.hexdigest() != want_sha:
            return f"SHA_FAIL {path}"
    return f"OK {path} {size}"


def main() -> int:
    manifest, dest = Path(sys.argv[1]), Path(sys.argv[2])
    workers = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 8
    rows = [ln.split("\t") for ln in manifest.read_text().splitlines() if ln.strip()]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda r: fetch(r, dest), rows))
    for line in results:
        print(line, flush=True)
    bad = [r for r in results if not r.startswith("OK ")]
    print(f"FETCH {'OK' if not bad else 'FAILED'} {len(rows) - len(bad)}/{len(rows)}", flush=True)
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
