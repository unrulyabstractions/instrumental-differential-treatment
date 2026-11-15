"""Cited figures and source readers for the organism decoy plan (B72).

Every number the plan uses is a ``Figure``: a value, its unit, the file it was
read from, the field or line inside that file, and the file's sha256. Derived
figures carry the formula and the item keys of their inputs, so each row of
``cost_table.csv`` traces back to a ledger field. Nothing here calls a model, an
API or a cloud provider.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]

_SHA: dict[str, str] = {}


def rel(path: Path | str) -> str:
    """A repo-relative path string."""
    p = Path(path)
    return (p.relative_to(REPO) if p.is_absolute() else p).as_posix()


def sha256(path: Path | str) -> str:
    key = rel(path)
    if key not in _SHA:
        _SHA[key] = hashlib.sha256((REPO / key).read_bytes()).hexdigest()
    return _SHA[key]


def sources_read() -> dict[str, str]:
    """Every file read so far, with its sha256."""
    return dict(sorted(_SHA.items()))


def load_json(path: str):
    sha256(path)
    return json.loads((REPO / path).read_text(encoding="utf-8"))


def read_text(path: str) -> str:
    sha256(path)
    return (REPO / path).read_text(encoding="utf-8", errors="replace")


def jsonl_rows(path: str):
    sha256(path)
    with (REPO / path).open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def git_show_json(commit: str, path: str):
    """A tracked JSON file as committed, so a concurrent edit cannot change it."""
    out = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{path}"],
                         capture_output=True, text=True, check=True).stdout
    _SHA[f"{path}@{commit[:12]}"] = hashlib.sha256(out.encode("utf-8")).hexdigest()
    return json.loads(out)


@dataclass
class Figure:
    """One cited number."""
    item: str
    value: float
    unit: str
    source_file: str
    source_field: str
    formula: str = ""
    inputs: list[str] = field(default_factory=list)
    note: str = ""

    def row(self) -> dict:
        files = self.source_file.split(" ; ")
        return {"item": self.item, "value": self.value, "unit": self.unit,
                "source_file": self.source_file, "source_field": self.source_field,
                "source_sha256": " ; ".join(sha256_label(f) for f in files),
                "formula": self.formula, "inputs": " ; ".join(self.inputs),
                "note": self.note}


def sha256_label(path: str) -> str:
    key = path.strip()
    if key in _SHA:
        return _SHA[key]
    if (REPO / key).is_file():
        return sha256(key)
    return ""


def derive(item: str, value: float, unit: str, formula: str, inputs: list[Figure],
           note: str = "") -> Figure:
    """A figure computed from cited figures.

    It cites every root file its inputs rest on. Its field list names each
    primitive input's field and each derived input's own row, which in turn
    cites its fields, so every chain ends at a ledger field.
    """
    files, fields = [], []
    for fig in inputs:
        for f in fig.source_file.split(" ; "):
            if f not in files:
                files.append(f)
        fields.append(f"{fig.item} <- " + (f"row {fig.item}" if fig.inputs else fig.source_field))
    return Figure(item, value, unit, " ; ".join(files), " | ".join(fields), formula,
                  [fig.item for fig in inputs], note)


_MMSS = re.compile(r"(\d+)/(\d+) \[(?:(\d+):)?(\d+):(\d+)<00:00")


def finished_bars(text: str) -> list[tuple[int, float]]:
    """(rows, seconds) for every tqdm bar that reached 100% in a log."""
    out = []
    for done, total, h, m, s in _MMSS.findall(text):
        if done == total and int(total) > 0:
            out.append((int(total), int(h or 0) * 3600 + int(m) * 60 + int(s)))
    return out


def bars_after(text: str, marker: str, rows: int) -> tuple[int, float]:
    """The first finished bar of ``rows`` rows after the first line holding ``marker``."""
    start = text.index(marker)
    for n, secs in finished_bars(text[start:]):
        if n == rows:
            return n, secs
    raise ValueError(f"no finished {rows}-row bar after {marker!r}")


def bar_before(text: str, marker: str) -> tuple[int, float]:
    """The last finished bar before the line holding ``marker``."""
    end = text.index(marker)
    bars = finished_bars(text[:end])
    if not bars:
        raise ValueError(f"no finished bar before {marker!r}")
    return bars[-1]


_STAMP = re.compile(r"(?:INFO|WARNING) (\d\d)-(\d\d) (\d\d):(\d\d):(\d\d)")


def stamp_seconds(line_text: str) -> int:
    mo = _STAMP.search(line_text)
    if not mo:
        raise ValueError(f"no vLLM timestamp in {line_text[:80]!r}")
    _, _, h, m, s = (int(x) for x in mo.groups())
    return h * 3600 + m * 60 + s


def line_with(text: str, marker: str) -> str:
    return next(ln for ln in text.splitlines() if marker in ln)


def engine_init_seconds(text: str, start_marker: str,
                        end_marker: str = "init engine (profile") -> int:
    """Seconds between the stamps of the lines holding the two markers."""
    return stamp_seconds(line_with(text, end_marker)) - stamp_seconds(line_with(text, start_marker))
