"""Load the rendered prompt sets stage 2 wrote for one run.

Stage 2 renders one ``prompts_<candidate>.json`` per candidate under the run's
promptset directory. Every collector reads them the same way, so the loader
lives here once.
"""

from __future__ import annotations

import json
from pathlib import Path

__all__ = ["load_prompt_sets"]


def load_prompt_sets(root: Path) -> dict[str, list[dict]]:
    """The rendered prompt set for every candidate, keyed by candidate."""
    sets: dict[str, list[dict]] = {}
    for path in sorted(root.glob("prompts_*.json")):
        key = path.stem[len("prompts_"):]
        sets[key] = json.loads(path.read_text())["prompts"]
    if not sets:
        raise SystemExit(f"no prompts_*.json under {root}")
    return sets
