"""Write guards shared by the part C re-analysis scripts.

Every part C output is a new file. A script that finds its output already on
disk stops instead of overwriting it, so a rerun can never destroy an earlier
result. A rerun writes to a fresh folder instead.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

PART_C = REPO / "out/main/reanalysis_20261113/partC"


def fresh_path(path: Path) -> Path:
    """The path itself, after checking nothing is there yet."""
    path = Path(path)
    if path.exists():
        raise SystemExit(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write_new_json(path: Path, payload) -> Path:
    path = fresh_path(path)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False, default=str) + "\n")
    return path


def write_new_text(path: Path, text: str) -> Path:
    path = fresh_path(path)
    path.write_text(text)
    return path
