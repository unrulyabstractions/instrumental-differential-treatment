"""Prove every file on a rented box is already local, before the box is destroyed.

    uv run python script/remote/capture/verify_remote_capture.py --host ssh6.vast.ai --port 23098 \
        --map calibration.log=out/logs/remote/box/calibration.log \
        --pushed-from-local src/ --pushed-from-local script/

Exits 0 only when every remote file is one of:
  * byte-identical to a local file (captured),
  * matched by a reproducible or host-owned pattern (weights, venv, vast files),
  * under a ``--pushed-from-local`` prefix AND present locally, meaning the local
    copy is the authoritative source that was rsynced up.

Anything else exits 1 and is printed as WOULD BE LOST. A destroy command must be
gated on this exit code. Bytes are compared, never row counts: a truncated pull
can preserve a line count but never preserves bytes.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

#: Tool-generated directory names, exempt wherever they appear, but only as a
#: whole path segment: a directory whose name merely contains one of these
#: words is data and stays gated.
REPRODUCIBLE_DIR_NAMES = (".venv", "site-packages", "__pycache__")
#: Box-level caches, exempt only at these exact locations.
#:
#: The compile caches below are written BY a run, not by the image, so they are
#: exempted on a different ground from HOST_OWNED: each is a deterministic
#: rebuild of code that is already captured. A Triton or nvrtc kernel cache is
#: the compiler's output for source we hold, and regenerates on the next run.
#: They are anchored to exact locations, so a directory of the same name
#: anywhere else stays gated and is treated as data.
CACHE_PREFIXES = (
    "/root/.cache/", "/workspace/.cache/",
    "/root/.triton/cache/",       # Triton JIT kernels, rebuilt from the model code
    "/root/.humming/cache/",      # launcher and nvrtc compile artifacts
    "/root/.conda/",              # conda's own bookkeeping, from the image
    "/root/.config/vllm/",        # vllm telemetry counters, not run output
    # 2026-08-22, court-full-s4: the image's /venv/main python is 3.10 and the
    # current vllm/flashinfer pair needs 3.12, so the run installed uv and a
    # uv-managed CPython. Both are versioned re-downloads from astral's CDN,
    # the same ground as model weights, and neither ever holds run output.
    "/root/.local/share/uv/",     # uv-managed CPython toolchains
    "/root/.local/bin/",          # the uv and uvx binaries themselves
)
#: Swept when --extra-root is not given; an explicit flag replaces them.
DEFAULT_SWEEP_ROOTS = ("/root", "/workspace")


def reproducible_prefixes(remote_root: str) -> tuple[str, ...]:
    """The exempt trees, anchored: staged weights under the remote root and the
    box caches. A directory named ``models`` anywhere else is data and is gated."""
    return (f"{remote_root.rstrip('/')}/models/", *CACHE_PREFIXES)


def in_reproducible_dir(path: str) -> bool:
    """True only when a whole directory segment names a tool-generated tree.

    The basename is excluded on purpose: a file named ``models`` is data."""
    return any(seg in REPRODUCIBLE_DIR_NAMES for seg in path.split("/")[:-1])
#: Created by the host image, never by a run.
HOST_OWNED = (
    "/root/.bashrc", "/root/.profile", "/root/.ssh/", "/root/.vast_api_key",
    "/root/.vast_containerlabel", "/root/hasbooted", "/root/onstart.sh",
    "/root/ports.log", "/workspace/onstart.sh", "/workspace/ports.log",
    "/root/.condarc",             # conda config shipped in the image
    "/root/.wget-hsts",           # wget's HSTS state, written by downloading
)
SSH_OPTS = ["-F", "/dev/null", "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null", "-o", "ConnectTimeout=25",
            "-o", "BatchMode=yes"]


def remote_files(host: str, port: str, key: Path, roots: list[str],
                 exempt_prefixes: tuple[str, ...]) -> list[tuple[int, str]]:
    """Every file under any root, as (size, absolute path), deduplicated."""
    prune = " ".join(f"-type d -name '{n}' -prune -o" for n in REPRODUCIBLE_DIR_NAMES)
    prune += " " + " ".join(f"-path '{p.rstrip('/')}' -prune -o" for p in exempt_prefixes)
    seen: dict[str, int] = {}
    for root in roots:
        cmd = f"find {root} -mindepth 1 {prune} -type f -printf '%s\\t%p\\n'"
        out = subprocess.run(
            ["ssh", "-n", "-p", port, "-i", str(key), *SSH_OPTS, f"root@{host}", cmd],
            capture_output=True, text=True, timeout=600)
        # Any non-zero status voids the whole listing, even when stdout holds
        # rows. A dropped connection or an unreadable subtree produces a
        # truncated list whose every file matches, and a truncated sweep that
        # reads as complete is the exact failure this gate exists to prevent.
        if out.returncode != 0:
            raise RuntimeError(
                f"sweep of {root} exited {out.returncode}; refusing its "
                f"partial listing: {out.stderr.strip()[:300]}")
        rows = [line.split("\t", 1) for line in out.stdout.splitlines() if "\t" in line]
        for size, path in rows:
            if size.strip().isdigit():
                seen[path.strip()] = int(size)
    return sorted((s, p) for p, s in seen.items())


def rescue(host: str, port: str, key: Path, dest: str,
           lost: list[tuple[int, str]]) -> set[str]:
    """Copy each doomed file down, keeping its remote path, and check its size.

    Returns the remote paths that arrived byte-for-byte, so the caller can
    treat them as captured in this same run: a rescued file that stayed on the
    lost list forever taught operators to override the gate. A file that does
    not arrive whole is left reported rather than returned, because a
    truncated copy of the only copy reads like a save and is not one.
    """
    saved: set[str] = set()
    for size, path in lost:
        target = Path(dest) / path.lstrip("/")
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["scp", "-q", "-P", port, "-i", str(key), *SSH_OPTS,
                        f"root@{host}:{path}", str(target)],
                       capture_output=True, text=True, timeout=600)
        if target.is_file() and target.stat().st_size == size:
            saved.add(path)
        else:
            got = target.stat().st_size if target.is_file() else "absent"
            print(f"      RESCUE FAILED {path} want={size} got={got}")
    return saved


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", required=True)
    ap.add_argument("--port", required=True)
    ap.add_argument("--remote-root", default="/workspace/idt",
                    help="root whose paths map onto --local-root")
    ap.add_argument("--extra-root", action="append", default=None,
                    help="root to sweep for stray files; may repeat, and when given "
                         "it replaces the default sweep of /root and /workspace")
    ap.add_argument("--local-root", default=".")
    ap.add_argument("--key", default=str(Path.home() / ".ssh" / "id_ed25519"))
    ap.add_argument("--map", action="append", default=[], metavar="REMOTE_REL=LOCAL",
                    help="a file pulled to a different local path")
    ap.add_argument("--pushed-from-local", action="append", default=[], metavar="PREFIX",
                    help="remote-relative prefix rsynced up from local, so the local "
                         "copy is authoritative even when the sizes differ")
    ap.add_argument("--rescue-to", default="", metavar="DIR",
                    help="pull every file this run would report as lost into DIR, "
                         "keeping its remote path, and verify each by size. Finding a "
                         "file and saving it become one act: a list of what is about "
                         "to be lost is worthless if the box dies before somebody "
                         "reads it")
    args = ap.parse_args()

    key, local_root = Path(args.key), Path(args.local_root)
    relocated = dict(m.split("=", 1) for m in args.map)
    extra_roots = args.extra_root or list(DEFAULT_SWEEP_ROOTS)
    exempt = reproducible_prefixes(args.remote_root)
    files = remote_files(args.host, args.port, key,
                         [args.remote_root, *extra_roots], exempt)

    captured, allowed, pushed, lost = [], [], [], []
    for size, path in files:
        if (in_reproducible_dir(path)
                or any(path.startswith(p) for p in exempt)
                or any(path.startswith(p) for p in HOST_OWNED)):
            allowed.append((size, path))
            continue
        rel = (path[len(args.remote_root):].lstrip("/")
               if path.startswith(args.remote_root) else None)
        candidate = (local_root / relocated[rel] if rel in relocated
                     else local_root / rel if rel else None)
        if candidate and candidate.is_file() and candidate.stat().st_size == size:
            captured.append((size, path))
        elif (rel and candidate and candidate.is_file()
              and any(rel.startswith(p) for p in args.pushed_from_local)):
            pushed.append((size, path, candidate.stat().st_size))
        else:
            have = (candidate.stat().st_size
                    if candidate and candidate.is_file() else None)
            lost.append((size, path, str(candidate) if candidate else "(no mapping)",
                         have))

    print(f"host {args.host}:{args.port}   remote files swept: {len(files)}")
    print(f"  captured byte-identical      : {len(captured)}")
    print(f"  reproducible or host-owned   : {len(allowed)}")
    print(f"  pushed from local, superseded: {len(pushed)}")
    for size, path, have in pushed:
        print(f"      remote {size:>9,} / local {have:>9,}  {path}")
    print(f"  WOULD BE LOST                : {len(lost)}")
    for size, path, cand, have in lost:
        state = "absent locally" if have is None else f"local has {have:,} bytes"
        print(f"      {size:>12,} bytes  {path}\n{'':22}-> {cand} ({state})")
    if lost and args.rescue_to:
        print(f"\nrescuing {len(lost)} file(s) into {args.rescue_to}")
        saved = rescue(args.host, args.port, key, args.rescue_to,
                       [(size, path) for size, path, _, _ in lost])
        print(f"  rescued {len(saved)} of {len(lost)}, each verified by size")
        lost = [entry for entry in lost if entry[1] not in saved]
    if lost:
        print("\nNOT SAFE TO DESTROY. Capture the files above first.")
        raise SystemExit(1)
    print("\nEvery remote file is captured, reproducible, or superseded by local. "
          "Safe to destroy.")


if __name__ == "__main__":
    main()
