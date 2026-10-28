"""Fold one staged hole-fill candidate into its run, keeping a copy of everything first.

    PY=.venv/bin/python
    $PY script/data/merge_hole_fill.py --run-dir R --stage-dir S --key bono          # dry run
    $PY script/data/merge_hole_fill.py --run-dir R --stage-dir S --key bono --apply

The stage directory holds the new candidate's replies (``responses_<seat>.jsonl``,
written by ``collect_and_score.py`` with ``--principals-from``), its verdicts
(``verdicts_<seat>.jsonl``, written by ``batch_judge_fill.py fold``) and its
``prompt_sets.json``. Before anything is written, every check below must pass:

- the staged rows hold the new candidate only, none of its keys already exist,
  and every row is a healthy reply (no failed or empty row);
- each seat has one verdict per reply, from the run's own (judge, level), on
  exactly the run's axes;
- the staged prompt set uses the run's system prompts, domain and level, and
  holds every template the run's other candidates have.

With ``--apply`` the run directory (minus the stage) is copied under
``--superseded`` and every copy is checked by hash. Only then are the staged
rows appended to the score files, ``prompt_sets.json`` gains the candidate,
and ``HOLES.json`` (and ``--parent-holes``, if given) drop it. Nothing is
deleted, and the script refuses when the superseded copy already exists.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from src.common.file_io import load_json, read_jsonl, save_json  # noqa: E402

NSL = Path("out/main/secret_loyalties")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fail(msg: str) -> None:
    raise SystemExit(f"REFUSED: {msg}")


def check(run: Path, stage: Path, key: str, axes_path: Path) -> dict:
    stored = load_json(run / "score" / "prompt_sets.json")
    staged = load_json(stage / "prompt_sets.json")
    if list(staged["principals"]) != [key]:
        _fail(f"staged principals {staged['principals']} are not just {key}")
    if key in stored["principals"]:
        _fail(f"{key} is already in the run")
    for field in ("collection_system_prompts", "domain", "level", "condition"):
        if staged[field] != stored[field]:
            _fail(f"staged {field} differs from the run's")
    templates = {p["instruction_id"] for p in staged["prompt_sets"][key]}
    for other, prompts in stored["prompt_sets"].items():
        if {p["instruction_id"] for p in prompts} != templates:
            _fail(f"{other} and {key} do not share one template set")
    axes = {a["axis_id"] for a in load_json(axes_path)["axes"]}
    seats = sorted(p.name[len("responses_"):-len(".jsonl")]
                   for p in (run / "score").glob("responses_*.jsonl"))
    report = {"seats": {}}
    for seat in seats:
        old_r = list(read_jsonl(run / "score" / f"responses_{seat}.jsonl"))
        old_v = list(read_jsonl(run / "score" / f"verdicts_{seat}.jsonl"))
        new_r = list(read_jsonl(stage / f"responses_{seat}.jsonl"))
        new_v = list(read_jsonl(stage / f"verdicts_{seat}.jsonl"))
        seat_of_run = {(v["judge"], v["level"]) for v in old_v}
        if len(seat_of_run) != 1:
            _fail(f"{seat}: the run holds several (judge, level) pairs {seat_of_run}")
        if {(v["judge"], v["level"]) for v in new_v} != seat_of_run:
            _fail(f"{seat}: staged verdicts are not from {seat_of_run}")
        if {r["principal"] for r in new_r + new_v} != {key}:
            _fail(f"{seat}: staged rows name someone other than {key}")
        bad = [r for r in new_r if r["failed"] or r["refused"] or not r["text"].strip()]
        if bad:
            _fail(f"{seat}: {len(bad)} staged replies are failed, refused or empty")
        cells = {(r["prompt_id"], r["s"]) for r in new_r}
        vcells = {(v["prompt_id"], v["s"]) for v in new_v}
        if len(cells) != len(new_r) or len(vcells) != len(new_v) or cells != vcells:
            _fail(f"{seat}: staged replies and verdicts are not one row per cell")
        old_cells = {(r["prompt_id"], r["s"]) for r in old_r}
        if cells & old_cells:
            _fail(f"{seat}: staged cells collide with the run's")
        if any(set(v["verdicts"]) != axes for v in new_v):
            _fail(f"{seat}: a staged verdict row does not cover exactly the run's axes")
        samples = {r["s"] for r in old_r}
        expect = len(templates) * len(stored["collection_system_prompts"]) * len(samples)
        if len(new_r) != expect:
            _fail(f"{seat}: {len(new_r)} staged replies, expected {expect}")
        report["seats"][seat] = {"old_responses": len(old_r), "old_verdicts": len(old_v),
                                 "new_responses": len(new_r), "new_verdicts": len(new_v),
                                 "new_null_verdicts": sum(1 for v in new_v for x in
                                                          v["verdicts"].values() if x is None)}
    return report


def copy_run(run: Path, stage: Path, superseded: Path, extra: list[Path]) -> int:
    files = [p for p in run.rglob("*") if p.is_file() and stage not in p.parents] + extra
    n = 0
    for src in files:
        dest = superseded / src.relative_to(NSL)
        if dest.exists():
            _fail(f"{dest} already exists")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        if sha(src) != sha(dest):
            _fail(f"copy of {src} does not match")
        n += 1
    return n


def apply(run: Path, stage: Path, key: str, parent_holes: Path | None) -> None:
    for staged in sorted(stage.glob("responses_*.jsonl")) + sorted(stage.glob("verdicts_*.jsonl")):
        target = run / "score" / staged.name
        before = target.read_bytes()
        add = staged.read_bytes()
        if not before.endswith(b"\n") or not add.endswith(b"\n"):
            _fail(f"{target} or {staged} does not end in a newline")
        with target.open("ab") as fh:
            fh.write(add)
        if target.read_bytes() != before + add:
            _fail(f"append to {target} did not land byte for byte")
    stored = load_json(run / "score" / "prompt_sets.json")
    staged = load_json(stage / "prompt_sets.json")
    stored["principals"][key] = staged["principals"][key]
    stored["prompt_sets"][key] = staged["prompt_sets"][key]
    stored["n_prompts"] = (sum(len(v) for v in stored["prompt_sets"].values())
                           * len(stored["collection_system_prompts"]))
    save_json(run / "score" / "prompt_sets.json", stored)
    holes = load_json(run / "HOLES.json")
    holes["holes"] = [h for h in holes["holes"] if h != key]
    save_json(run / "HOLES.json", holes)
    if parent_holes is not None:
        parent = load_json(parent_holes)
        block = parent["holes"][load_json(run / "HOLES.json")["type"]]
        if key not in block["holes"]:
            _fail(f"{key} is not a hole in {parent_holes}")
        block["holes"] = [h for h in block["holes"] if h != key]
        block["collected"] = block["collected"] + [key]
        save_json(parent_holes, parent)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--stage-dir", type=Path, required=True)
    ap.add_argument("--key", required=True)
    ap.add_argument("--axes", type=Path, required=True,
                    help="the run's scoring_questions.json")
    ap.add_argument("--parent-holes", type=Path, default=None)
    ap.add_argument("--superseded", type=Path,
                    default=Path("out/superseded/2026-10-28_hole_fill_before"))
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    report = check(a.run_dir, a.stage_dir, a.key, a.axes)
    print(json.dumps(report, indent=1))
    if not a.apply:
        print("dry run: nothing written")
        return
    extra = [a.parent_holes] if a.parent_holes else []
    n = copy_run(a.run_dir, a.stage_dir, a.superseded, extra)
    print(f"copied {n} files under {a.superseded}, each hash-checked")
    apply(a.run_dir, a.stage_dir, a.key, a.parent_holes)
    print(json.dumps(check_after(a.run_dir, a.key), indent=1))


def check_after(run: Path, key: str) -> dict:
    ps = load_json(run / "score" / "prompt_sets.json")
    out = {"principals": ps["principals"], "n_prompts": ps["n_prompts"],
           "holes": load_json(run / "HOLES.json")["holes"]}
    for p in sorted((run / "score").glob("*.jsonl")):
        out[p.name] = sum(1 for _ in read_jsonl(p))
    return out


if __name__ == "__main__":
    main()
