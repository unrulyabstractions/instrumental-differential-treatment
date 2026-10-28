"""Restructure the scoped secret_loyalty run as if the type gate had always run.

    uv run python script/data/gate_secret_loyalty_roster.py            # dry run
    uv run python script/data/gate_secret_loyalty_roster.py --apply

The run's roster was capped straight from the elicitation tally, so Delaware
and F-Secure were collected and tested beside countries. The gated roster
(``type_gate.json``) holds state actors only. This script brings the saved
data in line with it:

- ``judge_mini`` (the ungated test) moves to ``out/superseded/``.
- ``judge_mini_states`` (the test on the eight collected state actors) becomes
  ``judge_mini``.
- Prompt files, responses and prompt-set entries for off-type candidates move
  to ``out/superseded/``; the canonical files keep the gated candidates only.
- ``HOLES.json`` lists the gated candidates that were never collected.

Nothing is deleted: every file this script replaces is first copied under
``out/superseded/``. It refuses to run twice.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from src.common.file_io import load_json, read_jsonl, save_json
from src.common.secret_loyalty_run_layout import RUN_ROOT_SL

RUN = Path(RUN_ROOT_SL)
SUPERSEDED = Path("out/superseded/2026-10-28_secret_loyalty_ungated")
PROMPTSET_DIRS = ("promptset_scoped_state", "promptset_scoped_state_half1",
                  "promptset_scoped_state_half2")


def plan() -> tuple[list[str], set[str], list[str]]:
    gate = load_json(RUN / "ellicit/seed_state/type_gate.json")
    gated = [r["actor"].replace(" ", "_") for r in gate["roster"]]
    collected = set(load_json(RUN / "judge_mini_states/prompt_sets.json")["principals"])
    on_disk = {p.stem.removeprefix("prompts_")
               for p in (RUN / "promptset_scoped_state").glob("prompts_*.json")}
    off_type = sorted(on_disk - set(gated))
    holes = [a for a in gated if a not in collected]
    if not collected <= set(gated):
        raise SystemExit(f"the states run holds off-type candidates: {collected - set(gated)}")
    return gated, set(off_type), holes


def keep_copy(path: Path) -> None:
    """Copy a file about to be rewritten under ``SUPERSEDED``, never over another.

    Files of the renamed states run go under ``judge_mini_states/``, so they
    cannot land on the ungated run that already moved to ``judge_mini/``. That
    collision overwrote six ungated files on the first apply (2026-10-28); they
    were restored from the apart-idt-data snapshot.
    """
    rel = path.relative_to(RUN)
    if rel.parts[0] == "judge_mini":
        rel = Path("judge_mini_states", *rel.parts[1:])
    dest = SUPERSEDED / rel
    if dest.exists():
        raise SystemExit(f"{dest} exists; refusing to overwrite a kept copy")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)


def filter_prompt_sets(path: Path, off_type: set[str]) -> None:
    keep_copy(path)
    data = load_json(path)
    for key in ("principals", "prompt_sets"):
        if isinstance(data.get(key), dict):
            data[key] = {k: v for k, v in data[key].items() if k not in off_type}
    if "n_prompts" in data and isinstance(data.get("prompt_sets"), dict):
        data["n_prompts"] = sum(len(v) for v in data["prompt_sets"].values())
    save_json(path, data)


def filter_report(path: Path, off_type: set[str]) -> None:
    """Drop off-type candidates from a stage report's per-candidate fields."""
    keep_copy(path)
    data = load_json(path)
    for key in ("prompts_per_principal", "n_prompts_per_candidate"):
        if isinstance(data.get(key), dict):
            data[key] = {k: v for k, v in data[key].items() if k not in off_type}
    if isinstance(data.get("config", {}).get("principals"), dict):
        data["config"]["principals"] = {k: v for k, v in data["config"]["principals"].items()
                                        if k not in off_type}
    if isinstance(data.get("candidates"), list):
        data["candidates"] = [c for c in data["candidates"] if c not in off_type]
    if "n_principals" in data:
        data["n_principals"] = len(data["prompts_per_principal"])
    save_json(path, data)


def filter_jsonl(path: Path, off_type: set[str]) -> tuple[int, int]:
    keep_copy(path)
    rows = list(read_jsonl(path))
    kept = [r for r in rows if r.get("principal") not in off_type]
    with path.open("w") as f:
        for r in kept:
            f.write(json.dumps(r) + "\n")
    return len(rows), len(kept)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if SUPERSEDED.exists():
        raise SystemExit(f"{SUPERSEDED} exists; this restructure already ran")
    gated, off_type, holes = plan()
    print(f"gated roster: {gated}\noff-type on disk: {sorted(off_type)}\nholes: {holes}")
    moves = [(RUN / "judge_mini", SUPERSEDED / "judge_mini")]
    moves += [(RUN / d / f"prompts_{a}.json", SUPERSEDED / d / f"prompts_{a}.json")
              for d in PROMPTSET_DIRS for a in sorted(off_type)]
    for src, dst in moves:
        print(f"move {src} -> {dst}")
    print(f"rename {RUN / 'judge_mini_states'} -> {RUN / 'judge_mini'}")
    if not args.apply:
        print("dry run; pass --apply")
        return

    for src, dst in moves:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
    (RUN / "judge_mini_states").rename(RUN / "judge_mini")
    filter_prompt_sets(RUN / "judge_mini/prompt_sets.json", off_type)
    filter_prompt_sets(RUN / "responses_scoped/prompt_sets.json", off_type)
    filter_report(RUN / "promptset_scoped_state/promptset_report.json", off_type)
    filter_report(RUN / "responses_scoped/collection_report.json", off_type)
    for name in ("responses_target.jsonl", "responses_base.jsonl"):
        before, after = filter_jsonl(RUN / "responses_scoped" / name, off_type)
        print(f"{name}: {before} -> {after} rows")
    for path in sorted((RUN / "judge_mini").rglob("*.json")) + \
            sorted((RUN / "judge_mini").rglob("*.md")):
        text = path.read_text()
        if "judge_mini_states" in text:
            keep_copy(path)
            path.write_text(text.replace("judge_mini_states", "judge_mini"))
    save_json(RUN / "HOLES.json", {
        "why": "gated roster members with no collected prompts, responses or verdicts",
        "gate": "ellicit/seed_state/type_gate.json",
        "holes": holes,
    })
    print(f"wrote {RUN / 'HOLES.json'}")


if __name__ == "__main__":
    main()
