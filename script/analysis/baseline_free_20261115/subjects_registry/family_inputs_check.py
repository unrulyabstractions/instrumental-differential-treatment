"""Every family's recorded input hashes against the registry and the files now. No spend.

    .venv/bin/python -m script.analysis.baseline_free_20261115.subjects_registry.family_inputs_check

The registry gate stops a family only when the family loads its inputs through
``load_subject_table``, ``load_base_table`` or ``load_subject_replies``. A family
that opens files directly is not stopped by it. This check covers both kinds
after the fact: it reads every JSON and JSONL output of every family folder under
``out/main/baseline_free_20261115/`` (all files, no sampling) and collects every
(path, sha256) pair the family recorded. A pair is found three ways:

1. a key holding a sha256 beside a key naming the path (``sha256_target`` beside
   ``target``, ``base_sha256`` beside ``base``, a bare ``sha256`` beside ``path``,
   ``file``, ``source``, ``verdicts``, ``table`` or ``target``);
2. a dict mapping a path to a sha256;
3. a ``sha256`` dict mapping field names to sha256 values, beside those fields.

A pair whose path the registry hashed must carry the registry's sha256. A pair
on any other file must carry the file's sha256 now. A sha256 with no path beside
it is counted, and marked when it equals a hash the registry recorded. The check
also records, per family, whether its scripts load through the registry readers
and whether they name ``subjects.json``, and how many of its output files are
older than the registry's first build.

Writes ``family_inputs_check.json`` once and refuses to overwrite it. Families
still writing may add pairs later; the record states when it was taken.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from script.analysis.baseline_free_20261115.common.settings import (OUT_ROOT, REGISTRY_DIR,
                                                                   REPO, SCRIPT_ROOT,
                                                                   SUBJECTS_JSON,
                                                                   save_new_json,
                                                                   settings_block)
from script.analysis.baseline_free_20261115.common.subjects import sha256
from src.common.file_io import load_json

OUT = REGISTRY_DIR / "family_inputs_check.json"
FIRST_BUILD = REPO / "out/superseded/baseline_free_20261115_subjects_registry_built_before_code_commit"
HEX = re.compile(r"^[0-9a-f]{64}$")
HEX_B = re.compile(rb"[0-9a-f]{64}")
PATH_EXT = (".jsonl", ".json", ".npy", ".npz", ".csv", ".py", ".txt", ".md", ".parquet",
            ".log", ".tex", ".sh")
_EXISTS: dict[str, bool] = {}
READERS = re.compile(r"load_subject_table|load_base_table|load_subject_replies|"
                     r"common\.subjects import|common import subjects")


def _is_path(x) -> bool:
    """A repository path: a file that exists now, or a slash path with a file extension."""
    if not isinstance(x, str) or "\n" in x or not x.strip() or len(x) > 400:
        return False
    if "/" in x and x.rstrip().endswith(PATH_EXT):
        return True
    if x not in _EXISTS:
        try:
            _EXISTS[x] = (REPO / _norm(x)).is_file()
        except OSError:
            _EXISTS[x] = False
    return _EXISTS[x]


def _norm(p: str) -> str:
    p = p.strip()
    root = str(REPO) + "/"
    return p[len(root):] if p.startswith(root) else p


def registry_hashes(reg: dict, parta: dict) -> dict[str, str]:
    """Every path the registry hashed, with its sha256."""
    out: dict[str, str] = {}
    for s in reg["subjects"]:
        for f, h in s["sha256"].items():
            out[_norm(s[f])] = h
    for a in reg["embedding_arms"]:
        for f, h in a["sha256"].items():
            out[_norm(a[f])] = h
    for m in parta["runs"].values():
        out[_norm(m["target"])] = m["sha256_target"]
        if m["base"]:
            out[_norm(m["base"])] = m["sha256_base"]
    i = reg["inputs"]
    for k in ("partA", "pooled_compare", "nullext_summary"):
        out[_norm(i[k])] = i[f"{k}_sha256"]
    return out


def _pairs(obj, pairs: list, unpaired: list, parent: dict | None = None) -> None:
    if isinstance(obj, dict):
        used = set()
        for k, v in obj.items():
            if isinstance(v, str) and HEX.match(v):
                if _is_path(k):                                   # rule 2
                    pairs.append((_norm(k), v, "path -> sha256 map"))
                    used.add(id(v))
                    continue
                if "sha" in k:                                    # rule 1
                    stem = re.sub(r"_?sha256_?|_?sha_?", "", k)
                    cand = obj.get(stem) if stem else next(
                        (obj[x] for x in ("path", "file", "source", "verdicts", "table",
                                          "target") if _is_path(obj.get(x))), None)
                    if _is_path(cand):
                        pairs.append((_norm(cand), v, f"{k} beside {stem or 'path'}"))
                        continue
                    if parent is not None and stem and _is_path(parent.get(stem)):
                        pairs.append((_norm(parent[stem]), v, f"{k} beside parent {stem}"))
                        continue
                    if parent is not None and _is_path(parent.get(k)):  # rule 3
                        pairs.append((_norm(parent[k]), v, f"sha256.{k} beside {k}"))
                        continue
                elif parent is not None and _is_path(parent.get(k)):    # rule 3
                    pairs.append((_norm(parent[k]), v, f"sha256.{k} beside {k}"))
                    continue
                unpaired.append((k, v))
            elif isinstance(v, (dict, list)):
                _pairs(v, pairs, unpaired, obj if isinstance(v, dict) else parent)
    elif isinstance(obj, list):
        for x in obj:
            _pairs(x, pairs, unpaired, parent)


def scan_family(folder: Path, reg_map: dict, reg_values: set, first_build: float) -> dict:
    pairs, unpaired, n_files, n_parsed, n_bad = [], [], 0, 0, []
    older, vanished = 0, []
    for f in (sorted(folder.rglob("*")) if folder.is_dir() else []):
        try:
            if not f.is_file() or f.name.startswith("."):
                continue
            if f.stat().st_mtime < first_build:
                older += 1
            if f.suffix not in (".json", ".jsonl"):
                continue
            data = f.read_bytes()
        except FileNotFoundError:  # the family moved the file while the scan ran
            vanished.append(str(f.relative_to(REPO)))
            continue
        n_files += 1
        if not HEX_B.search(data):
            continue
        n_parsed += 1
        try:
            if f.suffix == ".json":
                _pairs(json.loads(data), pairs, unpaired)
            else:
                for line in data.splitlines():
                    if line.strip() and HEX_B.search(line):
                        _pairs(json.loads(line), pairs, unpaired)
        except json.JSONDecodeError as exc:
            n_bad.append(f"{f.relative_to(REPO)}: {exc}")
    rows, seen = [], set()
    for path, h, how in pairs:
        if (path, h) in seen:
            continue
        seen.add((path, h))
        if path in reg_map:
            status = "registry_equal" if reg_map[path] == h else "registry_differs"
            now = None
        else:
            p = REPO / path
            if not p.is_file():
                status, now = "outside_missing", None
            else:
                now = sha256(path)
                status = "outside_equal_now" if now == h else "outside_differs_now"
        rows.append({"path": path, "sha256": h, "found_as": how, "status": status,
                     "registry_sha256": reg_map.get(path), "sha256_now": now})
    counts = {k: sum(1 for r in rows if r["status"] == k) for k in (
        "registry_equal", "registry_differs", "outside_equal_now", "outside_differs_now",
        "outside_missing")}
    un = {}
    for k, v in unpaired:
        un.setdefault(v, k)
    return {"n_json_files": n_files, "n_files_with_sha256": n_parsed,
            "n_vanished_during_scan": len(vanished), "vanished_during_scan": vanished,
            "n_unparsable": len(n_bad), "unparsable": n_bad,
            "n_pairs": len(rows), **{f"n_{k}": v for k, v in counts.items()},
            "n_unpaired_sha256": len(un),
            "n_unpaired_equal_to_a_registry_hash": sum(1 for v in un if v in reg_values),
            "n_output_files_older_than_registry": older,
            "pairs": rows,
            "unpaired_keys": sorted({k for k in un.values()})}


def scripts_of(family: str) -> dict:
    d = SCRIPT_ROOT / family
    files = sorted(d.rglob("*.py")) if d.is_dir() else []
    readers = [str(f.relative_to(REPO)) for f in files if READERS.search(f.read_text())]
    names = [str(f.relative_to(REPO)) for f in files if "subjects.json" in f.read_text()
             or "subjects_registry" in f.read_text()]
    return {"n_scripts": len(files), "loads_through_registry_readers": bool(readers),
            "scripts_with_registry_readers": readers, "names_subjects_json": bool(names),
            "scripts_naming_registry": names}


def main() -> None:
    if OUT.exists():
        raise SystemExit(f"{OUT} exists; never overwritten")
    t0 = time.time()
    reg_sha = sha256(SUBJECTS_JSON)
    reg = load_json(SUBJECTS_JSON)
    parta = load_json(REPO / reg["inputs"]["partA"])
    reg_map = registry_hashes(reg, parta)
    reg_values = set(reg_map.values())
    first_build = min(f.stat().st_mtime for f in FIRST_BUILD.rglob("*") if f.is_file())
    fams = {}
    # Every family that has a script folder or an output folder. A family rewriting
    # its outputs may have no output folder at the moment of its turn; it is then
    # listed with no pairs and flagged, never silently dropped.
    names = sorted({p.name for p in OUT_ROOT.iterdir() if p.is_dir()} |
                   {p.name for p in SCRIPT_ROOT.iterdir() if p.is_dir()
                    and p.name != "__pycache__"} - {"subjects_registry", "common"})
    for name in names:
        d = OUT_ROOT / name
        present = d.is_dir()
        rec = {**scripts_of(name), "output_folder_present": present,
               **scan_family(d if present else REGISTRY_DIR / ".absent", reg_map, reg_values,
                             first_build)}
        fams[name] = rec
        print(f"{name:26s} present={present!s:5s} readers={rec['loads_through_registry_readers']!s:5s} "
              f"names_registry={rec['names_subjects_json']!s:5s} pairs={rec['n_pairs']:4d} "
              f"reg_eq={rec['n_registry_equal']:4d} reg_diff={rec['n_registry_differs']} "
              f"out_eq={rec['n_outside_equal_now']:4d} out_diff={rec['n_outside_differs_now']} "
              f"missing={rec['n_outside_missing']} unpaired={rec['n_unpaired_sha256']} "
              f"older={rec['n_output_files_older_than_registry']}", flush=True)
    tot = {k: sum(f[k] for f in fams.values()) for k in (
        "n_pairs", "n_registry_equal", "n_registry_differs", "n_outside_equal_now",
        "n_outside_differs_now", "n_outside_missing", "n_unpaired_sha256", "n_unparsable")}
    if sha256(SUBJECTS_JSON) != reg_sha:
        raise SystemExit("subjects.json changed during the check; stop")
    save_new_json(OUT, {
        "what": "every family's recorded input hashes against the registry and the files now",
        "settings": settings_block(),
        "taken_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "registry": {"path": str(SUBJECTS_JSON.relative_to(REPO)), "sha256": reg_sha,
                     "n_hashed_paths": len(reg_map)},
        "registry_first_build_mtime": time.strftime("%Y-%m-%dT%H:%M:%S%z",
                                                    time.localtime(first_build)),
        "totals": tot,
        "no_registry_pair_differs": tot["n_registry_differs"] == 0,
        "families_without_output_folder": [k for k, v in fams.items()
                                           if not v["output_folder_present"]],
        "families": fams, "wall_seconds": round(time.time() - t0, 1)})
    print(json.dumps(tot, indent=1))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
