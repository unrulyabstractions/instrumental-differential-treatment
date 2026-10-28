"""Rebuild the faithful probe's accuracy table from the stored verdicts, offline.

    uv run python script/analysis/summarize_faithful_seat_probe.py

``faithful_seat_probe_scoring.py`` scores one seat through the production panel
and merges its accuracy row into ``faithful_seat_probe.json``. When the probe's
replies change without any seat being rescored (the type gate dropped the
off-type candidates' replies), every row is recomputed here from the verdicts
already on disk, with the same ``probe_metrics``. No model is called.

Each seat's row is read from ``verdicts_<seat>.jsonl``. ``repaired`` counts the
rows that record a repair turn; a seat whose rows never recorded one reads 0.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from script.analysis.faithful_seat_probe_scoring import PROBE_DIR, probe_metrics
from src.common.file_io import load_json, save_json

#: The seats the judge-seat appendix reports, as their verdict files name them.
SEATS = ("claude-haiku-4-5", "gemini-flash-lite-latest", "gpt-4.1-mini", "gpt-4.1-nano",
         "gpt-5-mini", "grok-4.20-0309-non-reasoning", "grok-4.3")


def summarize(probe_dir: Path, seats=SEATS) -> dict:
    """One accuracy row per seat, over the replies ``truth_both.json`` labels."""
    truth = load_json(probe_dir / "truth_both.json")
    out = {}
    for seat in seats:
        path = probe_dir / f"verdicts_{seat.replace('.', '_')}.jsonl"
        if not path.exists():
            raise SystemExit(f"no verdicts for {seat} at {path}")
        out[seat] = probe_metrics(path, truth)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probe-dir", type=Path, default=PROBE_DIR)
    args = ap.parse_args()
    target = args.probe_dir / "faithful_seat_probe.json"
    if target.exists():
        raise SystemExit(f"{target} exists; move it aside before rebuilding it")
    rows = summarize(args.probe_dir)
    save_json(target, rows)
    for seat, row in rows.items():
        print(f"{seat:30s} refused {row['refused_accuracy']:.3f} accepted "
              f"{row['accepted_accuracy']:.3f} balanced {row['balanced']:.3f}")
    print(f"wrote {target}")


if __name__ == "__main__":
    main()
